import json
import re
import yaml
import os
from typing import Dict, Optional
from jinja2 import Template
from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil
from biz.utils.code_wrapper import CodeWrapper

# 常量定义
CHANGED_PROMPT_FILENAME = "5_changed_prompt.json"


class JavaCodePrinter:
    def __init__(self):
        """
        初始化Java代码打印机
        """
        self.java_code_data = {}

    def _clean_java_code(self, java_code: str) -> str:
        """
        清理Java代码，减少过多空行，保持原有缩进
        author  lichaojie
        """
        if not java_code or not java_code.strip():
            return java_code

        lines = java_code.split('\n')
        cleaned_lines = []
        consecutive_empty_lines = 0

        for line in lines:
            if line.strip():
                # 非空行，重置连续空行计数
                consecutive_empty_lines = 0
                cleaned_lines.append(line)
            else:
                # 空行，最多保留一个连续空行
                consecutive_empty_lines += 1
                if consecutive_empty_lines <= 1:
                    cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def print_markdown(self):
        """以简洁的markdown格式打印Java代码"""
        target_method = list(self.java_code_data.keys())[0]
        classes_data = self.java_code_data[target_method]

        print(f"# {target_method.split('.')[-1].split('(')[0]} 相关代码")
        print(f"**目标方法**: `{target_method}`\n")

        for class_signature, java_code in classes_data.items():
            class_name = class_signature.split('.')[-1]
            cleaned_code = self._clean_java_code(java_code)

            print(f"## {class_name}")
            print(f"**包路径**: `{class_signature}`\n")
            print("```java")
            print(cleaned_code)
            print("```\n")

    def print_compact_markdown(self):
        """以极简的markdown格式打印Java代码"""
        target_method = list(self.java_code_data.keys())[0]
        classes_data = self.java_code_data[target_method]

        print(f"# {target_method}\n")

        for class_signature, java_code in classes_data.items():
            class_name = class_signature.split('.')[-1]
            cleaned_code = self._clean_java_code(java_code)

            print(f"## {class_name}")
            print("```java")
            print(cleaned_code)
            print("```\n")

    def generate_markdown_from_data(self, json_data: dict) -> str:
        """从JSON数据生成markdown字符串"""
        markdown_parts = []
        # 遍历所有方法
        for method_signature, classes_data in json_data.items():
            for class_signature, java_code in classes_data.items():
                cleaned_code = self._clean_java_code(java_code)
                markdown_parts.append("```java")
                markdown_parts.append(cleaned_code)
                markdown_parts.append("```")
        return "\n".join(markdown_parts)


def generate_markdown_from_json_data(json_data: dict) -> str:
    """
    静态方法：从JSON数据生成markdown字符串
    
    Args:
        json_data: Java代码输出数据，格式为 {method_signature: {class_signature: java_code, ...}, ...}
        
    Returns:
        str: markdown格式的字符串
    """
    printer = JavaCodePrinter()
    return printer.generate_markdown_from_data(json_data)


def delete_prompt_file(project_name: str, workspace_path: str = None) -> bool:
    """
    删除格式化字段文件
    
    Args:
        project_name: 项目名称
        workspace_path: 工作空间路径，默认为当前目录下的workspace
        
    Returns:
        删除成功返回True，失败返回False
    """
    workspace_path = workspace_path or os.path.join(os.getcwd(), 'workspace')
    output_file = FileUtil.get_project_file_path(workspace_path, project_name, CHANGED_PROMPT_FILENAME)
    return FileUtil.delete_file(output_file)


def generate_assemble_prompt(changed_methods_file: str, code_context_file: str, project_name: str,
                             workspace_path: str = None) -> str:
    """生成格式化的提示词字段"""

    try:
        # 加载变更方法数据
        changed_methods = FileUtil.load_changed_methods_from_file(changed_methods_file)
        if not changed_methods:
            logger.warn("无法加载变更方法数据，跳过format字段生成")
            return ""

        # 加载Java代码输出数据
        code_context = FileUtil.load_code_context_from_file(code_context_file)
        if not code_context:
            logger.warn("无法加载Java代码输出数据，跳过format字段生成")
            return ""

        # 为每个变更单独生成format字段
        for change_index, change_data in changed_methods.items():
            old_code = change_data.get('old_code', '')
            new_code = change_data.get('new_code', '')
            file_path = change_data.get('file_path', '')
            # generate_markdown_from_json_data(code_context[change_index]['self'])

            # 获取当前变更的Java代码内容

            contents= [val for key, val in next(iter(code_context[change_index].values())).items() if key == "self"]
            join_contents = "\n\n".join(contents)
            context = f"```java\n{join_contents}\n```"

            # 将结果存储到map中
            change_data['prompt'] = context
            change_data['language'] = 'java'

        # 将数据写入临时文件
        output_file = _save_format_fields_to_file(changed_methods, project_name, workspace_path)
        logger.info(f"格式化字段数据已保存到: {output_file}")
        return output_file

    except Exception as e:
        logger.error(f"生成format字段过程中发生错误: {str(e)}")

    return ""


def generate_assemble_web_prompt(webhook_data, changed_method_signatures_map: dict, workspace_path) -> str:
    """生成格式化的提示词字段"""
    # 加载prompt模板
    prompts = _load_prompt_templates("conf/prompt_templates.yml")
    if not prompts:
        logger.warn("无法加载prompt模板，跳过format字段生成")
        return ""

    item_prompt_template = prompts.get("item_prompt", "")
    if not item_prompt_template:
        logger.warn("未找到item_prompt模板，跳过format字段生成")
        return ""

    # 为每个变更单独生成format字段
    for change_index, change_data in changed_method_signatures_map.items():
        old_code = change_data.get('old_code', '')
        new_code = change_data.get('new_code', '')
        file_path = change_data.get('file_path', '')
        context = change_data.get('content', '')

        # 使用CodeWrapper包裹代码
        old_code = CodeWrapper.wrap_code_to_md(old_code, file_path)
        new_code = CodeWrapper.wrap_code_to_md(new_code, file_path)
        context = CodeWrapper.wrap_code_to_md(context, file_path)

        # 使用Jinja2模板渲染format字段
        template = Template(item_prompt_template)
        format_field = template.render(
            old_code=old_code,
            new_code=new_code,
            context=context,
            file_path=file_path
        )
        change_data['prompt'] = format_field

    output_file = _save_format_fields_to_file(changed_method_signatures_map, webhook_data['project']['name'],
                                              workspace_path)
    logger.info(f"格式化字段数据已保存到: {output_file}")
    return output_file


def _save_format_fields_to_file(format_fields: Dict[int, str], project_name: str = None,
                                workspace_path: str = None) -> str:
    """
    将格式化字段数据保存到临时文件
    
    Args:
        format_fields: 格式化字段数据
        project_name: 项目名称
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径
    """
    try:
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, CHANGED_PROMPT_FILENAME)

        # 先读取已存在的数据
        existing_data = FileUtil.load_json_from_file(output_file) or {}

        # 追加新数据
        existing_data.update(format_fields)

        # 保存回文件
        if FileUtil.save_json_to_file(existing_data, output_file):
            return output_file
        else:
            return ""

    except Exception as e:
        logger.error(f"保存格式化字段数据到文件时发生错误: {str(e)}")
        return ""


def _load_prompt_templates(prompt_templates_file: str) -> Optional[Dict]:
    """加载prompt模板"""
    try:
        with open(prompt_templates_file, "r", encoding="utf-8") as file:
            return yaml.safe_load(file).get("call_chain_analysis", {})
    except Exception as e:
        logger.error(f"加载prompt模板失败: {str(e)}")
        return None
