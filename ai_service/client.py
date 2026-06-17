# 强制清空所有代理环境变量，解决Flask运行时代理拦截超时
import os
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["NO_PROXY"] = "*"
os.environ["ALL_PROXY"] = ""

import requests
import json
import re
import logging
from config import Config

# 日志配置，控制台打印完整AI返回内容方便排错
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self):
        self.api_key = Config.DOUBAN_API_KEY
        self.api_url = Config.DOUBAN_API_URL
        self.model_ep_id = Config.DOUBAN_ENDPOINT_ID
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.timeout = 60  # 超时60秒，AI生成多道题时可能较慢
        self.max_retries = 2  # 超时自动重试1次

    def _clean_json_text(self, raw_text: str) -> str:
        """清洗AI返回文本，剔除markdown、多余换行、外层包装，只保留标准JSON数组"""
        # 移除```json 代码块标记
        raw_text = re.sub(r'```(json)?', '', raw_text)
        raw_text = raw_text.strip()
        # 匹配最外层[]，只提取数组内容，兼容AI额外套对象的情况
        match_res = re.search(r'\[.*\]', raw_text, re.S)
        if match_res:
            return match_res.group()
        return raw_text

    def _send_ark_request(self, prompt: str, temp: float = 0.7, max_tok: int = 2000) -> str:
        """通用火山方舟请求封装，复用逻辑，统一捕获异常"""
        payload = {
            "model": self.model_ep_id,
            "messages": [
                {"role": "system", "content": "你是专业出题阅卷老师，只输出用户要求的标准JSON，不要多余文字、标题、注释、换行说明"},
                {"role": "user", "content": prompt.strip()}
            ],
            "temperature": temp,
            "max_tokens": max_tok
        }
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"API请求（第{attempt}次）...")
                resp = requests.post(
                    url=self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=self.timeout
                )
                logger.info(f"API状态码: {resp.status_code}")
                resp.raise_for_status()  # 4xx/5xx直接抛异常
                resp_data = resp.json()
                raw_content = resp_data["choices"][0]["message"]["content"]
                logger.info(f"AI原始返回文本:\n{raw_content}")
                clean_content = self._clean_json_text(raw_content)
                logger.info(f"清洗后JSON字符串:\n{clean_content}")
                return clean_content
            except requests.exceptions.Timeout as e:
                last_err = e
                logger.warning(f"第{attempt}次请求超时: {str(e)}")
                if attempt < self.max_retries:
                    logger.info("自动重试中...")
                    continue
            except requests.exceptions.RequestException as e:
                err_msg = f"网络请求失败: {str(e)}"
                logger.error(err_msg)
                raise Exception(err_msg)
            except Exception as e:
                err_msg = f"AI接口处理异常: {str(e)}"
                logger.error(err_msg)
                raise Exception(err_msg)
        # 所有重试都超时
        raise Exception(f"网络请求失败（重试{self.max_retries}次均超时）: {str(last_err)}")

    def generate_question(self, major: str, question_type: str, difficulty: str, count: int = 5):
        """AI批量生成考试题目，返回可直接loads的纯JSON数组字符串"""
        # 题型中文映射
        type_labels = {
            'single_choice': '单选题', 'multiple_choice': '多选题',
            'fill_blank': '填空题', 'true_false': '判断题',
            'short_answer': '问答题', 'programming': '编程题',
            'application': '应用题', 'calculation': '计算题',
        }
        type_cn = type_labels.get(question_type, question_type)

        # 针对题型生成不同的字段提示
        if question_type in ('single_choice', 'multiple_choice'):
            field_hint = '选择题：content题干、options字符串数组(4个选项)、answer标准答案、analysis解析'
        elif question_type == 'fill_blank':
            field_hint = '填空题：content题干（空格用____表示）、options为空数组[]、answer标准答案、analysis解析'
        elif question_type == 'true_false':
            field_hint = '判断题：content题干、options为空数组[]、answer填"正确"或"错误"、analysis解析'
        elif question_type == 'programming':
            field_hint = '编程题：content题目要求及输入输出描述、options为空数组[]、answer参考代码、analysis解题思路'
        elif question_type == 'application':
            field_hint = '应用题：content应用场景描述和问题、options为空数组[]、answer完整解答过程、analysis知识点解析'
        elif question_type == 'calculation':
            field_hint = '计算题：content计算要求、options为空数组[]、answer完整计算步骤和结果、analysis公式原理说明'
        else:
            field_hint = '问答题：content题干、options为空数组[]、answer参考答案、analysis解析'

        prompt = f"""
请为【{major}】专业生成{count}道{difficulty}难度的{type_cn}。
严格仅输出JSON数组，禁止任何外层对象、文字说明、markdown、换行注释。
字段规范：{field_hint}
输出模板：
[
    {{
        "content": "题干内容",
        "options": [],
        "answer": "正确答案",
        "analysis": "知识点解析"
    }}
]
        """
        return self._send_ark_request(prompt, temp=0.7, max_tok=3000)

    def grade_answer(self, question_content: str, correct_answer: str, student_answer: str):
        """AI批改作答，返回固定JSON字符串"""
        prompt = f"""
题目：{question_content}
标准答案：{correct_answer}
学生作答：{student_answer}
评分要求：
- 客观题（选择/填空/判断）：完全一致才给满分
- 主观题（问答/编程/应用/计算）：根据思路正确性、完整性、逻辑性给分
仅输出JSON，字段：is_correct(布尔, 主观题意思相近即可为true), score(0-100整数), analysis(简短评语)
示例：{{"is_correct":true,"score":80,"analysis":"思路正确，但缺少边界处理"}}
        """
        return self._send_ark_request(prompt, temp=0.3, max_tok=800)

    def generate_analysis(self, question_content: str, correct_answer: str, student_answer: str):
        """生成详细答题解析"""
        prompt = f"""
题目：{question_content}
标准答案：{correct_answer}
学生作答：{student_answer}
输出详细知识点解析，无需JSON，纯中文文本即可
        """
        return self._send_ark_request(prompt, temp=0.5, max_tok=1200)