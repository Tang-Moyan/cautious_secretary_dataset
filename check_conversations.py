#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查并清理对话数据脚本
检查每条数据的conversations字段中"from": "human"和"from": "gpt"的数量是否匹配且与轮次一致
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple

# 数据根目录
DATA_ROOT = Path("data/cautious_secretary_raw")

# 统计信息
stats = {
    "total_files": 0,
    "total_data_before": 0,
    "total_data_after": 0,
    "total_removed": 0,
    "files_processed": 0,
    "files_with_removals": 0,
    "by_domain": defaultdict(lambda: {
        "files": 0,
        "data_before": 0,
        "data_after": 0,
        "removed": 0
    }),
    "by_round": defaultdict(lambda: {
        "files": 0,
        "data_before": 0,
        "data_after": 0,
        "removed": 0
    }),
    "by_ambiguity_type": defaultdict(lambda: {
        "files": 0,
        "data_before": 0,
        "data_after": 0,
        "removed": 0
    }),
    "error_details": []
}


def extract_round_number(filename: str) -> int:
    """从文件名中提取轮次数"""
    # 文件名格式: 1_round.json, 2_round.json, etc.
    try:
        return int(filename.split('_')[0])
    except (ValueError, IndexError):
        return 0


def check_conversation(data_item: dict, expected_rounds: int) -> Tuple[bool, str]:
    """
    检查单条数据的conversations字段
    
    Returns:
        (is_valid, error_message)
    """
    # 检查system字段
    if "system" not in data_item:
        return False, "缺少system字段"
    
    if "conversations" not in data_item:
        return False, "缺少conversations字段"
    
    conversations = data_item["conversations"]
    if not isinstance(conversations, list):
        return False, "conversations不是list类型"
    
    human_count = 0
    gpt_count = 0
    last_gpt_value = None
    
    for conv in conversations:
        if not isinstance(conv, dict):
            return False, "conversations中的元素不是dict类型"
        
        if "from" not in conv:
            return False, "conversation中缺少from字段"
        
        if conv["from"] == "human":
            human_count += 1
        elif conv["from"] == "gpt":
            gpt_count += 1
            # 记录最后一个gpt的value
            if "value" in conv:
                last_gpt_value = conv["value"]
    
    # 检查数量是否匹配
    if human_count != gpt_count:
        return False, f"human数量({human_count})与gpt数量({gpt_count})不匹配"
    
    # 检查是否与轮次匹配
    if human_count != expected_rounds:
        return False, f"轮次数量({human_count})与期望轮次({expected_rounds})不匹配"
    
    # 检查最后一个gpt的value是否以"【完整请求总结】"开头
    if last_gpt_value is None:
        return False, "最后一个gpt对话缺少value字段"
    
    if not isinstance(last_gpt_value, str):
        return False, "最后一个gpt的value不是字符串类型"
    
    if not last_gpt_value.startswith("【完整请求总结】"):
        return False, f"最后一个gpt的value未以'【完整请求总结】'开头，实际开头: {last_gpt_value[:20]}..."
    
    return True, ""


