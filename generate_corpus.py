#!/usr/bin/env python3
"""
自动生成语料脚本
使用DeepSeek API自动生成训练语料
"""

import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Tuple

from client import DeepSeekClient
from client.deepseek_client import (
    DEEPSEEK_API_KEY,
    MODEL_NAME,
    MAX_TOKENS_OUTPUT_REASONER_MAX,
    MAX_TOKENS_OUTPUT_STANDARD,
    MAX_CONTEXT_LENGTH,
    TEMPERATURE,
)
import config
from command_generation import (
    parse_generation_plan,
    extract_domain_code,
    extract_type_code,
    extract_round_num,
    build_generation_instruction,
)
from utils import (
    extract_json_from_text,
    count_data_items,
    save_json_data,
)


def generate_single_task(client: DeepSeekClient, domain_line: str, type_line: str, round_line: str, initial_prompt: str) -> bool:
    """生成单个任务的数据（50条）
    
    每个任务开始时重置会话（只保留system prompt），然后通过多轮对话生成数据。
    如果数据不够，在同一会话中继续对话补齐。
    
    Args:
        client: DeepSeek客户端
        domain_line: 领域行
        type_line: 类型行
        round_line: 轮次行
        initial_prompt: 初始prompt（避免重复读取文件）
    """
    # 提取代码用于构建文件路径
    domain_code = extract_domain_code(domain_line)
    type_code = extract_type_code(type_line)
    round_num = extract_round_num(round_line)
    
    print(f"\n{'='*80}")
    print(f"📝 开始生成: {domain_line} - {type_line} - {round_line}")
    print(f"{'='*80}")
    
    # 每个任务开始时重置会话（只保留system prompt）
    client.reset_session(initial_prompt)
    
    # 构建文件路径
    output_file = config.OUTPUT_BASE_DIR / domain_code / type_code / f"{round_num}_round.json"
    
    # 检查已有数据量
    initial_count = count_data_items(output_file)
    if initial_count >= config.TARGET_ITEMS_PER_TASK:
        print(f"✅ 该任务已完成 ({initial_count}/{config.TARGET_ITEMS_PER_TASK})，跳过")
        return True
    
    # 计算需要生成的数据条数
    needed_count = config.TARGET_ITEMS_PER_TASK - initial_count
    print(f"📊 当前已有 {initial_count} 条数据，需要生成 {needed_count} 条")
    
    # 根据轮次和需要的数据量估算输出token数（保守估算，加buffer）
    estimated_output_tokens = client.estimate_output_tokens(round_num, needed_count)
    print(f"📊 估算输出token数: {estimated_output_tokens} tokens")
    
    # 检查是否超过模型最大限制
    if "reasoner" in MODEL_NAME.lower():
        max_allowed = MAX_TOKENS_OUTPUT_REASONER_MAX
    else:
        max_allowed = MAX_TOKENS_OUTPUT_STANDARD
    
    # 如果预估输出token数超过模型最大限制，调整needed_count
    if estimated_output_tokens > max_allowed:
        print(f"⚠️  预估输出token数({estimated_output_tokens})超过模型最大限制({max_allowed})，调整数据量...")
        # 根据最大限制反推可以生成的数据量
        tokens_per_item = config.TOKENS_PER_ITEM_BY_ROUND.get(round_num, 1000)
        adjusted_count = int(max_allowed / (tokens_per_item * 1.2))
        if adjusted_count < 1:
            adjusted_count = 1
        print(f"📊 调整后的数据量: {adjusted_count} 条（原计划 {needed_count} 条）")
        needed_count = adjusted_count
        # 重新估算输出token数
        estimated_output_tokens = client.estimate_output_tokens(round_num, needed_count)
        print(f"📊 调整后的估算输出token数: {estimated_output_tokens} tokens")
    
    # 构建生成指令（根据调整后的数据量）
    instruction = build_generation_instruction(domain_line, type_line, round_line, count=needed_count)
    
    # 发送生成指令（作为user message）
    print(f"📤 发送生成指令（要求生成{needed_count}条数据，max_tokens={estimated_output_tokens}）...")
    
    # 注意：由于任务开始时已重置会话（只有system prompt），token肯定足够，无需检查
    # 发送生成指令（作为user message），使用估算的output_tokens作为max_tokens
    response = client.send_message(instruction, max_tokens=estimated_output_tokens)
    
    if not response:
        print("❌ 获取响应失败")
        return False
    
    # 提取JSON数据
    print("🔍 提取JSON数据...")
    json_data = extract_json_from_text(response)
    
    if json_data:
        save_json_data(output_file, json_data)
        current_count = count_data_items(output_file)
        print(f"✅ 首次生成: {len(json_data)} 条数据")
    else:
        print("⚠️  未能从响应中提取JSON，尝试保存原始响应...")
        # 保存原始响应以便调试（追加模式，添加时间戳）
        debug_file = output_file.parent / f"{round_num}_round_debug.txt"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"时间戳: {timestamp}\n")
            f.write(f"{'='*80}\n")
            f.write(response)
            f.write(f"\n{'='*80}\n\n")
        print(f"原始响应已追加保存到: {debug_file}")
        # 保持原有的数据量，不要重置为0（因为文件中的数据还在）
        current_count = initial_count
        print(f"⚠️  JSON提取失败，保持当前数据量: {current_count}/{config.TARGET_ITEMS_PER_TASK}")
    
    # 检查数据量，如果不足则继续补齐
    retry_count = 0
    
    while current_count < config.TARGET_ITEMS_PER_TASK and retry_count < config.MAX_RETRIES:
        needed = config.TARGET_ITEMS_PER_TASK - current_count
        print(f"📊 当前数据量: {current_count}/{config.TARGET_ITEMS_PER_TASK}，需要补齐 {needed} 条")
        
        # 根据轮次和需要的数据量估算输出token数（保守估算，加buffer）
        estimated_output_tokens = client.estimate_output_tokens(round_num, needed)
        
        # 检查是否超过模型最大限制
        if "reasoner" in MODEL_NAME.lower():
            max_allowed = MAX_TOKENS_OUTPUT_REASONER_MAX
        else:
            max_allowed = MAX_TOKENS_OUTPUT_STANDARD
        
        # 如果预估输出token数超过模型最大限制，调整needed数量
        if estimated_output_tokens > max_allowed:
            print(f"⚠️  预估输出token数({estimated_output_tokens})超过模型最大限制({max_allowed})，调整数据量...")
            tokens_per_item = config.TOKENS_PER_ITEM_BY_ROUND.get(round_num, 1000)
            adjusted_needed = int(max_allowed / (tokens_per_item * 1.2))
            if adjusted_needed < 1:
                adjusted_needed = 1
            print(f"📊 调整后的补齐数量: {adjusted_needed} 条（原计划 {needed} 条）")
            needed = adjusted_needed
            # 重新估算输出token数
            estimated_output_tokens = client.estimate_output_tokens(round_num, needed)
            print(f"📊 调整后的估算输出token数: {estimated_output_tokens} tokens")
        
        print(f"📊 估算补齐需要约{estimated_output_tokens} tokens")
        
        # 构建补齐消息（作为user message，在同一会话中继续对话）
        supplement_msg = f"现在已经生成了{current_count}条数据，帮我把剩下的{needed}条数据补齐"
        
        # 在发送请求前检查token是否足够，如果不够则开启新会话
        session_reset = client.ensure_session_ready(supplement_msg, estimated_output_tokens)
        
        if session_reset:
            # 如果开启了新会话，需要重新发送完整的生成指令
            # 因为新会话中没有之前的上下文，不能发送"补齐"指令
            print(f"📤 新会话已开启，重新发送生成指令（需要{needed}条数据）...")
            instruction = build_generation_instruction(domain_line, type_line, round_line, count=needed)
            response = client.send_message(instruction, max_tokens=estimated_output_tokens)
        else:
            # Token足够，直接发送补齐请求（在同一会话中继续对话）
            print(f"📤 发送补齐请求（需要{needed}条，max_tokens={estimated_output_tokens}）...")
            response = client.send_message(supplement_msg, max_tokens=estimated_output_tokens)
        
        if not response:
            print("❌ 获取响应失败")
            retry_count += 1
            time.sleep(config.RETRY_DELAY)
            continue
        
        # 提取JSON数据
        json_data = extract_json_from_text(response)
        
        if json_data:
            save_json_data(output_file, json_data)
            current_count = count_data_items(output_file)
            retry_count = 0  # 成功则重置重试计数
        else:
            print("⚠️  未能从响应中提取JSON")
            retry_count += 1
            time.sleep(config.RETRY_DELAY)
    
    if current_count >= config.TARGET_ITEMS_PER_TASK:
        print(f"✅ 任务完成！最终数据量: {current_count}/{config.TARGET_ITEMS_PER_TASK}")
    else:
        print(f"⚠️  任务未完全完成，当前数据量: {current_count}/{config.TARGET_ITEMS_PER_TASK}")
        # 记录未完成的任务到文件（追加模式，添加时间戳）
        incomplete_file = config.OUTPUT_BASE_DIR / "incomplete_tasks.txt"
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        task_info = f"[{timestamp}] {domain_code} | {type_code} | {round_num}_round | {current_count}/{config.TARGET_ITEMS_PER_TASK}\n"
        try:
            with open(incomplete_file, 'a', encoding='utf-8') as f:
                f.write(task_info)
            print(f"📝 未完成任务已追加记录到: {incomplete_file}")
        except Exception as e:
            print(f"⚠️  记录未完成任务失败: {e}")
    
    # 任务完成后重置会话，准备下一个任务（复用已读取的initial_prompt）
    client.reset_session(initial_prompt)
    
    # 短暂休息，避免API限流（只有在成功处理后才休息）
    if current_count > 0:  # 如果有生成数据，说明进行了API请求
        print(f"⏳ 等待{config.SUCCESS_DELAY}秒，避免API限流...")
        time.sleep(config.SUCCESS_DELAY)
    
    return current_count >= config.TARGET_ITEMS_PER_TASK


