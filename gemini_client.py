# gemini_client.py
# -*- coding: utf-8 -*-
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL_NAME
import logging # 用于记录日志

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GeminiClient:
    """
    封装与 Google Gemini API 的交互。
    """
    def __init__(self, api_key: str = GEMINI_API_KEY, model_name: str = GEMINI_MODEL_NAME):
        """
        初始化 Gemini 客户端。

        Args:
            api_key (str): Google AI Studio 的 API 密钥。
            model_name (str): 要使用的 Gemini 模型名称。
        """
        if not api_key:
            raise ValueError("API 密钥不能为空。")
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
            logging.info(f"Gemini 客户端初始化成功，使用模型：{model_name}")
        except Exception as e:
            logging.error(f"Gemini 配置失败: {e}")
            raise ConnectionError(f"无法配置 Gemini API: {e}") from e

    def generate_text(self, prompt: str, temperature: float = 0.7, max_output_tokens: int = 8192) -> str:
        """
        使用指定的提示词生成文本。

        Args:
            prompt (str): 发送给模型的提示词。
            temperature (float): 控制生成文本的随机性 (0.0-1.0)。
            max_output_tokens (int): 生成文本的最大 token 数量。

        Returns:
            str: 模型生成的文本。

        Raises:
            Exception: 如果 API 调用失败。
        """
        logging.info(f"向 Gemini 发送请求 (部分提示词): {prompt[:200]}...") # 只记录提示词开头部分
        try:
            # 设置生成配置
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens
            )
            # 发送请求
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                # 可选：添加安全设置
                # safety_settings=[...]
            )

            # 检查是否有响应文本
            if response.parts:
                 # 检查是否有候选内容被阻止
                if not response.candidates:
                     logging.warning("Gemini 响应被阻止。可能原因：安全设置、提示词问题。")
                     # 尝试获取阻止原因 (如果可用)
                     block_reason = "未知"
                     try:
                         if response.prompt_feedback and response.prompt_feedback.block_reason:
                             block_reason = response.prompt_feedback.block_reason.name
                         elif response.candidates and response.candidates[0].finish_reason != 'STOP':
                              block_reason = response.candidates[0].finish_reason.name
                     except Exception:
                         pass # 获取原因失败也没关系
                     return f"错误：Gemini 响应被阻止。原因: {block_reason}。请检查提示词或调整安全设置。"

                generated_text = response.text
                logging.info(f"Gemini 响应接收成功 (部分内容): {generated_text[:200]}...") # 只记录响应开头部分
                return generated_text
            else:
                # 处理没有 parts 的情况，可能因为内容被完全阻止
                logging.warning("Gemini 响应为空或被阻止。")
                # 尝试获取更详细的反馈
                block_reason = "未知"
                finish_reason = "未知"
                try:
                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                        block_reason = response.prompt_feedback.block_reason.name
                    if response.candidates and response.candidates[0].finish_reason != 'STOP':
                         finish_reason = response.candidates[0].finish_reason.name
                except Exception:
                    pass
                return f"错误：Gemini 未返回有效内容。可能原因：内容被阻止 (Block Reason: {block_reason}, Finish Reason: {finish_reason})。请检查提示词。"

        except genai.types.generation_types.BlockedPromptException as bpe:
            logging.error(f"Gemini API 请求失败：提示词被阻止。 {bpe}")
            return f"错误：提示词包含不安全内容，已被 Gemini 阻止。"
        except Exception as e:
            logging.error(f"Gemini API 请求失败: {e}")
            # 可以根据需要进行重试或其他错误处理
            return f"错误：调用 Gemini API 时出错: {e}" # 返回错误信息给调用者