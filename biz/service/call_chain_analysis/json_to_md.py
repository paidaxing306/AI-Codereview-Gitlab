"""
JSON到Markdown转换工具类
用于将review_result的JSON格式转换为Markdown表格格式
"""

from typing import List, Dict, Any
import json
from biz.utils.log import logger


class JsonToMdConverter:
    """JSON到Markdown转换器"""
    
    @staticmethod
    def convert_review_results_to_md(review_results: List[Dict[str, Any]]) -> str:
        """
        将review_result的JSON列表转换为Markdown表格格式
        
        Args:
            review_results: review_result的JSON数据列表
                格式: [{"name": "UserService.getUser()", "issue": "问题描述", "level": "🔴 高", "content": "详细内容"}, ...]
        
        Returns:
            str: Markdown格式的AI审查报告
        """
        if not review_results:
            logger.info("没有review_result数据，返回空报告")
            return "## 🧠 AI审查报告\n\n暂无审查问题发现。"
        
        # 构建Markdown表格
        md_lines = []
        md_lines.append("## 🧠 AI审查报告")
        md_lines.append("| 类名方法名 | 存在的问题 | 问题级别 |")
        md_lines.append("|------------|------------|----------|")
        
        # 去重处理，避免重复的审查结果
        seen_entries = set()
        
        for result in review_results:
            if not isinstance(result, dict):
                logger.warning(f"跳过非字典格式的review_result: {result}")
                continue
                
            name = result.get('name', '未知方法')
            issue = result.get('issue', '未知问题')
            level = result.get('level', '🟢 低')
            
            # 创建唯一标识符用于去重
            entry_key = f"{name}|{issue}|{level}"
            if entry_key in seen_entries:
                continue
            seen_entries.add(entry_key)
            
            # 清理和格式化数据
            name = JsonToMdConverter._clean_text(name)
            issue = JsonToMdConverter._clean_text(issue)
            level = JsonToMdConverter._clean_text(level)
            
            # 添加表格行
            md_lines.append(f"| {name} | {issue} | {level} |")
        
        return '\n'.join(md_lines)

    
    @staticmethod
    def _is_valid_review_result(data: Dict[str, Any]) -> bool:
        """
        验证是否为有效的review_result JSON格式
        
        Args:
            data: 待验证的字典数据
            
        Returns:
            bool: 是否为有效格式
        """
        required_keys = ['name', 'issue', 'level']
        return all(key in data for key in required_keys)
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """
        清理文本，移除不必要的字符和格式
        
        Args:
            text: 待清理的文本
            
        Returns:
            str: 清理后的文本
        """
        if not isinstance(text, str):
            return str(text)
        
        # 移除多余的空白字符
        text = text.strip()
        
        # 移除Markdown表格中的管道符，避免破坏表格格式
        text = text.replace('|', '\\|')
        
        return text

    @staticmethod
    def issue_fix_suggestion_to_md(review_results: List[Dict[str, Any]]) -> str:
        """
        将review_result的JSON列表转换为问题修正建议的Markdown格式
        
        Args:
            review_results: review_result的JSON数据列表
                格式: [{"name": "UserService.getUser()", "issue": "问题描述", "level": "🔴 高", "content": "详细内容"}, ...]
        
        Returns:
            str: Markdown格式的问题修正建议报告
        """
        if not review_results:
            logger.info("没有review_result数据，返回空的问题修正建议")
            return ""
        
        md_sections = []
        
        for result in review_results:
            if not isinstance(result, dict):
                logger.warning(f"跳过非字典格式的review_result: {result}")
                continue
                
            name = result.get('name', '未知方法')
            issue = result.get('issue', '未知问题')
            level = result.get('level', '🟢 低')
            content = result.get('content', '暂无详细内容')
            
            # 格式化单个问题的Markdown
            section = f"\n## {name}\n{level}\n{issue}\n{content}\n"
            md_sections.append(section)

        return "## 🧠 AI审查报告 - 问题分析  "+'\n\n'.join(md_sections)
