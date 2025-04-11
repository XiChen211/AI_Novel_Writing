# utils.py
# -*- coding: utf-8 -*-
import logging

def extract_text_between_markers(text: str, start_marker: str, end_marker: str) -> str:
    """
    从文本中提取位于起始和结束标记之间的内容。

    Args:
        text (str): 包含标记的完整文本。
        start_marker (str): 起始标记。
        end_marker (str): 结束标记。

    Returns:
        str: 提取到的文本，如果未找到标记则返回空字符串。
    """
    try:
        start_index = text.index(start_marker) + len(start_marker)
        end_index = text.index(end_marker, start_index)
        return text[start_index:end_index].strip()
    except ValueError:
        logging.warning(f"未能在文本中找到标记 '{start_marker}' 或 '{end_marker}'。")
        return "" # 或者返回 None，或者原始文本的一部分

# 可以添加更多辅助函数，例如：
# - 验证输入格式
# - 清理 API 返回的文本（例如移除多余的解释）