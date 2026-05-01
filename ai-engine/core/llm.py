"""
DeepSeek API 客户端封装（OpenAI 兼容接口，base_url 指向 DeepSeek）
"""
from openai import OpenAI

from core.config import settings


def _client() -> OpenAI:
    return OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )


def chat_with_deepseek(messages, temperature=0.2, max_tokens=1200):
    """
    调用 DeepSeek API 进行对话
    
    Args:
        messages: 消息列表，格式为 [{"role": "user/system", "content": "..."}]
        temperature: 温度参数，控制输出随机性
        max_tokens: 最大生成 token 数
    
    Returns:
        str: AI 生成的回复内容
    """
    resp = _client().chat.completions.create(# 调用 DeepSeek API
        model=settings.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=False,
    )
    return resp.choices[0].message.content or ""#返回第一个回复选项的内容
