import os
import re
import json
import time
from typing import Dict, List,  Tuple, Optional
from dataclasses import dataclass, asdict

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil


@dataclass
class ClassSignature:
    class_signature_name: str
    class_source_code: str
    field_signature_name: List[str]
    method_signature_name: List[str]
    class_path: str


@dataclass
class MethodSignature:
    class_signature_name: str
    method_source_code: str
    usaged_fields: List[str]
    usage_method_signature_name: List[str]


@dataclass
class FieldSignature:
    field_signature_name: str
    field_source_code: str


class JavaProjectAnalyzer:
    def __init__(self):
        self.class_signatures: Dict[str, ClassSignature] = {}
        self.method_signatures: Dict[str, MethodSignature] = {}
        self.field_signatures: Dict[str, FieldSignature] = {}
        
        # 预编译正则表达式以提高性能
        self._method_pattern = re.compile(
            r'(?:@\w+(?:\s*\([^)]*\))?\s*\n\s*)*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{',
            re.MULTILINE
        )
        self._annotation_pattern = re.compile(r'@\w+(?:\s*\([^)]*\))?')
        
        # 包名匹配
        self._package_pattern = re.compile(r'package\s+([\w.]+);')
        
        # 类定义匹配
        self._class_pattern = re.compile(r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{')
        self._class_pattern_simple = re.compile(r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+\w+(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{')
        
        # 字段匹配
        self._field_pattern = re.compile(r'(?:private|public|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*[=;]')
        self._field_name_pattern = re.compile(r'[\w<>\[\]]+\s+(\w+)\s*[=;]')
        
        # 方法签名匹配
        self._method_signature_pattern = re.compile(r'((?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\))')
        self._method_return_type_pattern = re.compile(r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+\s*\([^)]*\))')
        
        # 参数匹配
        self._param_pattern = re.compile(r'\(([^)]*)\)')
        self._param_type_name_pattern = re.compile(r'([\w<>\[\]]+(?:\.\.\.)?)\s+\w+')
        
        # 方法调用匹配
        self._method_call_pattern = re.compile(r'(\w+)\.(\w+)\s*\(')
        self._method_name_pattern = re.compile(r'(\w+)\s*\(')
        
        # 注解匹配
        self._annotation_valid_pattern = re.compile(r'@\w+')
        
        # 空行清理
        self._empty_lines_pattern = re.compile(r'\n\s*\n\s*\n+')
    
    def analyze_project(self, project_path: str) -> Tuple[Dict[str, ClassSignature], 
                                                         Dict[str, MethodSignature], 
                                                         Dict[str, FieldSignature]]:
        """
        分析Java项目目录，解析所有.java文件
        
        Args:
            project_path: Java项目根目录路径
            
        Returns:
            Tuple包含三个字典：
            - class_signatures: key为class_signature_name, value为ClassSignature
            - method_signatures: key为method_signature_name, value为MethodSignature  
            - field_signatures: key为field_signature_name, value为FieldSignature
        """
        self.class_signatures.clear()
        self.method_signatures.clear()
        self.field_signatures.clear()
        
        # 保存项目根目录路径，用于计算相对路径
        self.project_path = project_path
        
        # 遍历项目目录，找到所有.java文件
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('.java'):
                    file_path = os.path.join(root, file)
                    self._analyze_java_file(file_path)
        
        # 分析所有方法之间的调用关系
        for method_sig_name, method_sig in self.method_signatures.items():
            # 分析方法中调用的其他方法
            used_methods = self._analyze_method_method_usage(method_sig.method_source_code, self.method_signatures)
            
            # 更新MethodSignature中的usage_method_signature_name
            method_sig.usage_method_signature_name = used_methods
        
        return self.class_signatures, self.method_signatures, self.field_signatures

    def format_java_code(self, code: str) -> str:
        """
        简化格式化 Java 代码
        2个以上连续换行变成2个
        
        Args:
            code: 要格式化的Java代码字符串
            
        Returns:
            格式化后的Java代码字符串
        """
        if not code or not code.strip():
            return code
        # 清理多余的空行，将2个以上连续换行变成2个
        code = self._empty_lines_pattern.sub('\n\n', code)
        return code.strip()

    def _analyze_java_file(self, file_path: str):
        """分析单个Java文件"""
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析文件基本信息
            # 计算相对于项目根目录的路径
            class_path = os.path.relpath(file_path, self.project_path)
            # 将路径分隔符统一为反斜杠
            class_path = class_path.replace(os.sep, '\\')
            
            # 解析包名
            package_match = self._package_pattern.search(content)
            package_name = package_match.group(1) if package_match else ""
            
            file_info = {
                'class_path': class_path,
                'package_name': package_name
            }
            
            # 分析所有类
            # 查找所有类定义（包括前面的注释）
            class_matches = self._class_pattern.finditer(content)
            
            for class_match in class_matches:
                self._analyze_single_class(content, class_match, file_info)
                
        except Exception as e:
            logger.error(f"解析文件 {file_path} 时出错: {e}")

    def _analyze_single_class(self, content: str, class_match, file_info: Dict[str, str]):
        """分析单个类"""
        class_name = class_match.group(1)
        class_signature_name = f"{file_info['package_name']}.{class_name}" if file_info['package_name'] else class_name
        
        # 提取类的内容（包括前面的注释）
        class_start = class_match.start()
        class_content_with_comments = self._extract_class_content_with_comments(content, class_start)
        
        # 分析字段
        field_names = self._analyze_class_fields(class_content_with_comments, class_signature_name)
        
        # 分析方法
        method_names = self._analyze_class_methods(class_content_with_comments, class_signature_name, field_names)
        
        # 创建类签名
        self._create_class_signature(class_content_with_comments, class_signature_name, field_names, method_names, file_info['class_path'])

    def _analyze_class_fields(self, class_content: str, class_signature_name: str) -> List[str]:
        """分析类中的字段"""
        fields = self._extract_fields(class_content)
        field_names = []
        
        for field in fields:
            # 从字段代码中提取字段名
            match = self._field_name_pattern.search(field)
            field_name = match.group(1) if match else ""
            field_signature_name = f"{class_signature_name}.{field_name}"
            field_names.append(field_signature_name)
            
            self.field_signatures[field_signature_name] = FieldSignature(
                field_signature_name=field_signature_name,
                field_source_code=self.format_java_code(field.strip())
            )
        
        return field_names

    def _analyze_class_methods(self, class_content: str, class_signature_name: str, field_names: List[str]) -> List[str]:
        """分析类中的方法"""
        methods = self._extract_methods(class_content)
        method_names = []
        
        for method in methods:
            method_signature = self._extract_method_signature(method)
            method_signature_name = f"{class_signature_name}.{method_signature}"
            method_names.append(method_signature_name)
            
            # 分析方法中使用的字段
            used_fields = self._analyze_method_field_usage(method, field_names)
            
            # 创建MethodSignature，稍后更新调用的方法信息
            self.method_signatures[method_signature_name] = MethodSignature(
                class_signature_name=class_signature_name,
                method_source_code=self.format_java_code(method.strip()),
                usaged_fields=used_fields,
                usage_method_signature_name=[]  # 稍后更新
            )
        
        return method_names

    def _create_class_signature(self, class_content: str, class_signature_name: str, 
                               field_names: List[str], method_names: List[str], class_path: str):
        """创建类签名"""
        # 简化实现：直接使用类内容，只保留类定义和注释部分
        # 提取类定义行和注释
        simple_class = self._extract_simple_class_source_code(class_content)
        
        self.class_signatures[class_signature_name] = ClassSignature(
            class_signature_name=class_signature_name,
            class_source_code=simple_class,
            field_signature_name=field_names,
            method_signature_name=method_names,
            class_path=class_path
        )
    
    def _extract_simple_class_source_code(self, class_content: str) -> str:
        """
        提取类的签名，只保留类定义和注释，移除字段和方法
        
        Args:
            class_content: 类的完整内容
            
        Returns:
            只包含类定义和注释的类签名
        """
        if not class_content:
            return class_content
        
        # 找到类定义开始的位置
        class_match = self._class_pattern_simple.search(class_content)
        if not class_match:
            return class_content
        
        class_start = class_match.start()
        
        # 提取类定义之前的注释部分
        comment_part = class_content[:class_start]
        
        # 提取类定义行（包括继承和实现）
        class_definition = class_match.group(0)
        
        # 组合结果：注释 + 类定义 + 结束大括号
        class_signature = comment_part + class_definition + "\n}"
        
        return class_signature
    
    def _extract_class_content_with_comments(self, content: str, class_start: int) -> str:
        """提取类的完整内容（包括前面的注释）"""
        # 首先找到类定义开始的位置
        brace_count = 0
        start_brace = False
        class_end = class_start
        
        for i in range(class_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    class_end = i + 1
                    break
        
        # 向前查找类定义之前的注释
        comment_start = self._find_class_comment_start(content, class_start)
        
        # 提取包含注释的类内容
        class_content_with_comments = content[comment_start:class_end]
        
        return class_content_with_comments
    
    def _find_class_comment_start(self, content: str, class_start: int) -> int:
        """查找类定义之前的注释开始位置"""
        # 从类定义开始位置向前查找
        pos = class_start - 1
        
        # 跳过空白字符
        while pos >= 0 and content[pos].isspace():
            pos -= 1
        
        # 检查是否有行注释 //
        line_comment_pos = pos
        while line_comment_pos >= 0:
            if content[line_comment_pos] == '\n':
                break
            line_comment_pos -= 1
        
        # 检查行注释
        if line_comment_pos >= 0:
            line_start = line_comment_pos + 1
            line_content = content[line_start:pos + 1].strip()
            if line_content.startswith('//'):
                # 继续向前查找更多行注释
                while line_comment_pos >= 0:
                    prev_line_end = line_comment_pos
                    line_comment_pos -= 1
                    while line_comment_pos >= 0 and content[line_comment_pos] != '\n':
                        line_comment_pos -= 1
                    
                    if line_comment_pos >= 0:
                        line_start = line_comment_pos + 1
                        line_content = content[line_start:prev_line_end].strip()
                        if line_content.startswith('//'):
                            pos = line_start
                        else:
                            break
                    else:
                        break
        
        # 检查是否有块注释 /* */
        block_comment_start = self._find_block_comment_start(content, pos)
        if block_comment_start >= 0:
            pos = block_comment_start
        
        return pos
    
    def _find_block_comment_start(self, content: str, end_pos: int) -> int:
        """查找块注释的开始位置"""
        # 从指定位置向前查找 /* */ 或 /** */
        pos = end_pos
        while pos >= 1:
            if content[pos] == '/' and content[pos - 1] == '*':
                # 找到 */ 结束标记，继续向前查找 /* 或 /** 开始标记
                pos -= 2
                while pos >= 1:
                    if content[pos] == '*' and content[pos - 1] == '/':
                        # 检查是否是 /** 格式（Javadoc注释）
                        if pos >= 2 and content[pos - 2] == '*':
                            return pos - 2  # 返回 /** 的开始位置
                        else:
                            return pos - 1  # 返回 /* 的开始位置
                    pos -= 1
                break
            pos -= 1
        
        return -1
    
    def _extract_class_content(self, content: str, class_start: int) -> str:
        """提取类的完整内容"""
        brace_count = 0
        start_brace = False
        class_content = ""
        
        for i in range(class_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    class_content = content[class_start:i+1]
                    break
        
        return class_content
    
    def _extract_fields(self, class_content: str) -> List[str]:
        """提取类中的字段定义"""
        fields = []
        
        # 找到所有字段定义
        field_matches = self._field_pattern.finditer(class_content)
        for match in field_matches:
            field_line = match.group(0)
            # 确保这是字段而不是方法参数或局部变量
            if self._is_field_definition(field_line, class_content, match.start()):
                fields.append(field_line)
        
        return fields



    def _extract_methods(self, class_content: str) -> List[str]:
        """提取类中的方法定义"""
        methods = []
        
        # 使用预编译的正则表达式匹配所有方法定义（包括带注解和不带注解的）
        method_matches = self._method_pattern.finditer(class_content)
        
        for match in method_matches:
            method_start = match.start()
            method_content = self._extract_method_content_optimized(class_content, method_start)
            if method_content:
                methods.append(method_content)
        
        return methods
    
    def _extract_method_content_optimized(self, content: str, method_start: int) -> str:
        """提取方法的完整内容（包括前面的注解）- 优化版本"""
        # 找到方法体的结束位置
        brace_count = 0
        start_brace = False
        method_end = method_start
        
        for i in range(method_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    method_end = i + 1
                    break
        
        # 向前查找注解开始位置 - 使用优化的算法
        annotation_start = self._find_annotation_start_optimized(content, method_start)
        
        return content[annotation_start:method_end]
    
    def _find_method_annotation_start(self, content: str, method_start: int) -> int:
        """查找方法定义之前的注解开始位置"""
        # 从方法定义开始位置向前查找
        pos = method_start - 1
        
        # 跳过空白字符
        while pos >= 0 and content[pos].isspace():
            pos -= 1
        
        # 检查是否有行注释 //
        line_comment_pos = pos
        while line_comment_pos >= 0:
            if content[line_comment_pos] == '\n':
                break
            line_comment_pos -= 1
        
        # 检查行注释
        if line_comment_pos >= 0:
            line_start = line_comment_pos + 1
            line_content = content[line_start:pos + 1].strip()
            if line_content.startswith('//'):
                # 继续向前查找更多行注释
                while line_comment_pos >= 0:
                    prev_line_end = line_comment_pos
                    line_comment_pos -= 1
                    while line_comment_pos >= 0 and content[line_comment_pos] != '\n':
                        line_comment_pos -= 1
                    
                    if line_comment_pos >= 0:
                        line_start = line_comment_pos + 1
                        line_content = content[line_start:prev_line_end].strip()
                        if line_content.startswith('//'):
                            pos = line_start
                        else:
                            break
                    else:
                        break
        
        # 检查是否有块注释 /* */
        block_comment_start = self._find_block_comment_start(content, pos)
        if block_comment_start >= 0:
            pos = block_comment_start
        
        # 检查是否有注解 @Annotation
        annotation_start = self._find_annotation_start(content, pos)
        if annotation_start >= 0:
            pos = annotation_start
        
        return pos + 1
    
    def _find_annotation_start_optimized(self, content: str, method_start: int) -> int:
        """查找注解的开始位置 - 优化版本"""
        # 从方法开始位置向前查找，最多查找200个字符
        search_start = max(0, method_start - 200)
        search_content = content[search_start:method_start]
        
        # 使用预编译的正则表达式查找所有注解
        annotations = list(self._annotation_pattern.finditer(search_content))
        
        if not annotations:
            return method_start
        
        # 返回最后一个注解的开始位置
        last_annotation = annotations[-1]
        return search_start + last_annotation.start()
    
    def _find_annotation_start(self, content: str, end_pos: int) -> int:
        """查找注解的开始位置 - 优化版本"""
        # 限制搜索范围，避免在大型文件中搜索过远
        search_start = max(0, end_pos - 500)
        search_content = content[search_start:end_pos]
        
        # 使用 rfind 快速找到最后一个 @ 符号的位置
        last_at_pos = search_content.rfind('@')
        if last_at_pos == -1:
            return end_pos
        
        # 计算在原始内容中的位置
        actual_pos = search_start + last_at_pos
        
        # 验证这是一个有效的注解（简单检查）
        # 从 @ 位置开始，查找注解的结束位置
        annotation_end = actual_pos + 1
        while (annotation_end < len(content) and 
               annotation_end < actual_pos + 100 and  # 限制注解长度
               not content[annotation_end].isspace() and 
               content[annotation_end] not in ';{'):
            annotation_end += 1
        
        # 检查注解是否有效（包含字母数字字符）
        annotation_text = content[actual_pos:annotation_end]
        if self._annotation_valid_pattern.match(annotation_text):
            return actual_pos
        
        return end_pos
    

    
    
    def _extract_method_signature(self, method_code: str) -> str:
        """从方法代码中提取完整的方法签名（移除返回类型和参数名，只保留方法名和参数类型）"""
        # 匹配方法签名的开始部分（返回类型 + 方法名 + 参数列表）
        match = self._method_signature_pattern.search(method_code)
        if match:
            signature = match.group(1).strip()
            # 移除参数名，保留参数类型
            signature = self._remove_parameter_names(signature)
            # 移除返回类型，只保留方法名和参数类型
            return_type_match = self._method_return_type_pattern.search(signature)
            signature = return_type_match.group(1).strip() if return_type_match else signature
            return signature
        return ""
    

    
    def _remove_parameter_names(self, signature: str) -> str:
        """移除方法签名中的参数名，保留参数类型"""
        # 匹配参数列表部分
        match = self._param_pattern.search(signature)
        if not match:
            return signature
        
        params_str = match.group(1)
        if not params_str.strip():
            return signature
        
        # 分割参数
        params = [p.strip() for p in params_str.split(',')]
        new_params = []
        
        for param in params:
            if param.strip():
                # 匹配参数类型和名称：type name 或 type... name
                param_match = self._param_type_name_pattern.match(param)
                if param_match:
                    param_type = param_match.group(1)
                    new_params.append(param_type)
                else:
                    # 如果没有匹配到，保留原参数（可能是泛型或其他复杂情况）
                    new_params.append(param)
        
        # 重建签名
        new_params_str = ', '.join(new_params)
        new_signature = self._param_pattern.sub(f'({new_params_str})', signature)
        return new_signature
    

    

    def _is_field_definition(self, field_line: str, class_content: str, field_start: int) -> bool:
        """判断是否为字段定义（而不是方法参数或局部变量）"""
        # 检查是否在方法内部
        before_content = class_content[:field_start]
        
        # 计算大括号数量，判断是否在方法内部
        brace_count = 0
        for char in before_content:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
        
        # 如果大括号数量为1，说明在类级别，是字段定义
        return brace_count == 1
    


    
    def _analyze_method_field_usage(self, method_code: str, field_names: List[str]) -> List[str]:
        """分析方法中使用的字段"""
        used_fields = []
        
        for field_name in field_names:
            # 提取字段的简单名称（去掉类名前缀）
            simple_field_name = field_name.split('.')[-1]
            
            # 检查方法中是否使用了这个字段
            # 匹配 this.fieldName 或直接 fieldName
            field_usage_pattern = rf'\b(?:this\.)?{re.escape(simple_field_name)}\b'
            if re.search(field_usage_pattern, method_code):
                used_fields.append(field_name)
        
        return used_fields
    
    def _analyze_method_method_usage(self, method_code: str, all_methods: Dict[str, MethodSignature]) -> List[str]:
        """分析方法中调用的其他方法"""
        used_methods = []
        
        # 查找所有方法调用
        method_calls = self._method_call_pattern.findall(method_code)
        
        # 处理对象方法调用
        for obj_name, method_name in method_calls:
            # 排除Java关键字和系统类
            java_keywords = {'if', 'for', 'while', 'switch', 'return', 'new', 'super', 'this', 'System', 'List', 'Optional', 'out', 'isPresent', 'get'}
            if method_name in java_keywords:
                continue
                
            # 查找匹配的方法签名
            for method_sig_name, method_sig in all_methods.items():
                # 提取方法名（现在格式是：methodName(type1, type2)）
                method_part = method_sig_name.split('.')[-1]
                # 匹配方法名：methodName(type1, type2) -> methodName
                method_name_match = self._method_name_pattern.search(method_part)
                if method_name_match:
                    sig_method_name = method_name_match.group(1)
                else:
                    sig_method_name = method_part.split('(')[0]
                
                # 检查方法名是否匹配
                if sig_method_name == method_name:
                    used_methods.append(method_sig_name)
        
        return list(set(used_methods))  # 去重
    
def analyze_java_project(project_path: str) -> Tuple[Dict[str, ClassSignature], 
                                                    Dict[str, MethodSignature], 
                                                    Dict[str, FieldSignature]]:
    """
    分析Java项目的便捷函数
    
    Args:
        project_path: Java项目根目录路径
        
    Returns:
        Tuple包含三个字典：
        - class_signatures: key为class_signature_name, value为ClassSignature
        - method_signatures: key为method_signature_name, value为MethodSignature  
        - field_signatures: key为field_signature_name, value为FieldSignature
    """
    analyzer = JavaProjectAnalyzer()
    return analyzer.analyze_project(project_path)


def save_and_analysis_to_json(project_path: str, output_file: str = "1_analyze_project.json"):
    """
    分析Java项目并保存结果到JSON文件
    
    Args:
        project_path: Java项目根目录路径
        output_file: 输出JSON文件路径，默认为"1_analyze_project.json"
        
    Returns:
        Dict: 包含分析结果的字典
    """
    class_sigs, method_sigs, field_sigs = analyze_java_project(project_path)
    
    # 将分析结果合并为一个字典
    analysis_result = {
        "class_signatures": {name: asdict(sig) for name, sig in class_sigs.items()},
        "method_signatures": {name: asdict(sig) for name, sig in method_sigs.items()},
        "field_signatures": {name: asdict(sig) for name, sig in field_sigs.items()}
    }
    
    # 写入JSON文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"分析结果已保存到 {output_file}")
    logger.info(f"类数量: {len(class_sigs)}, 方法数量: {len(method_sigs)}, 字段数量: {len(field_sigs)}")
    
    return analysis_result


def analyze_java_project_static(project_info: dict, workspace_path: str = None) -> Optional[str]:
    """
    分析Java项目（静态方法）
    
    Args:
        project_info: 项目信息
        workspace_path: 工作空间路径
        
    Returns:
        分析结果文件路径，失败时返回None
    """
    try:
        project_path = project_info['path']
        project_name = project_info['name']
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, "1_analyze_project.json")
        
        # 检查项目路径是否存在
        if not os.path.exists(project_path):
            logger.warn(f"项目路径不存在，跳过Java项目分析: {project_path}")
            return None

        start_time = time.time()
        logger.info(f"开始分析Java项目: {project_path}")
        
        # 使用java_project_analyzer分析项目
        analysis_result = save_and_analysis_to_json(project_path, output_file)
        
        analysis_duration = time.time() - start_time
        logger.info(f"Java项目分析完成，耗时: {analysis_duration:.2f}秒")
        logger.info(f"结果保存到: {output_file}")
        logger.info(f"分析统计 - 类数量: {len(analysis_result.get('class_signatures', {}))}")
        logger.info(f"分析统计 - 方法数量: {len(analysis_result.get('method_signatures', {}))}")
        logger.info(f"分析统计 - 字段数量: {len(analysis_result.get('field_signatures', {}))}")
        
        return output_file

    except Exception as e:
        logger.error(f"Java项目分析过程中发生错误: {str(e)}")
        return None


