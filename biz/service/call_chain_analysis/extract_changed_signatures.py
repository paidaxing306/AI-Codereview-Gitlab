"""
变更方法签名提取模块
负责从代码变更中提取方法签名信息
"""

import os
import re
from typing import Dict, List, Tuple

from biz.service.call_chain_analysis.file_util import FileUtil
from biz.service.call_chain_analysis.java_project_analyzer import JavaProjectAnalyzer
from biz.utils.code_parser import GitDiffParser
from biz.utils.log import logger


class ChangedSignatureExtractor:
    """
    变更方法签名提取器
    负责从代码变更中提取方法签名信息
    """

    def __init__(self, workspace_path: str = None):
        """
        初始化变更方法签名提取器
        
        Args:
            workspace_path: 工作空间路径，默认为当前目录下的workspace
        """
        self.workspace_path = workspace_path or os.path.join(os.getcwd(), 'workspace')

    def extract_changed_method_signatures(self, changes: list, project_name: str = None, analysis_result_file: str = None) -> str:
        """
        提取变更的方法签名
        
        Args:
            changes: 代码变更列表
            project_name: 项目名称，用于生成临时文件路径
            analysis_result_file: 项目分析结果文件路径
            
        Returns:
            临时文件路径，包含变更方法签名数据
        """
        changed_method_signatures_map = {}
        
        try:
            logger.info("=== 开始解析Git diff获取变更前后的代码 ===")
            
            for i, change in enumerate(changes):
                if not self._is_java_change(change):
                    continue
                
                diff_content = change.get('diff', '')
                file_path = change.get('new_path', '')
                
                logger.info(f"解析第 {i+1} 个Java文件变更: {file_path}")
                

                # 解析diff获取变更前后的代码
                old_code, new_code = self._parse_diff_content(diff_content)
                
                # 如果new_code为空则跳过
                if not new_code or not new_code.strip():
                    logger.info(f"Change {i} 的new_code为空，跳过处理")
                    continue

                # 解析当前变更的方法签名
                method_signatures = self._extract_method_signatures_from_code(new_code, file_path, analysis_result_file)
                
                if method_signatures:
                    changed_method_signatures_map[i] = {
                        'method_signatures': method_signatures,
                        'old_code': old_code,
                        'new_code': new_code,
                        'file_path': file_path,
                        'diffs_text': diff_content
                    }
                    logger.info(f"Change {i} 的方法签名: {method_signatures}")
                else:
                    logger.info(f"Change {i} 未解析到方法签名")

            if changed_method_signatures_map:
                logger.info(f"成功解析出 {len(changed_method_signatures_map)} 个变更的方法签名")
                logger.info(f"变更的方法签名Map: {changed_method_signatures_map}")
                
                # 将数据写入临时文件
                output_file = self._save_changed_methods_to_file(changed_method_signatures_map, project_name)
                logger.info(f"变更方法签名数据已保存到: {output_file}")
                return output_file
            else:
                logger.info("未发现变更的方法签名")
                return ""
                
        except Exception as e:
            logger.error(f"解析变更方法签名过程中发生错误: {str(e)}")
            return ""

    def _is_java_change(self, change: dict) -> bool:
        """检查是否为Java文件变更"""
        return (isinstance(change, dict) and 
                change.get('diff') and 
                change.get('new_path', '').endswith('.java'))

    def _parse_diff_content(self, diff_content: str) -> Tuple[str, str]:
        """解析diff内容获取变更前后的代码"""
        diff_parser = GitDiffParser(diff_content)
        diff_parser.parse_diff()
        return diff_parser.get_old_code(), diff_parser.get_new_code()



    def _extract_method_signatures_from_code(self, code: str, file_path: str, analysis_result_file: str = None) -> List[str]:
        """从代码片段中提取方法签名，通过查找包含该代码片段的完整方法"""
        if not code or not file_path.endswith('.java'):
            return []

        try:
            # 1. 根据 file_path 找出对应的文件
            actual_file_path = self._find_actual_file_path(file_path)
            if not actual_file_path:
                logger.warn(f"无法找到文件: {file_path}")
                return []
            
            # 2. 从分析结果文件中找出对应的类签名
            analysis_data = FileUtil.load_analysis_result_from_file(analysis_result_file)
            
            if not analysis_data:
                logger.warn(f"无法加载分析结果文件: {analysis_result_file}")
                return []
            
            # 3. 根据文件路径找到对应的类签名
            class_signature_name = self._find_class_signature_by_file_path(actual_file_path, analysis_data)
            if not class_signature_name:
                logger.warn(f"无法找到文件 {file_path} 对应的类签名")
                return []
            
            logger.info(f"找到类签名: {class_signature_name}")
            
            # 4. 根据类签名找出对应的方法签名
            method_signatures = self._find_method_signatures_by_class(class_signature_name, analysis_data)
            if not method_signatures:
                logger.warn(f"类 {class_signature_name} 中没有找到方法签名")
                return []
            
            # 5. 从代码片段中直接提取方法签名，而不是依赖_contains_code_snippet
            matched_method_signatures = self._extract_method_signatures_from_code_snippet(code, class_signature_name)
            
            return matched_method_signatures
            
        except Exception as e:
            logger.error(f"提取方法签名时发生错误: {str(e)}")
            return []

    def _extract_method_signatures_from_code_snippet(self, code: str, class_signature_name: str) -> List[str]:
        """
        直接复用 JavaProjectAnalyzer 的方法提取签名
        """
        if not code or not class_signature_name:
            return []
        analyzer = JavaProjectAnalyzer()
        results = []
        for m in analyzer._method_pattern.finditer(code):
            method_code = analyzer._extract_method_content_optimized(code, m.start())
            sig = analyzer._extract_method_signature(method_code)
            if sig:
                results.append(f"{class_signature_name}.{sig}")
        return results

    def _extract_method_content_from_snippet(self, code: str, method_start: int) -> str:
        """
        从代码片段中提取方法的完整内容（包括注解）
        
        Args:
            code: 代码片段
            method_start: 方法开始位置
            
        Returns:
            方法的完整内容
        """
        if method_start >= len(code):
            return ""
        
        # 找到方法体的结束位置
        brace_count = 0
        start_brace = False
        method_end = method_start
        
        for i in range(method_start, len(code)):
            char = code[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    method_end = i + 1
                    break
        
        # 向前查找注解开始位置
        annotation_start = self._find_annotation_start_in_snippet(code, method_start)
        
        return code[annotation_start:method_end]

    def _find_annotation_start_in_snippet(self, code: str, method_start: int) -> int:
        """
        在代码片段中查找注解的开始位置
        
        Args:
            code: 代码片段
            method_start: 方法开始位置
            
        Returns:
            注解开始位置
        """
        # 从方法开始位置向前查找，最多查找200个字符
        search_start = max(0, method_start - 200)
        search_content = code[search_start:method_start]
        
        # 查找所有注解
        annotation_pattern = re.compile(r'@\w+(?:\s*\([^)]*\))?')
        annotations = list(annotation_pattern.finditer(search_content))
        
        if not annotations:
            return method_start
        
        # 返回最后一个注解的开始位置
        last_annotation = annotations[-1]
        return search_start + last_annotation.start()

    def _extract_method_signature_from_snippet(self, method_code: str, method_signature_pattern, 
                                             method_return_type_pattern, param_pattern, param_type_name_pattern) -> str:
        """
        从方法代码中提取方法签名（移除返回类型和参数名，只保留方法名和参数类型）
        
        Args:
            method_code: 方法代码
            method_signature_pattern: 方法签名模式
            method_return_type_pattern: 方法返回类型模式
            param_pattern: 参数模式
            param_type_name_pattern: 参数类型名称模式
            
        Returns:
            方法签名
        """
        # 匹配方法签名的开始部分（返回类型 + 方法名 + 参数列表）
        match = method_signature_pattern.search(method_code)
        if match:
            signature = match.group(1).strip()
            # 移除参数名，保留参数类型
            signature = self._remove_parameter_names_from_snippet(signature, param_pattern, param_type_name_pattern)
            # 移除返回类型，只保留方法名和参数类型
            return_type_match = method_return_type_pattern.search(signature)
            signature = return_type_match.group(1).strip() if return_type_match else signature
            return signature
        return ""

    def _remove_parameter_names_from_snippet(self, signature: str, param_pattern, param_type_name_pattern) -> str:
        """
        移除方法签名中的参数名，保留参数类型
        
        Args:
            signature: 方法签名
            param_pattern: 参数模式
            param_type_name_pattern: 参数类型名称模式
            
        Returns:
            处理后的方法签名
        """
        # 匹配参数列表部分
        match = param_pattern.search(signature)
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
                param_match = param_type_name_pattern.match(param)
                if param_match:
                    param_type = param_match.group(1)
                    new_params.append(param_type)
                else:
                    # 如果没有匹配到，保留原参数（可能是泛型或其他复杂情况）
                    new_params.append(param)
        
        # 重建签名
        new_params_str = ', '.join(new_params)
        new_signature = param_pattern.sub(f'({new_params_str})', signature)
        return new_signature

    def _find_class_signature_by_file_path(self, file_path: str, analysis_data: dict) -> str:
        """
        根据文件路径找到对应的类签名
        
        Args:
            file_path: 文件路径
            analysis_data: 分析结果数据
            
        Returns:
            类签名，如果找不到则返回空字符串
            
        author  lichaojie
        """
        try:
            # 计算相对于工作空间的路径
            if os.path.isabs(file_path):
                try:
                    relative_path = os.path.relpath(file_path, self.workspace_path)
                except ValueError:
                    # 如果文件不在工作空间内，使用文件名
                    relative_path = os.path.basename(file_path)
            else:
                relative_path = file_path
            
            # 标准化路径，统一使用正斜杠格式（Python支持跨平台）
            relative_path = os.path.normpath(relative_path).replace(os.sep, '/')
            
            logger.info(f"查找类签名，相对路径: {relative_path}")
            
            # 在 class_signatures 中查找匹配的类
            class_signatures = analysis_data.get('class_signatures', {})
            
            for class_signature_name, class_data in class_signatures.items():
                class_path = class_data.get('class_path', '')
                if class_path:
                    # 标准化类路径，统一使用正斜杠格式
                    normalized_class_path = os.path.normpath(class_path).replace(os.sep, '/')
                    
                    # 直接比较标准化后的路径
                    if normalized_class_path == relative_path:
                        logger.info(f"找到匹配的类路径: {normalized_class_path}")
                        return class_signature_name
                    # 也尝试匹配文件名
                    elif os.path.basename(normalized_class_path) == os.path.basename(relative_path):
                        logger.info(f"通过文件名找到匹配的类: {class_signature_name}")
                        return class_signature_name
            
            logger.warn(f"未找到匹配的类签名，相对路径: {relative_path}")
            return ""
            
        except Exception as e:
            logger.error(f"查找类签名时发生错误: {str(e)}")
            return ""

    def _find_method_signatures_by_class(self, class_signature_name: str, analysis_data: dict) -> List[str]:
        """
        根据类签名找出对应的方法签名列表
        
        Args:
            class_signature_name: 类签名
            analysis_data: 分析结果数据
            
        Returns:
            方法签名列表
        """

        all_method_signatures = analysis_data.get('class_signatures', {})
        classes=all_method_signatures.get(class_signature_name,{})
        methods = classes.get('method_signature_name', [])
        return methods

    def _clean_code_snippet(self, code: str) -> str:
        """
        清理代码片段，移除空白字符、注释等，便于比较
        
        Args:
            code: 原始代码
            
        Returns:
            清理后的代码
        """
        if not code:
            return ""
        
        # 移除注释
        # 移除单行注释 //
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        
        # 移除多行注释 /* */
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # 移除注解
        code = re.sub(r'@\w+(?:\s*\([^)]*\))?', '', code)
        
        # 移除字符串字面量中的内容（避免字符串中的代码影响匹配）
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'[^']*'", "''", code)
        
        # 移除多余的空白字符（包括换行符、制表符等）
        code = re.sub(r'\s+', ' ', code)
        
        # 移除首尾空白
        code = code.strip()
        
        # 移除分号后的空白
        code = re.sub(r';\s*', ';', code)
        
        # 移除括号前后的空白
        code = re.sub(r'\s*\(\s*', '(', code)
        code = re.sub(r'\s*\)\s*', ')', code)
        
        # 移除大括号前后的空白
        code = re.sub(r'\s*\{\s*', '{', code)
        code = re.sub(r'\s*\}\s*', '}', code)
        
        # 移除逗号后的空白
        code = re.sub(r',\s*', ',', code)
        
        # 移除点号前后的空白
        code = re.sub(r'\s*\.\s*', '.', code)
        
        return code

    def _split_code_statements(self, code: str) -> List[str]:
        """
        将代码按语句分割
        
        Args:
            code: 清理后的代码
            
        Returns:
            语句列表
        """
        if not code:
            return []
        
        # 按分号分割语句
        statements = [stmt.strip() for stmt in code.split(';') if stmt.strip()]
        
        # 过滤掉太短的语句
        statements = [stmt for stmt in statements if len(stmt) > 5]
        
        return statements

    def _extract_identifiers(self, code: str) -> List[str]:
        """
        从代码中提取标识符（方法名、变量名等）
        
        Args:
            code: 清理后的代码
            
        Returns:
            标识符列表
        """
        if not code:
            return []
        
        # 提取Java标识符（字母、数字、下划线组成，以字母或下划线开头）
        identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', code)
        
        # 过滤掉Java关键字和常见系统方法
        java_keywords = {
            'if', 'for', 'while', 'switch', 'return', 'new', 'super', 'this', 'System', 'List', 'Optional', 'out', 'isPresent', 'get',
            'set', 'add', 'remove', 'contains', 'size', 'isEmpty', 'clear', 'iterator', 'toString', 'equals', 'hashCode',
            'clone', 'finalize', 'wait', 'notify', 'notifyAll', 'getClass', 'print', 'println', 'printf', 'format',
            'parse', 'valueOf', 'substring', 'length', 'charAt', 'indexOf', 'lastIndexOf', 'replace', 'split',
            'trim', 'toLowerCase', 'toUpperCase', 'startsWith', 'endsWith', 'contains', 'matches', 'replaceAll',
            'append', 'insert', 'delete', 'reverse', 'capacity', 'ensureCapacity', 'setLength', 'charAt',
            'put', 'get', 'remove', 'containsKey', 'containsValue', 'keySet', 'values', 'entrySet', 'clear',
            'add', 'offer', 'poll', 'peek', 'element', 'remove', 'contains', 'size', 'isEmpty', 'clear',
            'push', 'pop', 'peek', 'empty', 'search', 'capacity', 'trimToSize', 'ensureCapacity',
            'public', 'private', 'protected', 'static', 'final', 'abstract', 'class', 'interface', 'extends', 'implements',
            'void', 'int', 'long', 'double', 'float', 'boolean', 'char', 'byte', 'short', 'String', 'Object'
        }
        
        # 过滤掉关键字和太短的标识符
        filtered_identifiers = []
        for ident in identifiers:
            if (ident not in java_keywords and 
                len(ident) > 2 and 
                ident not in filtered_identifiers):
                filtered_identifiers.append(ident)
        
        return filtered_identifiers

    def _contains_code_snippet(self, method_content: str, code_snippet: str) -> bool:
        """
        检查方法内容是否包含代码片段
        
        Args:
            method_content: 完整的方法内容
            code_snippet: 要查找的代码片段
            
        Returns:
            是否包含代码片段
        """
        if not method_content or not code_snippet:
            return False
        
        # 如果代码片段太短，可能误匹配，设置最小长度
        if len(code_snippet) < 10:
            return False
        
        # 对方法内容和代码片段都进行相同的标准化处理
        cleaned_method_content = self._clean_code_snippet(method_content)
        cleaned_code_snippet = self._clean_code_snippet(code_snippet)
        
        # 如果清理后的方法内容太短，可能不是有效的方法
        if len(cleaned_method_content) < 20:
            return False
        
        # 如果清理后的代码片段太短，可能误匹配
        if len(cleaned_code_snippet) < 10:
            return False
        
        # 检查清理后的代码片段是否包含在清理后的方法内容中
        is_contained = cleaned_code_snippet in cleaned_method_content
        
        # 如果精确匹配失败，尝试多种匹配策略
        if not is_contained:
            # 策略1：按语句分割，尝试匹配部分语句
            if len(cleaned_code_snippet) > 20:
                statements = self._split_code_statements(cleaned_code_snippet)
                for statement in statements:
                    if len(statement) > 10 and statement in cleaned_method_content:
                        is_contained = True
                        logger.debug(f"通过部分语句匹配成功: '{statement}'")
                        break
            
            # 策略2：移除所有空白字符后比较
            if not is_contained:
                no_space_code = re.sub(r'\s+', '', cleaned_code_snippet)
                no_space_method = re.sub(r'\s+', '', cleaned_method_content)
                if len(no_space_code) > 10 and no_space_code in no_space_method:
                    is_contained = True
                    logger.debug(f"通过无空白字符匹配成功: '{no_space_code}'")
            
            # 策略3：提取关键标识符进行匹配
            if not is_contained:
                code_identifiers = self._extract_identifiers(cleaned_code_snippet)
                method_identifiers = self._extract_identifiers(cleaned_method_content)
                if code_identifiers and len(code_identifiers) >= 2:
                    # 检查是否大部分标识符都匹配
                    matched_count = sum(1 for ident in code_identifiers if ident in method_identifiers)
                    if matched_count >= min(3, len(code_identifiers)):
                        is_contained = True
                        logger.debug(f"通过标识符匹配成功: {code_identifiers}")
        
        # 添加调试日志
        if not is_contained:
            logger.debug(f"代码片段匹配失败:")
            logger.debug(f"清理后的代码片段: '{cleaned_code_snippet}'")
            logger.debug(f"清理后的方法内容长度: {len(cleaned_method_content)}")
            logger.debug(f"方法内容前100字符: '{cleaned_method_content[:100]}'")
        else:
            logger.debug(f"代码片段匹配成功: '{cleaned_code_snippet}'")
        
        return is_contained

    def _find_actual_file_path(self, file_path: str) -> str:
        """
        查找实际的文件路径
        
        Args:
            file_path: 相对路径或绝对路径
            
        Returns:
            实际的文件路径，如果找不到则返回空字符串
        """
        # 如果已经是绝对路径且存在，直接返回
        if os.path.isabs(file_path) and os.path.exists(file_path):
            return file_path
        
        # 尝试相对于工作空间路径
        workspace_file_path = os.path.join(self.workspace_path, file_path)
        if os.path.exists(workspace_file_path):
            return workspace_file_path
        
        # 尝试相对于当前工作目录
        current_dir_file_path = os.path.join(os.getcwd(), file_path)
        if os.path.exists(current_dir_file_path):
            return current_dir_file_path
        
        # 尝试在workspace目录下递归查找
        for root, dirs, files in os.walk(self.workspace_path):
            for file in files:
                if file == os.path.basename(file_path):
                    full_path = os.path.join(root, file)
                    # 检查路径是否匹配（统一使用正斜杠进行比较）
                    normalized_file_path = file_path.replace('\\', '/').replace(os.sep, '/')
                    normalized_full_path = full_path.replace('\\', '/').replace(os.sep, '/')
                    if normalized_file_path in normalized_full_path:
                        return full_path
        
        return ""

    def _save_changed_methods_to_file(self, changed_methods: Dict[int, Dict], project_name: str = None) -> str:
        """
        将变更方法数据保存到临时文件
        
        Args:
            changed_methods: 变更方法数据
            project_name: 项目名称
            
        Returns:
            临时文件路径
        """
        try:
            output_file = FileUtil.get_project_file_path(self.workspace_path, project_name, "2_changed_methods.json")
            
            if FileUtil.save_json_to_file(changed_methods, output_file):
                return output_file
            else:
                return ""
            
        except Exception as e:
            logger.error(f"保存变更方法数据到文件时发生错误: {str(e)}")
            return ""

 
def extract_changed_method_signatures_static(changes: list, project_name: str = None, workspace_path: str = None, analysis_result_file: str = None) -> str:
    """
    提取变更的方法签名（静态方法）
    
    Args:
        changes: 代码变更列表
        project_name: 项目名称，用于生成临时文件路径
        workspace_path: 工作空间路径
        analysis_result_file: 项目分析结果文件路径
        
    Returns:
        临时文件路径，包含变更方法签名数据
    """
    try:
        # 创建 ChangedSignatureExtractor 实例
        extractor = ChangedSignatureExtractor(workspace_path)
        
        # 调用实例方法
        return extractor.extract_changed_method_signatures(changes, project_name, analysis_result_file)
        
    except Exception as e:
        logger.error(f"提取变更方法签名过程中发生错误: {str(e)}")
        return ""

 