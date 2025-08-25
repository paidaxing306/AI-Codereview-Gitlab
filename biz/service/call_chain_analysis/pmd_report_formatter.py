import os
from typing import Dict, List, Optional

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil


class PMDReportFormatter:
    """
    PMD报告格式化工具类
    用于将PMD报告数据转换为Markdown表格格式
    """

    @staticmethod
    def format_pmd_report_to_markdown_table(pmd_report_file: str, branch_name: str = 'master') -> Optional[str]:
        """
        将PMD报告文件格式化为Markdown表格

        Args:
            pmd_report_file: PMD报告文件路径
            branch_name: 分支名称，默认为master

        Returns:
            格式化后的Markdown表格字符串，失败时返回None
        """
        try:
            # 加载PMD报告数据
            pmd_report_data = FileUtil.load_json_from_file(pmd_report_file)
            if not pmd_report_data:
                logger.warn("无法加载PMD报告数据")
                return None

            # 检查是否有文件数据
            if 'files' not in pmd_report_data or not pmd_report_data['files']:
                logger.info("PMD报告中没有文件数据")
                return None

            # 生成Markdown表格
            markdown_table = PMDReportFormatter._generate_markdown_table(pmd_report_data['files'], branch_name)
            
            if markdown_table:
                logger.info("PMD报告已成功格式化为Markdown表格")
                return markdown_table
            else:
                logger.warn("PMD报告格式化失败，没有有效的违规数据")
                return None

        except Exception as e:
            logger.error(f"格式化PMD报告时发生错误: {str(e)}")
            return None

    @staticmethod
    def _generate_markdown_table(files_data: List[Dict], branch_name: str = 'master') -> Optional[str]:
        """
        生成Markdown表格

        Args:
            files_data: 文件数据列表
            branch_name: 分支名称，默认为master

        Returns:
            Markdown表格字符串
        """
        try:
            # 表格头部
            table_header = "| 文件名 | 原因 | 优先级 |\n"
            table_separator = "|--------|------|--------|\n"
            
            # 收集所有违规数据
            violations_data = []
            
            for file_info in files_data:
                filename = file_info.get('filename', '')
                
                violations = file_info.get('violations', [])
                for violation in violations:
                    beginline = violation.get('beginline', 0)
                    endline = violation.get('endline', 0)
                    description = violation.get('description', '')
                    priority = violation.get('priority', 0)
                    
                    # 格式化文件名，包含代码位置
                    formatted_filename = PMDReportFormatter._format_filename_with_location(filename, beginline, endline, branch_name)
                    
                    # 格式化优先级
                    priority_text = PMDReportFormatter._format_priority(priority)
                    
                    violations_data.append({
                        'formatted_filename': formatted_filename,
                        'description': description,
                        'priority': priority_text
                    })
            
            if not violations_data:
                logger.info("没有找到违规数据")
                return None
            
            # 生成表格行
            table_rows = []
            for violation in violations_data:
                row = f"| {violation['formatted_filename']} | {violation['description']} | {violation['priority']} |"
                table_rows.append(row)
            
            # 组装完整的Markdown表格
            markdown_table = table_header + table_separator + '\n'.join(table_rows)
            
            # 添加统计信息
            total_violations = len(violations_data)
            markdown_table += f"\n\n**总计发现 {total_violations} 个代码规范问题**"
            
            return markdown_table

        except Exception as e:
            logger.error(f"生成Markdown表格时发生错误: {str(e)}")
            return None

    @staticmethod
    def _format_filename_with_location(absolute_filename: str, beginline: int, endline: int, branch_name: str = 'master') -> str:
        """
        格式化文件名为 [文件名:行号范围](GitLab URL) 格式

        Args:
            absolute_filename: 绝对文件路径
            beginline: 开始行号
            endline: 结束行号
            branch_name: 分支名称，默认为master

        Returns:
            格式化的文件名字符串
        """
        try:
            # 获取文件名
            file_name = os.path.basename(absolute_filename)
            
            # 转换为GitLab URL格式
            gitlab_url = PMDReportFormatter._convert_to_gitlab_url(absolute_filename, branch_name)
            
            # 格式化代码位置
            if beginline == endline:
                location = f"{beginline}"
            else:
                location = f"{beginline}-{endline}"
            
            # 格式化为 [文件名:行号范围](GitLab URL) 格式
            return f"[{file_name}:{location}]({gitlab_url})"
            
        except Exception as e:
            logger.warn(f"格式化文件名时发生错误: {str(e)}")
            return os.path.basename(absolute_filename)

    @staticmethod
    def _format_filename_with_path(absolute_filename: str) -> str:
        """
        格式化文件名为 [文件名](GitLab URL) 格式

        Args:
            absolute_filename: 绝对文件路径

        Returns:
            格式化的文件名字符串
        """
        try:
            # 获取文件名
            file_name = os.path.basename(absolute_filename)
            
            # 转换为GitLab URL格式
            gitlab_url = PMDReportFormatter._convert_to_gitlab_url(absolute_filename)
            
            # 格式化为 [文件名](GitLab URL) 格式
            return f"[{file_name}]({gitlab_url})"
            
        except Exception as e:
            logger.warn(f"格式化文件名时发生错误: {str(e)}")
            return os.path.basename(absolute_filename)

    @staticmethod
    def _convert_to_gitlab_url(absolute_filename: str, branch_name: str = 'master') -> str:
        """
        将绝对文件路径转换为GitLab URL

        Args:
            absolute_filename: 绝对文件路径
            branch_name: 分支名称，默认为master

        Returns:
            GitLab URL字符串
        """
        try:
            # 查找workspace路径
            workspace_index = absolute_filename.find('workspace')
            if workspace_index == -1:
                # 如果没有找到workspace，返回原始路径
                return absolute_filename.replace('\\', '/')
            
            # 从workspace之后开始截取相对路径
            relative_path = absolute_filename[workspace_index + len('workspace') + 1:]
            relative_path = relative_path.replace('\\', '/')  # 统一使用正斜杠
            
            # 分割路径获取项目名和文件路径
            path_parts = relative_path.split('/')
            if len(path_parts) < 2:
                return absolute_filename.replace('\\', '/')
            
            # 第一个部分是项目名
            project_name = path_parts[0]
            
            # 剩余部分是文件路径
            file_path = '/'.join(path_parts[1:])
            
            # 构建GitLab URL
            # 格式: https://git.qncentury.com/qnvip-ai/{project_name}/-/blob/{branch_name}/{file_path}
            gitlab_url = f"https://git.qncentury.com/qnvip-ai/{project_name}/-/blob/{branch_name}/{file_path}"
            
            return gitlab_url
            
        except Exception as e:
            logger.warn(f"转换GitLab URL时发生错误: {str(e)}")
            return absolute_filename.replace('\\', '/')

    @staticmethod
    def _split_filename_and_path(absolute_filename: str) -> tuple[str, str]:
        """
        分割文件名和路径

        Args:
            absolute_filename: 绝对文件路径

        Returns:
            (文件名, 文件路径) 元组
        """
        try:
            # 查找workspace路径
            workspace_index = absolute_filename.find('workspace')
            if workspace_index != -1:
                # 从workspace之后开始截取
                relative_path = absolute_filename[workspace_index + len('workspace') + 1:]
                relative_path = relative_path.replace('\\', '/')  # 统一使用正斜杠
                
                # 分割文件名和路径
                path_parts = relative_path.split('/')
                if len(path_parts) > 1:
                    file_name = path_parts[-1]  # 最后一个部分是文件名
                    file_path = '/'.join(path_parts[:-1])  # 前面的部分是路径
                else:
                    # 只有文件名，没有路径
                    file_name = relative_path
                    file_path = ''
            else:
                # 如果没有找到workspace，使用原始路径
                file_name = os.path.basename(absolute_filename)
                file_path = os.path.dirname(absolute_filename)
            
            return file_name, file_path
            
        except Exception as e:
            logger.warn(f"分割文件名和路径时发生错误: {str(e)}")
            return os.path.basename(absolute_filename), ''

    @staticmethod
    def _get_relative_filename(absolute_filename: str) -> str:
        """
        获取相对文件名，去掉工作空间路径前缀

        Args:
            absolute_filename: 绝对文件路径

        Returns:
            相对文件名
        """
        try:
            # 查找workspace路径
            workspace_index = absolute_filename.find('workspace')
            if workspace_index != -1:
                # 从workspace之后开始截取
                relative_path = absolute_filename[workspace_index + len('workspace') + 1:]
                return relative_path.replace('\\', '/')  # 统一使用正斜杠
            else:
                # 如果没有找到workspace，返回文件名部分
                return os.path.basename(absolute_filename)
        except Exception as e:
            logger.warn(f"处理文件名时发生错误: {str(e)}")
            return absolute_filename

    @staticmethod
    def _format_priority(priority: int) -> str:
        """
        格式化优先级

        Args:
            priority: 优先级数字

        Returns:
            格式化的优先级文本
        """
        priority_map = {
            1: "🔴 高",
            2: "🟡 中",
            3: "🟢 低",
            4: "⚪ 信息",
            5: "⚪ 信息"
        }
        
        return priority_map.get(priority, f"未知({priority})")

    @staticmethod
    def format_pmd_report_static(pmd_report_file: str, branch_name: str = 'master') -> Optional[str]:
        """
        静态方法：格式化PMD报告文件

        Args:
            pmd_report_file: PMD报告文件路径
            branch_name: 分支名称，默认为master

        Returns:
            格式化后的Markdown表格字符串，失败时返回None
        """
        return PMDReportFormatter.format_pmd_report_to_markdown_table(pmd_report_file, branch_name) 