import os
import re
import platform


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，使其在所有操作系统（Windows、Mac、Linux）上都是有效的
    
    Args:
        filename: 原始文件名
        
    Returns:
        清理后的有效文件名
    """
    if not filename:
        return "unknown_file"
    
    # 获取当前操作系统
    system = platform.system().lower()
    
    # 定义不同操作系统的非法字符
    illegal_chars = {
        'windows': r'[<>:"/\\|?*\x00-\x1f]',  # Windows非法字符
        'darwin': r'[<>:"/\\|?*\x00-\x1f]',   # macOS非法字符（与Windows类似）
        'linux': r'[<>:"/\\|?*\x00-\x1f]'     # Linux非法字符（与Windows类似）
    }
    
    # 获取当前系统的非法字符模式
    illegal_pattern = illegal_chars.get(system, illegal_chars['linux'])
    
    # 替换非法字符为下划线
    sanitized = re.sub(illegal_pattern, '_', filename)
    
    # 移除或替换其他可能导致问题的字符（保留字母、数字、连字符、下划线、点）
    sanitized = re.sub(r'[^\w\-_.]', '_', sanitized)
    
    # 确保文件名不以点或空格开头或结尾
    sanitized = sanitized.strip('._ ')
    
    # 处理特殊情况
    if not sanitized:
        return "unknown_file"
    
    # Windows和macOS不允许某些保留名称
    reserved_names = {
        'windows': ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                   'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                   'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'],
        'darwin': ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                  'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                  'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'],
        'linux': []  # Linux没有保留名称限制
    }
    
    reserved = reserved_names.get(system, [])
    if sanitized.upper() in reserved:
        sanitized = f"_{sanitized}_"
    
    # 限制文件名长度（考虑不同系统的限制）
    max_length = {
        'windows': 255,  # Windows NTFS
        'darwin': 255,   # macOS HFS+/APFS
        'linux': 255     # Linux ext4
    }
    
    max_len = max_length.get(system, 255)
    if len(sanitized) > max_len:
        # 保留扩展名（如果有的话）
        name, ext = os.path.splitext(sanitized)
        max_name_len = max_len - len(ext)
        sanitized = name[:max_name_len] + ext
    
    return sanitized


def get_directory_tree(directory, ignore_spec=None, max_depth=2, depth=0, project_root=None, prefix="",
                       only_dirs=False):
    """
    以 tree 命令的格式返回目录结构，并应用 .gitignore 规则。

    :param directory: 需要扫描的目录
    :param ignore_spec: PathSpec 对象，用于匹配 .gitignore 规则
    :param max_depth: 最大扫描深度
    :param depth: 当前递归深度（用于内部递归）
    :param project_root: 项目根目录（仅在首次调用时设置）
    :param prefix: 当前层级的前缀符号
    :param only_dirs: 是否仅返回目录结构，默认返回所有（目录+文件）
    :return: 目录结构字符串
    """
    if max_depth is not None and depth >= max_depth:
        return ""  # 超过最大深度，返回空字符串

    if project_root is None:
        project_root = os.path.abspath(directory)

    entries = sorted(os.listdir(directory))  # 排序，保证一致性
    entries = [e for e in entries if not e.startswith(".")]  # 忽略隐藏文件

    tree_lines = []  # 用于存储目录结构的字符串列表

    for index, entry in enumerate(entries):
        path = os.path.join(directory, entry)
        relative_path = os.path.relpath(path, start=project_root)  # 计算相对路径

        # 如果只返回目录，且不是目录，跳过
        if only_dirs and not os.path.isdir(path):
            continue

        # 如果是目录，添加斜杠
        if os.path.isdir(path):
            relative_path += "/"

        # 应用 .gitignore 规则
        if ignore_spec and ignore_spec.match_file(relative_path):
            continue  # 忽略匹配的文件/目录

        # 是否是当前目录的最后一个元素
        is_last = (index == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        tree_lines.append(prefix + connector + entry)

        # 如果只返回目录且是目录，递归扫描子目录
        if os.path.isdir(path):
            new_prefix = prefix + ("    " if is_last else "│   ")
            sub_tree = get_directory_tree(path, ignore_spec, max_depth, depth + 1, project_root, new_prefix,
                                          only_dirs=only_dirs)
            if sub_tree:  # 如果子目录有内容，添加到 tree_lines
                tree_lines.extend(sub_tree.split("\n"))  # 将子目录内容拆分为列表并扩展

    return "\n".join(tree_lines)