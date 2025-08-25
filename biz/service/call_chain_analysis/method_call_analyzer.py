import json
import os
from collections import deque
from typing import List, Dict

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil


class MethodCallAnalyzer:
    def __init__(self, json_file_path: str = "1_analyze_project.json"):
        """
        初始化方法调用分析器
        
        Args:
            json_file_path: 分析结果JSON文件路径
            skip_paths: 要跳过的路径，用逗号分隔，例如："xxx\\src\\main\\java\\com\\xxx\\xx\\dal\\dto"
                       如果为None，则从环境变量CODE_CALL_CHAIN_RELATED_METHOD_SKIP_PATH读取
        """

        self.json_file_path = json_file_path

        skip_paths = os.getenv("CODE_CALL_CHAIN_RELATED_METHOD_SKIP_PATH", "")
        
        self.skip_paths = []
        if skip_paths:
            self.skip_paths = [path.strip() for path in skip_paths.split(',')]
        
        self.analysis_data = self._load_analysis_data()
        self._build_caller_mapping()
    
    def _load_analysis_data(self) -> Dict:
        """加载分析数据"""
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"找不到文件: {self.json_file_path}")
        except json.JSONDecodeError:
            raise ValueError(f"JSON文件格式错误: {self.json_file_path}")
    
    def _build_caller_mapping(self):
        """
        构建方法调用者映射关系
        为每个方法找到调用它的方法列表
        """
        self.caller_mapping = {}
        
        # 遍历所有方法，构建调用者映射
        for method_signature, method_info in self.analysis_data["method_signatures"].items():
            # 获取该方法调用的其他方法
            called_methods = method_info.get("usage_method_signature_name", [])
            
            # 为每个被调用的方法记录调用者
            for called_method in called_methods:
                if called_method not in self.caller_mapping:
                    self.caller_mapping[called_method] = []
                self.caller_mapping[called_method].append(method_signature)
    
    def _is_method_in_skip_path(self, method_signature: str) -> bool:
        """
        检查方法是否在跳过的路径中
        
        Args:
            method_signature: 方法签名
            
        Returns:
            bool: 如果方法在跳过的路径中返回True，否则返回False
        """
        if not self.skip_paths:
            return False
        
        # 获取方法所属的类签名
        method_info = self.analysis_data["method_signatures"].get(method_signature)
        if not method_info:
            return False
        
        class_signature_name = method_info.get("class_signature_name")
        if not class_signature_name:
            return False
        
        # 获取类信息
        class_info = self.analysis_data["class_signatures"].get(class_signature_name)
        if not class_info:
            return False
        
        class_path = class_info.get("class_path", "")
        if not class_path:
            return False
        
        # 检查类路径是否在跳过的路径中
        for skip_path in self.skip_paths:
            if class_path.startswith(skip_path):
                return True
        
        return False
    
 
    
    def get_method_call_chain_by_depth(self, method_signature: str, max_depth: int = 3) -> Dict[int, List[str]]:
        """
        按深度分层获取方法调用链
        
        Args:
            method_signature: 方法签名
            max_depth: 最大调用深度
            
        Returns:
            Dict[int, List[str]]: 按深度分层的调用链，key为深度，value为该层的方法列表
        """
        if method_signature not in self.analysis_data["method_signatures"]:
            raise ValueError(f"方法签名不存在: {method_signature}")
        
        # 按深度分层的调用链
        call_chain_by_depth = {}
        visited = set()
        queue = deque([(method_signature, 0)])
        
        while queue:
            current_method, current_depth = queue.popleft()
            
            # 如果已经访问过或者超过最大深度，跳过
            if current_method in visited or current_depth > max_depth:
                continue
            
            # 如果方法在跳过的路径中，跳过
            if self._is_method_in_skip_path(current_method):
                continue
            
            # 标记为已访问
            visited.add(current_method)
            
            # 按深度分组
            if current_depth not in call_chain_by_depth:
                call_chain_by_depth[current_depth] = []
            call_chain_by_depth[current_depth].append(current_method)
            
            # 如果还没达到最大深度，继续查找下一层调用
            if current_depth < max_depth:
                used_methods = self.analysis_data["method_signatures"][current_method]["usage_method_signature_name"]
                for used_method in used_methods:
                    if used_method not in visited:
                        queue.append((used_method, current_depth + 1))
        
        return call_chain_by_depth
    
    def get_method_callers_by_height(self, method_signature: str, max_height: int = 3) -> Dict[int, List[str]]:
        """
        按高度分层获取方法被调用链
        
        Args:
            method_signature: 方法签名
            max_height: 最大调用高度
            
        Returns:
            Dict[int, List[str]]: 按高度分层的被调用链，key为高度，value为该层的方法列表
        """
        if method_signature not in self.analysis_data["method_signatures"]:
            raise ValueError(f"方法签名不存在: {method_signature}")
        
        # 按高度分层的被调用链
        caller_chain_by_height = {}
        visited = set()
        queue = deque([(method_signature, 0)])
        
        while queue:
            current_method, current_height = queue.popleft()
            
            # 如果已经访问过或者超过最大高度，跳过
            if current_method in visited or current_height > max_height:
                continue
            
            # 如果方法在跳过的路径中，跳过
            if self._is_method_in_skip_path(current_method):
                continue
            
            # 标记为已访问
            visited.add(current_method)
            
            # 按高度分组
            if current_height not in caller_chain_by_height:
                caller_chain_by_height[current_height] = []
            caller_chain_by_height[current_height].append(current_method)
            
            # 如果还没达到最大高度，继续查找上一层的调用者
            if current_height < max_height:
                callers = self.caller_mapping.get(current_method, [])
                for caller in callers:
                    if caller not in visited:
                        queue.append((caller, current_height + 1))
        
        return caller_chain_by_height
    
    def get_complete_method_relationship(self, method_signature: str, max_calls_out: int = 1, max_calls_in: int = 3) -> Dict:
        """
        获取方法的完整调用关系（调用的方法和被调用的方法）
        
        Args:
            method_signature: 方法签名
            max_calls_out: 最大调用出去的深度（该方法调用的其他方法）
            max_calls_in: 最大被调用进来的高度（调用该方法的方法）
            
        Returns:
            Dict: 包含调用方法和被调用方法的完整关系
        """
        if method_signature not in self.analysis_data["method_signatures"]:
            raise ValueError(f"方法签名不存在: {method_signature}")
        
        # 获取该方法调用的其他方法（向下调用链，按深度分层）
        called_methods = self.get_method_call_chain_by_depth(method_signature, max_calls_out)
        
        # 获取调用该方法的方法（向上调用链，按高度分层）
        caller_methods = self.get_method_callers_by_height(method_signature, max_calls_in)
        
        return {
            "calls_out": called_methods,  # 该方法调用的其他方法（向下调用链）
            "calls_in": caller_methods    # 调用该方法的方法（向上调用链）
        }
    
 
 
    
 
    



