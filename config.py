#!/usr/bin/env python3
"""
主程序配置
包含所有可配置的参数
"""

from pathlib import Path

# 项目路径
# 脚本所在目录作为项目根目录
PROJECT_ROOT = Path(__file__).parent
INITIAL_PROMPT_FILE = PROJECT_ROOT / "initial_prompt.txt"
OUTPUT_BASE_DIR = PROJECT_ROOT / "data" / "cautious_secretary_raw"

# 根据轮次估算每条数据的token数（用于计算需要的输出token）
# 根据实际生成的数据分析（Beauty_Hairdressing/condition_missing，各50条）
TOKENS_PER_ITEM_BY_ROUND = {
    1: 365,   # 1轮：每条约365 tokens（实际平均：365，范围：337-422）
    2: 344,   # 2轮：每条约344 tokens（实际平均：344，范围：301-403）
    3: 354,   # 3轮：每条约354 tokens（实际平均：354，范围：321-399）
    4: 481,   # 4轮：每条约481 tokens（实际平均：482，范围：443-576）
    5: 425,   # 5轮：每条约425 tokens（实际平均：426，范围：395-468）
}

# 任务配置
TARGET_ITEMS_PER_TASK = 50  # 每个任务的目标数据条数
MAX_RETRIES = 3  # 最多重试次数
RETRY_DELAY = 2  # 重试延迟（秒）
SUCCESS_DELAY = 5  # 成功处理后的延迟（秒）

# 并发配置
ENABLE_CONCURRENCY = True  # 是否启用并发，默认True
CONCURRENT_WORKERS = 10  # 并发worker数量，默认10
