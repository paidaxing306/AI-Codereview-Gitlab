import subprocess
import sys
import os
import json
import glob
import re
import time
from typing import Dict, List, Optional, Tuple

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil


class PMDCheckPlugin:
    """
    PMD代码检查插件类
    """
    
    def __init__(self):
        """
        初始化PMD检查插件，从环境变量读取跳过规则列表和文件名关键词
        """
        skip_rule_list_str = os.environ.get('CODE_CALL_CHAIN_P3C_SKIP_ROLE', '')
        if skip_rule_list_str:
            self.skip_rule_list = [rule.strip() for rule in skip_rule_list_str.split(',') if rule.strip()]
            logger.info(f"从环境变量读取到跳过规则列表: {self.skip_rule_list}")
        else:
            self.skip_rule_list = []
            logger.info("环境变量CODE_CALL_CHAIN_P3C_SKIP_ROLE未设置，使用空列表")
        
        # 初始化文件名关键词过滤列表
        self.skip_filename_keywords = ['test']
        logger.info(f"文件名关键词过滤列表: {self.skip_filename_keywords}")
    
    def get_project_level(self, project_name: str) -> int:
        """
        根据项目名称获取对应的p3c检查级别
        
        参数:
            project_name: 项目名称
            
        返回:
            级别对应的数字: 1(高级), 2(中级), 3(低级)
        """
        # 级别映射
        level_mapping = {
            'HIGH': 1,
            'MIDDLE': 2, 
            'LOW': 3
        }
        
        # 获取默认级别
        default_level = os.environ.get('CODE_ANALYSIS_PROJECT_JAVA_P3C_LEVEL_DEFAULT', 'HIGH')
        default_level_num = level_mapping.get(default_level.upper(), 1)
        
        # 获取各级别对应的项目列表
        high_projects = os.environ.get('CODE_ANALYSIS_PROJECT_JAVA_P3C_LEVEL_HIGH', '').split(',')
        middle_projects = os.environ.get('CODE_ANALYSIS_PROJECT_JAVA_P3C_LEVEL_MIDDLE', '').split(',')
        low_projects = os.environ.get('CODE_ANALYSIS_PROJECT_JAVA_P3C_LEVEL_LOW', '').split(',')
        
        # 清理项目名称（去除空格和空字符串）
        high_projects = [p.strip() for p in high_projects if p.strip()]
        middle_projects = [p.strip() for p in middle_projects if p.strip()]
        low_projects = [p.strip() for p in low_projects if p.strip()]
        
        # 根据项目名称确定级别
        if project_name in high_projects:
            level_num = 1
            level_name = 'HIGH'
        elif project_name in middle_projects:
            level_num = 2
            level_name = 'MIDDLE'
        elif project_name in low_projects:
            level_num = 3
            level_name = 'LOW'
        else:
            level_num = default_level_num
            level_name = default_level.upper()
        
        logger.info(f"项目 {project_name} 使用 {level_name} 级别 (数字: {level_num})")
        return level_num


    def get_change_level(self, project_name: str) -> int:
        """
        根据项目名称获取对应的p3c检查级别

        参数:
            project_name: 项目名称

        返回:
            级别对应的数字: 1(高级), 2(中级), 3(低级)
        """
        # 级别映射
        level_mapping = {
            'HIGH': 1,
            'MIDDLE': 2,
            'LOW': 3
        }

        # 获取默认级别
        default_level = os.environ.get('CODE_ANALYSIS_CHANGE_JAVA_P3C_LEVEL_DEFAULT', 'HIGH')
        default_level_num = level_mapping.get(default_level.upper(), 1)

        # 获取各级别对应的项目列表
        high_projects = os.environ.get('CODE_ANALYSIS_CHANGE_JAVA_P3C_LEVEL_HIGH', '').split(',')
        middle_projects = os.environ.get('CODE_ANALYSIS_CHANGE_JAVA_P3C_LEVEL_MIDDLE', '').split(',')
        low_projects = os.environ.get('CODE_ANALYSIS_CHANGE_JAVA_P3C_LEVEL_LOW', '').split(',')

        # 清理项目名称（去除空格和空字符串）
        high_projects = [p.strip() for p in high_projects if p.strip()]
        middle_projects = [p.strip() for p in middle_projects if p.strip()]
        low_projects = [p.strip() for p in low_projects if p.strip()]

        # 根据项目名称确定级别
        if project_name in high_projects:
            level_num = 1
            level_name = 'HIGH'
        elif project_name in middle_projects:
            level_num = 2
            level_name = 'MIDDLE'
        elif project_name in low_projects:
            level_num = 3
            level_name = 'LOW'
        else:
            level_num = default_level_num
            level_name = default_level.upper()

        logger.info(f"变更 {project_name} 使用 {level_name} 级别 (数字: {level_num})")
        return level_num

    def filter_violations(self, report_data: Dict) -> Dict:
        """
        根据skip_rule_list过滤violations，并根据文件名关键词过滤文件
        
        参数:
            report_data: PMD报告数据
            
        返回:
            过滤后的报告数据
        """
        if 'files' not in report_data:
            return report_data
        
        start_time = time.time()
        filtered_files = []
        total_violations_before = 0
        total_violations_after = 0
        skipped_files_count = 0
        
        for file_info in report_data['files']:
            filename = file_info.get('filename', '')
            violations = file_info.get('violations', [])
            total_violations_before += len(violations)
            
            # 检查文件名是否包含需要跳过的关键词
            should_skip_file = False
            for keyword in self.skip_filename_keywords:
                if keyword.lower() in filename.lower():
                    should_skip_file = True
                    # logger.debug(f"跳过包含关键词 '{keyword}' 的文件: {filename}")
                    break
            
            if should_skip_file:
                skipped_files_count += 1
                continue
            
            # 过滤violations（如果skip_rule_list不为空）
            if self.skip_rule_list:
                filtered_violations = []
                for violation in violations:
                    rule = violation.get('rule', '')
                    if rule not in self.skip_rule_list:
                        filtered_violations.append(violation)

                violations = filtered_violations
            
            # 创建新的文件信息
            filtered_file_info = file_info.copy()
            filtered_file_info['violations'] = violations
            filtered_files.append(filtered_file_info)
            
            total_violations_after += len(violations)
        
        # 创建过滤后的报告数据
        filtered_report_data = report_data.copy()
        filtered_report_data['files'] = filtered_files
        
        elapsed_time = time.time() - start_time
        logger.info(f"过滤完成: 原始violations数量 {total_violations_before}, 过滤后 {total_violations_after}, 跳过文件数 {skipped_files_count}, 耗时: {elapsed_time:.3f}秒")
        
        return filtered_report_data


