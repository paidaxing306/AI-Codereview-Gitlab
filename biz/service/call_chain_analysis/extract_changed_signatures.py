"""
变更方法签名提取模块
负责从代码变更中提取方法签名信息
"""

import os
import re
from typing import Dict, List, Tuple
from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil
from biz.utils.code_parser import GitDiffParser
from biz.service.call_chain_analysis.java_project_analyzer import JavaProjectAnalyzer



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

    def extract_changed_method_signatures(self, changes: list, project_name: str = None) -> str:
        """
        提取变更的方法签名
        
        Args:
            changes: 代码变更列表
            project_name: 项目名称，用于生成临时文件路径
            
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
                
                # 先过滤diff_content
                filtered_diff_content = self._filter_diff_content(diff_content)
                
                # 解析diff获取变更前后的代码
                old_code, new_code = self._parse_diff_content(filtered_diff_content)
                
                # 如果new_code为空则跳过
                if not new_code or not new_code.strip():
                    logger.info(f"Change {i} 的new_code为空，跳过处理")
                    continue

                # 解析当前变更的方法签名
                method_signatures = self._extract_method_signatures_from_code(new_code, file_path)
                
                if method_signatures:
                    changed_method_signatures_map[i] = {
                        'method_signatures': method_signatures,
                        'old_code': old_code,
                        'new_code': new_code,
                        'file_path': file_path,
                        'diffs_text': filtered_diff_content
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

    def _filter_diff_content(self, diff_content: str) -> str:
        """
        过滤diff内容，移除package、import行和空行
        
        Args:
            diff_content: 原始diff内容
            
        Returns:
            过滤后的diff内容
        """
        if not diff_content:
            return diff_content
            
        lines = diff_content.split('\n')
        filtered_lines = []
        
        for line in lines:
            # 跳过空行
            if not line.strip():
                continue
            # 跳过以+package、-package、+import、-import开头的行
            if (line.startswith('+import') or line.startswith('-import')):
                continue
            if line.startswith('@@') and  line.startswith('@@'):
                continue
            # 跳过strip后以+、-开头的行
            stripped_line = line.strip()
            if stripped_line == '+' or stripped_line == '-':
                continue
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def _extract_method_signatures_from_code(self, code: str, file_path: str) -> List[str]:
        """从代码中提取方法签名"""
        if not code or not file_path.endswith('.java'):
            return []
        
        try:
            java_analyzer = JavaProjectAnalyzer()
            formatted_code = java_analyzer.format_java_code(code)
            
            # 提取包名
            package_match = re.search(r'package\s+([\w.]+);', formatted_code)
            package_name = package_match.group(1) if package_match else ""
            
            # 查找类定义
            class_pattern = r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{'
            class_matches = re.finditer(class_pattern, formatted_code)
            
            method_signatures = []
            for class_match in class_matches:
                class_name = class_match.group(1)
                class_signature_name = f"{package_name}.{class_name}" if package_name else class_name
                
                # 提取类内容和方法
                class_start = class_match.start()
                class_content = java_analyzer._extract_class_content(formatted_code, class_start)
                extracted_methods = java_analyzer._extract_methods(class_content)
                
                # 提取方法签名
                for method_content in extracted_methods:
                    method_signature = java_analyzer._extract_method_signature(method_content)
                    if method_signature:
                        method_signature_name = f"{class_signature_name}.{method_signature}"
                        method_signatures.append(method_signature_name)
            
            return method_signatures
            
        except Exception as e:
            logger.error(f"提取方法签名时发生错误: {str(e)}")
            return []

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

 
def extract_changed_method_signatures_static(changes: list, project_name: str = None, workspace_path: str = None) -> str:
    """
    提取变更的方法签名（静态方法）
    
    Args:
        changes: 代码变更列表
        project_name: 项目名称，用于生成临时文件路径
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径，包含变更方法签名数据
    """
    try:
        # 创建 ChangedSignatureExtractor 实例
        extractor = ChangedSignatureExtractor(workspace_path)
        
        # 调用实例方法
        return extractor.extract_changed_method_signatures(changes, project_name)
        
    except Exception as e:
        logger.error(f"提取变更方法签名过程中发生错误: {str(e)}")
        return ""

 