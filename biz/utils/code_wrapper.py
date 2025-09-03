"""
代码格式包裹工具类
根据文件扩展名自动选择对应的markdown代码块格式
"""
import os
from typing import Dict, Optional


class CodeWrapper:
    """代码格式包裹工具类"""
    
    # 文件扩展名到语言标识符的映射
    EXTENSION_TO_LANGUAGE: Dict[str, str] = {
        # JavaScript/TypeScript
        '.js': 'js',
        '.jsx': 'jsx', 
        '.ts': 'ts',
        '.tsx': 'tsx',
        '.mjs': 'js',
        '.cjs': 'js',
        '.vue': 'vue',


        # Java
        '.java': 'java',
        
        # Python
        '.py': 'python',
        '.pyw': 'python',
        
        # C/C++
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.hxx': 'cpp',
        
        # C#
        '.cs': 'csharp',
        
        # Go
        '.go': 'go',
        
        # Rust
        '.rs': 'rust',
        
        # PHP
        '.php': 'php',
        
        # Ruby
        '.rb': 'ruby',
        
        # Swift
        '.swift': 'swift',
        
        # Kotlin
        '.kt': 'kotlin',
        '.kts': 'kotlin',
        
        # Scala
        '.scala': 'scala',
        
        # Shell
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.fish': 'fish',
        
        # Web
        '.html': 'html',
        '.htm': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        
        # Config/Data
        '.json': 'json',
        '.xml': 'xml',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'ini',
        
        # SQL
        '.sql': 'sql',
        
        # Markdown
        '.md': 'markdown',
        '.markdown': 'markdown',
        
        # Docker
        'dockerfile': 'dockerfile',
        '.dockerfile': 'dockerfile',
        
        # Other
        '.txt': 'text',
        '.log': 'text',
        '.properties': 'properties',
        '.gradle': 'gradle',
        '.groovy': 'groovy',
        '.r': 'r',
        '.R': 'r',
        '.m': 'matlab',
        '.pl': 'perl',
        '.lua': 'lua',
        '.vim': 'vim',
        '.vimrc': 'vim',
    }
    
    @classmethod
    def get_language_from_file_path(cls, file_path: str) -> str:
        """
        根据文件路径获取对应的语言标识符
        
        Args:
            file_path: 文件路径
            
        Returns:
            语言标识符，如果未找到则返回'text'
        """
        if not file_path:
            return 'text'
            
        # 获取文件名（处理路径分隔符）
        filename = os.path.basename(file_path.replace('\\', '/'))
        
        # 特殊文件名处理
        filename_lower = filename.lower()
        if filename_lower in ['dockerfile', 'makefile', 'rakefile', 'gemfile']:
            return cls.EXTENSION_TO_LANGUAGE.get(filename_lower, 'text')
        
        # 获取文件扩展名
        _, ext = os.path.splitext(filename)
        ext_lower = ext.lower()
        
        return cls.EXTENSION_TO_LANGUAGE.get(ext_lower, 'text')
    
    @classmethod
    def wrap_code(cls, code: str, file_path: str = None, language: str = None) -> str:
        """
        使用markdown代码块格式包裹代码
        
        Args:
            code: 要包裹的代码内容
            file_path: 文件路径（用于自动检测语言）
            language: 指定的语言标识符（优先级高于file_path）
            
        Returns:
            包裹后的markdown代码块
        """
        if not code:
            return '```\n\n```'
            
        # 确定语言标识符
        if language:
            lang = language
        elif file_path:
            lang = cls.get_language_from_file_path(file_path)
        else:
            lang = 'text'
        
        # 确保代码末尾没有多余的换行符
        code = code.rstrip('\n')
        
        return f'```{lang}\n{code}\n```'
    
    @classmethod
    def wrap_code_to_md(cls, code: str, file_path: str) -> str:
        """
        根据文件路径包裹代码为markdown格式
        
        Args:
            code: 代码内容
            file_path: 文件路径（用于自动检测语言）
            
        Returns:
            包裹后的markdown代码块
        """
        return cls.wrap_code(code, file_path=file_path)
    
    @classmethod
    def add_language_support(cls, extension: str, language: str) -> None:
        """
        添加新的文件扩展名支持
        
        Args:
            extension: 文件扩展名（包含点号，如'.vue'）
            language: 对应的语言标识符
        """
        cls.EXTENSION_TO_LANGUAGE[extension.lower()] = language
    
    @classmethod
    def get_supported_extensions(cls) -> Dict[str, str]:
        """
        获取所有支持的文件扩展名及其对应的语言标识符
        
        Returns:
            扩展名到语言标识符的映射字典
        """
        return cls.EXTENSION_TO_LANGUAGE.copy()
