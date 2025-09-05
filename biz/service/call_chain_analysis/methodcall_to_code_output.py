#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方法调用关系转换为代码输出格式
将3_method_calls.json中的方法调用关系转换为4_code_context.json格式
从1_analyze_project.json中提取相关的方法源码并组成完整的类

实现思路：
1. 3_method_calls.json 遍历的key作为4_code_context.json的key（支持多个方法签名）
2. 取出calls_out和calls_in的方法签名，从1_analyze_project.json查找method_signatures的对象，根据class_signature_name分组
3. 根据class_signature_name从1_analyze_project.json的class_signatures找出对象
4. 然后class_signature_name作为key，value为class_source_code + method_source_code组成的Java源码，组成一个class_source_map
5. 把class_source_map放入4_code_context.json，支持多个方法签名的结果
"""

import json
import re
import os
from typing import Dict, List, Set, Optional

from biz.utils.log import logger
from biz.service.call_chain_analysis.file_util import FileUtil


class MethodCallToCodeOutput:
    def __init__(self, method_call_file: str = None, analyze_project_file: str = None, output_file: str = None):
        """
        初始化转换器

        Args:
            method_call_file: 3_method_calls.json文件路径（可选）
            analyze_project_file: 1_analyze_project.json文件路径（可选）
            output_file: 输出文件路径（可选）
        """
        self.method_call_file = method_call_file
        self.analyze_project_file = analyze_project_file
        self.output_file = output_file

        # 数据存储
        self.method_call_data = {}
        self.analyze_project_data = {}

        # 缓存1_analyze_project.json的数据结构
        self.class_signatures = {}  # class_signature_name -> class_signature对象
        self.method_signatures = {}  # method_signature -> method_signature对象

    def load_data_from_files(self):
        """从文件加载数据"""
        if self.method_call_file:
            self.method_call_data = self._load_json_file(self.method_call_file)
        if self.analyze_project_file:
            self.analyze_project_data = self._load_json_file(self.analyze_project_file)

        # 初始化缓存
        self._init_caches()

    def load_data_from_dict(self, method_call_data: dict, analyze_project_data: dict):
        """
        从字典数据加载
        
        Args:
            method_call_data: 方法调用数据
            analyze_project_data: 项目分析数据
        """
        self.method_call_data = method_call_data
        self.analyze_project_data = analyze_project_data

        # 初始化缓存
        self._init_caches()

    def _load_json_file(self, file_path: str) -> dict:
        """加载JSON文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载文件 {file_path} 失败: {e}")
            return {}

    def _init_caches(self):
        """初始化1_analyze_project.json的缓存"""
        print("正在初始化1_analyze_project.json缓存...")

        # 缓存class_signatures
        if 'class_signatures' in self.analyze_project_data:
            for class_name, class_data in self.analyze_project_data['class_signatures'].items():
                self.class_signatures[class_name] = class_data

        # 缓存method_signatures
        if 'method_signatures' in self.analyze_project_data:
            for method_signature, method_data in self.analyze_project_data['method_signatures'].items():
                self.method_signatures[method_signature] = method_data

        print(f"缓存初始化完成: {len(self.class_signatures)} 个类, {len(self.method_signatures)} 个方法")

    def _get_all_related_methods(self, method_signature: str) -> Set[str]:
        """
        获取与方法相关的所有方法签名（包括调用的方法和被调用的方法）

        Args:
            method_signature: 起始方法签名

        Returns:
            相关方法签名集合
        """
        related_methods = set()

        if method_signature not in self.method_call_data:
            # 如果找不到该方法，至少添加起始方法本身
            related_methods.add(method_signature)
            print(f"警告: 在3_method_calls.json中未找到方法 {method_signature}")
            return related_methods

        method_data = self.method_call_data[method_signature]

        # 添加被调用的方法（calls_out）
        if 'calls_out' in method_data:
            for level_methods in method_data['calls_out'].values():
                for method in level_methods:
                    related_methods.add(method)

        # 添加调用者方法（calls_in）
        if 'calls_in' in method_data:
            for level_methods in method_data['calls_in'].values():
                for method in level_methods:
                    related_methods.add(method)

        # 添加起始方法本身
        related_methods.add(method_signature)

        print(f"方法 {method_signature} 相关的方法数量: {len(related_methods)}")
        return related_methods

    def _group_methods_by_class(self, method_signatures: Set[str]) -> Dict[str, List[str]]:
        """
        按class_signature_name分组方法签名

        Args:
            method_signatures: 方法签名集合

        Returns:
            类名到方法签名列表的映射
        """
        class_methods = {}

        for method_signature in method_signatures:
            # 从method_signatures中查找对应的class_signature_name
            if method_signature in self.method_signatures:
                class_signature_name = self.method_signatures[method_signature].get('class_signature_name', '')
                if class_signature_name:
                    if class_signature_name not in class_methods:
                        class_methods[class_signature_name] = []
                    class_methods[class_signature_name].append(method_signature)
            else:
                print(f"警告: 未找到方法 {method_signature} 在method_signatures中")

        return class_methods

    def _build_class_source_code(self, class_signature_name: str, method_signatures: List[str]) -> str:
        """
        构建完整的类源码（class_source_code + field_source_code + method_source_code）

        Args:
            class_signature_name: 类签名名称
            method_signatures: 方法签名列表

        Returns:
            完整的类源码
        """
        # 从class_signatures中获取类源码
        class_source_code = ""
        if class_signature_name in self.class_signatures:
            class_source_code = self.class_signatures[class_signature_name].get('class_source_code', '')

        if not class_source_code:
            print(f"警告: 未找到类 {class_signature_name} 的class_source_code")
            return ""

        # 收集所有方法用到的字段
        used_field_signatures = set()
        method_source_codes = []

        for method_signature in method_signatures:
            if method_signature in self.method_signatures:
                method_data = self.method_signatures[method_signature]
                method_source_code = method_data.get('method_source_code', '')
                if method_source_code:
                    method_source_codes.append(method_source_code)
                else:
                    print(f"警告: 未找到方法 {method_signature} 的method_source_code")

                # 收集方法中使用的字段
                usaged_fields = method_data.get('usaged_fields', [])
                used_field_signatures.update(usaged_fields)
            else:
                print(f"警告: 未找到方法 {method_signature} 在method_signatures中")

        # 从field_signatures中获取字段源码
        field_source_codes = []

        field_signatures_data = self.analyze_project_data.get('field_signatures', {})
        for field_signature_name in used_field_signatures:
            field_source_code = field_signatures_data.get(field_signature_name, {}).get('field_source_code', '')
            if field_source_code:
                field_source_codes.append(field_source_code)

        # 组合类源码、字段源码和方法源码
        combined_source = class_source_code.rstrip()
        if combined_source.endswith('}'):
            combined_source = combined_source[:-1]  # 移除最后的 }

            # 添加字段源码
            if field_source_codes:
                combined_source += "\n"
                for field_source in field_source_codes:
                    # 缩进字段源码
                    field_lines = field_source.split('\n')
                    for line in field_lines:
                        if line.strip():  # 跳过空行
                            combined_source += f"\n    {line}"
                combined_source += "\n"

            # 添加方法源码
            if method_source_codes:
                for method_source in method_source_codes:
                    # 缩进方法源码
                    method_lines = method_source.split('\n')
                    for line in method_lines:
                        combined_source += f"\n    {line}"
                    combined_source += "\n"

            combined_source += "}"  # 重新添加最后的 }
        else:
            print(f"警告: 类 {class_signature_name} 的源码格式异常")
            combined_source = class_source_code

        return combined_source

    def convert(self) -> dict:
        """
        执行转换
        
        Returns:
            dict: 转换结果
        """
        print("开始转换方法调用关系到代码输出格式...")
        print(f"处理 {len(self.method_call_data)} 个方法调用关系")

        result = {}

        # 1. 3_method_calls.json 遍历的key作为4_code_context.json的key（支持多个方法签名）
        for i, method_signature in enumerate(self.method_call_data.keys(), 1):
            print(f"\n[{i}/{len(self.method_call_data)}] 处理方法: {method_signature}")

            # 2. 取出calls_out和calls_in的方法签名
            related_methods = self._get_all_related_methods(method_signature)

            # 3. 根据class_signature_name分组
            class_methods = self._group_methods_by_class(related_methods)
            print(f"  涉及 {len(class_methods)} 个类")

            # 4. 构建class_source_map
            class_source_map = {}
            for class_signature_name, method_list in class_methods.items():
                print(f"  构建类: {class_signature_name} (包含 {len(method_list)} 个方法)")
                class_source_code = self._build_class_source_code(class_signature_name, method_list)
                if class_source_code:
                    class_source_map[class_signature_name] = class_source_code

            # 取方法本身的源码同时，再取同文件里的调用到的方法
            need_class = method_signature.rpartition('.')[0]
            need_methods = [method_signature]

            for sig in self.method_signatures[method_signature]['usage_method_signature_name']:
                if need_class == sig.rpartition('.')[0]:
                    need_methods.append(sig)

            class_source_map['self'] = self._build_class_source_code(need_class, need_methods)
            # 5. 把class_source_map放入4_code_context.json
            if class_source_map:
                result[method_signature] = class_source_map
                print(f"  ✓ 成功构建 {len(class_source_map)} 个类的源码")
            else:
                print(f"  ✗ 未能构建任何类的源码")

        # 保存结果到文件（如果指定了输出文件）
        if self.output_file:
            self._save_result(result)
            print(f"\n转换完成，结果已保存到 {self.output_file}")

        print(f"总共处理了 {len(result)} 个方法调用关系")
        return result

    def _save_result(self, result: dict):
        """保存结果到文件"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存结果失败: {e}")


def convert_method_calls_to_code_output(method_call_data: dict, analyze_project_data: dict) -> dict:
    """
    静态方法：将方法调用数据转换为代码输出格式
    
    Args:
        method_call_data: 方法调用数据
        analyze_project_data: 项目分析数据
        
    Returns:
        dict: 转换结果
    """
    converter = MethodCallToCodeOutput()
    converter.load_data_from_dict(method_call_data, analyze_project_data)
    return converter.convert()


def format_code_context(method_calls_file: str, analysis_file: str, project_name: str = None,
                        workspace_path: str = None) -> str:
    """
    生成Java代码输出
    
    Args:
        method_calls_file: 方法调用关系数据文件路径
        analysis_file: 项目分析结果文件路径
        project_name: 项目名称，用于生成临时文件路径
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径，包含Java代码输出数据
    """
    code_context_map = {}

    try:
        # 加载方法调用关系数据
        method_calls = FileUtil.load_method_calls_from_file(method_calls_file)
        if not method_calls:
            logger.warn("无法加载方法调用关系数据，跳过code_context生成")
            return ""

        if not os.path.exists(analysis_file):
            logger.warn(f"1_analyze_project.json 文件不存在，跳过code_context生成: {analysis_file}")
            return ""

        # 加载1_analyze_project.json数据
        analyze_project_data = FileUtil.load_analysis_result_from_file(analysis_file)
        if analyze_project_data is None:
            logger.warn(f"1_analyze_project.json 文件不存在或读取失败，跳过code_context生成: {analysis_file}")
            return ""

        # 为每个变更生成code_context
        for change_index, method_calls_data in method_calls.items():
            try:
                logger.info(f"开始为Change {change_index} 生成code_context")

                # 调用转换方法
                code_context = convert_method_calls_to_code_output(
                    method_call_data=method_calls_data,
                    analyze_project_data=analyze_project_data
                )

                # 将结果存储到map中
                code_context_map[change_index] = code_context

                logger.info(f"Change {change_index} 的code_context已生成，包含 {len(code_context)} 个方法")

            except Exception as e:
                logger.error(f"为Change {change_index} 生成code_context时发生错误: {str(e)}")
                continue

        logger.info(f"成功生成 {len(code_context_map)} 个变更的code_context")

        # 将数据写入临时文件
        output_file = _save_code_context_to_file(code_context_map, project_name, workspace_path)
        logger.info(f"Java代码输出数据已保存到: {output_file}")
        return output_file

    except Exception as e:
        logger.error(f"生成code_context过程中发生错误: {str(e)}")

    return ""


def _save_code_context_to_file(code_context: Dict[int, Dict], project_name: str = None,
                               workspace_path: str = None) -> str:
    """
    将Java代码输出数据保存到临时文件
    
    Args:
        code_context: Java代码输出数据
        project_name: 项目名称
        workspace_path: 工作空间路径
        
    Returns:
        临时文件路径
    """
    try:
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, "4_code_context.json")

        if FileUtil.save_json_to_file(code_context, output_file):
            return output_file
        else:
            return ""

    except Exception as e:
        logger.error(f"保存Java代码输出数据到文件时发生错误: {str(e)}")
        return ""
