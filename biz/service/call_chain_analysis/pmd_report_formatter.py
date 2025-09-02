import os
from typing import Dict, List, Optional

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil
from biz.service.call_chain_analysis.pmd_check_plugin import PMDCheckPlugin


class PMDReportFormatter:
    """
    PMD报告格式化工具类
    用于将PMD报告数据转换为Markdown表格格式
    """

    @staticmethod
    def format_pmd_report_to_markdown_table(pmd_report_file: str, branch_name: str = 'master', webhook_data: dict = None) -> Optional[str]:
        """
        将PMD报告文件格式化为Markdown表格

        Args:
            pmd_report_file: PMD报告文件路径
            branch_name: 分支名称，默认为master
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

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

            # 获取检查级别
            PMDReportFormatter.filter_by_level(pmd_report_data, webhook_data)

            # 生成Markdown表格
            markdown_table = PMDReportFormatter._generate_markdown_table(pmd_report_data['files'], branch_name, webhook_data)
            
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
    def filter_by_level(pmd_report_data, webhook_data):
        project_name = webhook_data['project']["name"]
        project_level = PMDCheckPlugin().get_project_level(project_name)
        change_level = PMDCheckPlugin().get_change_level(project_name)
        # 使用 project_level 和 change_level 对 pmd_report_data进行一次过滤
        # 当"in_change": true 时使用 change_level，保留 priority<= change_level
        # 当"in_change": false 时使用 project_level，保留 priority<= project_level
        filtered_files = []
        for file_info in pmd_report_data['files']:
            filename = file_info.get('filename', '')
            violations = file_info.get('violations', [])

            # 检查文件是否在变更中
            in_change = file_info.get('in_change', False)
            current_level = change_level if in_change else project_level

            # 过滤violations，只保留优先级小于等于当前级别的
            filtered_violations = []
            for violation in violations:
                priority = violation.get('priority', 5)
                if priority <= current_level:
                    filtered_violations.append(violation)

            # 如果过滤后还有violations，则保留该文件
            if filtered_violations:
                filtered_file_info = file_info.copy()
                filtered_file_info['violations'] = filtered_violations
                filtered_files.append(filtered_file_info)
        # 更新过滤后的数据
        pmd_report_data['files'] = filtered_files

    @staticmethod
    def _generate_markdown_table(files_data: List[Dict], branch_name: str = 'master', webhook_data: dict = None) -> Optional[str]:
        """
        生成Markdown表格

        Args:
            files_data: 文件数据列表
            branch_name: 分支名称，默认为master
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

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
                    formatted_filename = PMDReportFormatter._format_filename_with_location(filename, beginline, endline, branch_name, webhook_data)
                    
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

            
            return markdown_table

        except Exception as e:
            logger.error(f"生成Markdown表格时发生错误: {str(e)}")
            return None

    @staticmethod
    def _format_filename_with_location(absolute_filename: str, beginline: int, endline: int, branch_name: str = 'master', webhook_data: dict = None) -> str:
        """
        格式化文件名为 [文件名:行号范围](GitLab URL) 格式

        Args:
            absolute_filename: 绝对文件路径
            beginline: 开始行号
            endline: 结束行号
            branch_name: 分支名称，默认为master
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

        Returns:
            格式化的文件名字符串
        """
        try:
            # 获取文件名
            file_name = os.path.basename(absolute_filename)
            
            # 转换为GitLab URL格式
            gitlab_url = PMDReportFormatter._convert_to_gitlab_url(absolute_filename, branch_name, webhook_data)
            
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
    def _format_filename_with_path(absolute_filename: str, webhook_data: dict = None) -> str:
        """
        格式化文件名为 [文件名](GitLab URL) 格式

        Args:
            absolute_filename: 绝对文件路径
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

        Returns:
            格式化的文件名字符串
        """
        try:
            # 获取文件名
            file_name = os.path.basename(absolute_filename)
            
            # 转换为GitLab URL格式
            gitlab_url = PMDReportFormatter._convert_to_gitlab_url(absolute_filename, 'master', webhook_data)
            
            # 格式化为 [文件名](GitLab URL) 格式
            return f"[{file_name}]({gitlab_url})"
            
        except Exception as e:
            logger.warn(f"格式化文件名时发生错误: {str(e)}")
            return os.path.basename(absolute_filename)

    @staticmethod
    def _convert_to_gitlab_url(absolute_filename: str, branch_name: str = 'master', webhook_data: dict = None) -> str:
        """
        将绝对文件路径转换为GitLab URL

        Args:
            absolute_filename: 绝对文件路径
            branch_name: 分支名称，默认为master
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

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
            
            # 从webhook_data中获取GitLab URL信息
            if webhook_data and 'project' in webhook_data:
                project_info = webhook_data['project']
                # 使用web_url作为基础URL
                web_url = project_info.get('web_url', '')
                if web_url:
                    # 从web_url中提取基础URL
                    if web_url.endswith('/'):
                        base_url = web_url[:-1]  # 去掉末尾的斜杠
                    else:
                        base_url = web_url
                    
                    # 构建GitLab URL
                    gitlab_url = f"{base_url}/-/blob/{branch_name}/{file_path}"
                    return gitlab_url
            
            # 如果没有webhook_data或无法获取URL，使用默认格式
            # 从webhook_data中尝试获取域名信息
            if webhook_data and 'project' in webhook_data:
                project_info = webhook_data['project']
                git_http_url = project_info.get('git_http_url', '')
                if git_http_url:
                    # 从git_http_url中提取域名和路径
                    # 格式: http://git.qncentury.com/qnvip-business-front/qnvip-rent-group/qnvip-rent-unite-group.git
                    if git_http_url.endswith('.git'):
                        git_http_url = git_http_url[:-4]  # 去掉.git后缀
                    
                    # 构建GitLab URL
                    gitlab_url = f"{git_http_url}/-/blob/{branch_name}/{file_path}"
                    return gitlab_url
   
 
            return "null"
            
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


    _PRIORITY_MAPPING = {
        1: "🔴 高",
        2: "🟡 中",
        3: "🟢 低",
        4: "⚪",
        5: "⚪"
    }

 
    @staticmethod
    def _format_priority(priority: int) -> str:
        """
        格式化PMD报告的优先级为可读的文本格式
        author  lichaojie
        """
        if not isinstance(priority, int):
            return f"❓ 无效优先级({priority})"
        priority = min(max(priority, 1), 5)
        return PMDReportFormatter._PRIORITY_MAPPING.get(priority, f"❓ 未知优先级({priority})")
    @staticmethod
    def format_pmd_report_static(pmd_report_file: str, branch_name: str = 'master', webhook_data: dict = None) -> Optional[str]:
        """
        静态方法：格式化PMD报告文件

        Args:
            pmd_report_file: PMD报告文件路径
            branch_name: 分支名称，默认为master
            webhook_data: GitLab webhook数据，用于获取GitLab URL信息

        Returns:
            格式化后的Markdown表格字符串，失败时返回None
        """
        return PMDReportFormatter.format_pmd_report_to_markdown_table(pmd_report_file, branch_name, webhook_data) 