def analyze_method_calls_static(changed_methods_file: str, analysis_file: str, project_name: str = None, workspace_path: str = None) -> str:
    """
    分析方法调用关系（静态方法）
    
    Args:
        changed_methods_file: 变更方法数据文件路径
        analysis_file: 项目分析结果文件路径
        project_name: 项目名称，用于生成临时文件路径
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径，包含方法调用关系数据
    """
    method_signature_jsoncall_map = {}
    
    try:
        # 加载变更方法数据
        changed_methods = FileUtil.load_changed_methods_from_file(changed_methods_file)
        if not changed_methods:
            logger.warn("无法加载变更方法数据，跳过调用关系分析")
            return ""
        
        if not os.path.exists(analysis_file):
            logger.warn(f"1_analyze_project.json 文件不存在，跳过调用关系分析: {analysis_file}")
            return ""

        # 统计总的方法数量
        total_methods = sum(len(change_data['method_signatures']) for change_data in changed_methods.values())
        logger.info(f"开始分析 {len(changed_methods)} 个变更，共 {total_methods} 个方法的调用关系")
        
        # 创建方法调用分析器
        analyzer = MethodCallAnalyzer(analysis_file)
        
        # 为每个变更的方法生成调用关系JSON
        method_count = 0
        for change_index, change_data in changed_methods.items():
            method_signatures = change_data['method_signatures']
            change_method_calls_data = {}
            
            for method_signature in method_signatures:
                method_count += 1
                try:
                    logger.info(f"分析Change {change_index} 的第 {method_count} 个方法: {method_signature}")
                    
                    # 获取完整的调用关系数据
                    # max_calls_out=1: 分析该方法调用的其他方法，最多分析1层深度
                    # max_calls_in=3: 分析调用该方法的方法，最多分析3层高度
                    relationship = analyzer.get_complete_method_relationship(
                        method_signature=method_signature,
                        max_calls_out=1,
                        max_calls_in=2
                    )
                    
                    # 将调用关系数据添加到当前变更的JSON中
                    change_method_calls_data[method_signature] = {
                        "calls_out": relationship["calls_out"],
                        "calls_in": relationship["calls_in"]
                    }
                    
                    logger.info(f"方法 {method_signature} 的调用关系已分析完成")
                    
                except Exception as e:
                    logger.error(f"分析方法 {method_signature} 的调用关系时发生错误: {str(e)}")
                    continue
            
            # 将当前变更的所有方法调用关系数据添加到map中
            method_signature_jsoncall_map[change_index] = change_method_calls_data
        
        logger.info(f"完成所有变更方法的调用关系分析")
        logger.info(f"方法调用数据Map: {method_signature_jsoncall_map}")
        
        # 将数据写入临时文件
        output_file = _save_method_calls_to_file(method_signature_jsoncall_map, project_name, workspace_path)
        logger.info(f"方法调用关系数据已保存到: {output_file}")
        return output_file
            
    except Exception as e:
        logger.error(f"分析变更方法调用关系过程中发生错误: {str(e)}")
        return ""

def _save_method_calls_to_file(method_calls: Dict[int, Dict], project_name: str = None, workspace_path: str = None) -> str:
    """
    将方法调用关系数据保存到临时文件
    
    Args:
        method_calls: 方法调用关系数据
        project_name: 项目名称
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径
    """
    try:
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, "3_method_calls.json")
        
        if FileUtil.save_json_to_file(method_calls, output_file):
            return output_file
        else:
            return ""
        
    except Exception as e:
        logger.error(f"保存方法调用关系数据到文件时发生错误: {str(e)}")
        return ""



