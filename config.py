# config.py
# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量获取 API 密钥
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 如果没有在 .env 文件中设置，你可以在这里硬编码（非常不推荐！）
# if not GEMINI_API_KEY:
#     GEMINI_API_KEY = "YOUR_API_KEY_HERE" # 非常不推荐

if not GEMINI_API_KEY:
    raise ValueError("未找到 Gemini API 密钥。请在 .env 文件或环境变量中设置 GEMINI_API_KEY。")

# 可以添加其他配置，例如模型名称
# GEMINI_MODEL_NAME = "gemini-2.5-pro-exp-03-25" # 或者 'gemini-pro' 等适合文本生成的模型
GEMINI_MODEL_NAME = "gemini-2.0-flash" # 或者 'gemini-pro' 等适合文本生成的模型
