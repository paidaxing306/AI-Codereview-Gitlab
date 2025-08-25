import json
import os
from typing import Dict, Any, Optional
from biz.utils.log import logger


class FileUtil:
    """
    通用文件操作工具类
    提供JSON文件的读写操作
    """
    
    @staticmethod
    def save_json_to_file(data: Any, file_path: str, ensure_ascii: bool = False, indent: int = 2) -> bool:
        """
        将数据保存为JSON文件
        
        Args:
            data: 要保存的数据
            file_path: 文件路径
            ensure_ascii: 是否确保ASCII编码
            indent: 缩进空格数
            
        Returns:
            保存成功返回True，失败返回False
        """
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 将数据写入JSON文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            
            logger.info(f"数据已保存到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存数据到文件时发生错误: {str(e)}")
            return False
    
    @staticmethod
    def load_json_from_file(file_path: str) -> Optional[Any]:
        """
        从JSON文件加载数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            加载的数据，失败时返回None
        """
        try:
            if not file_path or not os.path.exists(file_path):
                logger.warn(f"文件不存在: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"从文件加载数据: {file_path}")
            return data
            
        except Exception as e:
            logger.error(f"从文件加载数据时发生错误: {str(e)}")
            return None

    @staticmethod
    def load_json_with_fallback(file_path: str, data_type: str = "数据", default_return=None, return_empty_dict: bool = False) -> Any:
        """
        从JSON文件加载数据，带错误处理和回退机制
        
        Args:
            file_path: 文件路径
            data_type: 数据类型描述，用于日志
            default_return: 默认返回值
            return_empty_dict: 是否在失败时返回空字典（而不是None）
            
        Returns:
            加载的数据，失败时返回default_return或空字典
        """
        try:
            if not os.path.exists(file_path):
                logger.warn(f"{data_type}文件不存在: {file_path}")
                return {} if return_empty_dict else default_return
            
            data = FileUtil.load_json_from_file(file_path)
            if data:
                logger.info(f"成功从文件加载{data_type}: {file_path}")
                return data
            else:
                logger.warn(f"从文件加载{data_type}失败: {file_path}")
                return {} if return_empty_dict else default_return
                
        except Exception as e:
            logger.error(f"从文件加载{data_type}时发生错误: {str(e)}")
            return {} if return_empty_dict else default_return

    @staticmethod
    def load_changed_methods_from_file(file_path: str) -> Dict[int, Dict]:
        """
        从文件加载变更方法数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            变更方法数据字典，失败时返回空字典
        """
        return FileUtil.load_json_with_fallback(file_path, "变更方法数据", return_empty_dict=True)

    @staticmethod
    def load_analysis_result_from_file(file_path: str) -> Optional[Dict]:
        """
        从文件加载项目分析结果数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            项目分析结果数据，失败时返回None
        """
        return FileUtil.load_json_with_fallback(file_path, "项目分析结果", default_return=None)

    @staticmethod
    def load_method_calls_from_file(file_path: str) -> Dict[int, Dict]:
        """
        从文件加载方法调用关系数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            方法调用关系数据字典，失败时返回空字典
        """
        return FileUtil.load_json_with_fallback(file_path, "方法调用关系数据", return_empty_dict=True)

    @staticmethod
    def load_code_context_from_file(file_path: str) -> Dict[int, Dict]:
        """
        从文件加载Java代码输出数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            Java代码输出数据字典，失败时返回空字典
        """
        return FileUtil.load_json_with_fallback(file_path, "Java代码输出数据", return_empty_dict=True)

    @staticmethod
    def load_prompts_from_file(file_path: str) -> Dict[int, str]:
        """
        从文件加载格式化字段数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            格式化字段映射，失败时返回空字典
        """
        return FileUtil.load_json_with_fallback(file_path, "格式化字段数据", return_empty_dict=True)
    
    @staticmethod
    def get_project_tmp_dir(workspace_path: str, project_name: str = None) -> str:
        """
        获取项目临时目录路径
        
        Args:
            workspace_path: 工作空间路径
            project_name: 项目名称，默认为'qnvip-qwen'
            
        Returns:
            项目临时目录路径
        """
        project_name = project_name or 'qnvip-qwen'
        return os.path.join(workspace_path, f"{project_name}_tmp")
    
    @staticmethod
    def get_project_file_path(workspace_path: str, project_name: str, filename: str) -> str:
        """
        获取项目文件路径
        
        Args:
            workspace_path: 工作空间路径
            project_name: 项目名称
            filename: 文件名
            
        Returns:
            完整的文件路径
        """
        project_tmp_dir = FileUtil.get_project_tmp_dir(workspace_path, project_name)
        return os.path.join(project_tmp_dir, filename) 