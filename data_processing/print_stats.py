#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印统计报告"""

import json
from pathlib import Path

# 从脚本所在位置查找统计文件
SCRIPT_DIR = Path(__file__).parent.resolve()
STATS_FILE = SCRIPT_DIR / "conversation_check_stats.json"

if not STATS_FILE.exists():
    print(f"错误: 统计文件不存在: {STATS_FILE}")
    print("请先运行 check_conversations.py 生成统计文件")
    exit(1)

with open(STATS_FILE, 'r', encoding='utf-8') as f:
    stats = json.load(f)

print('='*80)
print('对话数据检查统计报告')
print('='*80)

print(f'\n总体统计:')
print(f'  处理文件数: {stats["total_files"]}')
print(f'  处理数据总数(清理前): {stats["total_data_before"]}')
print(f'  处理数据总数(清理后): {stats["total_data_after"]}')
print(f'  删除数据总数: {stats["total_removed"]}')
print(f'  有数据删除的文件数: {stats["files_with_removals"]}')
if stats['total_data_before'] > 0:
    print(f'  删除率: {stats["total_removed"]/stats["total_data_before"]*100:.2f}%')

print(f'\n按轮次统计:')
for k in sorted(stats['by_round'].keys(), key=lambda x: int(x)):
    r = stats['by_round'][k]
    rate = r['removed']/r['data_before']*100 if r['data_before'] > 0 else 0
    print(f'  {k}_round: 清理前{r["data_before"]}, 清理后{r["data_after"]}, 删除{r["removed"]} ({rate:.2f}%)')

print(f'\n按模糊类型统计:')
for k in sorted(stats['by_ambiguity_type'].keys()):
    v = stats['by_ambiguity_type'][k]
    rate = v['removed']/v['data_before']*100 if v['data_before'] > 0 else 0
    print(f'  {k}: 清理前{v["data_before"]}, 清理后{v["data_after"]}, 删除{v["removed"]} ({rate:.2f}%)')

print(f'\n按领域统计 (删除数最多的前10个):')
domain_list = sorted(stats['by_domain'].items(), key=lambda x: x[1]['removed'], reverse=True)[:10]
for domain, d in domain_list:
    rate = d['removed']/d['data_before']*100 if d['data_before'] > 0 else 0
    print(f'  {domain}: 清理前{d["data_before"]}, 清理后{d["data_after"]}, 删除{d["removed"]} ({rate:.2f}%)')

print(f'\n错误详情 (前5个):')
for i, detail in enumerate(stats['error_details'][:5], 1):
    print(f'  {i}. {detail["file"]}')
    print(f'     删除: {detail["removed"]} 条')
    for err in detail['errors'][:3]:
        print(f'     - {err}')
