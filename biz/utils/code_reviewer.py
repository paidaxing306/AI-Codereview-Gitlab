import abc
import os
import re
import time
from typing import Dict, Any, List

import yaml
from jinja2 import Template

from biz.llm.factory import Factory
from biz.utils.log import logger
from biz.utils.token_util import count_tokens, truncate_text_by_tokens


class BaseReviewer(abc.ABC):
    """代码审查基类"""

    def __init__(self, prompt_key: str):
        self.client = Factory().getClient()
        self.prompts = self._load_prompts(prompt_key, os.getenv("REVIEW_STYLE", "professional"))

    def _load_prompts(self, prompt_key: str, style="professional") -> Dict[str, Any]:
        """加载提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            # 在打开 YAML 文件时显式指定编码为 UTF-8，避免使用系统默认的 GBK 编码。
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get(prompt_key, {})

                # 使用Jinja2渲染模板
                def render_template(template_str: str) -> str:
                    return Template(template_str).render(style=style)

                system_prompt = render_template(prompts["system_prompt"])
                user_prompt = render_template(prompts["user_prompt"])

                return {
                    "system_message": {"role": "system", "content": system_prompt},
                    "user_message": {"role": "user", "content": user_prompt},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载提示词配置失败: {e}")
            raise Exception(f"提示词配置加载失败: {e}")

    def call_llm(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM 进行代码审核"""
        logger.info(f"向 AI 发送代码 Review 请求, messages: {messages}")
        
        # 记录开始时间
        start_time = time.time()
        review_result = self.client.completions(messages=messages)
        # 计算耗时
        elapsed_time = time.time() - start_time
        
        logger.info(f"LLM调用耗时: {elapsed_time:.3f}秒")
        logger.info(f"收到 AI 返回结果: {review_result}")
        return review_result

    @abc.abstractmethod
    def review_code(self, *args, **kwargs) -> str:
        """抽象方法，子类必须实现"""
        pass


class CodeReviewer(BaseReviewer):
    """代码 Diff 级别的审查"""

    def __init__(self):
        super().__init__("code_review_prompt")

    def review_and_strip_code(self, changes_text: str, commits_text: str = "") -> str:
        """
        Review判断changes_text超出取前REVIEW_MAX_TOKENS个token，超出则截断changes_text，
        调用review_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param changes_text:
        :param commits_text:
        :return:
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 10000))
        # 如果changes为空,打印日志
        if not changes_text:
            logger.info("代码为空, diffs_text = %", str(changes_text))
            return "代码为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断changes_text
        tokens_count = count_tokens(changes_text)
        if tokens_count > review_max_tokens:
            changes_text = truncate_text_by_tokens(changes_text, review_max_tokens)

        review_result = self.review_code(changes_text, commits_text).strip()
        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_code(self, diffs_text: str, commits_text: str = "") -> str:
        """Review 代码并返回结果"""
        messages = [
            self.prompts["system_message"],
            {
                "role": "user",
                "content": self.prompts["user_message"]["content"].format(
                    diffs_text=diffs_text, commits_text=commits_text
                ),
            },
        ]
        return self.call_llm(messages)

    def review_and_analyze_call_chain_code(self, prompt_text: str, language: str = "") -> str:
        """
        调用链分析代码审查
        Review判断prompt_text超出取前REVIEW_MAX_TOKENS个token，超出则截断prompt_text，
        调用review_call_chain_code方法，返回review_result，如果review_result是markdown格式，则去掉头尾的```
        :param prompt_text: 调用链分析的提示词文本
        :param language: 文件路径，用于确定文件类型
        :return: 审查结果
        """
        # 如果超长，取前REVIEW_MAX_TOKENS个token
        review_max_tokens = int(os.getenv("REVIEW_MAX_TOKENS", 100000))
        # 如果prompt为空,打印日志
        if not prompt_text:
            logger.info("调用链分析提示词为空, prompt_text = %s", str(prompt_text))
            return "调用链分析提示词为空"

        # 计算tokens数量，如果超过REVIEW_MAX_TOKENS，截断prompt_text
        tokens_count = count_tokens(prompt_text)
        if tokens_count > review_max_tokens:
            prompt_text = truncate_text_by_tokens(prompt_text, review_max_tokens)

        review_result = self.review_call_chain_code(prompt_text, language).strip()

        if review_result.startswith("```markdown") and review_result.endswith("```"):
            return review_result[11:-3].strip()
        return review_result

    def review_call_chain_code(self, prompt_text: str, file_path: str = "") -> str:
        """调用链分析代码审查并返回结果"""
        # 加载调用链分析的提示词配置
        call_chain_prompts = self._load_call_chain_prompts(file_path)
        
        messages = [
            call_chain_prompts["system_message"],
            {
                "role": "user",
                "content": call_chain_prompts["user_message"]["content"].format(context=prompt_text),
            },
        ]
        return self.call_llm(messages)

    def _get_file_type(self, file_path: str) -> str:
        """根据文件路径确定文件类型"""
        if not file_path:
            return "java"  # 默认使用java类型
        
        file_extension = file_path.lower().split('.')[-1] if '.' in file_path else ""
        
        # Java文件
        if file_extension == "java":
            return "java"
        
        # Web前端文件
        if file_extension in ["js", "html", "vue", "jsx", "tsx"]:
            return "web"
        
        # 默认使用java类型
        return "java"

    def _load_call_chain_prompts(self, language: str = "") -> Dict[str, Any]:
        """加载调用链分析的提示词配置"""
        prompt_templates_file = "conf/prompt_templates.yml"
        try:
            with open(prompt_templates_file, "r", encoding="utf-8") as file:
                prompts = yaml.safe_load(file).get("call_chain_analysis", {})

                if language not in prompts["system_prompt"]:
                    logger.warning(f"未找到文件类型 {language} 的system_prompt配置，使用默认java配置")
                    language = "java"

                return {
                    "system_message": {"role": "system", "content":  prompts["system_prompt"][language]},
                    "user_message": {"role": "user", "content":  prompts["item_prompt"]},
                }
        except (FileNotFoundError, KeyError, yaml.YAMLError) as e:
            logger.error(f"加载调用链分析提示词配置失败: {e}")
            # 如果加载失败，使用默认的代码审查提示词
            return self.prompts


    @staticmethod
    def parse_review_score(review_text: str) -> int:
        """解析 AI 返回的 Review 结果，返回评分"""
        if not review_text:
            return 0
        match = re.search(r"总分[:：]\s*(\d+)分?", review_text)
        return int(match.group(1)) if match else 0

