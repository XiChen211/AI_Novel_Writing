# novel_data.py
# -*- coding: utf-8 -*-
import json
import os
import logging # 确保导入 logging
from typing import List, Dict, Optional, Any # 确保导入 typing

# 配置日志 (如果尚未在主程序或其他地方配置，可以在这里添加基础配置)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NovelData:
    """
    存储和管理小说的所有相关数据。
    """
    def __init__(self):
        """初始化空的小说数据结构。"""
        self.topic: Optional[str] = None
        self.genre: Optional[str] = None
        self.target_chapters: int = 10 # 默认目标章节数
        self.words_per_chapter: int = 3000 # 默认每章字数

        self.core_seed: Optional[str] = None
        self.character_dynamics: Optional[str] = None
        self.world_building: Optional[str] = None
        self.plot_architecture: Optional[str] = None

        self.chapter_list: List[Dict[str, Any]] = [] # 存储章节目录信息，例如 [{'number': 1, 'title': '...', 'summary': '...'}, ...]
        self.chapter_texts: Dict[int, str] = {} # 存储每个章节的正文 {chapter_number: text}

        self.global_summary: Optional[str] = "" # 全局前文摘要
        self.character_state: Optional[str] = None # 角色状态文档文本

        # 用于写作过程中的临时数据
        self.current_chapter_writing: Optional[int] = None # 正在写的章节号
        self.current_chapter_short_summary: Optional[str] = None # 当前章节的精准摘要
        self.knowledge_keywords: Optional[str] = None # 知识库检索关键词
        self.filtered_knowledge: Optional[str] = None # 过滤后的知识库内容

        self.unsaved_changes: bool = False # 标记是否有未保存的更改

    def _parse_chapter_list_string(self, blueprint_string: str) -> List[Dict[str, Any]]:
        """
        尝试解析章节蓝图字符串为结构化列表。
        (此函数保持不变，假设它能解析 Gemini 输出的格式)
        """
        chapters = []
        current_chapter = {}
        last_parsed_number = 0 # 用于在无法解析时递增
        try:
            lines = blueprint_string.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line: continue # 跳过空行

                if line.startswith("第") and "章 - " in line:
                    # 尝试解析章节号
                    try:
                        num_str = line.split("章", 1)[0].replace("第", "").strip()
                        chapter_number = int(num_str)
                        last_parsed_number = chapter_number # 记录最后成功解析的编号

                        # 如果已有章节，先保存上一个
                        if current_chapter.get('title'): # 检查是否有内容需要保存
                           if 'number' not in current_chapter: # 如果上一个没解析出编号
                               current_chapter['number'] = last_parsed_number + 1 # 使用递增编号
                               logging.warning(f"为章节 '{current_chapter.get('title', '未知')[:20]}...' 分配了递增编号 {current_chapter['number']}")
                           chapters.append(current_chapter)

                        current_chapter = {'number': chapter_number} # 开始新的章节，直接记录编号
                        try:
                            title_part = line.split(" - ", 1)[1]
                            current_chapter['title'] = title_part.strip()
                        except IndexError:
                            current_chapter['title'] = "未知标题"
                            logging.warning(f"无法从行 '{line}' 解析标题。")

                    except (ValueError, IndexError):
                         logging.warning(f"无法从行 '{line}' 解析章节号。将尝试使用递增值。")
                         if current_chapter.get('title'): # 保存上一个（如果存在）
                             if 'number' not in current_chapter:
                                 current_chapter['number'] = last_parsed_number + 1
                                 logging.warning(f"为章节 '{current_chapter.get('title', '未知')[:20]}...' 分配了递增编号 {current_chapter['number']}")
                             chapters.append(current_chapter)
                         # 开始一个新的章节，但标记为需要后续编号
                         current_chapter = {'title': line} # 暂时将整行存入标题，后续处理
                         # 不在这里设置 chapter_number

                # 解析其他属性，前提是当前 current_chapter 已经初始化（有 title 或 number）
                elif current_chapter:
                    if line.startswith("本章定位："):
                        current_chapter['role'] = line.replace("本章定位：", "").strip()
                    elif line.startswith("核心作用："):
                        current_chapter['purpose'] = line.replace("核心作用：", "").strip()
                    elif line.startswith("悬念密度："):
                        current_chapter['suspense_level'] = line.replace("悬念密度：", "").strip()
                    elif line.startswith("伏笔操作："):
                        current_chapter['foreshadowing'] = line.replace("伏笔操作：", "").strip()
                    elif line.startswith("认知颠覆："):
                        current_chapter['plot_twist_level'] = line.replace("认知颠覆：", "").strip()
                    elif line.startswith("本章简述："):
                        current_chapter['summary'] = line.replace("本章简述：", "").strip()

            # 添加最后一个章节
            if current_chapter.get('title'): # 确保最后一个有内容
                if 'number' not in current_chapter: # 如果最后一个没有解析出编号
                     current_chapter['number'] = last_parsed_number + 1
                     logging.warning(f"为最后一个章节 '{current_chapter.get('title', '未知')[:20]}...' 分配了递增编号 {current_chapter['number']}")
                chapters.append(current_chapter)

            # 再次检查并尝试为没有编号的章节分配递增编号 (可能效果有限)
            current_num = 0
            for i, ch in enumerate(chapters):
                if 'number' not in ch or not isinstance(ch.get('number'), int):
                    # 尝试从前一个章节推断
                    prev_num = chapters[i-1].get('number', current_num) if i > 0 else 0
                    ch['number'] = prev_num + 1
                    logging.warning(f"为章节 '{ch.get('title', '未知')[:20]}...' 分配了推断编号 {ch['number']}")
                current_num = ch['number']


            logging.info(f"尝试解析 {len(chapters)} 个章节蓝图。")
            chapters.sort(key=lambda x: x.get('number', float('inf'))) # 按章节号排序
            return chapters
        except Exception as e:
            logging.error(f"解析章节蓝图时出错: {e}\n原始文本:\n{blueprint_string[:500]}") # 只记录部分文本
            return chapters # 返回部分解析结果

    def update_chapter_list(self, blueprint_string: str, is_chunked: bool = False, start_chapter: Optional[int] = None):
        """
        用新的蓝图字符串更新或追加章节列表。

        Args:
            blueprint_string (str): 从 Gemini 获取的章节蓝图文本。
            is_chunked (bool): 指示这是否是分块生成的一部分。
            start_chapter (Optional[int]): 如果是分块，这是块的起始章节号。
        """
        new_chapters = self._parse_chapter_list_string(blueprint_string)
        if not new_chapters:
            logging.warning("解析出的新章节列表为空，不进行更新。")
            return

        if is_chunked and start_chapter is not None:
            # --- 分块更新逻辑 ---
            # 1. 移除旧列表中从 start_chapter 开始的所有章节 (避免重复或覆盖旧数据)
            original_count = len(self.chapter_list)
            self.chapter_list = [ch for ch in self.chapter_list if ch.get('number', -1) < start_chapter]
            removed_count = original_count - len(self.chapter_list)
            logging.info(f"分块更新：移除了 {removed_count} 个章节号 >= {start_chapter} 的旧章节。")

            # 2. 将新解析的章节（确保它们的编号符合预期范围，虽然解析函数会尝试处理）追加到列表
            #    添加一层检查，确保 new_chapters 里的编号确实 >= start_chapter
            valid_new_chapters = [ch for ch in new_chapters if ch.get('number', -1) >= start_chapter]
            if len(valid_new_chapters) != len(new_chapters):
                logging.warning(f"解析出的 {len(new_chapters) - len(valid_new_chapters)} 个新章节编号小于起始章节号 {start_chapter}，已被过滤。")

            self.chapter_list.extend(valid_new_chapters)
            logging.info(f"分块更新：添加了 {len(valid_new_chapters)} 个新章节。")

            # 3. 重新排序确保章节顺序正确
            self.chapter_list.sort(key=lambda x: x.get('number', float('inf')))
            logging.info("分块更新：章节列表已重新排序。")

        else:
            # --- 完全替换逻辑 ---
            self.chapter_list = new_chapters
            logging.info("章节列表已完全替换。")

        self.unsaved_changes = True
        logging.info(f"章节列表已更新，当前总章节数: {len(self.chapter_list)}")

    def get_chapter_info(self, chapter_number: int) -> Optional[Dict[str, Any]]:
        """根据章节号获取章节信息字典。"""
        for chapter in self.chapter_list:
            if chapter.get('number') == chapter_number:
                return chapter
        return None

    def get_previous_chapter_text(self, current_chapter_number: int) -> Optional[str]:
        """获取上一章节的文本内容。"""
        previous_number = current_chapter_number - 1
        return self.chapter_texts.get(previous_number)

    def get_previous_chapter_excerpt(self, current_chapter_number: int, num_paragraphs: int = 1) -> str:
        """获取上一章节结尾的指定段落数作为摘要。"""
        prev_text = self.get_previous_chapter_text(current_chapter_number)
        if not prev_text:
            return "无前文章节内容。"

        paragraphs = [p.strip() for p in prev_text.strip().split('\n') if p.strip()]
        if not paragraphs:
             return "前文章节内容为空。"

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
        """
        获取用于提示词的、格式化的现有章节列表字符串。

        Args:
            end_chapter_exclusive (Optional[int]): 只包含章节号小于此值的章节。如果为 None，则包含所有章节。

        Returns:
            str: 格式化的字符串，例如 "第1章 - 标题: 简述\n第2章 - 标题: 简述..."
                 如果列表为空，返回 "无"。
        """
        if not self.chapter_list:
            return "无"

        relevant_chapters = self.chapter_list
        if end_chapter_exclusive is not None:
            relevant_chapters = [ch for ch in self.chapter_list if ch.get('number', float('inf')) < end_chapter_exclusive]

        if not relevant_chapters:
             return "无"

        # 排序确保顺序正确（理论上 self.chapter_list 已经是排序的）
        relevant_chapters.sort(key=lambda x: x.get('number', float('inf')))

        output_lines = []
        for chapter in relevant_chapters:
            num = chapter.get('number', '?')
            title = chapter.get('title', '未知标题')
            summary = chapter.get('summary', '无简述')
            # 使用更简洁的格式，避免信息过多
            output_lines.append(f"第 {num} 章 - {title}: {summary}")

        return "\n".join(output_lines)


    def save_to_file(self, filepath: str):
        """将小说数据保存到 JSON 文件。"""
        data_to_save = {
            "topic": self.topic,
            "genre": self.genre,
            "target_chapters": self.target_chapters,
            "words_per_chapter": self.words_per_chapter,
            "core_seed": self.core_seed,
            "character_dynamics": self.character_dynamics,
            "world_building": self.world_building,
            "plot_architecture": self.plot_architecture,
            "chapter_list": self.chapter_list,
            "chapter_texts": self.chapter_texts,
            "global_summary": self.global_summary,
            "character_state": self.character_state,
            # 注意：不保存临时的写作状态数据
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            self.unsaved_changes = False # 保存后标记为已保存
            logging.info(f"小说数据已成功保存到: {filepath}")
        except Exception as e:
            logging.error(f"保存小说数据到文件失败: {e}")
            # 可以考虑通知用户保存失败

    def load_from_file(self, filepath: str):
        """从 JSON 文件加载小说数据。"""
        if not os.path.exists(filepath):
            logging.warning(f"加载失败：文件 {filepath} 不存在。")
            return False # 指示加载失败

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
            # JSON 加载时，字典的键会变成字符串，需要转换回整数
            self.chapter_texts = {int(k): v for k, v in loaded_data.get("chapter_texts", {}).items()}
            self.global_summary = loaded_data.get("global_summary", "")
            self.character_state = loaded_data.get("character_state")

            # 重置临时数据
            self.current_chapter_writing = None
            self.current_chapter_short_summary = None
            self.knowledge_keywords = None
            self.filtered_knowledge = None
            self.unsaved_changes = False # 加载后认为是干净状态

            logging.info(f"小说数据已成功从 {filepath} 加载。")
            return True # 指示加载成功
        except json.JSONDecodeError as e:
            logging.error(f"加载小说数据失败：无效的 JSON 文件 {filepath}。错误: {e}")
            return False
        except Exception as e:
            logging.error(f"加载小说数据失败: {e}")
            return False