def process_file(file_path: Path) -> Tuple[int, int, List[str]]:
    """
    处理单个json文件
    
    Returns:
        (原始数据数量, 清理后数据数量, 错误信息列表)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, [f"读取文件失败: {str(e)}"]
    
    if not isinstance(data, list):
        return 0, 0, [f"文件内容不是list类型"]
    
    expected_rounds = extract_round_number(file_path.name)
    if expected_rounds == 0:
        return 0, 0, [f"无法从文件名提取轮次数: {file_path.name}"]
    
    original_count = len(data)
    valid_data = []
    errors = []
    
    for idx, item in enumerate(data):
        is_valid, error_msg = check_conversation(item, expected_rounds)
        if is_valid:
            valid_data.append(item)
        else:
            errors.append(f"数据项#{idx+1}: {error_msg}")
    
    # 保存清理后的数据
    if len(valid_data) != original_count:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(valid_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            errors.append(f"保存文件失败: {str(e)}")
    
    return original_count, len(valid_data), errors


def process_all_files():
    """处理所有文件"""
    if not DATA_ROOT.exists():
        print(f"错误: 数据目录不存在: {DATA_ROOT}")
        return
    
    # 遍历所有领域文件夹
    for domain_dir in sorted(DATA_ROOT.iterdir()):
        if not domain_dir.is_dir():
            continue
        
        domain_name = domain_dir.name
        print(f"\n处理领域: {domain_name}")
        
        # 遍历所有模糊类型文件夹
        for ambiguity_dir in sorted(domain_dir.iterdir()):
            if not ambiguity_dir.is_dir():
                continue
            
            ambiguity_type = ambiguity_dir.name
            print(f"  处理模糊类型: {ambiguity_type}")
            
            # 遍历所有轮次文件
            for round_file in sorted(ambiguity_dir.glob("*_round.json")):
                stats["total_files"] += 1
                round_num = extract_round_number(round_file.name)
                
                print(f"    处理文件: {round_file.name}", end=" ... ")
                
                original_count, valid_count, errors = process_file(round_file)
                removed_count = original_count - valid_count
                
                # 更新统计信息
                stats["total_data_before"] += original_count
                stats["total_data_after"] += valid_count
                stats["total_removed"] += removed_count
                stats["files_processed"] += 1
                
                stats["by_domain"][domain_name]["files"] += 1
                stats["by_domain"][domain_name]["data_before"] += original_count
                stats["by_domain"][domain_name]["data_after"] += valid_count
                stats["by_domain"][domain_name]["removed"] += removed_count
                
                stats["by_round"][round_num]["files"] += 1
                stats["by_round"][round_num]["data_before"] += original_count
                stats["by_round"][round_num]["data_after"] += valid_count
                stats["by_round"][round_num]["removed"] += removed_count
                
                stats["by_ambiguity_type"][ambiguity_type]["files"] += 1
                stats["by_ambiguity_type"][ambiguity_type]["data_before"] += original_count
                stats["by_ambiguity_type"][ambiguity_type]["data_after"] += valid_count
                stats["by_ambiguity_type"][ambiguity_type]["removed"] += removed_count
                
                if removed_count > 0:
                    stats["files_with_removals"] += 1
                    print(f"移除了 {removed_count} 条数据")
                    if errors:
                        stats["error_details"].append({
                            "file": str(round_file),
                            "removed": removed_count,
                            "errors": errors[:5]  # 只保存前5个错误
                        })
                else:
                    print(f"通过 ({valid_count} 条数据)")


def print_statistics():
    """打印统计信息"""
    print("\n" + "="*80)
    print("统计报告")
    print("="*80)
    
    print(f"\n总体统计:")
    print(f"  处理文件数: {stats['total_files']}")
    print(f"  处理数据总数(清理前): {stats['total_data_before']}")
    print(f"  处理数据总数(清理后): {stats['total_data_after']}")
    print(f"  删除数据总数: {stats['total_removed']}")
    print(f"  有数据删除的文件数: {stats['files_with_removals']}")
    
    if stats['total_data_before'] > 0:
        removal_rate = stats['total_removed'] / stats['total_data_before'] * 100
        print(f"  删除率: {removal_rate:.2f}%")
    
    print(f"\n按领域统计:")
    for domain in sorted(stats['by_domain'].keys()):
        d = stats['by_domain'][domain]
        print(f"  {domain}:")
        print(f"    文件数: {d['files']}")
        print(f"    数据(清理前): {d['data_before']}")
        print(f"    数据(清理后): {d['data_after']}")
        print(f"    删除数: {d['removed']}")
        if d['data_before'] > 0:
            rate = d['removed'] / d['data_before'] * 100
            print(f"    删除率: {rate:.2f}%")
    
    print(f"\n按轮次统计:")
    for round_num in sorted(stats['by_round'].keys()):
        r = stats['by_round'][round_num]
        print(f"  {round_num}_round:")
        print(f"    文件数: {r['files']}")
        print(f"    数据(清理前): {r['data_before']}")
        print(f"    数据(清理后): {r['data_after']}")
        print(f"    删除数: {r['removed']}")
        if r['data_before'] > 0:
            rate = r['removed'] / r['data_before'] * 100
            print(f"    删除率: {rate:.2f}%")
    
    print(f"\n按模糊类型统计:")
    for amb_type in sorted(stats['by_ambiguity_type'].keys()):
        a = stats['by_ambiguity_type'][amb_type]
        print(f"  {amb_type}:")
        print(f"    文件数: {a['files']}")
        print(f"    数据(清理前): {a['data_before']}")
        print(f"    数据(清理后): {a['data_after']}")
        print(f"    删除数: {a['removed']}")
        if a['data_before'] > 0:
            rate = a['removed'] / a['data_before'] * 100
            print(f"    删除率: {rate:.2f}%")
    
    if stats['error_details']:
        print(f"\n错误详情 (前10个):")
        for i, detail in enumerate(stats['error_details'][:10], 1):
            print(f"  {i}. {detail['file']}")
            print(f"     删除: {detail['removed']} 条")
            for err in detail['errors']:
                print(f"     - {err}")


def save_statistics():
    """保存统计信息到JSON文件"""
    # 将defaultdict转换为普通dict以便JSON序列化
    stats_json = {
        "total_files": stats["total_files"],
        "total_data_before": stats["total_data_before"],
        "total_data_after": stats["total_data_after"],
        "total_removed": stats["total_removed"],
        "files_processed": stats["files_processed"],
        "files_with_removals": stats["files_with_removals"],
        "by_domain": dict(stats["by_domain"]),
        "by_round": {str(k): v for k, v in stats["by_round"].items()},
        "by_ambiguity_type": dict(stats["by_ambiguity_type"]),
        "error_details": stats["error_details"][:20]  # 只保存前20个错误详情
    }
    
    output_file = Path("conversation_check_stats.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(stats_json, f, ensure_ascii=False, indent=2)
    
    print(f"\n统计信息已保存到: {output_file}")


if __name__ == "__main__":
    print("开始检查对话数据...")
    process_all_files()
    print_statistics()
    save_statistics()
    print("\n检查完成!")