def extract_method_signatures_from_java_file(file_path: str, begin_line: int, end_line: int) -> List[str]:
    """
    从Java文件中提取指定行号范围内的方法签名
    
    参数:
        file_path: Java文件路径
        begin_line: 开始行号
        end_line: 结束行号
        
    返回:
        方法签名列表
    """
    method_signatures = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # 获取包名
        package_name = ""
        for line in lines:
            if line.strip().startswith("package "):
                package_name = line.strip().replace("package ", "").replace(";", "").strip()
                break
        
        # 获取类名
        class_name = ""
        for line in lines:
            if re.match(r'^\s*(public\s+)?(abstract\s+)?(final\s+)?class\s+\w+', line.strip()):
                class_name = re.search(r'class\s+(\w+)', line).group(1)
                break
        
        if not class_name:
            return method_signatures
        
        # 构建完整的类名
        full_class_name = f"{package_name}.{class_name}" if package_name else class_name
        
        # 解析方法签名
        current_line = 0
        in_method = False
        method_start_line = 0
        method_lines = []
        
        for line_num, line in enumerate(lines, 1):
            # 检查是否在目标行范围内
            if begin_line <= line_num <= end_line:
                # 检查是否是方法声明
                if re.match(r'^\s*(public|private|protected)?\s*(static\s+)?(final\s+)?(synchronized\s+)?(native\s+)?(abstract\s+)?(default\s+)?(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', line.strip()):
                    # 这是一个方法声明
                    method_match = re.search(r'(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(', line.strip())
                    if method_match:
                        return_type = method_match.group(1)
                        method_name = method_match.group(2)
                        
                        # 提取参数
                        params_start = line.find('(')
                        params_end = line.find(')')
                        if params_start != -1 and params_end != -1:
                            params_str = line[params_start+1:params_end].strip()
                            if params_str:
                                # 简单解析参数类型
                                params = []
                                param_parts = params_str.split(',')
                                for param in param_parts:
                                    param = param.strip()
                                    if param:
                                        # 提取参数类型（最后一个单词通常是参数名）
                                        param_type_match = re.search(r'(\w+(?:<[^>]+>)?)\s+\w+', param)
                                        if param_type_match:
                                            params.append(param_type_match.group(1))
                                        else:
                                            # 如果没有参数名，直接使用整个参数
                                            params.append(param)
                                
                                method_signature = f"{full_class_name}.{method_name}({', '.join(params)})"
                                method_signatures.append(method_signature)
                            else:
                                method_signature = f"{full_class_name}.{method_name}()"
                                method_signatures.append(method_signature)
        
        return method_signatures
        
    except Exception as e:
        print(f"解析文件 {file_path} 时出错: {str(e)}")
        return []


