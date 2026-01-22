#!/usr/bin/env python3
"""
工具函数
包含JSON提取、数据统计和保存等功能
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional


def extract_json_from_text(text: str) -> Optional[List[Dict]]:
    """从文本中提取JSON数组
    
    当使用 response_format: {"type": "json_object"} 时，
    DeepSeek API 返回的 content 字段直接就是 JSON 字符串（可能是对象或数组）。
    如果 content 本身就是有效的 JSON，直接解析即可。
    
    如果达到max_tokens限制导致响应被截断，会尝试提取已生成的完整数据，
    即使最后一条数据不完整也会返回已解析的完整数据。
    """
    # 方法0: 如果整个文本就是有效的JSON（使用json_object模式时的情况）
    text_stripped = text.strip()
    if text_stripped.startswith('[') or text_stripped.startswith('{'):
        try:
            data = json.loads(text_stripped)
            # 如果是数组，直接返回
            if isinstance(data, list) and len(data) > 0:
                return data
            # 如果是对象，检查是否包含数组字段（常见格式：{"data": [...]}）
            if isinstance(data, dict):
                # 查找包含数组的字段
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        return value
                # 如果没有找到数组字段，但对象本身可能就是我们需要的（单个对象包装成数组）
                # 这种情况通常不会发生，但为了兼容性保留
        except json.JSONDecodeError:
            # JSON解析失败，可能是被截断了，尝试提取部分数据
            if text_stripped.startswith('['):
                # 尝试从截断的数组中提取完整的对象
                return _extract_partial_json_array(text_stripped)
            pass  # 继续尝试其他方法
    
    # 方法1: 尝试从代码块中提取（兼容非JSON模式或模型在代码块中输出JSON的情况）
    code_block_patterns = [
        r'```json\s*(\[[\s\S]*?\])\s*```',
        r'```json\s*(\{[\s\S]*?\})\s*```',
        r'```\s*(\[[\s\S]*?\])\s*```',
        r'```\s*(\{[\s\S]*?\})\s*```',
    ]
    
    for pattern in code_block_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                if isinstance(data, list) and len(data) > 0:
                    return data
                # 如果是对象，查找数组字段
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            return value
            except json.JSONDecodeError:
                continue
    
    # 方法2: 查找最外层的JSON数组
    # 使用括号匹配来找到完整的数组
    bracket_count = 0
    start_idx = -1
    
    for i, char in enumerate(text):
        if char == '[':
            if bracket_count == 0:
                start_idx = i
            bracket_count += 1
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0 and start_idx != -1:
                json_str = text[start_idx:i+1]
                try:
                    data = json.loads(json_str)
                    if isinstance(data, list) and len(data) > 0:
                        return data
                except json.JSONDecodeError:
                    # 尝试修复常见问题
                    try:
                        # 移除末尾的逗号
                        json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                        # 移除注释行
                        lines = []
                        in_string = False
                        escape_next = False
                        for line in json_str.split('\n'):
                            cleaned_line = []
                            for char in line:
                                if escape_next:
                                    cleaned_line.append(char)
                                    escape_next = False
                                    continue
                                if char == '\\':
                                    escape_next = True
                                    cleaned_line.append(char)
                                elif char == '"' and not escape_next:
                                    in_string = not in_string
                                    cleaned_line.append(char)
                                elif char == '/' and not in_string and len(cleaned_line) > 0 and cleaned_line[-1] == '/':
                                    # 遇到 // 注释，移除这部分
                                    cleaned_line.pop()
                                    break
                                else:
                                    cleaned_line.append(char)
                            lines.append(''.join(cleaned_line))
                        json_str = '\n'.join(lines)
                        data = json.loads(json_str)
                        if isinstance(data, list) and len(data) > 0:
                            return data
                    except Exception:
                        # 修复失败，可能是截断了，尝试提取部分数据
                        if start_idx != -1:
                            partial_result = _extract_partial_json_array(text[start_idx:])
                            if partial_result:
                                return partial_result
                        pass
                start_idx = -1
    
    # 如果所有方法都失败，尝试从第一个[开始提取部分数据（处理截断情况）
    first_bracket = text.find('[')
    if first_bracket != -1:
        partial_result = _extract_partial_json_array(text[first_bracket:])
        if partial_result:
            return partial_result
    
    # 方法3: 尝试提取所有JSON对象并组合成数组
    try:
        # 查找所有独立的JSON对象
        object_pattern = r'\{\s*"[^"]*"\s*:[\s\S]*?\}'
        matches = re.finditer(object_pattern, text, re.DOTALL)
        objects = []
        for match in matches:
            try:
                obj = json.loads(match.group(0))
                if isinstance(obj, dict) and 'system' in obj:
                    objects.append(obj)
            except:
                continue
        
        if len(objects) > 0:
            return objects
    except:
        pass
    
    return None


def _extract_partial_json_array(text: str) -> Optional[List[Dict]]:
    """从可能被截断的JSON数组中提取完整的对象
    
    当达到max_tokens限制时，响应可能被截断，导致JSON不完整。
    此函数尝试提取所有完整的JSON对象，即使最后一条不完整也会返回已解析的数据。
    
    Args:
        text: 可能被截断的JSON数组文本（应该以[开头）
        
    Returns:
        提取到的完整JSON对象列表，如果没有找到则返回None
    """
    if not text.strip().startswith('['):
        return None
    
    # 找到第一个[的位置
    start_idx = text.find('[')
    if start_idx == -1:
        return None
    
    # 从第一个[开始，尝试提取完整的JSON对象
    # 策略：找到每个完整的{...}对象，即使数组没有闭合
    objects = []
    brace_count = 0
    obj_start = -1
    in_string = False
    escape_next = False
    
    i = start_idx + 1  # 跳过第一个[
    while i < len(text):
        char = text[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
        
        if char == '\\':
            escape_next = True
            i += 1
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            i += 1
            continue
        
        if in_string:
            i += 1
            continue
        
        if char == '{':
            if brace_count == 0:
                obj_start = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and obj_start != -1:
                # 找到一个完整的对象
                obj_str = text[obj_start:i+1]
                try:
                    obj = json.loads(obj_str)
                    if isinstance(obj, dict) and 'system' in obj:
                        objects.append(obj)
                except json.JSONDecodeError:
                    # 对象解析失败，跳过
                    pass
                obj_start = -1
        
        i += 1
    
    if len(objects) > 0:
        print(f"⚠️  检测到JSON可能被截断，已提取 {len(objects)} 条完整数据")
        return objects
    
    return None


def count_data_items(file_path: Path) -> int:
    """统计JSON文件中的数据条数（通过system字段数量）"""
    if not file_path.exists():
        return 0
    
    try:
        content = file_path.read_text(encoding='utf-8')
        # 统计 "system" 字段出现的次数
        count = len(re.findall(r'"system"\s*:', content))
        return count
    except Exception as e:
        print(f"⚠️  读取文件失败 {file_path}: {e}")
        return 0


def save_json_data(file_path: Path, new_data: List[Dict]):
    """保存JSON数据到文件（追加或创建）"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    existing_data = []
    if file_path.exists():
        try:
            content = file_path.read_text(encoding='utf-8')
            existing_data = json.loads(content)
            if not isinstance(existing_data, list):
                existing_data = []
        except:
            existing_data = []
    
    # 合并数据
    all_data = existing_data + new_data
    
    # 保存
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已保存 {len(new_data)} 条新数据到 {file_path} (总计: {len(all_data)} 条)")
