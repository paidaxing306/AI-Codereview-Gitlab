import xml.etree.ElementTree as ET
from biz.utils.log import logger


class XmlParser:
    """XML解析工具类"""
    
    @staticmethod
    def parse_review_items(xml_content: str) -> list:
        """
        解析XML格式的审查结果
        
        Args:
            xml_content: XML字符串，包含多个item元素
            
        Returns:
            解析后的dict列表，每个dict包含name、issue、level、content字段
            
        Example:
            输入XML:
            <item>
                <name>UserService.getUser()</name>
                <issue>存在具体的的问题</issue>
                <level>🔴 高</level>
                <content>问题修改建议</content>
            </item>
            
            输出:
            [{"name": "UserService.getUser()", "issue": "存在具体的的问题", "level": "🔴 高", "content": "问题修改建议"}]
        """
        try:
            if not xml_content or not xml_content.strip():
                return []
            
            # 预处理XML内容，将content标签内容包装为CDATA
            xml_to_parse = XmlParser._preprocess_xml_content(xml_content.strip())
            
            try:
                # 尝试直接解析，看是否已经有根元素
                root = ET.fromstring(xml_to_parse)
            except ET.ParseError:
                # 如果解析失败，说明可能没有根元素，添加包装后重试
                wrapped_xml = f"<root>{xml_to_parse}</root>"
                root = ET.fromstring(wrapped_xml)
            
            items = []
            # 遍历所有item元素
            for item_elem in root.findall('item'):
                name = XmlParser._get_element_text(item_elem, 'name')
                issue = XmlParser._get_element_text(item_elem, 'issue')
                level = XmlParser._get_element_text(item_elem, 'level')
                content = XmlParser._get_element_text(item_elem, 'content')
                

                content=content.replace("&lt;", "<")
                content=content.replace("&gt;", ">")
                content=content.replace("&amp;", "&")
 
                # 构造dict对象
                item_dict = {
                    'name': name,
                    'issue': issue,
                    'level': level,
                    'content': content
                }
                items.append(item_dict)
            
            return items
            
        except ET.ParseError as e:
            logger.error(f"XML解析错误: {str(e)}, xml_content: {xml_content}")
            return []
        except Exception as e:
            logger.error(f"解析XML时发生未知错误: {str(e)}, xml_content: {xml_content}")
            return []
    
    @staticmethod
    def _preprocess_xml_content(xml_content: str) -> str:
        """
        预处理XML内容，将content标签中的内容包装为CDATA以避免解析错误
        
        Args:
            xml_content: 原始XML字符串
            
        Returns:
            预处理后的XML字符串
        """
        import re
        
        # 使用正则表达式找到所有content标签及其内容
        def replace_content_with_cdata(match):
            tag_start = match.group(1)  # <content>
            content = match.group(2)    # 标签内容
            tag_end = match.group(3)    # </content>
            
            # 如果内容已经是CDATA，直接返回
            if content.strip().startswith('<![CDATA[') and content.strip().endswith(']]>'):
                return match.group(0)
            
            # 将内容包装为CDATA
            return f"{tag_start}<![CDATA[{content}]]>{tag_end}"
        
        # 匹配content标签及其内容（包括换行符和多行内容）
        pattern = r'(<content>)(.*?)(</content>)'
        processed_xml = re.sub(pattern, replace_content_with_cdata, xml_content, flags=re.DOTALL)
        
        return processed_xml
    
    @staticmethod
    def _get_element_text(parent_elem, tag_name: str) -> str:
        """
        安全获取XML元素的文本内容
        
        Args:
            parent_elem: 父元素
            tag_name: 子元素标签名
            
        Returns:
            元素文本内容，如果元素不存在则返回空字符串
        """
        element = parent_elem.find(tag_name)
        return element.text if element is not None and element.text is not None else ""
