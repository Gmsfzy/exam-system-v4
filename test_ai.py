# 清空代理环境变量，避免被代理拦截导致超时
import os
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["NO_PROXY"] = "*"
os.environ["ALL_PROXY"] = ""

import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("DOUBAN_API_KEY")
api_url = os.getenv("DOUBAN_API_URL")
model_id = os.getenv("DOUBAN_ENDPOINT_ID")

print(f"API Key: {api_key[:10]}..." if api_key else "API Key: 未配置!")
print(f"API URL: {api_url}")
print(f"Model ID: {model_id}")
print("-" * 50)

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}

payload = {
    "model": model_id,
    "messages": [
        {"role": "system", "content": "你是专业出题老师，只输出标准JSON"},
        {"role": "user", "content": "生成2道计算机基础单选题，JSON格式输出，包含content/options/answer字段"}
    ],
    "temperature": 0.7,
    "max_tokens": 2000
}

try:
    res = requests.post(api_url, headers=headers, json=payload, timeout=30)
    print(f"状态码: {res.status_code}")

    if res.status_code == 200:
        data = res.json()
        content = data["choices"][0]["message"]["content"]
        print(f"AI 返回内容:\n{content}")
    else:
        print(f"请求失败，响应内容:\n{res.text}")
except requests.exceptions.RequestException as e:
    print(f"网络请求异常: {e}")
except (json.JSONDecodeError, KeyError) as e:
    print(f"解析异常: {e}")
    print(f"原始响应: {res.text}")