import re
import os
from typing import List, Dict, Tuple
from biz.utils.log import logger
from biz.service.call_chain_analysis.java_project_analyzer import JavaProjectAnalyzer


class MethodSignatureExtractor:
    """
    方法签名提取器
    用于从Git diff中提取变更的方法签名
    """

    def __init__(self):
        self.java_analyzer = JavaProjectAnalyzer()

    def get_signatures_from_changes(self, changes: List[Dict]) -> List[str]:
        """
        从changes中提取所有变更的方法签名

        Args:
            changes:
            [{
  "diff" : "\n\nimport javax.annotation.Resource;\n\nimport org.springframework.stereotype.Service;\n\nimport com.baomidou.mybatisplus.core.metadata.IPage;\nimport com.qnvip.orm.base.BaseServiceImpl;\nimport com.qnvip.qwen.dal.dao.ChatHistoryCommentDaoService;\nimport com.qnvip.qwen.dal.dto.ChatHistoryCommentDTO;\nimport com.qnvip.qwen.dal.dto.ChatHistoryCommentQueryDTO;\nimport com.qnvip.qwen.dal.entity.ChatHistoryCommentDO;\nimport com.qnvip.qwen.dal.mapper.ChatHistoryCommentMapper;\nimport com.qnvip.qwen.util.CopierUtil;\n\nimport lombok.RequiredArgsConstructor;\nimport lombok.extern.slf4j.Slf4j;\n\n/**\n * 聊天记录评论表 存储层实现\n *\n * @author lichaojie\n * @description powered by qnvip\n * @date 2025/06/04 11:37\n */\n@Slf4j\n@Service\n@RequiredArgsConstructor\npublic class ChatHistoryCommentDaoServiceImpl extends BaseServiceImpl<ChatHistoryCommentMapper, ChatHistoryCommentDO>\n    implements ChatHistoryCommentDaoService {\n    @Resource\n    private ChatHistoryCommentMapper chatHistoryCommentMapper;\n\n    @Override\n    public IPage<ChatHistoryCommentDTO> page(IPage<ChatHistoryCommentDO> page, ChatHistoryCommentQueryDTO query) {\n        IPage<ChatHistoryCommentDO> pageData =\n            lambdaQuery().setEntity(CopierUtil.copy(query, ChatHistoryCommentDO.class)).page(page);\n        return pageData.convert(e -> CopierUtil.copy(e, ChatHistoryCommentDTO.class));\n    }\n}",
  "new_path" : "qnvip-qwen-acl/src/main/java/com/qnvip/qwen/dal/dao/impl/ChatHistoryCommentDaoServiceImpl.java"
},...]

        Returns:
            List[str]: 方法签名列表
        """
        changed_method_signatures = []

        for change in changes:
            if isinstance(change, dict):
                diff_content = change.get('diff', '')
                new_path = change.get('new_path', '')

                if diff_content and new_path.endswith('.java'):


                    # 从diff中提取方法签名（现在返回完整的方法签名，包含包名和类名）
                    method_signatures = self._extract_method_signature_from_diff(diff_content)

                    # 直接添加完整的方法签名
                    for method_sig in method_signatures:
                        changed_method_signatures.append(method_sig)
                        logger.info(f"发现变更的方法签名: {method_sig}")



        return changed_method_signatures

    def _extract_method_signature_from_diff(self, diff_content: str) -> List[str]:
        """
        从diff内容中提取方法签名
        尽可能重用JavaProjectAnalyzer的format_java_code和_extract_methods方法

        Args:
            diff_content: diff内容

        Returns:
            List[str]: 方法签名列表
        """
        method_signatures = []

        # 使用JavaProjectAnalyzer的format_java_code方法格式化代码
        formatted_diff = self.java_analyzer.format_java_code(diff_content)

        # 参考_analyze_java_file方法提取包名和类名
        package_match = re.search(r'package\s+([\w.]+);', formatted_diff)
        package_name = package_match.group(1) if package_match else ""
        
        # 查找所有类定义
        class_pattern = r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s+extends\s+[^{]+)?(?:\s+implements\s+[^{]+)?\s*\{'
        class_matches = re.finditer(class_pattern, formatted_diff)
        
        for class_match in class_matches:
            class_name = class_match.group(1)
            class_signature_name = f"{package_name}.{class_name}" if package_name else class_name
            
            # 提取类的内容（从类开始到结束）
            class_start = class_match.start()
            class_content = self.java_analyzer._extract_class_content(formatted_diff, class_start)
            
            # 直接重用JavaProjectAnalyzer的_extract_methods方法提取方法内容
            extracted_methods = self.java_analyzer._extract_methods(class_content)

            # 对每个提取的方法，使用JavaProjectAnalyzer的方法签名提取逻辑
            for method_content in extracted_methods:
                method_signature = self.java_analyzer._extract_method_signature(method_content)
                if method_signature:
                    # 构建完整的方法签名（包含包名和类名）
                    method_signature_name = f"{class_signature_name}.{method_signature}"
                    method_signatures.append(method_signature_name)

        return method_signatures


def get_method_signatures(changes: List[Dict]) -> List[str]:
    """
    便捷函数：从changes中提取变更的方法签名

    Args:
        changes: Git变更列表

    Returns:
        List[str]: 变更的方法签名列表
    """
    extractor = MethodSignatureExtractor()
    return extractor.get_signatures_from_changes(changes)
