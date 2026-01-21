#!/usr/bin/env python3
"""
命令生成相关函数
包含解析生成计划、构建生成指令等功能
"""

from pathlib import Path
from typing import List, Tuple

# 生成计划文件路径（相对于此文件）
GENERATION_PLAN_FILE = Path(__file__).parent / "generation_plan.txt"


def parse_generation_plan() -> Tuple[List[str], List[str], List[str]]:
    """解析generation_plan.txt，提取领域、模糊类型和轮次列表
    
    直接保存整行内容，不进行解析。
    文件格式：
    ## 领域列表（20个）
    美容美发 (Beauty_Hairdressing)
    ...
    ## 模糊类型列表（8种）
    condition_missing（条件缺失）
    ...
    ## 对话轮次列表（5种）
    1轮：...
    ...
    ## 生成指令
    ...
    """
    lines = GENERATION_PLAN_FILE.read_text(encoding='utf-8').split('\n')
    
    domains = []
    types = []
    rounds = []
    
    current_section = None
    
    for line in lines:
        line_stripped = line.strip()
        
        # 跳过空行
        if not line_stripped:
            continue
        
        # 检测章节标题（格式：## 标题）
        if line_stripped.startswith('##'):
            if '领域列表' in line_stripped:
                current_section = 'domains'
                continue
            elif '模糊类型列表' in line_stripped:
                current_section = 'types'
                continue
            elif '对话轮次列表' in line_stripped:
                current_section = 'rounds'
                continue
            elif '生成指令' in line_stripped:
                # 遇到"生成指令"章节，停止解析
                break
            else:
                # 其他##开头的行，跳过
                continue
        
        # 直接保存整行内容
        if current_section == 'domains':
            domains.append(line_stripped)
        elif current_section == 'types':
            types.append(line_stripped)
        elif current_section == 'rounds':
            rounds.append(line_stripped)
    
    # 验证解析结果
    if not domains:
        raise ValueError("未找到任何领域")
    if not types:
        raise ValueError("未找到任何模糊类型")
    if not rounds:
        raise ValueError("未找到任何对话轮次")
    
    return domains, types, rounds


def extract_domain_code(domain_line: str) -> str:
    """从领域行中提取代码，例如 "美容美发 (Beauty_Hairdressing)" -> "Beauty_Hairdressing" """
    if '(' in domain_line and ')' in domain_line:
        start = domain_line.rfind('(')
        end = domain_line.rfind(')')
        if start < end:
            return domain_line[start+1:end].strip()
    return ""


def extract_type_code(type_line: str) -> str:
    """从模糊类型行中提取代码，例如 "condition_missing（条件缺失）" -> "condition_missing" """
    if '（' in type_line:
        return type_line[:type_line.find('（')].strip()
    return ""


def extract_round_num(round_line: str) -> int:
    """从轮次行中提取数字，例如 "1轮：..." -> 1 """
    if round_line and round_line[0].isdigit():
        num_str = ''
        for char in round_line:
            if char.isdigit():
                num_str += char
            else:
                break
        if num_str:
            return int(num_str)
    return 0


def build_generation_instruction(domain_line: str, type_line: str, round_line: str, count: int = 50) -> str:
    """构建生成指令，直接使用整行内容
    
    Args:
        domain_line: 领域行
        type_line: 模糊类型行
        round_line: 轮次行
        count: 需要生成的数据条数，默认50条
    """
    instruction = f"""请生成{count}条数据，要求：
1. 领域：{domain_line}
2. 模糊类型：{type_line}
3. 对话轮次：{round_line}
4. 数据格式：必须输出为有效的JSON数组格式，每条数据为sharegpt格式（包含system和conversations字段）
5. 每条数据必须是完整的对话，以【完整请求总结】结束
6. 助手在信息不足时必须追问，在信息完整后必须总结
"""
    
    return instruction
