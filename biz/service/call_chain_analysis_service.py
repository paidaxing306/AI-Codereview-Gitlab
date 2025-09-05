import os
import time
from typing import Dict, List, Optional, Tuple

from biz.utils.log import logger
from biz.utils.git_util import GitUtil
from biz.service.call_chain_analysis.file_util import FileUtil
from biz.service.call_chain_analysis.java_project_analyzer import analyze_java_project_static
from biz.service.call_chain_analysis.method_call_analyzer import analyze_method_calls_static
from biz.service.call_chain_analysis.methodcall_to_code_output import format_code_context
from biz.service.call_chain_analysis.java_code_to_md import generate_assemble_prompt, delete_prompt_file,generate_assemble_web_prompt
from biz.service.call_chain_analysis.extract_changed_signatures import extract_changed_method_signatures_static
from biz.service.call_chain_analysis.pmd_check_plugin import run_pmd_check_static
from biz.service.call_chain_analysis.pmd_report_formatter import PMDReportFormatter



class CallChainAnalysisService:
    """
    调用链分析服务
    负责分析代码变更对调用链的影响
    """

    def __init__(self, workspace_path: str = None, plugin_path: str = None):
        """
        初始化调用链分析服务

        Args:
            workspace_path: 工作空间路径，默认为当前目录下的workspace
            plugin_path: 插件路径，默认为当前目录下的plugins
        """
        self.workspace_path = workspace_path or os.path.join(os.getcwd(), 'workspace')
        self.plugin_path = plugin_path or os.path.join(os.getcwd(), 'plugin')


    @staticmethod
    def before_process_changes(service, webhook_data):
        """
        在处理开始前，删除旧的 prompt 文件
        
        Args:
            service: CallChainAnalysisService 实例
            webhook_data: GitLab webhook数据
        """
        project_name = webhook_data.get('project', {}).get('name')
        if project_name:
            delete_prompt_file(project_name, service.workspace_path)
 



    @staticmethod
    def process(webhook_data: dict, github_token: str, changes: list, handler=None) -> Optional[Dict]:
        """
        处理调用链分析的主入口方法

        Args:
            webhook_data: GitLab webhook数据
            github_token: Git访问令牌
            changes: 代码变更列表
            handler: GitLab handler实例，用于提交评论

        Returns:
            调用链分析结果字典，失败时返回None
        """
        service = CallChainAnalysisService()

        # 清除文件
        CallChainAnalysisService.before_process_changes(service, webhook_data)

        java_changes = [
            change for change in changes
            if change['new_path'].endswith(".java")
        ]

        web_changes = [
            change for change in changes
            if change['new_path'].endswith((".js", ".html", ".vue", ".jsx", ".tsx"))
        ]

        ### .java
        result=[]
        if java_changes:
            result = service._process_java_changes(webhook_data, github_token, changes, handler)

        ### web .js,.html,.vue,.jsx,.tsx
        if web_changes:
            result = service._process_web_changes(webhook_data, changes)

        return result


    def _process_java_changes(self, webhook_data: dict, github_token: str, changes: list, handler=None) -> Optional[Dict]:
        """
        处理代码变更的调用链分析

        Args:
            webhook_data: GitLab webhook数据
            github_token: Git访问令牌
            changes: 代码变更列表
            handler: GitLab handler实例，用于提交评论

        Returns:
            调用链分析结果字典，失败时返回None
        """
        try:
            # 1. 克隆/更新项目到{workspace}
            project_info = self._clone_or_update_project(webhook_data, github_token)
            if not project_info:
                logger.warn("项目克隆失败，跳过调用链分析")
                return None

            # 2. 分析Java项目产生{workspace/project/1_analyze_project.json}
            analysis_result_file = analyze_java_project_static(project_info, self.workspace_path)
            if not analysis_result_file:
                logger.warn("Java项目分析失败，跳过调用链分析")
                return None

            # 3. 解析变更的方法签名产生{workspace/project/2_changed_methods.json}
            changed_methods_file = extract_changed_method_signatures_static(changes, project_info['name'],
                                                                            self.workspace_path,analysis_result_file)
            if not changed_methods_file:
                logger.info("未发现变更的方法签名，跳过调用链分析")
                return None

            # 3.1 plugin PMD代码检查产生{workspace/project_tmp/plugin_pmd_report_enhanced.json}
            # 从整个Java项目中提取所有Java文件路径，对整个项目进行PMD检查
            java_files_to_check = self._extract_java_files_from_changes(changes, project_info['path'])
            pmd_report_file = run_pmd_check_static(project_info['path'], project_info['name'], self.workspace_path,
                                                   self.plugin_path, self.changed_java_files)
            if pmd_report_file:
                logger.info(f"PMD代码检查完成，报告文件: {pmd_report_file}")
                
                # 3.1.1 格式化PMD报告为Markdown表格并提交到GitLab
                if handler:
                    self._submit_pmd_report_to_gitlab(pmd_report_file, handler, webhook_data)
            else:
                logger.warn("PMD代码检查失败，但不会影响后续调用链分析步骤，继续执行")


            # 实现3.2步骤：过滤PMD已检查的方法签名
            filtered_changed_methods_file = self._filter_pmd_checked_methods(
                pmd_report_file, changed_methods_file, project_info['name']
            )
            if filtered_changed_methods_file:
                logger.info(f"PMD过滤完成，过滤后的方法文件: {filtered_changed_methods_file}")
                # 使用过滤后的文件继续后续步骤
                changed_methods_file = filtered_changed_methods_file
            else:
                logger.warn("PMD过滤失败，将使用原始变更方法文件继续处理")

            # 4. 分析调用关系产生{workspace/project/3_method_calls.json}
            method_calls_file = analyze_method_calls_static(changed_methods_file, analysis_result_file,
                                                            project_info['name'], self.workspace_path)
            if not method_calls_file:
                logger.warn("调用关系分析失败，跳过调用链分析")
                return None

            # 5. 生成Java代码输出产生{workspace/project/4_code_context.json}
            code_context_file = format_code_context(method_calls_file, analysis_result_file, project_info['name'],
                                                    self.workspace_path)
            if not code_context_file:
                logger.warn("Java代码输出生成失败，跳过调用链分析")
                return None

            # 6. 组装提示词产生{workspace/project/CHANGED_PROMPT_FILENAME}
            changed_prompt_file = generate_assemble_prompt(changed_methods_file, code_context_file,
                                                           project_info['name'], self.workspace_path)
            if not changed_prompt_file:
                logger.warn("格式化字段生成失败，跳过调用链分析")
                return None

            # 7. 将提示词添加到changes中
            return FileUtil.load_prompts_from_file(changed_prompt_file)

        except Exception as e:
            logger.error(f"调用链分析过程中发生错误: {str(e)}")
            return None

    def _process_web_changes(self, webhook_data: dict, changes: list) -> Optional[ Dict]:
        """处理代码变更的调用链分析"""
        changed_prompt_file= generate_assemble_web_prompt(webhook_data, changes, self.workspace_path)
        return FileUtil.load_prompts_from_file(changed_prompt_file)






    def _extract_java_files_from_changes(self, changes: list, project_path: str) -> List[str]:
        """
        从整个Java项目中提取所有Java文件路径，同时记录变更文件信息
        
        Args:
            changes: 代码变更列表
            project_path: 项目根目录路径
            
        Returns:
            Java文件路径列表
        """
        # 获取所有变更的Java文件路径，用于后续标记in_change字段
        changed_java_files = set()
        for change in changes:
            if isinstance(change, dict):
                new_path = change.get('new_path', '')
                if new_path.endswith('.java'):
                    changed_java_files.add(new_path)
        
        # 递归查找项目中的所有Java文件
        java_files = []
        for root, dirs, files in os.walk(project_path):
            # 跳过一些常见的非源码目录
            dirs[:] = [d for d in dirs if d not in ['.git', 'target', 'build', 'out', 'bin', 'node_modules']]
            
            for file in files:
                if file.endswith('.java'):
                    # 构建相对于项目根目录的路径
                    rel_path = os.path.relpath(os.path.join(root, file), project_path)
                    # 转换为Unix风格的路径分隔符
                    rel_path = rel_path.replace(os.sep, '/')
                    
                    # 构建完整的文件路径
                    full_path = os.path.join(project_path, rel_path)
                    
                    # 检查文件是否存在
                    if os.path.exists(full_path):
                        java_files.append(full_path)
                        if rel_path in changed_java_files:
                            logger.info(f"添加变更的Java文件到PMD检查列表: {rel_path}")
                        else:
                            logger.debug(f"添加项目Java文件到PMD检查列表: {rel_path}")
        
        logger.info(f"从整个项目中提取到 {len(java_files)} 个Java文件进行PMD检查，其中 {len(changed_java_files)} 个为变更文件")
        
        # 将变更文件信息保存到实例变量中，供后续使用
        self.changed_java_files = changed_java_files
        
        return java_files

    def _clone_or_update_project(self, webhook_data: dict, github_token: str) -> Optional[Dict]:
        """
        克隆或更新项目到本地

        Args:
            webhook_data: GitLab webhook数据
            github_token: Git访问令牌

        Returns:
            项目信息字典，失败时返回None
        """
        try:
            project = webhook_data.get('project', {})
            source_branch = webhook_data.get('object_attributes', {}).get('source_branch', 'master')

            logger.info(f"MR信息 - 源分支: {source_branch}")
            logger.info(f"将使用源分支 {source_branch} 进行分析，因为变更代码在该分支中")

            # 获取可用的Git URL列表
            git_urls = self._get_git_urls(project)
            if not git_urls:
                logger.warn("无法获取项目git URL，跳过项目克隆")
                return None

            # 尝试克隆/更新项目
            success, error = self._try_clone_project(git_urls, source_branch, github_token)
            if not success:
                logger.error(f"项目克隆失败: {error}")
                return None

            return {
                'name': project.get('name', 'unknown_project'),
                'path': os.path.join(self.workspace_path, project.get('name', 'unknown_project'))
            }

        except Exception as e:
            logger.error(f"项目克隆过程中发生错误: {str(e)}")
            return None

    def _get_git_urls(self, project: dict) -> List[str]:
        """获取项目的Git URL列表"""
        git_urls = [
            project.get('git_http_url'),
            project.get('http_url'),
            project.get('git_ssh_url'),
            project.get('ssh_url'),
            project.get('url')
        ]
        return [url for url in git_urls if url]

    def _try_clone_project(self, git_urls: List[str], branch: str, token: str) -> Tuple[bool, str]:
        """尝试使用多个URL克隆项目"""
        git_start_time = time.time()

        for i, git_url in enumerate(git_urls):
            logger.info(f"尝试第{i + 1}个git URL: {git_url}")

            success, error = GitUtil.ensure_repository(
                git_url=git_url,
                workspace_path=self.workspace_path,
                branch_name=branch,
                token=token
            )

            if success:
                git_duration = time.time() - git_start_time
                logger.info(f"项目克隆/更新成功: {git_url}")
                logger.info(f"Git操作耗时: {git_duration:.2f}秒")
                return True, ""
            else:
                logger.warn(f"第{i + 1}个URL失败: {error}")
                if i < len(git_urls) - 1:
                    logger.info("尝试下一个URL...")

        git_duration = time.time() - git_start_time
        logger.error(f"所有URL都失败，Git操作总耗时: {git_duration:.2f}秒")
        return False, "所有Git URL都失败"

    def _filter_pmd_checked_methods(self, pmd_report_file: str, changed_methods_file: str, project_name: str) -> \
    Optional[str]:
        """
        过滤PMD已检查的方法签名

        Args:
            pmd_report_file: PMD报告文件路径
            changed_methods_file: 变更方法文件路径
            project_name: 项目名称

        Returns:
            过滤后的文件路径，失败时返回None
        """
        try:
            # 加载PMD报告数据
            pmd_report_data = FileUtil.load_json_from_file(pmd_report_file)
            if not pmd_report_data:
                logger.warn("无法加载PMD报告数据，跳过过滤")
                return None

            # 加载变更方法数据
            changed_methods_data = FileUtil.load_changed_methods_from_file(changed_methods_file)
            if not changed_methods_data:
                logger.warn("无法加载变更方法数据，跳过过滤")
                return None

            # 提取PMD报告中的方法签名
            skip_method_signatures_set = set()
            if 'files' in pmd_report_data:
                for file_info in pmd_report_data['files']:
                    method_signatures = file_info.get('method_signature', [])
                    if method_signatures:
                        skip_method_signatures_set.update(method_signatures)

            logger.info(f"从PMD报告中提取到 {len(skip_method_signatures_set)} 个需要跳过的方法签名")

            # 过滤变更方法数据
            filtered_changed_methods = {}
            total_original_methods = 0
            total_filtered_methods = 0

            for change_index, change_data in changed_methods_data.items():
                original_method_signatures = change_data.get('method_signatures', [])
                total_original_methods += len(original_method_signatures)

                # 过滤掉PMD已检查的方法签名
                filtered_method_signatures = [
                    method_sig for method_sig in original_method_signatures
                    if method_sig not in skip_method_signatures_set
                ]

                # 如果过滤后还有方法签名，则保留这个变更
                if filtered_method_signatures:
                    filtered_change_data = change_data.copy()
                    filtered_change_data['method_signatures'] = filtered_method_signatures
                    filtered_changed_methods[change_index] = filtered_change_data
                    total_filtered_methods += len(filtered_method_signatures)

                    logger.info(f"变更 {change_index}: 原始方法数 {len(original_method_signatures)}, "
                                f"过滤后方法数 {len(filtered_method_signatures)}")
                else:
                    logger.info(f"变更 {change_index}: 所有方法都被PMD检查过，已移除")

            logger.info(
                f"过滤完成: 原始变更数 {len(changed_methods_data)}, 过滤后变更数 {len(filtered_changed_methods)}")
            logger.info(f"方法签名过滤: 原始方法数 {total_original_methods}, 过滤后方法数 {total_filtered_methods}")

            # 保存过滤后的数据
            if filtered_changed_methods:
                output_file = FileUtil.get_project_file_path(self.workspace_path, project_name,
                                                             "2_changed_methods_filter.json")
                if FileUtil.save_json_to_file(filtered_changed_methods, output_file):
                    logger.info(f"过滤后的变更方法数据已保存到: {output_file}")
                    return output_file
                else:
                    logger.error("保存过滤后的变更方法数据失败")
                    return None
            else:
                logger.warn("过滤后没有剩余的方法签名")
                return None

        except Exception as e:
            logger.error(f"过滤PMD已检查方法时发生错误: {str(e)}")
            return None

    def _submit_pmd_report_to_gitlab(self, pmd_report_file: str, handler, webhook_data: dict) -> None:
        """
        将PMD报告格式化为Markdown表格并提交到GitLab

        Args:
            pmd_report_file: PMD报告文件路径
            handler: GitLab handler实例
            webhook_data: GitLab webhook数据，用于获取分支信息
        """
        try:
            # 获取分支信息
            source_branch = webhook_data.get('object_attributes', {}).get('source_branch', 'master')
            
            # 格式化PMD报告为Markdown表格
            markdown_table = PMDReportFormatter.format_pmd_report_static(pmd_report_file, source_branch, webhook_data)
            
            if markdown_table:
                # 添加标题和说明
                pmd_comment = f"""## 🔍 PMD代码规范检查报告

{markdown_table}
"""
                
                # 提交到GitLab
                handler.add_merge_request_notes(pmd_comment)
                logger.info("PMD报告已成功提交到GitLab")
            else:
                logger.info("PMD报告为空，跳过提交到GitLab")
                
        except Exception as e:
            logger.error(f"提交PMD报告到GitLab时发生错误: {str(e)}")





