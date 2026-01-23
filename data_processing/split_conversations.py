#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对话拆分脚本
将多轮对话数据拆分成多个"单轮回复"训练样本，输出为Alpaca格式

使用方法：
1. 先运行 consolidate_data.py 生成 consolidated_data.json
2. 然后运行此脚本：python split_conversations.py
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

# 脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_FILE = PROJECT_ROOT / "output_dataset" / "consolidated_data.json"
DEFAULT_OUTPUT_FILE = PROJECT_ROOT / "output_dataset" / "alpaca_format_data.json"


def split_conversation(original_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    将一条多轮对话拆分成多个单轮回复训练样本
    
    Args:
        original_data: 原始对话数据，包含 system 和 conversations 字段
        
    Returns:
        训练样本列表，每个样本为Alpaca格式
    """
    training_samples = []
    history = []  # 存储历史对话对 [["user1", "gpt1"], ["user2", "gpt2"], ...]
    system = original_data.get("system", "")
    conversations = original_data.get("conversations", [])
    
    current_user_input = None  # 当前轮次的用户输入
    
    for i, conv in enumerate(conversations):
        if conv.get("from") == "human":
            # 记录用户输入
            current_user_input = conv.get("value", "")
            
        elif conv.get("from") == "gpt":
            # 当遇到gpt回复时，创建一条训练样本
            gpt_response = conv.get("value", "")
            
            # 构建训练样本
            sample = {
                "instruction": current_user_input if current_user_input else "",
                "input": "",  # 可以为空，或者根据需要填充
                "output": gpt_response,
                "system": system if system else None,
            }
            
            # 添加历史对话（不包括当前轮次）
            if history:
                sample["history"] = history.copy()
            else:
                sample["history"] = []
            
            # 如果system为空，可以删除该字段（可选）
            if not sample["system"]:
                sample.pop("system", None)
            
            training_samples.append(sample)
            
            # 将当前轮次的对话对加入历史（用于下一轮）
            if current_user_input:
                history.append([current_user_input, gpt_response])
                current_user_input = None
    
    return training_samples


def process_data(
    input_file: str,
    output_file: str,
    max_samples: Optional[int] = None
) -> None:
    """
    处理数据文件，将多轮对话拆分成训练样本
    
    Args:
        input_file: 输入JSON文件路径
        output_file: 输出JSON文件路径
        max_samples: 最大处理样本数（用于测试），None表示处理全部
    """
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}")
        return
    
    print(f"正在读取输入文件: {input_path}")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            original_data_list = json.load(f)
    except Exception as e:
        print(f"错误: 读取文件失败: {str(e)}")
        return
    
    if not isinstance(original_data_list, list):
        print("错误: 输入文件格式不正确，应为JSON数组")
        return
    
    print(f"找到 {len(original_data_list)} 条原始对话数据")
    
    # 限制处理数量（用于测试）
    if max_samples is not None and max_samples > 0:
        original_data_list = original_data_list[:max_samples]
        print(f"限制处理数量为: {max_samples}")
    
    # 处理每条数据
    all_training_samples = []
    stats = {
        "total_original": len(original_data_list),
        "total_training_samples": 0,
        "conversations_by_rounds": {}  # 统计不同轮次的数量
    }
    
    print(f"\n正在处理数据...")
    for idx, original_data in enumerate(original_data_list):
        if idx % 1000 == 0 and idx > 0:
            print(f"  已处理 {idx}/{len(original_data_list)} 条原始数据...")
        
        samples = split_conversation(original_data)
        all_training_samples.extend(samples)
        
        # 统计轮次
        num_rounds = len(samples)
        stats["conversations_by_rounds"][num_rounds] = stats["conversations_by_rounds"].get(num_rounds, 0) + 1
    
    stats["total_training_samples"] = len(all_training_samples)
    
    # 保存输出文件
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n正在保存到输出文件: {output_path}")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_training_samples, f, ensure_ascii=False, indent=2)
        print(f"✅ 成功保存 {len(all_training_samples)} 条训练样本到 {output_path}")
    except Exception as e:
        print(f"❌ 保存文件失败: {str(e)}")
        return
    
    # 打印统计信息
    print(f"\n{'='*80}")
    print("统计信息")
    print(f"{'='*80}")
    print(f"原始对话数据: {stats['total_original']} 条")
    print(f"生成的训练样本: {stats['total_training_samples']} 条")
    print(f"平均每条对话生成: {stats['total_training_samples'] / stats['total_original']:.2f} 条训练样本")
    print(f"\n按轮次统计（原始对话的轮次数）:")
    for rounds in sorted(stats["conversations_by_rounds"].keys()):
        count = stats["conversations_by_rounds"][rounds]
        print(f"  {rounds} 轮对话: {count} 条")
    print(f"{'='*80}")
    
    # 打印示例
    if all_training_samples:
        print(f"\n示例训练样本（第1条）:")
        print(json.dumps(all_training_samples[0], ensure_ascii=False, indent=2))
        if len(all_training_samples) > 1:
            print(f"\n示例训练样本（第2条，如果有历史对话）:")
            # 找一个有历史对话的样本
            for sample in all_training_samples:
                if sample.get("history"):
                    print(json.dumps(sample, ensure_ascii=False, indent=2))
                    break


def main():
    parser = argparse.ArgumentParser(
        description='将多轮对话数据拆分成Alpaca格式的训练样本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:

  1. 使用默认输入输出路径:
     python split_conversations.py

  2. 指定输入和输出文件:
     python split_conversations.py --input input.json --output output.json

  3. 限制处理数量（用于测试）:
     python split_conversations.py --max-samples 100

  4. 组合使用:
     python split_conversations.py --input data.json --output train.json --max-samples 1000

默认路径:
  - 输入: output_dataset/consolidated_data.json
  - 输出: output_dataset/alpaca_format_data.json
        """
    )
    
    parser.add_argument(
        '--input',
        type=str,
        default=str(DEFAULT_INPUT_FILE),
        help=f'输入JSON文件路径（默认: {DEFAULT_INPUT_FILE}）'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=str(DEFAULT_OUTPUT_FILE),
        help=f'输出JSON文件路径（默认: {DEFAULT_OUTPUT_FILE}）'
    )
    
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help='最大处理样本数（用于测试），None表示处理全部'
    )
    
    args = parser.parse_args()
    
    # 执行处理
    process_data(
        input_file=args.input,
        output_file=args.output,
        max_samples=args.max_samples
    )


if __name__ == "__main__":
    main()