def add_method_signatures_to_report(report_data: Dict) -> Dict:
    """
    为PMD报告中的每个文件添加method_signature字段
    
    参数:
        report_data: PMD报告数据
        
    返回:
        添加了method_signature的报告数据
    """
    if 'files' not in report_data:
        return report_data
    
    for file_info in report_data['files']:
        filename = file_info.get('filename', '')
        violations = file_info.get('violations', [])
        
        # 收集所有违规行号范围
        line_ranges = []
        for violation in violations:
            begin_line = violation.get('beginline', 0)
            end_line = violation.get('endline', 0)
            if begin_line > 0 and end_line > 0:
                line_ranges.append((begin_line, end_line))
        
        # 提取方法签名
        method_signatures = []
        for begin_line, end_line in line_ranges:
            signatures = extract_method_signatures_from_java_file(filename, begin_line, end_line)
            method_signatures.extend(signatures)
        
        # 去重并添加到文件信息中
        file_info['method_signature'] = list(set(method_signatures))
    
    return report_data


def add_in_change_field_to_report(project_path, report_data: Dict, changed_java_files: set = None) -> Dict:
    """
    为PMD报告中的每个文件添加in_change字段，标记该文件是否在变更列表中
    
    参数:
        report_data: PMD报告数据
        changed_java_files: 变更的Java文件路径集合，用于标记in_change字段
        
    返回:
        添加了in_change字段的报告数据
    """
    if 'files' not in report_data:
        return report_data
    
    for file_info in report_data['files']:
        filename = file_info.get('filename', '')
        
        # 添加in_change字段，标记该文件是否在变更列表中
        if changed_java_files is not None:
            # 使用os.path.relpath基于project_path计算相对路径
            relative_path = os.path.relpath(filename, project_path)
            # 统一使用正斜杠作为路径分隔符
            relative_path = relative_path.replace(os.sep, '/')
            # 检查是否在变更文件列表中
            in_change = relative_path in changed_java_files
            file_info['in_change'] = in_change
        else:
            file_info['in_change'] = False
    
    return report_data


def run_pmd_check(project_path, output_file=None, plugin_path=None, project_name=None, changed_java_files=None):
    """运行PMD代码检查并生成报告"""
    # 卫语句：检查必要参数
    if not plugin_path or not os.path.exists(project_path):
        logger.error("参数错误：plugin_path不能为空或项目路径不存在")
        return None

    # 获取检查级别
    min_level = PMDCheckPlugin().get_project_level(project_name)

    # 构建命令
    command = _build_pmd_command(project_path, plugin_path)
    if not command:
        return None

    # 执行PMD检查
    result = subprocess.run(command, capture_output=True, text=True)
    logger.info(f"执行命令: {' '.join(command)}")

    # 卫语句：检查执行结果
    if result.returncode not in [0, 4]:
        logger.error(f"PMD检查失败，返回代码: {result.returncode}")
        return None

    # 处理输出
    report_data = _process_pmd_output(result, project_path, changed_java_files)
    if not report_data:
        return None

    # 保存报告
    if output_file and not _save_report(report_data, output_file):
        return None

    return report_data


