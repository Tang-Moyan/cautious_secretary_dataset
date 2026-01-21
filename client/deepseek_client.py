#!/usr/bin/env python3
"""
DeepSeek API客户端
"""

import os
import json
import re
import time
from typing import List, Dict, Optional
import requests

import sys
from pathlib import Path

# 添加父目录到路径，以便导入模块
sys.path.insert(0, str(Path(__file__).parent.parent))

import config

# DeepSeek API配置
DEEPSEEK_API_BASE = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Token和上下文配置
# DeepSeek API支持最大128K tokens上下文，但为了稳定性和成本控制，建议设置如下：
# 注意：不同轮次的数据量差异很大
# - 1轮对话：每条数据约400-600 tokens，50条约20000-30000 tokens
# - 5轮对话：每条数据约800-1200 tokens，50条约40000-60000 tokens
# DeepSeek API的max_tokens限制：
# - 标准模型：8000
# - reasoner模型：默认32K，最大64K

# 基础配置
MAX_TOKENS_OUTPUT_REASONER_MAX = 64000  # reasoner模型最大输出token数
MAX_TOKENS_OUTPUT_STANDARD = 8000  # 标准模型的最大输出token数
MAX_CONTEXT_LENGTH = 110000  # 会话总长度限制（留出约18K buffer，避免意外超限）

# Reasoner模型推理token配置
REASONING_TOKENS_BUFFER = 5000  # reasoner模型推理过程需要的额外token数（固定常数）
# 说明：基于实际场景分析，推理token通常占内容token的20-30%
# 对于50条数据（5轮），推理token约需8000+，但考虑到：
# 1. 大多数任务规模较小（1-10条），5000足够
# 2. 大规模任务可通过代码的自动重试机制处理
# 3. 5000 tokens约为50条5轮数据内容token的10-15%，提供合理的安全边际

# 模型选择：deepseek-chat（标准）或 deepseek-reasoner（推理模式，质量更高但稍慢）
# 默认使用 deepseek-reasoner 以保证生成质量
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")  # 可通过环境变量覆盖

# 生成参数（与网页版保持一致）
TEMPERATURE = 0.7  # 控制随机性，0.7是网页版常用值


