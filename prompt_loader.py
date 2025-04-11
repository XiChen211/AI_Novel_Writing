# prompt_loader.py
# -*- coding: utf-8 -*-
"""
加载 prompt.py 文件中定义的提示词变量。
"""
try:
    from prompt import (
        summarize_recent_chapters_prompt, knowledge_search_prompt,
        knowledge_filter_prompt, core_seed_prompt, character_dynamics_prompt,
        world_building_prompt, plot_architecture_prompt, chapter_blueprint_prompt,
        chunked_chapter_blueprint_prompt, summary_prompt, create_character_state_prompt,
        update_character_state_prompt, first_chapter_draft_prompt,
        next_chapter_draft_prompt, Character_Import_Prompt,
        summarize_written_chapters_prompt  # **** Import the new prompt ****
    )
    print("提示词加载成功。")
except ImportError as e:
    print(f"错误：无法从 prompt.py 加载提示词。请确保 prompt.py 文件存在且路径正确。{e}")
    exit()
except Exception as e:
    print(f"加载提示词时发生未知错误: {e}")
    exit()

# 将所有导入的提示词放入一个字典，方便按名称访问
prompts = {
    "summarize_recent_chapters": summarize_recent_chapters_prompt,
    "knowledge_search": knowledge_search_prompt,
    "knowledge_filter": knowledge_filter_prompt,
    "core_seed": core_seed_prompt,
    "character_dynamics": character_dynamics_prompt,
    "world_building": world_building_prompt,
    "plot_architecture": plot_architecture_prompt,
    "chapter_blueprint": chapter_blueprint_prompt,
    "chunked_chapter_blueprint": chunked_chapter_blueprint_prompt, # Keep original chunked prompt if needed elsewhere
    "summary_update": summary_prompt,
    "create_character_state": create_character_state_prompt,
    "update_character_state": update_character_state_prompt,
    "first_chapter_draft": first_chapter_draft_prompt,
    "next_chapter_draft": next_chapter_draft_prompt,
    "character_import": Character_Import_Prompt,
    "summarize_written_chapters": summarize_written_chapters_prompt, # **** Add the new prompt ****
}

def get_prompt(name: str) -> str:
    """
    根据名称获取提示词字符串。
    """
    if name in prompts:
        return prompts[name]
    else:
        raise KeyError(f"未找到名为 '{name}' 的提示词。")