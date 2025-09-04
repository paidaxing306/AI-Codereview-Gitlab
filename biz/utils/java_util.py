import tree_sitter_java
from tree_sitter import Language, Parser
from typing import List, Dict, Any


class JavaFieldExtractor:
    """Java类级别字段抽取工具类"""

    def __init__(self):
        self.java_language = Language(tree_sitter_java.language())
        self.parser = Parser(self.java_language)

    def _get_text(self, node, source: bytes) -> str:
        """获取节点的文本内容"""
        return source[node.start_byte:node.end_byte].decode("utf8")

    def _extract_class_fields(self, node, source: bytes) -> List[Dict[str, Any]]:
        """抽取类级别的字段源码"""
        results = []

        if node.type == 'field_declaration':
            # 这是一个字段声明
            field_code = self._get_text(node, source)

            # 尝试获取字段名
            field_name = ""
            for child in node.children:
                if child.type == 'variable_declarator':
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        field_name = self._get_text(name_node, source)
                        break

            # 获取修饰符
            modifiers = []
            for child in node.children:
                if child.type in ['public', 'private', 'protected', 'static', 'final', 'volatile', 'transient']:
                    modifiers.append(child.type)
                elif child.type == 'modifiers':
                    for mod_child in child.children:
                        if mod_child.type in ['public', 'private', 'protected', 'static', 'final', 'volatile',
                                              'transient']:
                            modifiers.append(mod_child.type)

            results.append({
                "name": field_name,
                "modifiers": modifiers,
                "source": field_code.strip()
            })

        # 递归遍历子节点
        for child in node.children:
            results.extend(self._extract_class_fields(child, source))

        return results

    def extract_fields(self, java_source: str) -> List[str]:
        """
        抽取Java类级别字段的源码

        Args:
            java_source: Java源码字符串

        Returns:
            List[str]: 字段源码列表
        """
        try:
            # 将字符串编码为字节
            java_code_bytes = java_source.encode("utf8")

            # 解析Java代码
            tree = self.parser.parse(java_code_bytes)
            root = tree.root_node

            # 抽取字段
            fields = self._extract_class_fields(root, java_code_bytes)

            # 只返回字段源码列表
            return [field["source"] for field in fields]

        except Exception as e:
            print(f"抽取字段时出错: {e}")
            return []

    def extract_fields_with_info(self, java_source: str) -> List[Dict[str, Any]]:
        """
        抽取Java类级别字段的详细信息

        Args:
            java_source: Java源码字符串

        Returns:
            List[Dict[str, Any]]: 包含字段名、修饰符和源码的字典列表
        """
        try:
            # 将字符串编码为字节
            java_code_bytes = java_source.encode("utf8")

            # 解析Java代码
            tree = self.parser.parse(java_code_bytes)
            root = tree.root_node

            # 抽取字段
            return self._extract_class_fields(root, java_code_bytes)

        except Exception as e:
            print(f"抽取字段时出错: {e}")
            return []


# 使用示例
if __name__ == "__main__":
    # 创建抽取器实例
    extractor = JavaFieldExtractor()

    # 示例Java代码
    java_code = '''package com.qnvip.qwen.bizService.impl;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.annotation.Resource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Slf4j
@Service
public class ReCallBizServiceImpl implements ReCallBizService {

    // 在类中定义线程池（确保重用）
    protected static final ExecutorService executorMutilQuestion =
        new ThreadPoolExecutor(9, 27, 60L, TimeUnit.SECONDS, new LinkedBlockingQueue<>(1024),
            new ThreadFactoryBuilder().setNamePrefix("ReCallBizServiceImpl-executor-%d").build(),
            new ThreadPoolExecutor.CallerRunsPolicy());

    protected static final ExecutorService executorRecall =
        new ThreadPoolExecutor(8, 32, 60L, TimeUnit.SECONDS, new LinkedBlockingQueue<>(1024),
            new ThreadFactoryBuilder().setNamePrefix("ReCallBizServiceImpl-executorRecall-%d").build(),
            new ThreadPoolExecutor.CallerRunsPolicy());

    @Resource
    private EsChunkSearchService esChunkSearchService;
    @Resource
    private MilvusChunkDocService milvusChunkDocService;
    @Resource
    private MilvusQaLinkService milvusQaLinkService;
    @Resource
    private FileQaDaoService fileQaDaoService;
    @Resource
    private FileChunkDataDaoService fileChunkDataDaoService;

    @Resource
    private FileOriginDaoService fileOriginDaoService;
    @Resource
    private FileRecallLogService fileRecallLogService;
    @Resource
    private ChunkCacheRedisService chunkCacheRedisService;
    @Resource
    private TeamBookService teamBookService;

    @Resource
    private GraphBizService graphBizService;

    @Value("${rerank.host}")
    private String rerankHost;

    // 其他方法...
}'''

    # 只获取字段源码列表
    field_sources = extractor.extract_fields(java_code)
    print("字段源码列表:")
    for i, source in enumerate(field_sources, 1):
        print(f"{i}. {source}")
        print("-" * 80)

    print(f"\n总共找到 {len(field_sources)} 个类级别字段")

    # 获取详细信息
    print("\n" + "=" * 80)
    print("详细信息:")
    field_details = extractor.extract_fields_with_info(java_code)
    for i, field in enumerate(field_details, 1):
        print(f"   源码: {field['source']}")
        print("-" * 80)