def generate_task_wrapper(args: Tuple[str, str, str, str, int, int]) -> Tuple[int, bool, str]:
    """任务包装函数，用于并发执行
    
    每个worker线程都会创建独立的client实例，确保线程安全。
    
    Args:
        args: (domain_line, type_line, round_line, initial_prompt, task_index, total_tasks)
    
    Returns:
        (task_index, success, error_message)
    """
    domain_line, type_line, round_line, initial_prompt, task_index, total_tasks = args
    
    # 每个worker使用独立的client实例
    client = DeepSeekClient(DEEPSEEK_API_KEY, model=MODEL_NAME)
    
    try:
        success = generate_single_task(
            client, domain_line, type_line, round_line, initial_prompt
        )
        return (task_index, success, "")
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        return (task_index, False, error_msg)


def main():
    """主函数"""
    # 检查API密钥
    if not DEEPSEEK_API_KEY:
        print("❌ 错误: 未设置DEEPSEEK_API_KEY环境变量")
        print("请设置环境变量:")
        print("  Linux/Mac: export DEEPSEEK_API_KEY='your-api-key'")
        print("  Windows:   set DEEPSEEK_API_KEY=your-api-key")
        print("\n或者创建 .env 文件（需要安装 python-dotenv）")
        return
    
    # 检查文件是否存在
    if not config.INITIAL_PROMPT_FILE.exists():
        print(f"❌ 错误: 找不到文件 {config.INITIAL_PROMPT_FILE}")
        return
    
    # 解析生成计划
    print("📖 解析生成计划...")
    try:
        domains, types, rounds = parse_generation_plan()
        print(f"✅ 解析完成:")
        print(f"   - 领域: {len(domains)}个")
        print(f"   - 模糊类型: {len(types)}种")
        print(f"   - 对话轮次: {len(rounds)}种")
        print(f"   - 总任务数: {len(domains)*len(types)*len(rounds)}个")
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 读取initial_prompt一次，避免重复读取文件
    initial_prompt = config.INITIAL_PROMPT_FILE.read_text(encoding='utf-8')
    
    # 确保未完成任务记录文件存在（不清空，保留历史记录）
    incomplete_file = config.OUTPUT_BASE_DIR / "incomplete_tasks.txt"
    try:
        incomplete_file.parent.mkdir(parents=True, exist_ok=True)
        if not incomplete_file.exists():
            incomplete_file.touch()
            print(f"📝 创建未完成任务记录文件: {incomplete_file}")
    except Exception as e:
        print(f"⚠️  初始化未完成任务记录文件失败: {e}")
    
    # 构建所有任务列表
    tasks = []
    task_index = 0
    for domain_line in domains:
        for type_line in types:
            for round_line in rounds:
                task_index += 1
                tasks.append((domain_line, type_line, round_line, task_index))
    
    total_tasks = len(tasks)
    print(f"\n🤖 使用模型: {MODEL_NAME}")
    print(f"📊 配置信息:")
    if "reasoner" in MODEL_NAME.lower():
        print(f"   - 最大输出tokens: {MAX_TOKENS_OUTPUT_REASONER_MAX} (reasoner模型)")
    else:
        print(f"   - 最大输出tokens: {MAX_TOKENS_OUTPUT_STANDARD} (标准模型)")
    print(f"   - 最大上下文长度: {MAX_CONTEXT_LENGTH}")
    print(f"   - Temperature: {TEMPERATURE}")
    print(f"   - max_tokens将根据预估输出长度动态设置")
    print(f"   - 并发模式: {'启用' if config.ENABLE_CONCURRENCY else '禁用'}")
    if config.ENABLE_CONCURRENCY:
        print(f"   - 并发worker数量: {config.CONCURRENT_WORKERS}")
    
    # 根据并发配置选择执行方式
    if config.ENABLE_CONCURRENCY and config.CONCURRENT_WORKERS > 1:
        # 并发执行
        print(f"\n🚀 使用并发模式执行，worker数量: {config.CONCURRENT_WORKERS}")
        print(f"📋 任务列表已构建，共 {total_tasks} 个任务，将并发执行")
        
        # 准备任务参数（每个任务只添加一次，确保无重复）
        task_args = []
        for domain_line, type_line, round_line, task_idx in tasks:
            task_args.append((
                domain_line, type_line, round_line, initial_prompt,
                task_idx, total_tasks
            ))
        
        # 使用线程池执行
        completed_count = 0
        success_count = 0
        failed_count = 0
        progress_lock = Lock()
        
        try:
            with ThreadPoolExecutor(max_workers=config.CONCURRENT_WORKERS) as executor:
                # 提交所有任务（每个任务只提交一次，确保无重复）
                future_to_task = {
                    executor.submit(generate_task_wrapper, args): args[4] 
                    for args in task_args
                }
                
                print(f"✅ 已提交 {len(future_to_task)} 个任务到线程池\n")
                
                # 处理完成的任务
                for future in as_completed(future_to_task):
                    task_idx = future_to_task[future]
                    try:
                        task_idx_result, success, error_msg = future.result()
                        with progress_lock:
                            completed_count += 1
                            if success:
                                success_count += 1
                                print(f"✅ 任务 {task_idx_result}/{total_tasks} 完成 (进度: {completed_count}/{total_tasks}, 成功: {success_count}, 失败: {failed_count})")
                            else:
                                failed_count += 1
                                print(f"⚠️  任务 {task_idx_result}/{total_tasks} 未完全完成 (进度: {completed_count}/{total_tasks}, 成功: {success_count}, 失败: {failed_count})")
                                if error_msg:
                                    # 只显示第一行错误，避免输出过长
                                    first_line = error_msg.split('\n')[0] if error_msg else ""
                                    if first_line:
                                        print(f"   错误: {first_line}")
                    except Exception as e:
                        with progress_lock:
                            completed_count += 1
                            failed_count += 1
                            print(f"❌ 任务 {task_idx}/{total_tasks} 执行异常: {e}")
                            import traceback
                            traceback.print_exc()
        except KeyboardInterrupt:
            print(f"\n⚠️  用户中断，已处理 {completed_count}/{total_tasks} 个任务")
            raise
        
        current_task = completed_count
    else:
        # 串行执行（原有逻辑）
        print(f"\n🔄 使用串行模式执行")
        
        # 初始化DeepSeek客户端（串行模式下共享一个client）
        client = DeepSeekClient(DEEPSEEK_API_KEY, model=MODEL_NAME)
        current_task = 0
        success_count = 0
        failed_count = 0
        
        for domain_line, type_line, round_line, task_idx in tasks:
            current_task += 1
            print(f"\n📊 进度: {current_task}/{total_tasks}")
            
            # 生成单个任务
            try:
                success = generate_single_task(
                    client, domain_line, type_line, round_line, initial_prompt
                )
                
                if success:
                    success_count += 1
                    print(f"✅ 任务 {current_task}/{total_tasks} 完成")
                else:
                    failed_count += 1
                    print(f"⚠️  任务 {current_task}/{total_tasks} 未完全完成")
            except KeyboardInterrupt:
                print(f"\n⚠️  用户中断，已处理 {current_task-1}/{total_tasks} 个任务")
                raise
            except Exception as e:
                failed_count += 1
                print(f"❌ 任务 {current_task}/{total_tasks} 出错: {e}")
                import traceback
                traceback.print_exc()
                # 继续处理下一个任务
    
    print(f"\n🎉 所有任务处理完成！")
    print(f"\n📊 统计信息:")
    print(f"   - 总任务数: {total_tasks}")
    print(f"   - 已完成: {current_task}")
    print(f"   - 成功: {success_count}")
    print(f"   - 失败/未完成: {failed_count}")
    print(f"   - 数据保存位置: {config.OUTPUT_BASE_DIR}")
    print(f"   - 输出目录: data/cautious_secretary_raw/")


if __name__ == "__main__":
    main()
