import json
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional



from biz.service.call_chain_analysis.file_util import FileUtil
from biz.utils.log import logger


@dataclass
class ClassSignature:
    class_signature_name: str
    class_source_code: str
    field_signature_name: List[str]
    method_signature_name: List[str]
    simple_method_signature_name_map: Dict[str, str]
    class_path: str


@dataclass
class MethodSignature:
    class_signature_name: str
    method_source_code: str
    usaged_fields: List[str]
    usage_method_signature_name: List[str]



@dataclass
class FieldSignature:
    field_class_signature_name: str
    field_name: str
    field_signature_name: str
    field_source_code: str
    



class JavaProjectAnalyzer:
    def __init__(self):
        self.class_signatures: Dict[str, ClassSignature] = {}
        self.method_signatures: Dict[str, MethodSignature] = {}
        self.field_signatures: Dict[str, FieldSignature] = {}
        
        # 方法名索引，用于快速查找方法调用
        # 格式: {class_signature_name: [method_signature_name]}
        self.method_name_index: Dict[str, List[str]] = {}
        
        # 方法名到方法签名的快速索引，用于高效查找
        # 格式: {method_name: [method_signature_name]}
        self.method_name_lookup: Dict[str, List[str]] = {}
        
        # 类方法索引，用于快速查找类中的方法
        # 格式: {class_signature_name: [method_signature_name]}
        self.class_method_index: Dict[str, List[str]] = {}

        self._method_signatures_keys = set()
        self._method_signatures_map = {}  # key: 移除括号的方法名, value: 完整方法签名
        
        # Java关键字和系统类，用于排除误判的方法调用
        self.java_keywords = {
            'if', 'for', 'while', 'switch', 'return', 'new', 'super', 'this', 'System', 'List', 'Optional', 'out', 'isPresent', 'get',
            'set', 'add', 'remove', 'contains', 'size', 'isEmpty', 'clear', 'iterator', 'toString', 'equals', 'hashCode',
            'clone', 'finalize', 'wait', 'notify', 'notifyAll', 'getClass', 'print', 'println', 'printf', 'format',
            'parse', 'valueOf', 'substring', 'length', 'charAt', 'indexOf', 'lastIndexOf', 'replace', 'split',
            'trim', 'toLowerCase', 'toUpperCase', 'startsWith', 'endsWith', 'contains', 'matches', 'replaceAll',
            'append', 'insert', 'delete', 'reverse', 'capacity', 'ensureCapacity', 'setLength', 'charAt',
            'put', 'get', 'remove', 'containsKey', 'containsValue', 'keySet', 'values', 'entrySet', 'clear',
            'add', 'offer', 'poll', 'peek', 'element', 'remove', 'contains', 'size', 'isEmpty', 'clear',
            'push', 'pop', 'peek', 'empty', 'search', 'capacity', 'trimToSize', 'ensureCapacity'
        }
        
        # 预编译正则表达式以提高性能
        self._method_pattern = re.compile(
            r'(?:@\w+(?:\s*\([^)]*\))?\s*\n\s*)*(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{',
            re.MULTILINE
        )
        self._annotation_pattern = re.compile(r'@\w+(?:\s*\([^)]*\))?')
        
        # 包名匹配
        self._package_pattern = re.compile(r'package\s+([\w.]+);')
        
        # import语句匹配
        self._import_pattern = re.compile(r'import\s+(?:static\s+)?([\w.*]+);')
        
        # 类和接口定义匹配
        self._class_pattern = re.compile(r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?(?:class|interface)\s+(\w+)(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{')
        self._class_pattern_simple = re.compile(r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?(?:class|interface)\s+\w+(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{')
        
        # 字段匹配 - 优化版本
        self._field_pattern = re.compile(r'(?:private|public|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*[=;]')
        self._field_name_pattern = re.compile(r'[\w<>\[\]]+\s+(\w+)\s*[=;]')
        
        # 类级别字段匹配 - 更精确的模式
        self._class_level_field_pattern = re.compile(
            r'(?:^|\n)\s*'  # 行首或换行后的空白
            r'(?:@\w+(?:\s*\([^)]*\))?\s*\n\s*)*'  # 注解
            r'(?:public|private|protected)?\s*'  # 访问修饰符
            r'(?:static\s+)?(?:final\s+)?'  # static/final修饰符
            r'[\w<>\[\]]+\s+'  # 类型
            r'(\w+)\s*'  # 字段名
            r'(?:=\s*[^;]*)?\s*;',  # 可选的初始化和分号
            re.MULTILINE
        )
        
        # 方法签名匹配
        self._method_signature_pattern = re.compile(r'((?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\))')
        self._method_return_type_pattern = re.compile(r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+\s*\([^)]*\))')
        
        # 参数匹配
        self._param_pattern = re.compile(r'\(([^)]*)\)')
        self._param_type_name_pattern = re.compile(r'([\w<>\[\]]+(?:\.\.\.)?)\s+\w+')
        
        # 方法调用匹配
        self._method_call_pattern = re.compile(r'(\w+)\.(\w+)\s*\(')
        self._method_name_pattern = re.compile(r'(\w+)\s*\(')
        
        # 注解匹配
        self._annotation_valid_pattern = re.compile(r'@\w+')
        
        # 空行清理
        self._empty_lines_pattern = re.compile(r'\n\s*\n\s*\n+')
        
        # 从环境变量读取包路径过滤关键词配置
        package_filter_keywords_str = os.environ.get('CODE_CALL_PACKAGE_FILE_FILTER_KEYWORDS', '.util.,.test.,.dto.,.model.,.vo.,.test,.domain.,.entity.,.enums.')
        self.PACKAGE_FILTER_KEYWORDS = [kw.strip() for kw in package_filter_keywords_str.split(',') if kw.strip()]

        # 从环境变量读取类过滤关键词配置
        class_filter_keywords_str = os.environ.get('CODE_CALL_CHAIN_JAVA_CLASS_FILTER_KEYWORDS', '.util.,.test.,.dto.,.model.,.vo.,.test,.domain.,.entity.,.enums.')
        self.CLASS_FILTER_KEYWORDS = [kw.strip() for kw in class_filter_keywords_str.split(',') if kw.strip()]

        # 从环境变量读取过滤关键词配置
        method_filter_keywords_str = os.environ.get('CODE_CALL_CHAIN_JAVA_METHOD_FILTER_KEYWORDS', '.getcode(),getbyid')
        self.METHOD_FILTER_KEYWORDS = [kw.strip() for kw in method_filter_keywords_str.split(',') if kw.strip()]

    
    def analyze_project(self, project_path: str) -> Tuple[Dict[str, ClassSignature], 
                                                         Dict[str, MethodSignature], 
                                                         Dict[str, FieldSignature]]:
        """
        分析Java项目目录，解析所有.java文件
        
        Args:
            project_path: Java项目根目录路径
            
        Returns:
            Tuple包含三个字典：
            - class_signatures: key为class_signature_name, value为ClassSignature
            - method_signatures: key为method_signature_name, value为MethodSignature  
            - field_signatures: key为field_signature_name, value为FieldSignature
        """
        self.class_signatures.clear()
        self.method_signatures.clear()
        self.field_signatures.clear()
        
        # 保存项目根目录路径，用于计算相对路径
        self.project_path = project_path

        start_time = time.time()

        # 遍历项目目录，找到所有.java文件
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('.java'):
                    file_path = os.path.join(root, file)
                    self._analyze_java_file(file_path)
        field_analysis_time = time.time() - start_time

        logger.info(
            f"分析java_file ，耗时: {field_analysis_time:.3f}秒")

        # 构建方法名索引，用于快速查找方法调用
        self._build_method_name_index()
        
        # 构建类方法索引，用于快速查找类中的方法
        self._build_class_method_index()

              # 为 self.method_signatures 建立 key 的 map 索引，提高查找效率
        # key: 移除括号的方法名, value: 完整方法签名
        self._build_simple_method_sig_map()

        # 分析所有方法之间的调用关系
        start_time = time.time()

        for  method_source_code,method_sig in self.method_signatures.items():
            # 使用正则表达式分析方法调用
            used_methods = self._analyze_method_method_usage(
                method_sig.method_source_code,
                method_sig.usaged_fields,
                method_sig.class_signature_name

            )
            
            # 更新MethodSignature中的usage_method_signature_name
            method_sig.usage_method_signature_name = used_methods

        method_analysis_time = time.time() - start_time
        if method_analysis_time > 1.0:
            logger.info(f"方法调用关系分析完成，耗时: {method_analysis_time:.3f}秒")
        
        return self.class_signatures, self.method_signatures, self.field_signatures

    def _build_simple_method_sig_map(self):
        self._method_signatures_map = {}
        for method_sig_key in self.method_signatures.keys():
            # 移除括号及其内容，例如：
            # com.qnvip.qwen.bizService.impl.FeishuDocSyncBizServiceImpl.writeLocalAndConvertToMarkdown(ExportTaskDownloadResponse, Function<Path, TeamBookDocDataDO>)
            # 转换为：
            # com.qnvip.qwen.bizService.impl.FeishuDocSyncBizServiceImpl.writeLocalAndConvertToMarkdown
            method_name_without_params = method_sig_key.split('(')[0]
            if method_name_without_params not in self._method_signatures_map:
                self._method_signatures_map[method_name_without_params] = []
            self._method_signatures_map[method_name_without_params].append(method_sig_key)

    def format_java_code(self, code: str) -> str:
        """
        简化格式化 Java 代码
        2个以上连续换行变成2个
        
        Args:
            code: 要格式化的Java代码字符串
            
        Returns:
            格式化后的Java代码字符串
        """
        if not code or not code.strip():
            return code
        # 清理多余的空行，将2个以上连续换行变成2个
        code = self._empty_lines_pattern.sub('\n\n', code)
        return code.strip()

    def _analyze_java_file(self, file_path: str):
        """分析单个Java文件"""
        try:
            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析文件基本信息
            # 计算相对于项目根目录的路径
            class_path = os.path.relpath(file_path, self.project_path)
            # 将路径分隔符统一为正斜杠，确保跨平台兼容
            class_path = class_path.replace(os.sep, '/')
            
            # 解析包名
            package_match = self._package_pattern.search(content)
            package_name = package_match.group(1) if package_match else ""
            
            # 解析import语句
            import_mappings = self._parse_imports(content)
            
            file_info = {
                'class_path': class_path,
                'package_name': package_name,
                'import_mappings': import_mappings
            }
            
            # 分析所有类
            # 查找所有类定义（包括前面的注释）
            class_matches = self._class_pattern.finditer(content)
            
            for class_match in class_matches:
                self._analyze_single_class(content, class_match, file_info)
                
        except Exception as e:
            logger.error(f"解析文件 {file_path} 时出错: {e}")

    def _parse_imports(self, content: str) -> Dict[str, str]:
        """
        解析Java文件中的import语句，返回类名到完整包名的映射
        
        Args:
            content: Java文件内容
            
        Returns:
            Dict[str, str]: 类名到完整包名的映射，例如 {"User" -> "com.example.model.User"}
        """
        import_mappings = {}
        
        # 查找所有import语句
        import_matches = self._import_pattern.finditer(content)
        
        for match in import_matches:
            import_statement = match.group(1)
            
            # 处理通配符import，如 import com.example.model.*;
            if import_statement.endswith('.*'):
                # 对于通配符import，我们无法直接映射，需要在实际使用时处理
                continue
            
            # 提取类名（最后一个点号后的部分）
            if '.' in import_statement:
                class_name = import_statement.split('.')[-1]
                import_mappings[class_name] = import_statement
        
        return import_mappings

    def _generate_impl_signatures(self, class_signature_name: str) -> List[str]:
        """
        为给定的类签名生成包含 Impl 结尾的实现类版本
        
        Args:
            class_signature_name: 原始类签名，如 "com.qnvip.qwen.service.ChatHistoryCommentService"
            
        Returns:
            List[str]: 包含原始签名和 Impl 版本的列表
        """
        signatures = [class_signature_name]
        
        # 如果类名不包含 Impl 结尾，则添加 Impl 版本
        if not class_signature_name.endswith('Impl'):
            impl_signature = class_signature_name + 'Impl'
            signatures.append(impl_signature)
        
        return signatures

    def _resolve_field_type_package(self, field_type: str, import_mappings: Dict[str, str], current_class_signature_name: str) -> str:
        """
        根据字段类型和import信息确定正确的包名
        
        Args:
            field_type: 字段类型，如 "User", "List<User>", "String"
            import_mappings: import映射，类名到完整包名的映射
            current_class_signature_name: 当前类的完整签名名称
            
        Returns:
            字段类型的完整包名
        """
        if not field_type:
            return current_class_signature_name
        
        # 处理泛型类型，如 List<User> -> User
        base_type = field_type
        if '<' in field_type:
            # 提取泛型参数
            generic_start = field_type.find('<')
            generic_end = field_type.rfind('>')
            if generic_start != -1 and generic_end != -1:
                generic_content = field_type[generic_start + 1:generic_end]
                # 对于泛型，我们主要关心泛型参数的类型
                # 这里简化处理，只取第一个泛型参数
                if ',' in generic_content:
                    base_type = generic_content.split(',')[0].strip()
                else:
                    base_type = generic_content.strip()
        
        # 处理数组类型，如 String[] -> String
        if base_type.endswith('[]'):
            base_type = base_type[:-2]
        
        # 处理基本类型和常见类型
        basic_types = ['String', 'Integer', 'Long', 'Double', 'Float', 'Boolean', 'Date', 'List', 'Map', 'Set', 'ArrayList', 'HashMap', 'HashSet']
        if base_type in basic_types:
            # 对于基本类型，使用当前类的包名
            return current_class_signature_name
        
        # 检查import映射中是否有这个类型
        if base_type in import_mappings:
            return import_mappings[base_type]
        
        # 如果import映射中没有，假设是同一个包中的类型
        current_package = '.'.join(current_class_signature_name.split('.')[:-1])
        return f"{current_package}.{base_type}"

    def _analyze_single_class(self, content: str, class_match, file_info: Dict[str, str]):
        """分析单个类"""
        class_name = class_match.group(1)
        class_signature_name = f"{file_info['package_name']}.{class_name}" if file_info['package_name'] else class_name
        
        # 过滤检查：包路径过滤
        if file_info['package_name']:
            for filter_keyword in self.PACKAGE_FILTER_KEYWORDS:
                if filter_keyword in file_info['package_name'].lower():
                    # logger.debug(f"过滤包路径: {file_info['package_name']} (包含关键词: {filter_keyword})")
                    return
        
        # 过滤检查：类名过滤
        for filter_keyword in self.CLASS_FILTER_KEYWORDS:
            if filter_keyword in class_signature_name.lower():
                # logger.debug(f"过滤类: {class_signature_name} (包含关键词: {filter_keyword})")
                return
        
        # 提取类的内容（包括前面的注释）
        class_start = class_match.start()
        class_content_with_comments = self._extract_class_content_with_comments(content, class_start)
        
        # 分析字段
        start_time = time.time()
        field_names = self._analyze_class_fields(class_content_with_comments, class_signature_name, file_info['import_mappings'])
        field_analysis_time = time.time() - start_time
        if field_analysis_time > 0.5:
            logger.info(f"分析类 {class_signature_name} 字段完成，耗时: {field_analysis_time:.3f}秒，字段数量: {len(field_names)}")
        
        # 分析方法
        start_time = time.time()
        method_names = self._analyze_class_methods(class_content_with_comments, class_signature_name, field_names)
        method_analysis_time = time.time() - start_time
        if method_analysis_time > 0.5:
            logger.info(f"分析类 {class_signature_name} 方法完成，耗时: {method_analysis_time:.3f}秒，方法数量: {len(method_names)}")
        
        # 创建类签名
        start_time = time.time()
        self._create_class_signature(class_content_with_comments, class_signature_name, field_names, method_names, file_info['class_path'])
        signature_creation_time = time.time() - start_time
        if signature_creation_time > 0.5:
            logger.info(f"创建类 {class_signature_name} 签名完成，耗时: {signature_creation_time:.3f}秒")



    def _analyze_class_fields(self, class_content: str, class_signature_name: str, import_mappings: Dict[str, str]) -> List[str]:
        """分析类中的字段"""
        start_time = time.time()
        
        fields = self._extract_fields(class_content)
        extract_time = time.time() - start_time
        
        field_names = []
        process_start_time = time.time()
        
        for field in fields:
            # 从字段代码中提取字段名
            match = self._field_name_pattern.search(field)
            field_name = match.group(1) if match else ""
            
            # 从字段代码中提取字段类型
            field_type = self._extract_field_type(field)
            
            # 根据字段类型和import信息确定正确的包名
            field_class_signature_name = self._resolve_field_type_package(field_type, import_mappings, class_signature_name)
            
            # 构建字段签名名称，包含原始版本和 Impl 版本
            field_class_signatures = self._generate_impl_signatures(field_class_signature_name)
            
            for field_class_sig in field_class_signatures:
                field_signature_name = f"{field_class_sig}.{field_name}"
                field_names.append(field_signature_name)
                
                self.field_signatures[field_signature_name] = FieldSignature(
                    field_class_signature_name=field_class_sig,
                    field_name=field_name,
                    field_signature_name=field_signature_name,
                    field_source_code=self.format_java_code(field.strip())
                )
        
        process_time = time.time() - process_start_time
        total_time = time.time() - start_time
        
        if total_time > 0.5:
            logger.info(f"分析类 {class_signature_name} 字段耗时过长 - 总耗时: {total_time:.3f}秒，提取字段: {extract_time:.3f}秒，处理字段: {process_time:.3f}秒，字段数量: {len(field_names)}")
        
        return field_names

    def _analyze_class_methods(self, class_content: str, class_signature_name: str, field_names: List[str]) -> List[str]:
        """分析类中的方法 - 原始正则表达式方法"""
        methods = self._extract_methods(class_content)
        method_names = []
        
        for method in methods:
            method_signature = self._extract_method_signature(method)
            
            # 为类签名生成原始版本和 Impl 版本
            class_signatures = self._generate_impl_signatures(class_signature_name)
            
            for class_sig in class_signatures:
                method_signature_name = f"{class_sig}.{method_signature}"
                
                # 过滤检查：方法名过滤
                should_filter = False
                for filter_keyword in self.METHOD_FILTER_KEYWORDS:
                    if filter_keyword in method_signature_name.lower():
                        # logger.debug(f"过滤方法: {method_signature_name} (包含关键词: {filter_keyword})")
                        should_filter = True
                        break
                
                if should_filter:
                    continue
                
                method_names.append(method_signature_name)
                
                # 分析方法中使用的字段
                used_fields = self._analyze_method_field_usage(method, field_names)
                
                # 创建MethodSignature，稍后更新调用的方法信息
                self.method_signatures[method_signature_name] = MethodSignature(
                    class_signature_name=class_sig,
                    method_source_code=self.format_java_code(method.strip()),
                    usaged_fields=used_fields,
                    usage_method_signature_name=[]  # 稍后更新
                )
        
        return method_names











    def _create_class_signature(self, class_content: str, class_signature_name: str, 
                               field_names: List[str], method_names: List[str], class_path: str):
        """创建类签名"""
        # 简化实现：直接使用类内容，只保留类定义和注释部分
        # 提取类定义行和注释
        simple_class = self._extract_simple_class_source_code(class_content)
        
        # 从完整的方法签名中提取简单的方法签名名称
        simple_method_signature_name_map = self._extract_simple_method_signature_names(method_names)
        
        self.class_signatures[class_signature_name] = ClassSignature(
            class_signature_name=class_signature_name,
            class_source_code=simple_class,
            field_signature_name=field_names,
            method_signature_name=method_names,
            simple_method_signature_name_map=simple_method_signature_name_map,
            class_path=class_path
        )
    
    def _extract_simple_method_signature_names(self, method_names: List[str]) -> Dict[str, str]:
        """
        从完整的方法签名中提取简单的方法签名名称，返回一个map，key为method_signature_name，value为simple_method_name
        
        Args:
            method_names: 完整的方法签名名称列表，例如：
                ["com.qnvip.qwen.dal.dao.impl.ChatHistoryCommentDaoServiceImpl.page(IPage<ChatHistoryCommentDO>, ChatHistoryCommentQueryDTO)"]
        
        Returns:
            简单的方法签名名称map，例如：
                {"com.qnvip.qwen.dal.dao.impl.ChatHistoryCommentDaoServiceImpl.page(IPage<ChatHistoryCommentDO>, ChatHistoryCommentQueryDTO)": "page"}
        """
        simple_method_signature_name_map = {}
        
        for method_name in method_names:
            # 提取方法名部分（不包含参数列表和括号）
            # 例如：com.qnvip.qwen.dal.dao.impl.ChatHistoryCommentDaoServiceImpl.page(IPage<ChatHistoryCommentDO>, ChatHistoryCommentQueryDTO)
            # 需要提取：page
            
            # 找到最后一个点号的位置，获取方法名和参数部分
            last_dot_index = method_name.rfind('.')
            if last_dot_index != -1:
                method_with_params = method_name[last_dot_index + 1:]
                # 找到括号的位置，只取方法名部分
                paren_index = method_with_params.find('(')
                if paren_index != -1:
                    simple_method_name = method_with_params[:paren_index]
                else:
                    simple_method_name = method_with_params
                simple_method_signature_name_map[method_name] = simple_method_name
            else:
                # 如果没有找到点号，直接使用方法名（去掉括号）
                paren_index = method_name.find('(')
                if paren_index != -1:
                    simple_method_name = method_name[:paren_index]
                else:
                    simple_method_name = method_name
                simple_method_signature_name_map[method_name] = simple_method_name
        
        return simple_method_signature_name_map
    
    def _extract_simple_class_source_code(self, class_content: str) -> str:
        """
        提取类的签名，只保留类定义和注释，移除字段和方法
        
        Args:
            class_content: 类的完整内容
            
        Returns:
            只包含类定义和注释的类签名
        """
        if not class_content:
            return class_content
        
        # 找到类定义开始的位置
        class_match = self._class_pattern_simple.search(class_content)
        if not class_match:
            return class_content
        
        class_start = class_match.start()
        
        # 提取类定义之前的注释部分
        comment_part = class_content[:class_start]
        
        # 提取类定义行（包括继承和实现）
        class_definition = class_match.group(0)
        
        # 组合结果：注释 + 类定义 + 结束大括号
        class_signature = comment_part + class_definition + "\n}"
        
        return class_signature
    
    def _extract_class_content_with_comments(self, content: str, class_start: int) -> str:
        """提取类的完整内容（包括前面的注释）"""
        # 首先找到类定义开始的位置
        brace_count = 0
        start_brace = False
        class_end = class_start
        
        for i in range(class_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    class_end = i + 1
                    break
        
        # 向前查找类定义之前的注释
        comment_start = self._find_class_comment_start(content, class_start)
        
        # 确保注释开始位置不为负数
        if comment_start < 0:
            comment_start = 0
        
        # 提取包含注释的类内容
        class_content_with_comments = content[comment_start:class_end]
        
        return class_content_with_comments
    
    def _find_class_comment_start(self, content: str, class_start: int) -> int:
        """查找类定义之前的注释开始位置"""
        # 从类定义开始位置向前查找
        pos = class_start - 1
        
        # 跳过空白字符
        while pos >= 0 and content[pos].isspace():
            pos -= 1
        
        # 检查是否有行注释 //
        line_comment_pos = pos
        while line_comment_pos >= 0:
            if content[line_comment_pos] == '\n':
                break
            line_comment_pos -= 1
        
        # 检查行注释
        if line_comment_pos >= 0:
            line_start = line_comment_pos + 1
            line_content = content[line_start:pos + 1].strip()
            if line_content.startswith('//'):
                # 继续向前查找更多行注释
                while line_comment_pos >= 0:
                    prev_line_end = line_comment_pos
                    line_comment_pos -= 1
                    while line_comment_pos >= 0 and content[line_comment_pos] != '\n':
                        line_comment_pos -= 1
                    
                    if line_comment_pos >= 0:
                        line_start = line_comment_pos + 1
                        line_content = content[line_start:prev_line_end].strip()
                        if line_content.startswith('//'):
                            pos = line_start
                        else:
                            break
                    else:
                        break
        
        # 检查是否有块注释 /* */
        block_comment_start = self._find_block_comment_start(content, pos)
        if block_comment_start >= 0:
            pos = block_comment_start
        
        return pos
    
    def _find_block_comment_start(self, content: str, end_pos: int) -> int:
        """查找块注释的开始位置"""
        # 从指定位置向前查找 /* */ 或 /** */
        pos = end_pos
        while pos >= 1:
            if content[pos] == '/' and content[pos - 1] == '*':
                # 找到 */ 结束标记，继续向前查找 /* 或 /** 开始标记
                pos -= 2
                while pos >= 1:
                    if content[pos] == '*' and content[pos - 1] == '/':
                        # 检查是否是 /** 格式（Javadoc注释）
                        if pos >= 2 and content[pos - 2] == '*':
                            return pos - 2  # 返回 /** 的开始位置
                        else:
                            return pos - 1  # 返回 /* 的开始位置
                    pos -= 1
                break
            pos -= 1
        
        return -1
    
    def _extract_class_content(self, content: str, class_start: int) -> str:
        """提取类的完整内容"""
        brace_count = 0
        start_brace = False
        class_content = ""
        
        for i in range(class_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    class_content = content[class_start:i+1]
                    break
        
        return class_content
    
    def _extract_fields(self, class_content: str) -> List[str]:
        """提取类中的字段定义"""
        fields = []
        
        # 首先分析方法的位置，创建排除区域
        method_regions = self._get_method_regions(class_content)
        
        # 使用预编译的正则表达式找到所有可能的字段定义
        field_matches = self._class_level_field_pattern.finditer(class_content)
        
        for match in field_matches:
            field_start = match.start()
            field_text = match.group(0)
            
            # 检查字段是否在任何方法区域内
            if not self._is_in_method_region(field_start, method_regions):
                fields.append(field_text)
        
        return fields
    
    def _get_method_regions(self, class_content: str) -> List[Tuple[int, int]]:
        """获取所有方法的位置区域"""
        method_regions = []
        method_matches = self._method_pattern.finditer(class_content)
        
        for match in method_matches:
            method_start = match.start()
            method_end = self._find_method_end(class_content, method_start)
            if method_end > method_start:
                method_regions.append((method_start, method_end))
        
        return method_regions
    
    def _find_method_end(self, content: str, method_start: int) -> int:
        """找到方法的结束位置"""
        brace_count = 0
        start_brace = False
        
        for i in range(method_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    return i + 1
        
        return method_start
    
    def _is_in_method_region(self, position: int, method_regions: List[Tuple[int, int]]) -> bool:
        """检查位置是否在方法区域内"""
        for start, end in method_regions:
            if start <= position <= end:
                return True
        return False

    def _extract_methods(self, class_content: str) -> List[str]:
        """提取类中的方法定义"""
        methods = []
        
        # 使用预编译的正则表达式匹配所有方法定义（包括带注解和不带注解的）
        method_matches = self._method_pattern.finditer(class_content)
        
        for match in method_matches:
            method_start = match.start()
            method_content = self._extract_method_content_optimized(class_content, method_start)
            if method_content:
                methods.append(method_content)
        
        return methods
    
    def _extract_method_content_optimized(self, content: str, method_start: int) -> str:
        """提取方法的完整内容（包括前面的注解）- 优化版本"""
        # 找到方法体的结束位置
        brace_count = 0
        start_brace = False
        method_end = method_start
        
        for i in range(method_start, len(content)):
            char = content[i]
            if char == '{':
                if not start_brace:
                    start_brace = True
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if start_brace and brace_count == 0:
                    method_end = i + 1
                    break
        
        # 向前查找注解开始位置 - 使用优化的算法
        annotation_start = self._find_annotation_start_optimized(content, method_start)
        
        return content[annotation_start:method_end]
    
    def _find_method_annotation_start(self, content: str, method_start: int) -> int:
        """查找方法定义之前的注解开始位置"""
        # 从方法定义开始位置向前查找
        pos = method_start - 1
        
        # 跳过空白字符
        while pos >= 0 and content[pos].isspace():
            pos -= 1
        
        # 检查是否有行注释 //
        line_comment_pos = pos
        while line_comment_pos >= 0:
            if content[line_comment_pos] == '\n':
                break
            line_comment_pos -= 1
        
        # 检查行注释
        if line_comment_pos >= 0:
            line_start = line_comment_pos + 1
            line_content = content[line_start:pos + 1].strip()
            if line_content.startswith('//'):
                # 继续向前查找更多行注释
                while line_comment_pos >= 0:
                    prev_line_end = line_comment_pos
                    line_comment_pos -= 1
                    while line_comment_pos >= 0 and content[line_comment_pos] != '\n':
                        line_comment_pos -= 1
                    
                    if line_comment_pos >= 0:
                        line_start = line_comment_pos + 1
                        line_content = content[line_start:prev_line_end].strip()
                        if line_content.startswith('//'):
                            pos = line_start
                        else:
                            break
                    else:
                        break
        
        # 检查是否有块注释 /* */
        block_comment_start = self._find_block_comment_start(content, pos)
        if block_comment_start >= 0:
            pos = block_comment_start
        
        # 检查是否有注解 @Annotation
        annotation_start = self._find_annotation_start(content, pos)
        if annotation_start >= 0:
            pos = annotation_start
        
        return pos + 1
    
    def _find_annotation_start_optimized(self, content: str, method_start: int) -> int:
        """查找注解的开始位置 - 优化版本，避免包含字段定义"""
        # 从方法开始位置向前查找，最多查找200个字符
        search_start = max(0, method_start - 200)
        search_content = content[search_start:method_start]
        
        # 使用预编译的正则表达式查找所有注解
        annotations = list(self._annotation_pattern.finditer(search_content))
        
        if not annotations:
            return method_start
        
        # 从最后一个注解开始，向前检查是否属于方法定义
        # 需要确保注解后面紧跟的是方法定义，而不是字段定义
        for i in range(len(annotations) - 1, -1, -1):
            annotation = annotations[i]
            annotation_start = search_start + annotation.start()
            
            # 使用辅助方法判断注解是否属于方法定义
            if self._is_method_annotation(content, annotation_start, method_start):
                return annotation_start
        
        # 如果没有找到合适的方法注解，返回方法开始位置
        return method_start
    
    def _is_method_annotation(self, content: str, annotation_start: int, method_start: int) -> bool:
        """判断注解是否属于方法定义"""
        # 获取注解后面到方法开始之间的内容
        between_content = content[annotation_start:method_start].strip()
        
        # 如果中间内容包含分号，说明注解属于字段定义
        if ';' in between_content:
            return False
            
        # 检查是否匹配方法定义模式
        # 方法定义通常包含：修饰符 + 返回类型 + 方法名 + 参数列表 + {
        method_def_pattern = r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+\w+\s*\([^)]*\)\s*\{'
        return bool(re.search(method_def_pattern, between_content))
    
    def _find_annotation_start(self, content: str, end_pos: int) -> int:
        """查找注解的开始位置 - 优化版本"""
        # 限制搜索范围，避免在大型文件中搜索过远
        search_start = max(0, end_pos - 500)
        search_content = content[search_start:end_pos]
        
        # 使用 rfind 快速找到最后一个 @ 符号的位置
        last_at_pos = search_content.rfind('@')
        if last_at_pos == -1:
            return end_pos
        
        # 计算在原始内容中的位置
        actual_pos = search_start + last_at_pos
        
        # 验证这是一个有效的注解（简单检查）
        # 从 @ 位置开始，查找注解的结束位置
        annotation_end = actual_pos + 1
        while (annotation_end < len(content) and 
               annotation_end < actual_pos + 100 and  # 限制注解长度
               not content[annotation_end].isspace() and 
               content[annotation_end] not in ';{'):
            annotation_end += 1
        
        # 检查注解是否有效（包含字母数字字符）
        annotation_text = content[actual_pos:annotation_end]
        if self._annotation_valid_pattern.match(annotation_text):
            return actual_pos
        
        return end_pos
    

    
    
    def _extract_method_signature(self, method_code: str) -> str:
        """从方法代码中提取完整的方法签名（移除返回类型和参数名，只保留方法名和参数类型）"""
        # 匹配方法签名的开始部分（返回类型 + 方法名 + 参数列表）
        match = self._method_signature_pattern.search(method_code)
        if match:
            signature = match.group(1).strip()
            # 移除参数名，保留参数类型
            signature = self._remove_parameter_names(signature)
            # 移除返回类型，只保留方法名和参数类型
            return_type_match = self._method_return_type_pattern.search(signature)
            signature = return_type_match.group(1).strip() if return_type_match else signature
            return signature
        return ""
    

    
    def _remove_parameter_names(self, signature: str) -> str:
        """移除方法签名中的参数名，保留参数类型"""
        # 匹配参数列表部分
        match = self._param_pattern.search(signature)
        if not match:
            return signature
        
        params_str = match.group(1)
        if not params_str.strip():
            return signature
        
        # 分割参数
        params = [p.strip() for p in params_str.split(',')]
        new_params = []
        
        for param in params:
            if param.strip():
                # 匹配参数类型和名称：type name 或 type... name
                param_match = self._param_type_name_pattern.match(param)
                if param_match:
                    param_type = param_match.group(1)
                    new_params.append(param_type)
                else:
                    # 如果没有匹配到，保留原参数（可能是泛型或其他复杂情况）
                    new_params.append(param)
        
        # 重建签名
        new_params_str = ', '.join(new_params)
        new_signature = self._param_pattern.sub(f'({new_params_str})', signature)
        return new_signature

    def _analyze_method_field_usage(self, method_code: str, field_names: List[str]) -> List[str]:
        """分析方法中使用的字段"""
        used_fields = []
        
        for field_name in field_names:
            # 提取字段的简单名称（去掉类名前缀）
            simple_field_name = field_name.split('.')[-1]
            
            # 检查方法中是否使用了这个字段
            # 匹配 this.fieldName 或直接 fieldName
            field_usage_pattern = rf'\b(?:this\.)?{re.escape(simple_field_name)}\b'
            if re.search(field_usage_pattern, method_code):
                used_fields.append(field_name)
        
        return used_fields

    def _analyze_method_method_usage(self, method_code: str, usaged_fields: List[str],class_signature_name:str) -> List[str]:
        """
        分析方法中调用的其他方法

        Args:
            method_code: 方法源代码
            usaged_fields: 方法中使用的字段列表

        Returns: 方法中调用的方法列表
        """
        method_calls = []
        
        # 遍历usaged_fields，分析每个字段的方法调用
        for field_signature_name in usaged_fields:
            # 从字段签名中提取field_class_signature_name和field_name
            if field_signature_name not in self.field_signatures:
                continue
                
            field_sig = self.field_signatures[field_signature_name]
            field_class_signature_name = field_sig.field_class_signature_name
            field_name = field_sig.field_name
            
            # 从self.class_signatures中获取对应的simple_method_signature_name_map
            if field_class_signature_name not in self.class_signatures:
                continue
                
            class_sig = self.class_signatures[field_class_signature_name]
            simple_method_signature_name_map = class_sig.simple_method_signature_name_map
            
            # 遍历simple_method_signature_name_map，检查字段方法调用
            for method_signature_name, simple_method_name in simple_method_signature_name_map.items():
                # field_name与simple_method_name用"."连接得到字段方法调用
                field_method_call = f"{field_name}.{simple_method_name}"
                
                # 在method_code中查找字段方法调用
                if field_method_call in method_code:
                    method_calls.append(method_signature_name)
        
        return method_calls
    
    def _extract_method_name_from_code(self, method_code: str) -> str:
        """从方法代码中提取方法名"""
        if not method_code:
            return ""
        
        # 使用正则表达式匹配方法定义，提取方法名
        # 匹配模式：修饰符 + 返回类型 + 方法名 + 参数列表
        method_def_pattern = r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)'
        match = re.search(method_def_pattern, method_code)
        
        if match:
            return match.group(1)
        
        return ""
    
    def _extract_current_method_name(self, method_sig) -> str:
        """从方法签名中提取当前方法名（保持向后兼容）"""
        if not method_sig or not hasattr(method_sig, 'method_source_code'):
            return ""
        
        return self._extract_method_name_from_code(method_sig.method_source_code)







    
    def _get_field_types(self, field_signatures: List[str]) -> List[str]:
        """
        从字段签名中提取字段类型（包含包信息）
        
        Args:
            field_signatures: 字段签名列表
            
        Returns:
            字段类型列表（包含包信息）
        """
        field_types = []
        for field_sig_name in field_signatures:
            if field_sig_name in self.field_signatures:
                field_sig = self.field_signatures[field_sig_name]
                # 使用字段签名中的field_class_signature_name，这个已经包含了正确的包信息
                field_class_name = field_sig.field_class_signature_name
                
                # 从字段源代码中提取类型
                field_type = self._extract_field_type(field_sig.field_source_code)
                if field_type:
                    # 对于基本类型，直接跳过
                    basic_types = ['String', 'Integer', 'Long', 'Double', 'Float', 'Boolean', 'Date', 'List', 'Map', 'Set', 'ArrayList', 'HashMap', 'HashSet']
                    if field_type in basic_types:
                        continue
                    else:
                        # 对于自定义类型，使用已经解析好的field_class_signature_name
                        field_types.append(field_class_name)
        return field_types
    
    def _extract_field_type(self, field_source_code: str) -> str:
        """
        从字段源代码中提取字段类型
        
        Args:
            field_source_code: 字段源代码
            
        Returns:
            字段类型
        """
        # 使用正则表达式匹配字段类型
        # 匹配模式：修饰符 + 类型 + 字段名
        type_pattern = re.compile(r'(?:private|public|protected)?\s*(?:static\s+)?(?:final\s+)?([\w<>\[\]]+)\s+(\w+)\s*[=;]')
        match = type_pattern.search(field_source_code)
        if match:
            field_type = match.group(1).strip()
            field_name = match.group(2).strip()
            
            # 验证提取的类型和字段名是否合理
            if field_type and field_name and field_type != field_name:
                return field_type
        return ""
    
    def _is_method_belongs_to_field_types(self, method_sig_name: str, field_types: List[str]) -> bool:
        """
        检查方法是否属于指定的字段类型
        
        Args:
            method_sig_name: 方法签名名称
            field_types: 字段类型列表
            
        Returns:
            如果方法属于字段类型之一则返回True
        """
        # 提取方法所属的类名
        # 方法签名格式：package.class.method(params)
        parts = method_sig_name.split('.')
        if len(parts) < 2:
            return False
            
        # 获取方法所属的类名（去掉方法名部分）
        class_name = '.'.join(parts[:-1])
        
        # 检查类名是否匹配字段类型
        for field_type in field_types:
            # 处理泛型类型，如 List<String> -> List
            base_type = field_type.split('<')[0] if '<' in field_type else field_type
            # 处理数组类型，如 String[] -> String
            base_type = base_type.replace('[]', '')
            
            # 处理基本类型和常见类型
            if base_type in ['String', 'Integer', 'Long', 'Double', 'Float', 'Boolean', 'Date', 'List', 'Map', 'Set']:
                # 对于基本类型和常见类型，检查方法是否属于这些类型
                if base_type in class_name:
                    return True
            else:
                # 对于自定义类型，检查类名是否完全匹配
                if class_name == base_type:
                    return True
                # 或者检查类名是否以字段类型结尾（处理包名不同的情况）
                elif class_name.endswith('.' + base_type.split('.')[-1]):
                    return True
                
        return False

    def _build_method_name_index(self):
        """构建方法名到方法签名的索引"""
        self.method_name_index.clear()
        self.method_name_lookup.clear()
        
        for method_sig_name in self.method_signatures.keys():
            # 提取类签名名称
            class_signature_name = '.'.join(method_sig_name.split('.')[:-1])
            
            # 使用class_signature_name作为第一层key，方法签名作为value的list
            if class_signature_name not in self.method_name_index:
                self.method_name_index[class_signature_name] = []
            self.method_name_index[class_signature_name].append(method_sig_name)
            
            # 提取方法名用于快速查找
            method_part = method_sig_name.split('.')[-1]
            method_name_match = self._method_name_pattern.search(method_part)
            if method_name_match:
                method_name = method_name_match.group(1)
            else:
                method_name = method_part.split('(')[0]
            
            # 构建方法名到方法签名的快速索引
            if method_name not in self.method_name_lookup:
                self.method_name_lookup[method_name] = []
            self.method_name_lookup[method_name].append(method_sig_name)

    def _build_class_method_index(self):
        """构建类方法索引，用于快速查找类中的方法"""
        self.class_method_index.clear()
        
        for class_signature_name, class_sig in self.class_signatures.items():
            # 使用class_signature_name作为key，method_signature_name列表作为value
            if class_signature_name not in self.class_method_index:
                self.class_method_index[class_signature_name] = []
            
            # 将类中的所有方法签名添加到索引中
            for method_signature_name in class_sig.method_signature_name:
                self.class_method_index[class_signature_name].append(method_signature_name)


def analyze_java_project(project_path: str) -> Tuple[Dict[str, ClassSignature], 
                                                    Dict[str, MethodSignature], 
                                                    Dict[str, FieldSignature]]:
    """
    分析Java项目的便捷函数
    
    Args:
        project_path: Java项目根目录路径
        
    Returns:
        Tuple包含三个字典：
        - class_signatures: key为class_signature_name, value为ClassSignature
        - method_signatures: key为method_signature_name, value为MethodSignature  
        - field_signatures: key为field_signature_name, value为FieldSignature
    """
    analyzer = JavaProjectAnalyzer()
    return analyzer.analyze_project(project_path)


def save_and_analysis_to_json(project_path: str, output_file: str = "1_analyze_project.json"):
    """
    分析Java项目并保存结果到JSON文件
    
    Args:
        project_path: Java项目根目录路径
        output_file: 输出JSON文件路径，默认为"1_analyze_project.json"
        
    Returns:
        Dict: 包含分析结果的字典
    """
    class_sigs, method_sigs, field_sigs = analyze_java_project(project_path)
    
    # 将分析结果合并为一个字典
    analysis_result = {
        "class_signatures": {name: asdict(sig) for name, sig in class_sigs.items()},
        "method_signatures": {name: asdict(sig) for name, sig in method_sigs.items()},
        "field_signatures": {name: asdict(sig) for name, sig in field_sigs.items()}
    }
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"创建输出目录: {output_dir}")
    
    # 写入JSON文件
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
    
    logger.info(f"分析结果已保存到 {output_file}")
    logger.info(f"类数量: {len(class_sigs)}, 方法数量: {len(method_sigs)}, 字段数量: {len(field_sigs)}")
    
    return analysis_result


def analyze_java_project_static(project_info: dict, workspace_path: str = None) -> Optional[str]:
    """
    分析Java项目（静态方法）
    
    Args:
        project_info: 项目信息
        workspace_path: 工作空间路径
        
    Returns:
        分析结果文件路径，失败时返回None
    """
    try:
        project_path = project_info['path']
        project_name = project_info['name']
        output_file = FileUtil.get_project_file_path(workspace_path, project_name, "1_analyze_project.json")
        
        # 检查项目路径是否存在
        if not os.path.exists(project_path):
            logger.warn(f"项目路径不存在，跳过Java项目分析: {project_path}")
            return None

        start_time = time.time()
        logger.info(f"开始分析Java项目: {project_path}")
        
        # 使用java_project_analyzer分析项目
        class_sigs, method_sigs, field_sigs = analyze_java_project(project_path)
        
        # 将分析结果合并为一个字典
        analysis_result = {
            "class_signatures": {name: asdict(sig) for name, sig in class_sigs.items()},
            "method_signatures": {name: asdict(sig) for name, sig in method_sigs.items()},
            "field_signatures": {name: asdict(sig) for name, sig in field_sigs.items()}
        }
        
        # 使用FileUtil保存结果，它会自动创建目录
        if not FileUtil.save_json_to_file(analysis_result, output_file):
            logger.error(f"保存分析结果失败: {output_file}")
            return None
        
        analysis_duration = time.time() - start_time
        logger.info(f"Java项目分析完成，耗时: {analysis_duration:.2f}秒")
        logger.info(f"结果保存到: {output_file}")
        logger.info(f"分析统计 - 类数量: {len(class_sigs)}")
        logger.info(f"分析统计 - 方法数量: {len(method_sigs)}")
        logger.info(f"分析统计 - 字段数量: {len(field_sigs)}")
        
        return output_file

    except Exception as e:
        logger.error(f"Java项目分析过程中发生错误: {str(e)}")
        return None


