#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据整理脚本
将 data/cautious_secretary_raw 下的所有数据整理成一个新的 JSON 文件

支持功能：
1. 指定输出文件名
2. 从每个轮次 JSON 文件中提取指定数量的数据（默认全部）
3. 排除模式：排除指定的文件或文件夹
4. 添加模式：只添加指定的文件或文件夹
"""

import json
import argparse
from pathlib import Path
from typing import List, Set, Optional
from collections import defaultdict

# 数据根目录（从脚本所在位置向上查找项目根目录）
SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_ROOT = PROJECT_ROOT / "data" / "cautious_secretary_raw"


def normalize_path(path_str: str) -> Path:
    """
    规范化路径，支持相对路径和绝对路径
    如果路径以 data/cautious_secretary_raw 开头，则去掉这个前缀
    """
    path_str_clean = str(path_str).strip()
    
    # 统一使用正斜杠
    path_str_normalized = path_str_clean.replace('\\', '/')
    
    # 如果路径以 data/cautious_secretary_raw 开头，去掉前缀
    if path_str_normalized.startswith('data/cautious_secretary_raw/'):
        path_str_normalized = path_str_normalized[len('data/cautious_secretary_raw/'):]
    elif path_str_normalized.startswith('./data/cautious_secretary_raw/'):
        path_str_normalized = path_str_normalized[len('./data/cautious_secretary_raw/'):]
    
    # 构建路径对象
    path = Path(path_str_normalized)
    
    # 如果是绝对路径，直接返回
    if path.is_absolute():
        return path
    
    # 构建相对于 DATA_ROOT 的完整路径
    full_path = DATA_ROOT / path_str_normalized
    
    # 如果路径不存在，尝试查找匹配的文件或目录
    if not full_path.exists():
        # 尝试查找匹配的文件（忽略大小写）
        path_str_lower = path_str_normalized.lower()
        for existing_path in DATA_ROOT.rglob("*"):
            if str(existing_path.relative_to(DATA_ROOT)).lower() == path_str_lower:
                return existing_path
    
    return full_path


def is_path_under(parent_path: Path, child_path: Path) -> bool:
    """
    检查 child_path 是否在 parent_path 下（兼容 Python 3.8+）
    
    Args:
        parent_path: 父路径
        child_path: 子路径
    
    Returns:
        True 如果 child_path 在 parent_path 下
    """
    try:
        # Python 3.9+ 支持 is_relative_to
        if hasattr(child_path, 'is_relative_to'):
            return child_path.is_relative_to(parent_path)
        else:
            # Python 3.8 使用 relative_to 方法
            child_path.relative_to(parent_path)
            return True
    except (ValueError, AttributeError):
        return False


def should_include_file(file_path: Path, exclude_paths: Set[Path], include_paths: Optional[Set[Path]], mode: str) -> bool:
    """
    判断文件是否应该被包含
    
    Args:
        file_path: 要检查的文件路径
        exclude_paths: 排除路径集合
        include_paths: 包含路径集合（仅在添加模式下使用）
        mode: 'exclude' 或 'include'
    
    Returns:
        True 如果应该包含，False 如果应该排除
    """
    # 将文件路径转换为相对于 DATA_ROOT 的路径
    try:
        rel_path = file_path.relative_to(DATA_ROOT)
    except ValueError:
        # 如果文件不在 DATA_ROOT 下，返回 False
        return False
    
    # 检查排除模式
    if mode == 'exclude':
        # 检查文件本身是否在排除列表中
        if file_path in exclude_paths:
            return False
        
        # 检查文件的任何父目录是否在排除列表中
        for exclude_path in exclude_paths:
            # 如果排除路径是目录，检查文件是否在该目录下
            if exclude_path.is_dir():
                if is_path_under(exclude_path, file_path):
                    return False
            # 如果排除路径是文件，直接比较
            elif exclude_path.is_file():
                if file_path == exclude_path:
                    return False
        
        return True
    
    # 检查添加模式
    elif mode == 'include':
        if include_paths is None or len(include_paths) == 0:
            return False
        
        # 检查文件本身是否在包含列表中
        if file_path in include_paths:
            return True
        
        # 检查文件的任何父目录是否在包含列表中
        for include_path in include_paths:
            # 如果包含路径是目录，检查文件是否在该目录下
            if include_path.is_dir():
                if is_path_under(include_path, file_path):
                    return True
            # 如果包含路径是文件，直接比较
            elif include_path.is_file():
                if file_path == include_path:
                    return True
        
        return False
    
    return True


def load_json_file(file_path: Path, max_items: Optional[int] = None) -> List[dict]:
    """
    加载 JSON 文件并返回数据列表
    
    Args:
        file_path: JSON 文件路径
        max_items: 最大提取数量，None 表示提取全部
    
    Returns:
        数据列表
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list):
            print(f"警告: {file_path} 不是数组格式，跳过")
            return []
        
        # 如果指定了最大数量，只取前 max_items 条
        if max_items is not None and max_items > 0:
            return data[:max_items]
        
        return data
    except Exception as e:
        print(f"错误: 读取文件 {file_path} 失败: {str(e)}")
        return []