class DeepSeekClient:
    """DeepSeek API客户端
    
    优化策略：
    1. 使用system message存储固定的initial prompt，利用Context Caching机制
    2. 只保留必要的对话历史，避免上下文过长
    3. 智能管理会话长度，在接近限制时开启新会话
    """
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model or MODEL_NAME
        self.session_messages: List[Dict] = []
        self.system_prompt: Optional[str] = None  # 固定的system prompt，用于缓存
        self.current_tokens = 0
        self.initial_prompt_tokens = 0  # initial prompt的token数，用于估算
        
    def _estimate_tokens(self, text: str) -> int:
        """粗略估算token数量（中文约1.5字符/token，英文约4字符/token）"""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
    
    def _check_if_need_new_session(self, message: str, estimated_output_tokens: int) -> bool:
        """检查发送指定消息是否需要开启新会话
        
        Args:
            message: 要发送的消息
            estimated_output_tokens: 预估的输出token数
            
        Returns:
            True表示需要开启新会话，False表示不需要
        """
        # 估算消息的token数
        message_tokens = self._estimate_tokens(message)
        
        # 计算发送后预期的总token数
        expected_total = self.current_tokens + message_tokens + estimated_output_tokens
        
        # 如果超过限制，需要开启新会话
        return expected_total >= MAX_CONTEXT_LENGTH
    
    def estimate_output_tokens(self, round_num: int, needed_count: int) -> int:
        """根据轮次和需要的数据量，估算输出token数（保守估算，加buffer）
        
        使用反比例关系来增加buffer量：
        - 数据越少，buffer比例越高（最高50%）
        - 数据越多，buffer比例越低（最低30%）
        - 50条时达到最低比例（30%）
        - 超出50条都按30%计算
        
        对于reasoner模型，额外增加固定的推理token常数。
        
        Args:
            round_num: 对话轮次（1-5）
            needed_count: 需要生成的数据条数
            
        Returns:
            预估的输出token数（保守估算，已加buffer）
        """
        # 估算每条数据的token数
        tokens_per_item = config.TOKENS_PER_ITEM_BY_ROUND.get(round_num, 1000)
        
        # 计算buffer比例（反比例关系）
        # 当needed_count = 1时，buffer = 50% (最高，即1.5倍)
        # 当needed_count = 50时，buffer = 30% (最低，即1.3倍)
        # 当needed_count > 50时，buffer = 30%
        if needed_count >= 50:
            buffer_ratio = 1.3  # 30% buffer (1 + 0.3 = 1.3)
        else:
            buffer_ratio = 1.5 - 0.2 * (needed_count / 50)
        
        # 计算基础token数（内容token）
        base_tokens = int(tokens_per_item * needed_count * buffer_ratio)
        
        # 对于reasoner模型，额外增加固定的推理token常数
        if "reasoner" in self.model.lower():
            estimated_tokens = base_tokens + REASONING_TOKENS_BUFFER
        else:
            estimated_tokens = base_tokens
        
        return estimated_tokens
    
    def start_new_session(self, initial_prompt: str) -> None:
        """开启新会话，直接将initial_prompt设置为system message
        
        根据DeepSeek API的多轮对话规范，直接将system prompt放入messages中。
        后续的user message和assistant response会追加到messages数组中。
        """
        self.session_messages = [{
            "role": "system",
            "content": initial_prompt
        }]
        self.system_prompt = initial_prompt
        self.initial_prompt_tokens = self._estimate_tokens(initial_prompt)
        self.current_tokens = self.initial_prompt_tokens
        print(f"✅ 新会话已开启 (system prompt: {self.initial_prompt_tokens} tokens)")
    
    def send_message(self, message: str, max_tokens: int) -> Optional[str]:
        """发送消息并获取回复（多轮对话）
        
        根据DeepSeek API规范，将user message添加到messages数组，发送请求后，
        将assistant response也添加到messages数组，形成完整的对话历史。
        
        Args:
            message: 要发送的消息
            max_tokens: 最大输出token数（必须指定，根据预估输出长度设置）
            
        注意：调用此方法前应该先检查token是否足够，如果不够应该先开启新会话
        """
        # 添加用户消息到messages数组
        self.session_messages.append({
            "role": "user",
            "content": message
        })
        
        message_tokens = self._estimate_tokens(message)
        self.current_tokens += message_tokens
        
        # 发送请求
        response = self._send_request(max_tokens=max_tokens)
        if response:
            # 将assistant的回复也添加到messages数组，形成完整的对话历史
            self.session_messages.append({
                "role": "assistant",
                "content": response
            })
            
            response_tokens = self._estimate_tokens(response)
            self.current_tokens += response_tokens
            return response
        return None
    
    def reset_session(self, initial_prompt: str) -> None:
        """重置会话，准备新的任务
        
        每个任务完成后，重置会话，只保留system prompt，准备下一个任务。
        """
        self.start_new_session(initial_prompt)
    
    def ensure_session_ready(self, message: str, estimated_output_tokens: int) -> bool:
        """确保会话有足够的token发送消息，如果不够则开启新会话
        
        Args:
            message: 要发送的消息
            estimated_output_tokens: 预估的输出token数
            
        Returns:
            True表示开启了新会话，False表示没有开启（token足够）
        """
        if self._check_if_need_new_session(message, estimated_output_tokens):
            print(f"⚠️  检测到token不足 ({self.current_tokens} tokens)，开启新会话...")
            # 使用传入的initial_prompt（避免重复读取文件）
            # 如果self.system_prompt存在，说明之前已经读取过，可以直接使用
            if self.system_prompt:
                initial_prompt = self.system_prompt
            else:
                initial_prompt = config.INITIAL_PROMPT_FILE.read_text(encoding='utf-8')
            self.start_new_session(initial_prompt)
            time.sleep(2)
            return True  # 返回True表示开启了新会话
        return False  # 返回False表示没有开启新会话（token足够）
    
    def _send_request(self, max_tokens: int, use_json_mode: bool = True) -> Optional[str]:
        """发送API请求
        
        Args:
            max_tokens: 最大输出token数（必须指定，根据预估输出长度设置）
            use_json_mode: 是否使用JSON模式（强制输出JSON格式），默认True
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 直接使用传入的max_tokens（已经在调用前根据预估输出长度设置好）
        max_output = max_tokens
        
        # 估算当前请求的输入token数（用于错误信息显示）
        estimated_input_tokens = self.current_tokens
        
        # 构建请求数据，符合DeepSeek API规范
        data = {
            "model": self.model,
            "messages": self.session_messages,
            "temperature": TEMPERATURE,
            "max_tokens": max_output,
            "stream": False,  # 不使用流式输出
        }
        
        # 如果使用reasoner模型，启用思考模式以保证生成质量
        # 思考模式会让模型进行推理思考，生成质量更高，但速度稍慢
        if "reasoner" in self.model.lower():
            data["thinking"] = {
                "type": "enabled"  # 启用思考模式，保证生成质量
            }
        
        # 使用JSON模式可以确保输出是有效的JSON格式
        # 注意：使用JSON模式时，prompt中必须明确要求生成JSON
        if use_json_mode:
            data["response_format"] = {
                "type": "json_object"
            }
        
        try:
            # 发送请求，增加连接和读取超时设置
            # timeout参数说明：
            # - 第一个值(30): 连接超时，表示建立TCP连接的最大等待时间
            #   如果30秒内无法连接到服务器，会抛出Timeout异常
            # - 第二个值(1800): 读取超时，表示从服务器接收数据的最大等待时间
            #   如果30分钟内没有收到任何数据，会抛出Timeout异常
            #   对于大数据量生成，需要足够长的读取超时时间
            response = requests.post(
                DEEPSEEK_API_BASE, 
                headers=headers, 
                json=data, 
                timeout=(30, 1800),  # (连接超时30秒, 读取超时1800秒=30分钟)
                stream=False  # 不使用流式，确保完整接收响应
            )
            response.raise_for_status()
            
            # 检查响应内容是否完整
            if not response.content:
                print(f"⚠️  警告: API返回空响应")
                return None
            
            # 尝试解析JSON
            try:
                result = response.json()
            except json.JSONDecodeError as json_err:
                print(f"⚠️  警告: JSON解析失败，响应可能不完整")
                print(f"响应状态码: {response.status_code}")
                print(f"响应内容长度: {len(response.content)} bytes")
                print(f"请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
                
                # 尝试从响应中提取usage信息（即使JSON解析失败，usage可能在响应中）
                try:
                    # 尝试用正则表达式提取usage信息
                    usage_match = re.search(r'"usage"\s*:\s*\{[^}]+\}', response.text)
                    if usage_match:
                        usage_str = usage_match.group(0)
                        print(f"   检测到usage信息: {usage_str}")
                except:
                    pass
                
                print(f"响应内容前500字符: {response.text[:500]}")
                print(f"JSON解析错误: {json_err}")
                return None
            
            # 检查是否有Context Caching命中（用于监控和优化）
            if "usage" in result:
                usage = result["usage"]
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                cache_hit = usage.get("prompt_cache_hit_tokens", 0)
                cache_miss = usage.get("prompt_cache_miss_tokens", 0)
                
                # 获取推理token数（reasoner模型）
                reasoning_tokens = 0
                if "completion_tokens_details" in usage:
                    completion_details = usage["completion_tokens_details"]
                    reasoning_tokens = completion_details.get("reasoning_tokens", 0)
                
                if cache_hit > 0:
                    total_prompt = cache_hit + cache_miss
                    hit_rate = cache_hit / total_prompt if total_prompt > 0 else 0
                    if hit_rate > 0.5:  # 缓存命中率超过50%时显示
                        print(f"💾 Context Cache命中: {cache_hit}/{total_prompt} tokens ({hit_rate*100:.1f}%)")
                
                # 显示详细的token使用情况
                if total_tokens > 0:
                    token_info = f"📊 Token使用: 输入={prompt_tokens}"
                    if cache_hit > 0:
                        token_info += f" (缓存命中={cache_hit}, 未命中={cache_miss})"
                    token_info += f", 输出={completion_tokens}"
                    if reasoning_tokens > 0:
                        token_info += f" (推理={reasoning_tokens}, 内容={completion_tokens - reasoning_tokens})"
                    token_info += f", 总计={total_tokens}, max_tokens={max_output}"
                    print(token_info)
            
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                content = choice["message"]["content"]
                
                # 检查finish_reason和token使用情况
                finish_reason = choice.get("finish_reason", "unknown")
                reasoning_tokens = 0
                content_tokens = 0
                if "usage" in result:
                    usage = result["usage"]
                    completion_tokens = usage.get("completion_tokens", 0)
                    if "completion_tokens_details" in usage:
                        completion_details = usage["completion_tokens_details"]
                        reasoning_tokens = completion_details.get("reasoning_tokens", 0)
                        content_tokens = completion_tokens - reasoning_tokens
                
                if finish_reason == "length":
                    # 检查是否是reasoner模型且只有推理token没有内容token
                    if "reasoner" in self.model.lower() and reasoning_tokens > 0 and content_tokens == 0:
                        print(f"⚠️  警告: 输出被截断，推理token用完了所有max_tokens（推理={reasoning_tokens}），没有剩余token生成内容")
                        print(f"   建议: 需要增加max_tokens以容纳推理过程和内容生成")
                        # 返回None，让调用方知道需要重试
                        return None
                    else:
                        print(f"⚠️  警告: 输出被截断（达到max_tokens限制），可能需要增加max_tokens或分批生成")
                elif finish_reason == "stop":
                    pass  # 正常完成
                else:
                    print(f"ℹ️  完成原因: {finish_reason}")
                
                # 检查content是否为空（reasoner模型推理用尽token时可能返回None或空字符串）
                if content is None or (isinstance(content, str) and len(content.strip()) == 0):
                    print(f"⚠️  警告: 响应内容为空，可能是推理token用尽了所有max_tokens")
                    if reasoning_tokens > 0:
                        print(f"   推理token: {reasoning_tokens}, 内容token: {content_tokens}")
                        print(f"   当前max_tokens={max_output}，建议至少增加到{int(max_output * 1.5)}以容纳推理和内容")
                    return None
                
                # 如果使用JSON模式，content字段直接就是JSON字符串，不需要额外提取
                # 但为了兼容性，仍然返回原始content，让extract_json_from_text处理
                return content
            else:
                print(f"❌ API返回格式异常: {result}")
                # 即使choices为空，也尝试显示usage信息
                if "usage" in result:
                    usage = result["usage"]
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                    print(f"   响应token信息: 输入={prompt_tokens}, 输出={completion_tokens}, 总计={total_tokens}")
                return None
                
        except requests.exceptions.Timeout as e:
            print(f"❌ API请求超时: {e}")
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            print(f"   提示: 可能是网络连接慢或服务器响应时间长，建议检查网络或增加超时时间")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"❌ API连接错误: {e}")
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            print(f"   提示: 网络连接失败，可能是网络不稳定或服务器不可达")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"❌ API请求HTTP错误: {e}")
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   错误详情: {error_detail}")
                    # 尝试从错误响应中提取token信息
                    if isinstance(error_detail, dict):
                        if "usage" in error_detail:
                            usage = error_detail["usage"]
                            prompt_tokens = usage.get("prompt_tokens", 0)
                            completion_tokens = usage.get("completion_tokens", 0)
                            total_tokens = usage.get("total_tokens", 0)
                            cache_hit = usage.get("prompt_cache_hit_tokens", 0)
                            cache_miss = usage.get("prompt_cache_miss_tokens", 0)
                            reasoning_tokens = 0
                            if "completion_tokens_details" in usage:
                                completion_details = usage["completion_tokens_details"]
                                reasoning_tokens = completion_details.get("reasoning_tokens", 0)
                            
                            token_info = f"   响应token信息: 输入={prompt_tokens}"
                            if cache_hit > 0:
                                token_info += f" (缓存命中={cache_hit}, 未命中={cache_miss})"
                            token_info += f", 输出={completion_tokens}"
                            if reasoning_tokens > 0:
                                token_info += f" (推理={reasoning_tokens}, 内容={completion_tokens - reasoning_tokens})"
                            token_info += f", 总计={total_tokens}"
                            print(token_info)
                except:
                    print(f"   响应状态码: {e.response.status_code}")
                    # 尝试从响应文本中提取usage信息
                    try:
                        usage_match = re.search(r'"usage"\s*:\s*\{[^}]+\}', e.response.text)
                        if usage_match:
                            print(f"   检测到usage信息: {usage_match.group(0)}")
                    except:
                        pass
                    print(f"   响应内容: {e.response.text[:500]}")
            return None
        except requests.exceptions.ChunkedEncodingError as e:
            print(f"❌ API响应接收错误（响应不完整）: {e}")
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            # 尝试从部分响应中提取usage信息
            try:
                if hasattr(e, 'response') and e.response is not None:
                    usage_match = re.search(r'"usage"\s*:\s*\{[^}]+\}', e.response.text)
                    if usage_match:
                        print(f"   检测到usage信息: {usage_match.group(0)}")
            except:
                pass
            print(f"   提示: 服务器在传输过程中关闭了连接，可能是网络不稳定或服务器问题")
            print(f"   建议: 稍后重试，或检查网络连接")
            return None
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            if "prematurely" in error_msg.lower() or "incomplete" in error_msg.lower():
                print(f"❌ API响应不完整: {e}")
                print(f"   提示: 响应在完全接收前结束，可能是网络中断或服务器提前关闭连接")
                print(f"   建议: 检查网络连接，稍后重试")
            else:
                print(f"❌ API请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ API响应JSON解析失败: {e}")
            print(f"   请求token信息: 输入≈{estimated_input_tokens}, max_tokens={max_output}")
            print(f"   提示: 响应可能不完整或格式错误")
            return None
