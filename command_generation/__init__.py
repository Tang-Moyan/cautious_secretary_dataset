"""
命令生成模块
"""

from .parser import (
    parse_generation_plan,
    extract_domain_code,
    extract_type_code,
    extract_round_num,
    build_generation_instruction,
)

__all__ = [
    'parse_generation_plan',
    'extract_domain_code',
    'extract_type_code',
    'extract_round_num',
    'build_generation_instruction',
]