def find_all_json_files(data_root: Path) -> List[Path]:
    """
    查找所有 *_round.json 文件
    
    Args:
        data_root: 数据根目录
    
    Returns:
        所有 JSON 文件路径列表
    """
    json_files = []
    for round_file in data_root.rglob("*_round.json"):
        json_files.append(round_file)
    return sorted(json_files)


def consolidate_data(
    output_file: Optional[str] = None,
    max_items_per_file: Optional[int] = None,
    mode: str = 'exclude',
    paths: List[str] = None
):
    """
    整理数据到新的 JSON 文件
    
    Args:
        output_file: 输出文件名（相对路径将相对于脚本目录，如果为None则使用默认路径）
        max_items_per_file: 每个文件最多提取的数据条数，None 表示全部
        mode: 'exclude' 或 'include'
        paths: 排除或包含的路径列表
    """
    if paths is None:
        paths = []
    
    # 如果没有指定输出文件，使用默认路径
    if output_file is None:
        output_dir = PROJECT_ROOT / "output_dataset"
        output_dir.mkdir(exist_ok=True)
        output_file = str(output_dir / "consolidated_data.json")
        print(f"使用默认输出路径: {output_file}")
    
    # 规范化路径
    if mode == 'exclude':
        exclude_paths = set()
        for p in paths:
            normalized = normalize_path(p)
            if not normalized.exists():
                print(f"警告: 路径不存在，将被忽略: {p} -> {normalized}")
            else:
                exclude_paths.add(normalized)
        include_paths = None
        print(f"排除模式: 将排除 {len(exclude_paths)} 个路径")
        for path in exclude_paths:
            try:
                rel_path = path.relative_to(DATA_ROOT)
                print(f"  - {rel_path}")
            except ValueError:
                print(f"  - {path}")
    else:
        include_paths = set()
        for p in paths:
            normalized = normalize_path(p)
            if not normalized.exists():
                print(f"警告: 路径不存在，将被忽略: {p} -> {normalized}")
            else:
                include_paths.add(normalized)
        exclude_paths = set()
        print(f"添加模式: 将只包含 {len(include_paths)} 个路径")
        for path in include_paths:
            try:
                rel_path = path.relative_to(DATA_ROOT)
                print(f"  - {rel_path}")
            except ValueError:
                print(f"  - {path}")
    
    # 检查数据根目录
    if not DATA_ROOT.exists():
        print(f"错误: 数据目录不存在: {DATA_ROOT}")
        return
    
    # 查找所有 JSON 文件
    print(f"\n正在查找所有数据文件...")
    all_json_files = find_all_json_files(DATA_ROOT)
    print(f"找到 {len(all_json_files)} 个 JSON 文件")
    
    # 过滤文件
    print(f"\n正在过滤文件...")
    filtered_files = []
    for file_path in all_json_files:
        if should_include_file(file_path, exclude_paths, include_paths, mode):
            filtered_files.append(file_path)
    
    print(f"过滤后剩余 {len(filtered_files)} 个文件")
    
    # 收集所有数据
    print(f"\n正在收集数据...")
    all_data = []
    stats = defaultdict(int)
    
    for file_path in filtered_files:
        data = load_json_file(file_path, max_items_per_file)
        if data:
            all_data.extend(data)
            # 统计信息
            rel_path = file_path.relative_to(DATA_ROOT)
            domain = rel_path.parts[0] if len(rel_path.parts) > 0 else "unknown"
            stats[domain] += len(data)
            print(f"  已处理: {rel_path} ({len(data)} 条数据)")
    
    # 处理输出文件路径：如果是相对路径，则相对于脚本目录
    output_path = Path(output_file)
    if not output_path.is_absolute():
        output_path = SCRIPT_DIR / output_path
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 保存到输出文件
    print(f"\n正在保存到 {output_path}...")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 成功保存 {len(all_data)} 条数据到 {output_path}")
    except Exception as e:
        print(f"❌ 保存文件失败: {str(e)}")
        return
    
    # 打印统计信息
    print(f"\n{'='*80}")
    print("统计信息")
    print(f"{'='*80}")
    print(f"总数据条数: {len(all_data)}")
    print(f"处理文件数: {len(filtered_files)}")
    print(f"\n按领域统计:")
    for domain in sorted(stats.keys()):
        print(f"  {domain}: {stats[domain]} 条")
    print(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='整理 data/cautious_secretary_raw 下的数据到一个新的 JSON 文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用示例:

  1. 排除模式 - 排除指定文件:
     python consolidate_data.py output.json --mode exclude --paths "Beauty_Hairdressing/condition_missing/2_round.json"

  2. 排除模式 - 排除整个文件夹:
     python consolidate_data.py output.json --mode exclude --paths "Beauty_Hairdressing/condition_missing"

  3. 排除模式 - 排除多个路径:
     python consolidate_data.py output.json --mode exclude --paths "Beauty_Hairdressing" "Education_Learning"

  4. 添加模式 - 只添加指定文件:
     python consolidate_data.py output.json --mode include --paths "Beauty_Hairdressing/condition_missing/2_round.json"

  5. 添加模式 - 只添加整个文件夹:
     python consolidate_data.py output.json --mode include --paths "Beauty_Hairdressing/condition_missing"

  6. 限制每个文件提取数量:
     python consolidate_data.py output.json --max-items 10

  7. 组合使用:
     python consolidate_data.py output.json --mode exclude --paths "Beauty_Hairdressing" --max-items 20

  8. 使用默认输出路径（不指定输出文件）:
     python consolidate_data.py --max-items 10
     # 将输出到 output_dataset/consolidated_data.json

路径格式说明:
  - 可以使用相对路径: "Beauty_Hairdressing/condition_missing/2_round.json"
  - 可以使用绝对路径: "C:/path/to/data/cautious_secretary_raw/Beauty_Hairdressing/..."
  - 路径会自动规范化，支持 Windows 和 Unix 风格路径
  - 输出文件路径：相对路径将相对于脚本所在目录
  - 如果不指定输出文件，将使用默认路径：output_dataset/consolidated_data.json
        """
    )
    
    parser.add_argument(
        'output_file',
        type=str,
        nargs='?',
        default=None,
        help='输出 JSON 文件名（可选，相对路径将相对于脚本目录。如果不指定，将使用默认路径：output_dataset/consolidated_data.json）'
    )
    
    parser.add_argument(
        '--max-items',
        type=int,
        default=None,
        help='从每个轮次 JSON 文件中提取的最大数据条数（默认：全部）'
    )
    
    parser.add_argument(
        '--mode',
        type=str,
        choices=['exclude', 'include'],
        default='exclude',
        help='模式：exclude（排除模式，默认）或 include（添加模式）'
    )
    
    parser.add_argument(
        '--paths',
        type=str,
        nargs='+',
        default=[],
        help='要排除或包含的路径列表（文件或文件夹）'
    )
    
    args = parser.parse_args()
    
    # 验证参数
    if args.mode == 'include' and len(args.paths) == 0:
        print("错误: 添加模式下必须指定至少一个路径")
        return
    
    # 执行整理
    consolidate_data(
        output_file=args.output_file,
        max_items_per_file=args.max_items,
        mode=args.mode,
        paths=args.paths
    )


if __name__ == "__main__":
    main()
