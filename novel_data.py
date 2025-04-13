# novel_data.py
# -*- coding: utf-8 -*-
import json
import os
import logging
import re # 从 main_window 移到这里可能更合适，如果解析逻辑依赖它
from typing import List, Dict, Optional, Any

class NovelData:
    """存储和管理小说的所有相关数据。"""
    def __init__(self):
        """初始化空的小说数据结构。"""
        self.topic: Optional[str] = None
        self.genre: Optional[str] = None
        self.target_chapters: int = 10
        self.words_per_chapter: int = 3000
        self.core_seed: Optional[str] = None
        self.character_dynamics: Optional[str] = None
        self.world_building: Optional[str] = None
        self.plot_architecture: Optional[str] = None
        self.chapter_list: List[Dict[str, Any]] = []
        self.chapter_texts: Dict[int, str] = {}
        # **** REMOVED self.global_summary ****
        # **** ADDED cumulative_summaries ****
        self.cumulative_summaries: Dict[int, str] = {} # 存储每章的累积摘要 {章节号: 摘要文本}
        self.character_state: Optional[str] = None
        # 临时数据
        self.current_chapter_writing: Optional[int] = None
        self.current_chapter_short_summary: Optional[str] = None
        self.knowledge_keywords: Optional[str] = None
        self.filtered_knowledge: Optional[str] = None
        self.unsaved_changes: bool = False

    def _parse_chapter_list_string(self, blueprint_string: str) -> List[Dict[str, Any]]:
        """尝试解析章节蓝图字符串为结构化列表。"""
        chapters = []
        current_chapter = {}
        last_parsed_number = 0
        try:
            lines = blueprint_string.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue

                match_num_title = re.match(r"第\s*(\d+)\s*章\s*-\s*(.*)", line)
                if match_num_title:
                    if current_chapter.get('title') or current_chapter.get('number'):
                        if 'number' not in current_chapter:
                            current_chapter['number'] = last_parsed_number + 1
                            logging.warning(f"为章节 '{current_chapter.get('title', '未知')[:20]}...' 分配了递增编号 {current_chapter['number']}")
                        chapters.append(current_chapter)
                    chapter_number = int(match_num_title.group(1))
                    title = match_num_title.group(2).strip()
                    current_chapter = {'number': chapter_number, 'title': title}
                    last_parsed_number = chapter_number
                    continue

                if current_chapter:
                    # 使用更健壮的分割方式，避免因冒号不匹配导致错误
                    parts = line.split("：", 1)
                    if len(parts) == 2:
                        key_text = parts[0].strip()
                        value_text = parts[1].strip()
                        if key_text == "本章定位": current_chapter['role'] = value_text
                        elif key_text == "核心作用": current_chapter['purpose'] = value_text
                        elif key_text == "悬念密度": current_chapter['suspense_level'] = value_text
                        elif key_text == "伏笔操作": current_chapter['foreshadowing'] = value_text
                        elif key_text == "认知颠覆": current_chapter['plot_twist_level'] = value_text
                        elif key_text == "涉及角色": current_chapter['characters_involved'] = value_text
                        elif key_text == "关键物品": current_chapter['key_items'] = value_text
                        elif key_text == "场景地点": current_chapter['scene_location'] = value_text
                        elif key_text == "时间限制": current_chapter['time_constraint'] = value_text
                        elif key_text == "本章简述": current_chapter['summary'] = value_text

            if current_chapter.get('title') or current_chapter.get('number'):
                if 'number' not in current_chapter:
                     current_chapter['number'] = last_parsed_number + 1
                     logging.warning(f"为最后一个章节 '{current_chapter.get('title', '未知')[:20]}...' 分配了递增编号 {current_chapter['number']}")
                chapters.append(current_chapter)

            current_num = 0
            assigned_numbers = set(ch.get('number') for ch in chapters if isinstance(ch.get('number'), int))
            for ch in chapters:
                if 'number' not in ch or not isinstance(ch.get('number'), int):
                    while current_num + 1 in assigned_numbers: current_num += 1
                    ch['number'] = current_num + 1
                    assigned_numbers.add(ch['number'])
                    logging.warning(f"为无编号章节 '{ch.get('title', '未知')[:20]}...' 分配了编号 {ch['number']}")
                current_num = max(current_num, ch.get('number', 0))

            logging.info(f"尝试解析 {len(chapters)} 个章节蓝图。")
            chapters.sort(key=lambda x: x.get('number', float('inf')))
            return chapters
        except Exception as e:
            logging.error(f"解析章节蓝图时出错: {e}\n原始文本片段:\n{blueprint_string[:500]}")
            chapters.sort(key=lambda x: x.get('number', float('inf')))
            return chapters


    def update_chapter_list(self, blueprint_string: str, is_chunked: bool = False, start_chapter: Optional[int] = None):
        """用新的蓝图字符串更新或追加章节列表。"""
        new_chapters = self._parse_chapter_list_string(blueprint_string)
        if not new_chapters: logging.warning("解析出的新章节列表为空，不进行更新。"); return

        if is_chunked and start_chapter is not None:
            original_count = len(self.chapter_list)
            self.chapter_list = [ch for ch in self.chapter_list if ch.get('number', -1) < start_chapter]
            removed_count = original_count - len(self.chapter_list)
            logging.info(f"分块更新：移除了 {removed_count} 个章节号 >= {start_chapter} 的旧章节。")
            valid_new_chapters = [ch for ch in new_chapters if ch.get('number', -1) >= start_chapter]
            if len(valid_new_chapters) != len(new_chapters): logging.warning(f"解析出的 {len(new_chapters) - len(valid_new_chapters)} 个新章节编号小于起始章节号 {start_chapter}，已被过滤。")
            self.chapter_list.extend(valid_new_chapters)
            logging.info(f"分块更新：添加了 {len(valid_new_chapters)} 个新章节。")
            self.chapter_list.sort(key=lambda x: x.get('number', float('inf')))
            logging.info("分块更新：章节列表已重新排序。")
        else:
            self.chapter_list = new_chapters
            logging.info("章节列表已完全替换。")
        self.unsaved_changes = True
        logging.info(f"章节列表已更新，当前总章节数: {len(self.chapter_list)}")

    def get_chapter_info(self, chapter_number: int) -> Optional[Dict[str, Any]]:
        """根据章节号获取章节蓝图信息字典。"""
        for chapter in self.chapter_list:
            if chapter.get('number') == chapter_number: return chapter
        return None

    def get_previous_chapter_text(self, current_chapter_number: int) -> Optional[str]:
        """获取上一章节的文本内容。"""
        previous_number = current_chapter_number - 1
        return self.chapter_texts.get(previous_number)

    def get_previous_chapter_excerpt(self, current_chapter_number: int, num_paragraphs: int = 1) -> str:
        """获取上一章节结尾的指定段落数作为摘要。"""
        prev_text = self.get_previous_chapter_text(current_chapter_number)
        if not prev_text: return "无前文章节内容。"
        paragraphs = [p.strip() for p in prev_text.strip().split('\n') if p.strip()]
        if not paragraphs: return "前文章节内容为空。"
        start_index = max(0, len(paragraphs) - num_paragraphs)
        excerpt = "\n".join(paragraphs[start_index:])
        return excerpt if excerpt else "前文章节内容为空或无法提取摘要。"

    def get_combined_text_last_n_chapters(self, current_chapter_number: int, n: int = 3) -> str:
        """获取当前章节之前的 N 章的合并文本。"""
        combined = []
        start_chapter = max(1, current_chapter_number - n)
        for i in range(start_chapter, current_chapter_number):
             text = self.chapter_texts.get(i)
             if text:
                 info = self.get_chapter_info(i)
                 title = info.get('title', f'第{i}章') if info else f'第{i}章'
                 combined.append(f"--- 第{i}章《{title}》---\n{text}\n--- 章节结束 ---")
        return "\n\n".join(combined) if combined else "无前续章节内容。"

    def get_chapter_list_string_for_prompt(self, end_chapter_exclusive: Optional[int] = None) -> str:
        """获取用于提示词的、格式化的现有章节列表字符串（仅标题和简述）。"""
        if not self.chapter_list: return "无"
        relevant_chapters = [ch for ch in self.chapter_list if end_chapter_exclusive is None or ch.get('number', float('inf')) < end_chapter_exclusive]
        if not relevant_chapters: return "无"
        relevant_chapters.sort(key=lambda x: x.get('number', float('inf')))
        output_lines = [f"第 {ch.get('number', '?')} 章 - {ch.get('title', '未知标题')}: {ch.get('summary', '无简述')}" for ch in relevant_chapters]
        return "\n".join(output_lines)

    # **** ADDED: Get cumulative summary for previous chapter ****
    def get_previous_cumulative_summary(self, current_chapter_number: int) -> str:
        """获取上一章的累积摘要。"""
        previous_number = current_chapter_number - 1
        return self.cumulative_summaries.get(previous_number, "") # 返回空字符串如果不存在

    def save_to_file(self, filepath: str):
        """将小说数据保存到 JSON 文件。"""
        data_to_save = {
            "topic": self.topic, "genre": self.genre, "target_chapters": self.target_chapters,
            "words_per_chapter": self.words_per_chapter, "core_seed": self.core_seed,
            "character_dynamics": self.character_dynamics, "world_building": self.world_building,
            "plot_architecture": self.plot_architecture, "chapter_list": self.chapter_list,
            "chapter_texts": self.chapter_texts,
            # **** SAVE cumulative_summaries ****
            "cumulative_summaries": self.cumulative_summaries,
            "character_state": self.character_state,
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            self.unsaved_changes = False
            logging.info(f"小说数据已成功保存到: {filepath}")
        except Exception as e:
            logging.error(f"保存小说数据到文件失败: {e}")

    def load_from_file(self, filepath: str) -> bool:
        """从 JSON 文件加载小说数据。"""
        if not os.path.exists(filepath): logging.warning(f"加载失败：文件 {filepath} 不存在。"); return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            self.topic = loaded_data.get("topic")
            self.genre = loaded_data.get("genre")
            self.target_chapters = loaded_data.get("target_chapters", 10)
            self.words_per_chapter = loaded_data.get("words_per_chapter", 3000)
            self.core_seed = loaded_data.get("core_seed")
            self.character_dynamics = loaded_data.get("character_dynamics")
            self.world_building = loaded_data.get("world_building")
            self.plot_architecture = loaded_data.get("plot_architecture")
            self.chapter_list = loaded_data.get("chapter_list", [])
            self.chapter_texts = {int(k): v for k, v in loaded_data.get("chapter_texts", {}).items()}
            # **** LOAD cumulative_summaries (convert keys to int) ****
            self.cumulative_summaries = {int(k): v for k, v in loaded_data.get("cumulative_summaries", {}).items()}
            self.character_state = loaded_data.get("character_state")
            # 重置临时数据
            self.current_chapter_writing = None
            self.current_chapter_short_summary = None
            self.knowledge_keywords = None
            self.filtered_knowledge = None
            self.unsaved_changes = False

            logging.info(f"小说数据已成功从 {filepath} 加载。")
            return True
        except json.JSONDecodeError as e:
            logging.error(f"加载小说数据失败：无效的 JSON 文件 {filepath}。错误: {e}"); return False
        except Exception as e:
            logging.exception(f"加载小说数据失败: {filepath}"); return False