def _build_pmd_command(project_path, plugin_path):
    """构建PMD命令"""
    # 设置PMD路径
    pmd_bin_dir = os.path.join(plugin_path, "pmd-bin-6.55.0", "bin")
    pmd_lib_dir = os.path.join(plugin_path, "pmd-bin-6.55.0", "lib")

    logger.info(f"项目路径: {project_path}, PMD库目录: {pmd_lib_dir}")

    rulesets = [
        "rulesets/java/ali-comment.xml", "rulesets/java/ali-constant.xml",
        "rulesets/java/ali-exception.xml", "rulesets/java/ali-flowcontrol.xml",
        "rulesets/java/ali-naming.xml", "rulesets/java/ali-oop.xml",
        "rulesets/java/ali-orm.xml", "rulesets/java/ali-other.xml",
        "rulesets/java/ali-set.xml"
    ]
    
    base_args = ["-d", project_path, "--minimum-priority", "2", "-R"] + rulesets + ["-f", "json"]
    
    if os.name == 'nt':  # Windows
        if not os.path.exists(pmd_lib_dir):
            logger.error(f"PMD库目录不存在: {pmd_lib_dir}")
            return None
        
        all_jars = glob.glob(os.path.join(pmd_lib_dir, "*.jar"))
        classpath = ";".join(all_jars)
        logger.info(f"找到 {len(all_jars)} 个JAR文件")
        
        return ["java", "-cp", classpath, "net.sourceforge.pmd.PMD"] + base_args
    else:  # Linux/Unix/macOS
        run_sh_path = os.path.join(pmd_bin_dir, "run.sh")
        if not os.path.exists(run_sh_path):
            logger.error(f"run.sh脚本不存在: {run_sh_path}")
            return None
        
        os.chmod(run_sh_path, 0o755)
        return [run_sh_path, "pmd"] + base_args


def _process_pmd_output(result, project_path, changed_java_files):
    """处理PMD输出"""
    if result.stderr:
        logger.warn(f"警告信息: {result.stderr}")
    
    if not result.stdout:
        logger.warn("PMD没有输出任何内容")
        return None
    
    try:
        report_data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.error(f"解析PMD输出JSON失败: {e}")
        return None
    
    # 处理报告数据
    pmd_plugin = PMDCheckPlugin()
    report_data = pmd_plugin.filter_violations(report_data)
    report_data = add_method_signatures_to_report(report_data)
    report_data = add_in_change_field_to_report(project_path, report_data, changed_java_files)
    
    return report_data


def _save_report(report_data, output_file):
    """保存报告到文件"""
    if FileUtil.save_json_to_file(report_data, output_file):
        logger.info(f"PMD报告已保存到: {output_file}")
        return True
    else:
        logger.error(f"保存PMD报告失败: {output_file}")
        return False


def run_pmd_check_static(project_path: str, project_name: str, workspace_path: str, plugin_path: str = None,
                         changed_java_files: set = None) -> Optional[str]:
    """
    运行PMD代码检查的静态方法，供调用链分析服务使用
    
    参数:
        project_path: 项目路径
        project_name: 项目名称
        workspace_path: 工作空间路径
        plugin_path: 插件路径，如果为None则使用默认路径
        files_to_check: 要检查的文件列表，如果为None则检查整个项目
        changed_java_files: 变更的Java文件路径集合，用于标记in_change字段
        
    返回:
        成功时返回PMD报告文件路径，失败时返回None
    """
    try:
        # 使用FileUtil构建输出文件路径
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, "plugin_pmd_report_enhanced.json")
        
        # 运行PMD检查
        report_data = run_pmd_check(project_path, output_file, plugin_path, project_name, changed_java_files)
        
        if report_data:
            logger.info(f"PMD检查成功完成，报告文件: {output_file}")
            return output_file
        else:
            logger.warn("PMD检查失败，返回None")
            return None
            
    except Exception as e:
        logger.error(f"PMD检查过程中发生错误: {str(e)}")
        return None

