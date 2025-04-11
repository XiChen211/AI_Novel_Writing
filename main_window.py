# main_window.py
# -*- coding: utf-8 -*-
import sys
import os
import logging
import re # 用于文件名清理
from typing import Optional, Dict, Any, List
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QTabWidget, QSpinBox, QMessageBox,
    QFileDialog, QListWidget, QListWidgetItem, QSplitter, QGroupBox, QFormLayout,
    QScrollArea,
    # **** 确保导入这些 ****
    QDialog, QDialogButtonBox
    # *********************
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

# 假设这些模块在你项目的同一目录下
from gemini_client import GeminiClient
from novel_data import NovelData
from prompt_loader import get_prompt
# from utils import extract_text_between_markers # 如果使用了 utils.py

# --- 后台任务线程 ---
class GenerationThread(QThread):
    """用于在后台执行耗时的 Gemini API 调用，避免UI冻结。"""
    generation_complete = pyqtSignal(str, str)
    generation_error = pyqtSignal(str, str)

    def __init__(self, gemini_client: GeminiClient, prompt: str, task_id: str, parent=None):
        super().__init__(parent)
        self.client = gemini_client
        self.prompt = prompt
        self.task_id = task_id

    def run(self):
        """执行 API 调用。"""
        try:
            logging.info(f"线程 {self.task_id} 开始执行。")
            result = self.client.generate_text(self.prompt)
            if result.startswith("错误："):
                self.generation_error.emit(result, self.task_id)
            else:
                self.generation_complete.emit(result, self.task_id)
            logging.info(f"线程 {self.task_id} 执行完毕。")
        except Exception as e:
            error_message = f"线程 {self.task_id} 执行出错: {e}"
            logging.error(error_message, exc_info=True) # Log traceback
            self.generation_error.emit(error_message, self.task_id)


# --- Full Screen Viewer Dialog ---
class FullScreenViewer(QDialog):
    """一个用于显示和编辑文本的弹出对话框"""
    def __init__(self, text_content, parent=None, window_title="章节内容预览/编辑", editable=False):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self.setMinimumSize(800, 600)

        self.layout = QVBoxLayout(self)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(text_content)
        self.text_edit.setReadOnly(not editable)

        font = QFont("Microsoft YaHei", 14) # 或者 SimSum, 你系统支持的字体
        self.text_edit.setFont(font)

        self.layout.addWidget(self.text_edit)

        if editable:
            self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            self.button_box.accepted.connect(self.accept)
            self.button_box.rejected.connect(self.reject)
            save_button = self.button_box.button(QDialogButtonBox.Save)
            if save_button: save_button.setText("保存并关闭")
        else:
            self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
            # 将 Close 信号连接到 reject() 或 accept() 都可以，效果是关闭对话框
            # 使用 clicked 连接更通用，可以捕捉到任何按钮点击
            self.button_box.clicked.connect(self.reject) # 点击关闭按钮等同于拒绝

        self.layout.addWidget(self.button_box)
        self.setLayout(self.layout)

    def get_text(self) -> str:
        """获取对话框中文本编辑器的内容"""
        return self.text_edit.toPlainText()


# --- 主窗口 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 小说写作助手 (Gemini)")
        self.setGeometry(100, 100, 1200, 800)

        # --- 初始化后端和数据 ---
        try:
            self.gemini_client = GeminiClient()
        except Exception as e:
            QMessageBox.critical(self, "初始化错误", f"无法初始化 Gemini 客户端: {e}\n请确保 API 密钥正确且网络连接正常。程序即将退出。")
            sys.exit(1)

        self.novel_data = NovelData()
        self.generation_thread: Optional[GenerationThread] = None # 类型提示
        self.last_chunk_start: Optional[int] = None
        self.regen_pending_data: Optional[Dict[str, Any]] = None

        # --- 创建 UI 元素 ---
        self.setup_ui()

        # --- 连接信号和槽 ---
        self.connect_signals()

        # --- 初始化状态 ---
        self.update_ui_from_data()
        self.update_status("就绪.")

    def setup_ui(self):
        """创建和布局 UI 控件。"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # --- 菜单栏 ---
        self.setup_menu_bar()

        # --- 选项卡界面 ---
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        # --- 1. 项目设置选项卡 ---
        self.setup_tab = QWidget()
        self.tab_widget.addTab(self.setup_tab, "项目设置 & 核心")
        setup_layout = QVBoxLayout(self.setup_tab)
        setup_input_group = QGroupBox("基础设定")
        setup_form_layout = QFormLayout()
        self.topic_input = QLineEdit()
        self.genre_input = QLineEdit()
        self.chapters_spinbox = QSpinBox()
        self.chapters_spinbox.setRange(1, 1000); self.chapters_spinbox.setValue(self.novel_data.target_chapters)
        self.words_spinbox = QSpinBox()
        self.words_spinbox.setRange(500, 10000); self.words_spinbox.setSingleStep(100); self.words_spinbox.setValue(self.novel_data.words_per_chapter)
        setup_form_layout.addRow("小说主题:", self.topic_input); setup_form_layout.addRow("小说类型:", self.genre_input)
        setup_form_layout.addRow("目标章节数:", self.chapters_spinbox); setup_form_layout.addRow("每章目标字数:", self.words_spinbox)
        setup_input_group.setLayout(setup_form_layout); setup_layout.addWidget(setup_input_group)
        self.generate_core_seed_button = QPushButton("1. 生成核心种子 (雪花第1层)"); setup_layout.addWidget(self.generate_core_seed_button)
        self.core_seed_display = QTextEdit(); self.core_seed_display.setReadOnly(True); self.core_seed_display.setPlaceholderText("此处显示生成的故事核心种子...")
        setup_layout.addWidget(QLabel("核心种子:")); setup_layout.addWidget(self.core_seed_display); setup_layout.addStretch()

        # --- 2. 角色 & 世界观 & 情节 选项卡 ---
        self.cdwp_tab = QWidget()
        self.tab_widget.addTab(self.cdwp_tab, "角色 & 世界 & 情节")
        cdwp_layout = QVBoxLayout(self.cdwp_tab)
        cdwp_splitter = QSplitter(Qt.Horizontal)
        cdwp_left_widget = QWidget(); cdwp_left_layout = QVBoxLayout(cdwp_left_widget)
        self.cdwp_user_guidance_input = QTextEdit(); self.cdwp_user_guidance_input.setPlaceholderText("可选：在此输入对角色、世界观或情节的具体指导..."); self.cdwp_user_guidance_input.setFixedHeight(100)
        self.generate_chars_button = QPushButton("2. 生成角色动力学"); self.generate_world_button = QPushButton("3. 生成世界构建矩阵")
        self.generate_plot_button = QPushButton("4. 生成情节架构"); self.create_char_state_button = QPushButton("初始化角色状态文档")
        cdwp_left_layout.addWidget(QLabel("用户指导 (可选):")); cdwp_left_layout.addWidget(self.cdwp_user_guidance_input)
        cdwp_left_layout.addWidget(self.generate_chars_button); cdwp_left_layout.addWidget(self.generate_world_button)
        cdwp_left_layout.addWidget(self.generate_plot_button); cdwp_left_layout.addWidget(self.create_char_state_button); cdwp_left_layout.addStretch()
        cdwp_right_tabs = QTabWidget()
        self.char_display = QTextEdit(); self.char_display.setReadOnly(True)
        self.world_display = QTextEdit(); self.world_display.setReadOnly(True)
        self.plot_display = QTextEdit(); self.plot_display.setReadOnly(True)
        self.char_state_display_tab = QTextEdit(); self.char_state_display_tab.setReadOnly(True); self.char_state_display_tab.setPlaceholderText("角色状态文档将在此显示...")
        cdwp_right_tabs.addTab(self.char_display, "角色动力学"); cdwp_right_tabs.addTab(self.world_display, "世界构建")
        cdwp_right_tabs.addTab(self.plot_display, "情节架构"); cdwp_right_tabs.addTab(self.char_state_display_tab, "角色状态")
        cdwp_splitter.addWidget(cdwp_left_widget); cdwp_splitter.addWidget(cdwp_right_tabs); cdwp_splitter.setSizes([300, 700]); cdwp_layout.addWidget(cdwp_splitter)

        # --- 3. 章节蓝图 选项卡 ---
        self.blueprint_tab = QWidget()
        self.tab_widget.addTab(self.blueprint_tab, "章节蓝图")
        blueprint_layout = QVBoxLayout(self.blueprint_tab)
        blueprint_control_group = QGroupBox("生成控制"); blueprint_control_main_layout = QVBoxLayout(blueprint_control_group)
        guidance_layout = QHBoxLayout(); self.blueprint_user_guidance_input = QLineEdit(); self.blueprint_user_guidance_input.setPlaceholderText("可选：对后续章节生成的额外指导...")
        guidance_layout.addWidget(QLabel("用户指导:")); guidance_layout.addWidget(self.blueprint_user_guidance_input); blueprint_control_main_layout.addLayout(guidance_layout)
        full_gen_layout = QHBoxLayout(); self.generate_blueprint_button = QPushButton("生成章节蓝图 (全部 - 覆盖!)"); full_gen_layout.addWidget(self.generate_blueprint_button)
        full_gen_layout.addStretch(); blueprint_control_main_layout.addLayout(full_gen_layout)
        chunk_gen_layout = QHBoxLayout(); self.start_chapter_spinbox = QSpinBox(); self.start_chapter_spinbox.setMinimum(1)
        self.end_chapter_spinbox = QSpinBox(); self.end_chapter_spinbox.setMinimum(1); self.generate_chunked_blueprint_button = QPushButton("生成/覆盖指定范围蓝图")
        chunk_gen_layout.addWidget(QLabel("从第")); chunk_gen_layout.addWidget(self.start_chapter_spinbox); chunk_gen_layout.addWidget(QLabel("章 到 第"))
        chunk_gen_layout.addWidget(self.end_chapter_spinbox); chunk_gen_layout.addWidget(QLabel("章")); chunk_gen_layout.addWidget(self.generate_chunked_blueprint_button)
        chunk_gen_layout.addStretch(); blueprint_control_main_layout.addLayout(chunk_gen_layout)
        regen_layout = QHBoxLayout(); self.regen_start_spinbox = QSpinBox(); self.regen_start_spinbox.setMinimum(1)
        self.regenerate_blueprint_button = QPushButton("从指定章重新生成后续蓝图 (覆盖后续!)")
        regen_layout.addWidget(QLabel("从第")); regen_layout.addWidget(self.regen_start_spinbox); regen_layout.addWidget(QLabel("章开始重新生成后续:"))
        regen_layout.addWidget(self.regenerate_blueprint_button); regen_layout.addStretch(); blueprint_control_main_layout.addLayout(regen_layout)
        blueprint_layout.addWidget(blueprint_control_group)
        list_group = QGroupBox("章节目录"); list_layout = QVBoxLayout(list_group); self.chapter_list_widget = QListWidget()
        self.total_chapters_label = QLabel("当前总章节数: 0"); list_layout.addWidget(self.total_chapters_label); list_layout.addWidget(self.chapter_list_widget)
        blueprint_layout.addWidget(list_group, 1)

        # --- 4. 章节写作 选项卡 ---
        self.writing_tab = QWidget()
        self.tab_widget.addTab(self.writing_tab, "章节写作")
        writing_layout = QVBoxLayout(self.writing_tab)
        writing_splitter = QSplitter(Qt.Vertical)
        writing_top_widget = QWidget(); writing_top_layout = QVBoxLayout(writing_top_widget)
        chapter_selection_layout = QHBoxLayout(); self.chapter_select_spinbox = QSpinBox(); self.chapter_select_spinbox.setMinimum(1)
        self.load_chapter_button = QPushButton("加载章节数据"); self.current_chapter_info_display = QLabel("请选择章节并点击加载..."); self.current_chapter_info_display.setWordWrap(True)
        chapter_selection_layout.addWidget(QLabel("当前写作章节:")); chapter_selection_layout.addWidget(self.chapter_select_spinbox); chapter_selection_layout.addWidget(self.load_chapter_button)
        chapter_selection_layout.addWidget(self.current_chapter_info_display, 1); writing_top_layout.addLayout(chapter_selection_layout)
        self.writing_user_guidance_input = QTextEdit(); self.writing_user_guidance_input.setPlaceholderText("针对本章写作的具体指导..."); self.writing_user_guidance_input.setMaximumHeight(80)
        writing_top_layout.addWidget(QLabel("用户指导 (本章):")); writing_top_layout.addWidget(self.writing_user_guidance_input)
        knowledge_layout = QHBoxLayout(); self.summarize_recent_button = QPushButton("生成当前章节摘要"); self.search_knowledge_button = QPushButton("生成知识库关键词")
        self.filter_knowledge_button = QPushButton("过滤知识库内容"); knowledge_layout.addWidget(self.summarize_recent_button); knowledge_layout.addWidget(self.search_knowledge_button)
        knowledge_layout.addWidget(self.filter_knowledge_button); knowledge_layout.addStretch(); writing_top_layout.addLayout(knowledge_layout)
        context_display_layout = QHBoxLayout(); summary_kn_group = QGroupBox("上下文参考"); summary_kn_layout = QFormLayout(summary_kn_group)
        self.short_summary_display = QTextEdit(); self.short_summary_display.setReadOnly(True); self.short_summary_display.setMaximumHeight(100); self.short_summary_display.setPlaceholderText("当前章节摘要...")
        summary_kn_layout.addRow("章节摘要:", self.short_summary_display); self.knowledge_keywords_display = QLineEdit(); self.knowledge_keywords_display.setReadOnly(True)
        self.knowledge_keywords_display.setPlaceholderText("知识库关键词..."); summary_kn_layout.addRow("知识关键词:", self.knowledge_keywords_display)
        self.knowledge_input_text = QTextEdit(); self.knowledge_input_text.setPlaceholderText("在此粘贴或输入相关知识库文本..."); self.knowledge_input_text.setMaximumHeight(100)
        summary_kn_layout.addRow("知识库输入:", self.knowledge_input_text); self.filtered_knowledge_display = QTextEdit(); self.filtered_knowledge_display.setReadOnly(True)
        self.filtered_knowledge_display.setMaximumHeight(100); self.filtered_knowledge_display.setPlaceholderText("过滤后的知识库内容...")
        summary_kn_layout.addRow("过滤后知识:", self.filtered_knowledge_display); context_display_layout.addWidget(summary_kn_group)
        other_context_scroll = QScrollArea(); other_context_scroll.setWidgetResizable(True); other_context_widget = QWidget(); other_context_layout = QVBoxLayout(other_context_widget)
        self.global_summary_display_writing = QTextEdit(); self.global_summary_display_writing.setReadOnly(True); self.global_summary_display_writing.setMaximumHeight(150)
        self.global_summary_display_writing.setPlaceholderText("全局前文摘要..."); other_context_layout.addWidget(QLabel("全局摘要:")); other_context_layout.addWidget(self.global_summary_display_writing)
        self.prev_excerpt_display = QTextEdit(); self.prev_excerpt_display.setReadOnly(True); self.prev_excerpt_display.setMaximumHeight(100)
        self.prev_excerpt_display.setPlaceholderText("前章结尾段落..."); other_context_layout.addWidget(QLabel("前章结尾:")); other_context_layout.addWidget(self.prev_excerpt_display)
        self.char_state_display_writing = QTextEdit(); self.char_state_display_writing.setReadOnly(True); self.char_state_display_writing.setMaximumHeight(200)
        self.char_state_display_writing.setPlaceholderText("当前角色状态..."); other_context_layout.addWidget(QLabel("角色状态:")); other_context_layout.addWidget(self.char_state_display_writing)
        other_context_layout.addStretch(); other_context_scroll.setWidget(other_context_widget); context_display_layout.addWidget(other_context_scroll)
        writing_top_layout.addLayout(context_display_layout); writing_splitter.addWidget(writing_top_widget)
        writing_bottom_widget = QWidget(); writing_bottom_layout = QVBoxLayout(writing_bottom_widget)
        button_layout_group = QHBoxLayout(); self.generate_draft_button = QPushButton("生成本章草稿"); self.save_draft_button = QPushButton("保存草稿到数据")
        self.view_fullscreen_button = QPushButton("放大查看/编辑"); button_layout_group.addWidget(self.generate_draft_button); button_layout_group.addWidget(self.save_draft_button)
        button_layout_group.addWidget(self.view_fullscreen_button); button_layout_group.addStretch(); writing_bottom_layout.addLayout(button_layout_group)
        self.chapter_text_edit = QTextEdit(); self.chapter_text_edit.setPlaceholderText("生成的章节草稿将显示在此处..."); font = QFont("Microsoft YaHei", 11); self.chapter_text_edit.setFont(font)
        writing_bottom_layout.addWidget(self.chapter_text_edit)
        update_button_layout = QHBoxLayout(); self.update_summary_button = QPushButton("更新全局摘要"); self.update_char_state_button = QPushButton("更新角色状态")
        update_button_layout.addWidget(self.update_summary_button); update_button_layout.addWidget(self.update_char_state_button); update_button_layout.addStretch()
        writing_bottom_layout.addLayout(update_button_layout); writing_splitter.addWidget(writing_bottom_widget)
        writing_splitter.setSizes([450, 550]); writing_layout.addWidget(writing_splitter)

        # --- 5. 角色导入 Tab ---
        self.import_tab = QWidget()
        self.tab_widget.addTab(self.import_tab, "角色导入")
        import_layout = QVBoxLayout(self.import_tab)
        self.import_text_input = QTextEdit(); self.import_text_input.setPlaceholderText("在此粘贴包含角色信息的小说文本...")
        self.import_analyze_button = QPushButton("分析并生成角色状态"); self.import_result_display = QTextEdit(); self.import_result_display.setReadOnly(True)
        self.import_result_display.setPlaceholderText("分析后的角色状态将在此显示..."); self.import_replace_button = QPushButton("用分析结果替换当前角色状态")
        import_layout.addWidget(QLabel("粘贴文本:")); import_layout.addWidget(self.import_text_input, 1); import_layout.addWidget(self.import_analyze_button)
        import_layout.addWidget(QLabel("分析结果:")); import_layout.addWidget(self.import_result_display, 1); import_layout.addWidget(self.import_replace_button)

        # --- 状态栏 ---
        self.statusBar().showMessage("就绪.")

    def setup_menu_bar(self):
        menubar = self.menuBar(); file_menu = menubar.addMenu("文件")
        save_action = file_menu.addAction("保存项目"); save_action.triggered.connect(self.save_project); save_action.setShortcut("Ctrl+S")
        load_action = file_menu.addAction("加载项目"); load_action.triggered.connect(self.load_project); load_action.setShortcut("Ctrl+O")
        file_menu.addSeparator(); exit_action = file_menu.addAction("退出"); exit_action.triggered.connect(self.close)

    def connect_signals(self):
        # 项目设置
        self.generate_core_seed_button.clicked.connect(self.on_generate_core_seed)
        self.chapters_spinbox.valueChanged.connect(lambda val: setattr(self.novel_data, 'target_chapters', val))
        self.chapters_spinbox.valueChanged.connect(self.update_blueprint_spinbox_ranges)
        self.words_spinbox.valueChanged.connect(lambda val: setattr(self.novel_data, 'words_per_chapter', val))
        self.topic_input.textChanged.connect(lambda text: setattr(self.novel_data, 'topic', text))
        self.genre_input.textChanged.connect(lambda text: setattr(self.novel_data, 'genre', text))
        # 角色、世界、情节
        self.generate_chars_button.clicked.connect(self.on_generate_character_dynamics)
        self.generate_world_button.clicked.connect(self.on_generate_world_building)
        self.generate_plot_button.clicked.connect(self.on_generate_plot_architecture)
        self.create_char_state_button.clicked.connect(self.on_create_character_state)
        # 章节蓝图
        self.generate_blueprint_button.clicked.connect(self.on_generate_chapter_blueprint)
        self.generate_chunked_blueprint_button.clicked.connect(self.on_generate_chunked_blueprint)
        self.regenerate_blueprint_button.clicked.connect(self.on_regenerate_blueprint) # 连接重新生成按钮
        self.chapter_list_widget.itemDoubleClicked.connect(self.on_chapter_list_double_clicked)
        # 章节写作
        self.load_chapter_button.clicked.connect(self.on_load_chapter_data)
        self.summarize_recent_button.clicked.connect(self.on_summarize_recent_chapters)
        self.search_knowledge_button.clicked.connect(self.on_search_knowledge)
        self.filter_knowledge_button.clicked.connect(self.on_filter_knowledge)
        self.generate_draft_button.clicked.connect(self.on_generate_chapter_draft)
        self.save_draft_button.clicked.connect(self.on_save_chapter_draft)
        self.view_fullscreen_button.clicked.connect(self.on_view_fullscreen) # 连接放大按钮
        self.update_summary_button.clicked.connect(self.on_update_global_summary)
        self.update_char_state_button.clicked.connect(self.on_update_character_state)
        # 角色导入
        self.import_analyze_button.clicked.connect(self.on_import_analyze_characters)
        self.import_replace_button.clicked.connect(self.on_import_replace_state)
        # 文本编辑区内容变化时标记未保存
        self.topic_input.textChanged.connect(self.mark_unsaved); self.genre_input.textChanged.connect(self.mark_unsaved)
        self.chapters_spinbox.valueChanged.connect(self.mark_unsaved); self.words_spinbox.valueChanged.connect(self.mark_unsaved)
        self.chapter_text_edit.textChanged.connect(self.mark_unsaved); self.writing_user_guidance_input.textChanged.connect(self.mark_unsaved)
        self.cdwp_user_guidance_input.textChanged.connect(self.mark_unsaved); self.blueprint_user_guidance_input.textChanged.connect(self.mark_unsaved)
        self.knowledge_input_text.textChanged.connect(self.mark_unsaved); self.import_text_input.textChanged.connect(self.mark_unsaved)

    def mark_unsaved(self):
        if not self.novel_data.unsaved_changes:
             self.novel_data.unsaved_changes = True
             self.setWindowTitle(self.windowTitle().replace(" *", "") + " *")

    def unmark_unsaved(self):
        if self.novel_data.unsaved_changes:
            self.novel_data.unsaved_changes = False
            title = self.windowTitle();
            if title.endswith(" *"): self.setWindowTitle(title[:-2])

    # --- 辅助函数 ---
    def update_status(self, message: str):
        logging.info(f"状态: {message}"); self.statusBar().showMessage(message)

    def run_generation_task(self, prompt_name: str, format_dict: dict, task_id: str):
        """启动一个后台生成任务。"""
        if self.generation_thread and self.generation_thread.isRunning():
            QMessageBox.warning(self, "请稍候", "另一个生成任务正在进行中..."); return
        try:
            prompt_template = get_prompt(prompt_name)
            final_format_dict = {k: (v if v is not None else "") for k, v in format_dict.items()}

            # **** 添加日志记录最终格式化字典和提示词 ****
            logging.debug(f"--- Formatting prompt '{prompt_name}' (task: {task_id}) ---")
            # 对长字符串进行截断，避免日志过长
            loggable_dict = {k: (str(v)[:100] + '...' if isinstance(v, str) and len(v) > 100 else v)
                             for k, v in final_format_dict.items()}
            logging.debug(f"Format Dictionary (values truncated): {loggable_dict}")

            final_prompt = prompt_template.format(**final_format_dict)
            logging.debug(f"Formatted Prompt (first 500 chars): {final_prompt[:500]}...")
            # ******************************************

            self.update_status(f"正在生成 {task_id}...")
            self.set_buttons_enabled(False)
            self.generation_thread = GenerationThread(self.gemini_client, final_prompt, task_id)
            self.generation_thread.generation_complete.connect(self.handle_generation_complete)
            self.generation_thread.generation_error.connect(self.handle_generation_error)
            self.generation_thread.finished.connect(self.on_generation_finished)
            self.generation_thread.start()
            logging.info(f"Generation thread for task '{task_id}' started.")

        except KeyError as e:
            logging.error(f"格式化提示词 '{prompt_name}' 时出错，缺少键: {e}")
            QMessageBox.critical(self, "格式化错误", f"准备提示词 '{prompt_name}' 时缺少必要的信息: {e}\n请检查是否已加载章节或生成所需的前置数据。")
            self.update_status(f"错误：准备提示词 {prompt_name} 失败。"); self.set_buttons_enabled(True)
        except Exception as e:
            logging.exception(f"准备或执行生成任务 '{task_id}' 时发生意外错误:")
            QMessageBox.critical(self, "错误", f"准备或执行生成任务 '{task_id}' 时出错: {e}")
            self.update_status(f"错误：任务 {task_id} 准备或执行时出错。"); self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        """启用或禁用大部分生成/操作按钮。"""
        excluded_buttons = ["保存项目", "加载项目", "退出"]
        for button in self.findChildren(QPushButton):
            if button.text() not in excluded_buttons: button.setEnabled(enabled)
        if hasattr(self, 'import_result_display') and hasattr(self, 'import_replace_button'):
             has_content = bool(self.import_result_display.toPlainText().strip())
             self.import_replace_button.setEnabled(has_content and enabled)

    def handle_generation_complete(self, result: str, task_id: str):
        """处理后台任务成功返回的结果。"""
        self.update_status(f"任务 {task_id} 完成。")
        try:
            if task_id == "core_seed":
                self.novel_data.core_seed = result; self.core_seed_display.setText(result); self.mark_unsaved()
            elif task_id == "character_dynamics":
                self.novel_data.character_dynamics = result; self.char_display.setText(result); self.mark_unsaved()
                QMessageBox.information(self, "下一步", "角色动力学已生成。现在可以初始化角色状态文档。")
            elif task_id == "world_building":
                self.novel_data.world_building = result; self.world_display.setText(result); self.mark_unsaved()
            elif task_id == "plot_architecture":
                self.novel_data.plot_architecture = result; self.plot_display.setText(result); self.mark_unsaved()
            elif task_id == "create_character_state":
                self.novel_data.character_state = result; self.char_state_display_tab.setText(result)
                self.char_state_display_writing.setText(result); self.mark_unsaved()
            elif task_id == "chapter_blueprint":
                self.novel_data.update_chapter_list(result, is_chunked=False); self.update_chapter_list_widget()
                self.update_chapter_select_spinbox_range(); self.mark_unsaved()
            elif task_id == "chapter_blueprint_chunk":
                start_chapter = self.last_chunk_start
                if start_chapter is None: logging.error("处理分块蓝图结果时未找到起始章节号！"); return
                self.novel_data.update_chapter_list(result, is_chunked=True, start_chapter=start_chapter)
                self.update_chapter_list_widget(); self.update_chapter_select_spinbox_range()
                self.last_chunk_start = None; self.mark_unsaved()

            # **** 处理剧情摘要结果 ****
            elif task_id == "written_chapters_summary_for_regen":
                if not self.regen_pending_data:
                     logging.error("收到剧情摘要但没有找到待处理的重新生成数据。")
                     QMessageBox.critical(self, "内部错误", "处理剧情摘要时发生错误。")
                     self.regen_pending_data = None; return

                written_summary = result
                logging.info("剧情进展摘要已生成。")
                self.update_status("剧情进展摘要已生成，正在准备生成后续蓝图...")
                QApplication.processEvents()

                start_chapter = self.regen_pending_data['start_chapter']
                total_chapters = self.regen_pending_data['total_chapters']
                guidance = self.regen_pending_data['guidance']

                # **** 在这里截断列表，就在获取上下文之前 ****
                self.novel_data.chapter_list = [ch for ch in self.novel_data.chapter_list if ch.get('number', -1) < start_chapter]
                self.update_chapter_list_widget(); QApplication.processEvents() # 更新UI显示截断结果

                existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_chapter)
                novel_architecture = f"核心种子: {self.novel_data.core_seed or 'N/A'}\n\n角色体系: {self.novel_data.character_dynamics or 'N/A'}\n\n世界观: {self.novel_data.world_building or 'N/A'}\n\n情节架构: {self.novel_data.plot_architecture or 'N/A'}"

                format_dict = {
                    "user_guidance": guidance, "novel_architecture": novel_architecture,
                    "previous_chapters_summary": written_summary, # 使用生成的摘要
                    "chapter_list": existing_list_str, "number_of_chapters": total_chapters,
                    "n": start_chapter, "m": total_chapters,
                }
                self.run_generation_task("chunked_chapter_blueprint", format_dict, "chapter_blueprint_regenerate")
                self.regen_pending_data = None # 清理挂起数据

            # **** 处理重新生成的蓝图结果 ****
            elif task_id == "chapter_blueprint_regenerate":
                try:
                    # 列表已在启动此任务前被截断
                    new_chapters = self.novel_data._parse_chapter_list_string(result)
                    if not new_chapters:
                         logging.warning("重新生成的章节蓝图解析结果为空。")
                         QMessageBox.warning(self, "生成警告", "AI未能生成有效的后续章节蓝图内容。")
                    else:
                         self.novel_data.chapter_list.extend(new_chapters) # 追加
                         self.novel_data.chapter_list.sort(key=lambda x: x.get('number', float('inf')))
                         logging.info(f"重新生成：成功添加了 {len(new_chapters)} 个新章节蓝图。")
                         self.update_chapter_list_widget(); self.update_chapter_select_spinbox_range(); self.mark_unsaved()
                         QMessageBox.information(self, "成功", "已基于已写内容重新生成后续章节蓝图。")
                except Exception as e:
                     logging.exception("处理重新生成的章节蓝图结果时出错:")
                     QMessageBox.critical(self, "处理错误", f"处理重新生成的章节蓝图结果时出错:\n{e}")

            elif task_id == "summarize_recent":
                summary_content = result;
                if "当前章节摘要:" in result:
                    try: summary_content = result.split("当前章节摘要:", 1)[1].strip()
                    except IndexError: pass
                self.novel_data.current_chapter_short_summary = summary_content; self.short_summary_display.setText(summary_content)
            elif task_id == "knowledge_search":
                self.novel_data.knowledge_keywords = result; self.knowledge_keywords_display.setText(result)
                QMessageBox.information(self, "提示", "知识库关键词已生成...")
            elif task_id == "knowledge_filter":
                self.novel_data.filtered_knowledge = result; self.filtered_knowledge_display.setText(result)
            elif task_id == "chapter_draft":
                self.chapter_text_edit.setText(result); QMessageBox.information(self, "提示", "章节草稿已生成...")
            elif task_id == "summary_update":
                summary_content = result; self.novel_data.global_summary = summary_content
                self.global_summary_display_writing.setText(summary_content); self.mark_unsaved(); QMessageBox.information(self, "成功", "全局摘要已更新。")
            elif task_id == "update_character_state":
                state_content = result; self.novel_data.character_state = state_content
                self.char_state_display_tab.setText(state_content); self.char_state_display_writing.setText(state_content)
                self.mark_unsaved(); QMessageBox.information(self, "成功", "角色状态已更新。")
            elif task_id == "character_import_analyze":
                self.import_result_display.setText(result)
                if result and result.strip(): self.import_replace_button.setEnabled(True)
                else: self.import_replace_button.setEnabled(False)
                QMessageBox.information(self, "分析完成", "角色状态分析完成。")
            else:
                logging.warning(f"收到了未知任务ID '{task_id}' 的完成信号。")
        except Exception as e:
             logging.exception(f"处理任务 {task_id} 的结果时发生错误:")
             QMessageBox.critical(self, "处理结果错误", f"处理任务 {task_id} 返回结果时出错:\n{e}")

    def handle_generation_error(self, error_message: str, task_id: str):
        """处理后台任务失败的情况。"""
        self.update_status(f"任务 {task_id} 失败。")
        QMessageBox.critical(self, f"生成错误 ({task_id})", f"生成过程中发生错误:\n{error_message}")
        self.last_chunk_start = None
        if task_id == "written_chapters_summary_for_regen":
             self.regen_pending_data = None # 摘要失败，清除挂起状态
             logging.error("剧情进展摘要生成失败，重新生成流程中止。")
        elif task_id == "chapter_blueprint_regenerate":
             QMessageBox.warning(self, "生成失败", "重新生成后续章节蓝图失败。当前列表可能只包含之前的章节。")

    def on_generation_finished(self):
        """后台任务完成后（无论成功或失败）调用。"""
        if not self.regen_pending_data: # 只有在没有挂起任务时才完全启用
             self.set_buttons_enabled(True)
             self.update_status("就绪.")
        self.generation_thread = None

    def update_blueprint_spinbox_ranges(self, max_chapters: int):
        safe_max = max(1, max_chapters)
        self.start_chapter_spinbox.setMaximum(safe_max); self.end_chapter_spinbox.setMaximum(safe_max)
        self.regen_start_spinbox.setMaximum(safe_max) # 更新重新生成起始章节范围
        if self.end_chapter_spinbox.value() > safe_max: self.end_chapter_spinbox.setValue(safe_max)
        if self.start_chapter_spinbox.value() > safe_max: self.start_chapter_spinbox.setValue(safe_max)
        if self.regen_start_spinbox.value() > safe_max: self.regen_start_spinbox.setValue(safe_max)

    def update_chapter_select_spinbox_range(self):
         max_chap = len(self.novel_data.chapter_list)
         self.chapter_select_spinbox.setMaximum(max_chap if max_chap > 0 else 1)

    def update_ui_from_data(self):
        """使用 self.novel_data 中的数据更新整个 UI 显示。"""
        logging.info("--- 开始执行 update_ui_from_data ---")
        current_topic = self.novel_data.topic or ""; current_genre = self.novel_data.genre or ""
        current_target_chapters = self.novel_data.target_chapters; current_words_per_chapter = self.novel_data.words_per_chapter
        current_core_seed = self.novel_data.core_seed or ""; current_char_dynamics = self.novel_data.character_dynamics or ""
        current_world_building = self.novel_data.world_building or ""; current_plot_architecture = self.novel_data.plot_architecture or ""
        current_char_state = self.novel_data.character_state or ""; current_global_summary = self.novel_data.global_summary or ""
        logging.info(f"用于更新UI的 novel_data.topic: {current_topic}")
        logging.info(f"用于更新UI的 novel_data.plot_architecture: {current_plot_architecture[:50] if current_plot_architecture else None}...")
        self.topic_input.setText(current_topic); self.genre_input.setText(current_genre)
        self.chapters_spinbox.setRange(1, 1000); self.chapters_spinbox.setValue(current_target_chapters)
        self.words_spinbox.setRange(500, 10000); self.words_spinbox.setValue(current_words_per_chapter)
        self.core_seed_display.setText(current_core_seed)
        self.char_display.setText(current_char_dynamics); self.world_display.setText(current_world_building)
        self.plot_display.setText(current_plot_architecture); self.char_state_display_tab.setText(current_char_state)
        self.update_chapter_list_widget(); self.update_blueprint_spinbox_ranges(current_target_chapters)
        default_end_chunk = min(10, current_target_chapters) if current_target_chapters > 0 else 1
        self.end_chapter_spinbox.setValue(max(1, default_end_chunk)); self.regen_start_spinbox.setValue(1)
        self.update_chapter_select_spinbox_range()
        self.current_chapter_info_display.setText("请选择章节并点击加载...")
        self.short_summary_display.clear(); self.knowledge_keywords_display.clear()
        self.knowledge_input_text.clear(); self.filtered_knowledge_display.clear()
        self.global_summary_display_writing.setText(current_global_summary)
        self.prev_excerpt_display.clear(); self.char_state_display_writing.setText(current_char_state)
        self.chapter_text_edit.clear(); self.writing_user_guidance_input.clear()
        self.import_text_input.clear(); self.import_result_display.clear(); self.import_replace_button.setEnabled(False)
        self.unmark_unsaved(); self.update_status("项目数据已加载/刷新。")

    def update_chapter_list_widget(self):
        self.chapter_list_widget.clear(); count = len(self.novel_data.chapter_list)
        self.total_chapters_label.setText(f"当前总章节数: {count}")
        if not self.novel_data.chapter_list: self.chapter_list_widget.addItem("暂无章节蓝图"); return
        for chapter in self.novel_data.chapter_list:
            num = chapter.get('number', '?'); title = chapter.get('title', '未知标题'); summary = chapter.get('summary', '无简述')
            display_text = f"第 {num} 章 - {title}\n  └ {summary}"; item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, chapter.get('number')); self.chapter_list_widget.addItem(item)

    # --- 槽函数 (按钮点击处理) ---
    def on_generate_core_seed(self):
        topic = self.topic_input.text().strip(); genre = self.genre_input.text().strip()
        num_chapters = self.chapters_spinbox.value(); word_num = self.words_spinbox.value()
        if not topic or not genre: QMessageBox.warning(self, "信息不足", "请输入小说主题和类型。"); return
        self.novel_data.topic = topic; self.novel_data.genre = genre
        self.novel_data.target_chapters = num_chapters; self.novel_data.words_per_chapter = word_num
        format_dict = { "topic": topic, "genre": genre, "number_of_chapters": num_chapters, "word_number": word_num, }
        self.run_generation_task("core_seed", format_dict, "core_seed")

    def on_generate_character_dynamics(self):
        if not self.novel_data.core_seed: QMessageBox.warning(self, "缺少前提", "请先生成核心种子。"); return
        format_dict = { "user_guidance": self.cdwp_user_guidance_input.toPlainText(), "core_seed": self.novel_data.core_seed, }
        self.run_generation_task("character_dynamics", format_dict, "character_dynamics")

    def on_generate_world_building(self):
        if not self.novel_data.core_seed: QMessageBox.warning(self, "缺少前提", "请先生成核心种子。"); return
        format_dict = { "user_guidance": self.cdwp_user_guidance_input.toPlainText(), "core_seed": self.novel_data.core_seed, }
        self.run_generation_task("world_building", format_dict, "world_building")

    def on_generate_plot_architecture(self):
         if not self.novel_data.core_seed or not self.novel_data.character_dynamics or not self.novel_data.world_building:
             QMessageBox.warning(self, "缺少前提", "请先生成核心种子、角色动力学和世界构建。"); return
         format_dict = { "user_guidance": self.cdwp_user_guidance_input.toPlainText(), "core_seed": self.novel_data.core_seed,
                         "character_dynamics": self.novel_data.character_dynamics, "world_building": self.novel_data.world_building, }
         self.run_generation_task("plot_architecture", format_dict, "plot_architecture")

    def on_create_character_state(self):
        if not self.novel_data.character_dynamics: QMessageBox.warning(self, "缺少前提", "请先生成角色动力学。"); return
        format_dict = { "character_dynamics": self.novel_data.character_dynamics }
        self.run_generation_task("create_character_state", format_dict, "create_character_state")

    def on_generate_chapter_blueprint(self):
        if not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        if self.novel_data.chapter_list:
             reply = QMessageBox.question(self, "确认覆盖", "当前已有章节蓝图...", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.No: return
        prompt_name = "chapter_blueprint"
        format_dict = { "user_guidance": self.blueprint_user_guidance_input.text(),
                        "novel_architecture": f"核心种子: {self.novel_data.core_seed or 'N/A'}\n\n角色体系: {self.novel_data.character_dynamics or 'N/A'}\n\n世界观: {self.novel_data.world_building or 'N/A'}\n\n情节架构: {self.novel_data.plot_architecture or 'N/A'}",
                        "number_of_chapters": self.novel_data.target_chapters }
        self.run_generation_task(prompt_name, format_dict, "chapter_blueprint")

    def on_generate_chunked_blueprint(self):
        if not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        start_chapter = self.start_chapter_spinbox.value(); end_chapter = self.end_chapter_spinbox.value()
        if start_chapter > end_chapter: QMessageBox.warning(self, "输入错误", "起始章节号不能大于结束章节号。"); return
        chapters_to_overwrite = [ch for ch in self.novel_data.chapter_list if start_chapter <= ch.get('number', -1) <= end_chapter]
        if chapters_to_overwrite:
             reply = QMessageBox.question(self, "确认覆盖", f"此操作将覆盖或替换从第 {start_chapter} 章到第 {end_chapter} 章的蓝图...", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.No: return
        self.last_chunk_start = start_chapter
        existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_chapter)
        prompt_name = "chunked_chapter_blueprint" # 使用原始提示词（不包含剧情摘要）
        format_dict = { "user_guidance": self.blueprint_user_guidance_input.text(),
                        "novel_architecture": f"核心种子: {self.novel_data.core_seed or 'N/A'}...", # Simplified
                        "previous_chapters_summary": "(此模式不使用已写内容摘要)", # 明确说明
                        "number_of_chapters": self.novel_data.target_chapters, "chapter_list": existing_list_str,
                        "n": start_chapter, "m": end_chapter }
        self.run_generation_task(prompt_name, format_dict, "chapter_blueprint_chunk")

    def on_regenerate_blueprint(self):
        """处理从指定章节开始重新生成后续蓝图的请求（第一步：生成摘要）。"""
        if not self.novel_data.plot_architecture:
            QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        if self.regen_pending_data:
             QMessageBox.warning(self, "请稍候", "已有一个重新生成任务正在处理中。"); return

        start_regen_chapter = self.regen_start_spinbox.value()
        total_target_chapters = self.novel_data.target_chapters

        if start_regen_chapter <= 0: QMessageBox.warning(self, "输入错误", "起始章节号必须大于 0。"); return
        if start_regen_chapter > total_target_chapters + 1:
             QMessageBox.warning(self, "输入错误", f"起始章节号不能大于目标章节数 {total_target_chapters} + 1。"); return

        # **** Handle start_regen_chapter == 1 case ****
        if start_regen_chapter == 1:
             reply = QMessageBox.question(self, "确认操作", "您选择从第 1 章开始重新生成...\n是否继续？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.Yes: self.on_generate_chapter_blueprint() # Call full generation
             return

        # --- If start_regen_chapter > 1 ---
        last_chapter_to_summarize = start_regen_chapter - 1
        combined_text_to_summarize = self.novel_data.get_combined_text_last_n_chapters(
            current_chapter_number=start_regen_chapter, n=last_chapter_to_summarize )

        if not combined_text_to_summarize or combined_text_to_summarize == "无前续章节内容.":
            reply = QMessageBox.question(self, "无已写内容", f"未找到第 1 章到第 {last_chapter_to_summarize} 章的已保存章节正文...\n是否仍要尝试仅基于旧蓝图摘要生成后续章节？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: return
            else:
                logging.info(f"重新生成（无内容摘要）：从第 {start_regen_chapter} 章开始。")
                self.novel_data.chapter_list = [ch for ch in self.novel_data.chapter_list if ch.get('number', -1) < start_regen_chapter]
                self.update_chapter_list_widget(); QApplication.processEvents()
                existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_regen_chapter)
                format_dict = { "user_guidance": self.blueprint_user_guidance_input.text(),
                                "novel_architecture": f"核心种子: ...", "previous_chapters_summary": "无 (未找到先前章节正文)",
                                "chapter_list": existing_list_str, "number_of_chapters": total_target_chapters,
                                "n": start_regen_chapter, "m": total_target_chapters, }
                self.run_generation_task("chunked_chapter_blueprint", format_dict, "chapter_blueprint_regenerate")
                return

        # --- Found content to summarize ---
        reply = QMessageBox.question(self, "确认重新生成", f"此操作将首先基于第 1 章到第 {last_chapter_to_summarize} 章的已保存正文生成剧情摘要...\n是否继续？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: return

        self.regen_pending_data = { 'start_chapter': start_regen_chapter, 'total_chapters': total_target_chapters, 'guidance': self.blueprint_user_guidance_input.text() }
        summary_format_dict = { "combined_chapters_text": combined_text_to_summarize }
        self.update_status(f"正在为前 {last_chapter_to_summarize} 章生成剧情摘要...")
        self.run_generation_task("summarize_written_chapters", summary_format_dict, "written_chapters_summary_for_regen")

    def on_chapter_list_double_clicked(self, item: QListWidgetItem):
        chapter_number = item.data(Qt.UserRole)
        if isinstance(chapter_number, int):
            writing_tab_index = -1
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "章节写作": writing_tab_index = i; break
            if writing_tab_index != -1: self.tab_widget.setCurrentIndex(writing_tab_index)
            else: logging.warning("未找到'章节写作'选项卡。")
            self.chapter_select_spinbox.setValue(chapter_number); self.on_load_chapter_data()
        else: QMessageBox.warning(self, "错误", "无法从此列表项获取有效的章节号。")

    def on_load_chapter_data(self):
        """加载选定章节的数据到写作选项卡的各个字段。"""
        logging.info(f"--- Attempting to load data for chapter {self.chapter_select_spinbox.value()} ---") # Add log
        chapter_number = self.chapter_select_spinbox.value()
        self.novel_data.current_chapter_writing = chapter_number # 记录当前正在操作的章节
        logging.debug(f"Set current_chapter_writing to {chapter_number}")

        current_chapter_info = self.novel_data.get_chapter_info(chapter_number)
        if not current_chapter_info:
            QMessageBox.warning(self, "错误", f"未找到第 {chapter_number} 章的蓝图信息。请先生成章节蓝图。")
            self.current_chapter_info_display.setText(f"错误：未找到第 {chapter_number} 章信息")
            self.chapter_text_edit.clear(); self.short_summary_display.clear(); self.knowledge_keywords_display.clear(); self.filtered_knowledge_display.clear(); self.prev_excerpt_display.clear();
            logging.warning(f"Could not find blueprint info for chapter {chapter_number}. Load aborted.")
            return

        logging.debug(f"Found blueprint info for chapter {chapter_number}: {current_chapter_info.get('title')}")
        info_text = (f"第 {chapter_number} 章《{current_chapter_info.get('title', 'N/A')}》\n定位: {current_chapter_info.get('role', 'N/A')}, 作用: {current_chapter_info.get('purpose', 'N/A')}, 悬念: {current_chapter_info.get('suspense_level', 'N/A')}\n"
                     f"伏笔: {current_chapter_info.get('foreshadowing', 'N/A')}, 颠覆: {current_chapter_info.get('plot_twist_level', 'N/A')}\n简述: {current_chapter_info.get('summary', 'N/A')}")
        self.current_chapter_info_display.setText(info_text)

        draft_text = self.novel_data.chapter_texts.get(chapter_number, "")
        logging.debug(f"Loading draft text (first 50 chars): {draft_text[:50]}...")
        try: self.chapter_text_edit.textChanged.disconnect(self.mark_unsaved)
        except TypeError: pass
        self.chapter_text_edit.setText(draft_text);
        self.chapter_text_edit.textChanged.connect(self.mark_unsaved)

        self.novel_data.current_chapter_short_summary = None; self.novel_data.knowledge_keywords = None; self.novel_data.filtered_knowledge = None
        self.short_summary_display.clear(); self.knowledge_keywords_display.clear(); self.filtered_knowledge_display.clear(); self.writing_user_guidance_input.clear()
        logging.debug("Cleared temporary chapter data fields.")

        global_summary_text = self.novel_data.global_summary or ""
        prev_excerpt_text = self.novel_data.get_previous_chapter_excerpt(chapter_number)
        char_state_text = self.novel_data.character_state or ""
        self.global_summary_display_writing.setText(global_summary_text)
        self.prev_excerpt_display.setText(prev_excerpt_text)
        self.char_state_display_writing.setText(char_state_text)
        logging.debug(f"Updated context displays (Global Summary: {len(global_summary_text)} chars, Prev Excerpt: {len(prev_excerpt_text)} chars, Char State: {len(char_state_text)} chars)")

        self.update_status(f"已加载第 {chapter_number} 章数据。")
        logging.info(f"on_load_chapter_data completed. current_chapter_writing set to: {self.novel_data.current_chapter_writing}") # Final check


    def _get_current_chapter_context(self, require_next_chapter=False) -> Optional[dict]:
        """获取当前写作章节所需的所有上下文信息。"""
        logging.debug(f"_get_current_chapter_context called, require_next_chapter={require_next_chapter}")
        chapter_number = self.novel_data.current_chapter_writing
        if chapter_number is None:
            QMessageBox.warning(self, "错误", "请先选择并加载一个要操作的章节。")
            logging.warning("_get_current_chapter_context: current_chapter_writing is None.")
            return None

        logging.debug(f"Current chapter number: {chapter_number}")
        current_info = self.novel_data.get_chapter_info(chapter_number)
        if not current_info:
            QMessageBox.warning(self, "错误", f"无法获取第 {chapter_number} 章的蓝图信息。")
            logging.warning(f"_get_current_chapter_context: Could not get info for chapter {chapter_number}.")
            return None
        logging.debug(f"Current chapter info found: {current_info.get('title')}")

        next_info = self.novel_data.get_chapter_info(chapter_number + 1)
        if require_next_chapter and not next_info:
            QMessageBox.warning(self, "缺少信息", f"无法获取下一章节（第 {chapter_number + 1} 章）的蓝图信息，无法生成当前章节摘要。请先生成后续章节蓝图。")
            logging.warning(f"_get_current_chapter_context: Required next chapter info (Chapter {chapter_number + 1}) not found.")
            return None # *** Critical fix ***
        elif not next_info:
             logging.debug(f"Next chapter info (Chapter {chapter_number + 1}) not found, but not strictly required.")

        default_next_info = {'number': chapter_number + 1, 'title': '（未定义）', 'role': '（未定义）', 'purpose': '（未定义）', 'suspense_level': '（未定义）', 'foreshadowing': '（未定义）', 'plot_twist_level': '（未定义）', 'summary': '（未定义）'}
        next_chapter_data = next_info or default_next_info

        combined_text_value = self.novel_data.get_combined_text_last_n_chapters(chapter_number)
        logging.debug(f"Combined text for prompt (first 100 chars): {combined_text_value[:100]}...")

        context = {
            "chapter_number": chapter_number, "novel_number": chapter_number,
            "chapter_title": current_info.get('title', '未知标题'), "chapter_role": current_info.get('role', '未知'),
            "chapter_purpose": current_info.get('purpose', '未知'), "suspense_level": current_info.get('suspense_level', '中等'),
            "foreshadowing": current_info.get('foreshadowing', '无'), "plot_twist_level": current_info.get('plot_twist_level', '★☆☆☆☆'),
            "chapter_summary": current_info.get('summary', '无'), "word_number": self.novel_data.words_per_chapter,
            "user_guidance": self.writing_user_guidance_input.toPlainText(),
            "characters_involved": current_info.get('characters_involved', ''), "key_items": current_info.get('key_items', ''),
            "scene_location": current_info.get('scene_location', ''), "time_constraint": current_info.get('time_constraint', ''),
            "next_chapter_number": next_chapter_data.get('number'), "next_chapter_title": next_chapter_data.get('title'),
            "next_chapter_role": next_chapter_data.get('role'), "next_chapter_purpose": next_chapter_data.get('purpose'),
            "next_chapter_suspense_level": next_chapter_data.get('suspense_level', '（未定义）'),
            "next_chapter_foreshadowing": next_chapter_data.get('foreshadowing', '（未定义）'),
            "next_chapter_plot_twist_level": next_chapter_data.get('plot_twist_level', '（未定义）'),
            "next_chapter_summary": next_chapter_data.get('summary', '（未定义）'),
            "global_summary": self.novel_data.global_summary, "previous_chapter_excerpt": self.novel_data.get_previous_chapter_excerpt(chapter_number),
            "character_state": self.novel_data.character_state, "short_summary": self.novel_data.current_chapter_short_summary,
            "filtered_context": self.novel_data.filtered_knowledge, "combined_text": combined_text_value, # Use the fetched value
            "retrieved_texts": self.knowledge_input_text.toPlainText(),
            "chapter_info": f"当前叙事需求：第{chapter_number}章 - {current_info.get('title', '')}\n{current_info.get('summary', '')}",
            "novel_setting": f"核心种子: {self.novel_data.core_seed or '未定义'}\n角色: {self.novel_data.character_dynamics or '未定义'}\n世界: {self.novel_data.world_building or '未定义'}",
        }
        logging.debug(f"_get_current_chapter_context returning context for chapter {chapter_number}")
        return context

    def on_summarize_recent_chapters(self):
        logging.info("--- Attempting to generate current chapter summary ---")
        context = self._get_current_chapter_context(require_next_chapter=True)
        if not context:
            logging.warning("Failed to get context for summarizing recent chapters. Aborting.")
            return # Abort if context failed (e.g., missing next chapter)
        logging.info("Context obtained successfully for summarize_recent. Proceeding.")
        self.run_generation_task("summarize_recent_chapters", context, "summarize_recent")

    def on_search_knowledge(self):
         context = self._get_current_chapter_context();
         if not context: return;
         if not self.novel_data.current_chapter_short_summary: QMessageBox.warning(self, "缺少信息", "建议先生成当前章节摘要...");
         self.run_generation_task("knowledge_search", context, "knowledge_search")

    def on_filter_knowledge(self):
        context = self._get_current_chapter_context();
        if not context: return;
        if not self.knowledge_input_text.toPlainText().strip(): QMessageBox.warning(self, "缺少内容", "请粘贴需要过滤的文本。"); return
        context["retrieved_texts"] = self.knowledge_input_text.toPlainText()
        self.run_generation_task("knowledge_filter", context, "knowledge_filter")

    def on_generate_chapter_draft(self):
        context = self._get_current_chapter_context(require_next_chapter=True);
        if not context: return;
        chapter_number = self.novel_data.current_chapter_writing;
        if chapter_number == 1: prompt_name = "first_chapter_draft";
        else: prompt_name = "next_chapter_draft";
        # ... (checks remain the same) ...
        self.run_generation_task(prompt_name, context, "chapter_draft")

    def on_save_chapter_draft(self):
        # ... (code remains the same as previous version with txt saving) ...
        chapter_number = self.novel_data.current_chapter_writing;
        if chapter_number is None: QMessageBox.warning(self, "错误", "没有指定要保存的章节号。"); return
        draft_text = self.chapter_text_edit.toPlainText(); self.novel_data.chapter_texts[chapter_number] = draft_text; self.mark_unsaved()
        self.update_status(f"第 {chapter_number} 章草稿已保存到内存。")
        try:
            chapter_info = self.novel_data.get_chapter_info(chapter_number); chapter_title = chapter_info.get('title', f'章节_{chapter_number}') if chapter_info else f'章节_{chapter_number}'
            sanitized_title = re.sub(r'[\\/*?:"<>|]', '', chapter_title); sanitized_title = re.sub(r'\s+', '_', sanitized_title).strip('_')
            if not sanitized_title: sanitized_title = f'章节_{chapter_number}'
            filename = f"{str(chapter_number).zfill(3)}_{sanitized_title}.txt"; save_directory = "chapters"; base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
            full_save_path = os.path.join(base_path, save_directory); os.makedirs(full_save_path, exist_ok=True); filepath = os.path.join(full_save_path, filename)
            with open(filepath, 'w', encoding='utf-8') as f: f.write(draft_text)
            logging.info(f"章节 {chapter_number} 已保存为 TXT 文件: {filepath}"); self.update_status(f"第 {chapter_number} 章草稿已保存到内存和 TXT 文件..."); QMessageBox.information(self, "保存成功", f"第 {chapter_number} 章草稿已更新，并保存为 TXT 文件...")
        except Exception as e:
            logging.exception(f"保存第 {chapter_number} 章为 TXT 文件时出错:"); QMessageBox.critical(self, "TXT 保存失败", f"将第 {chapter_number} 章保存为 TXT 文件时出错:\n{e}"); self.update_status(f"第 {chapter_number} 章草稿已保存到内存，但 TXT 文件保存失败。")

    def on_view_fullscreen(self):
        current_text = self.chapter_text_edit.toPlainText(); chapter_number = self.novel_data.current_chapter_writing
        title = f"第 {chapter_number} 章 内容预览/编辑" if chapter_number else "章节内容预览/编辑"; make_editable = True
        viewer_dialog = FullScreenViewer(current_text, self, window_title=title, editable=make_editable); result = viewer_dialog.exec_()
        if make_editable and result == QDialog.Accepted:
            edited_text = viewer_dialog.get_text();
            if edited_text != current_text:
                try: self.chapter_text_edit.textChanged.disconnect(self.mark_unsaved)
                except TypeError: pass
                self.chapter_text_edit.setText(edited_text); self.chapter_text_edit.textChanged.connect(self.mark_unsaved); self.mark_unsaved()
                self.update_status("已从放大窗口更新草稿，请记得点击“保存草稿到数据”。")

    def on_update_global_summary(self):
        chapter_number = self.novel_data.current_chapter_writing;
        if chapter_number is None: QMessageBox.warning(self, "错误", "请先加载章节..."); return
        chapter_text = self.novel_data.chapter_texts.get(chapter_number);
        if chapter_text is None: QMessageBox.warning(self, "缺少内容", f"第 {chapter_number} 章文本未保存..."); return
        format_dict = { "chapter_text": chapter_text, "global_summary": self.novel_data.global_summary or "" }
        self.run_generation_task("summary_update", format_dict, "summary_update")

    def on_update_character_state(self):
        chapter_number = self.novel_data.current_chapter_writing;
        if chapter_number is None: QMessageBox.warning(self, "错误", "请先加载章节..."); return
        chapter_text = self.novel_data.chapter_texts.get(chapter_number);
        if chapter_text is None: QMessageBox.warning(self, "缺少内容", f"第 {chapter_number} 章文本未保存..."); return
        if not self.novel_data.character_state: QMessageBox.warning(self, "缺少内容", "角色状态文档不存在..."); return
        format_dict = { "chapter_text": chapter_text, "old_state": self.novel_data.character_state }
        self.run_generation_task("update_character_state", format_dict, "update_character_state")

    def on_import_analyze_characters(self):
        content_to_analyze = self.import_text_input.toPlainText();
        if not content_to_analyze.strip(): QMessageBox.warning(self, "缺少内容", "请粘贴..."); return
        format_dict = { "content": content_to_analyze }; self.run_generation_task("character_import", format_dict, "character_import_analyze")

    def on_import_replace_state(self):
        analyzed_state = self.import_result_display.toPlainText();
        if not analyzed_state.strip(): QMessageBox.warning(self, "没有结果", "分析结果为空..."); return
        reply = QMessageBox.question(self, "确认替换", "确定替换角色状态文档吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.novel_data.character_state = analyzed_state; self.char_state_display_tab.setText(analyzed_state); self.char_state_display_writing.setText(analyzed_state)
            self.mark_unsaved(); self.update_status("角色状态已替换..."); QMessageBox.information(self, "替换成功", "角色状态文档已更新。"); self.import_replace_button.setEnabled(False)

    # --- 文件操作 ---
    def save_project(self):
        if not self.novel_data.topic and not self.novel_data.core_seed and not self.novel_data.chapter_list:
             QMessageBox.information(self, "无需保存", "项目内容似乎为空..."); return
        default_filename = f"{self.novel_data.topic or '未命名项目'}.json"; safe_filename = "".join([c for c in default_filename if c.isalnum() or c in (' ', '.', '_', '-')]).rstrip(); safe_filename = safe_filename.replace(" ", "_")
        filepath, _ = QFileDialog.getSaveFileName(self, "保存小说项目", safe_filename, "JSON 文件 (*.json)")
        if filepath:
            try:
                if not filepath.lower().endswith('.json'): filepath += '.json'
                self.novel_data.save_to_file(filepath); self.update_status(f"项目已保存到 {filepath}"); self.unmark_unsaved()
            except Exception as e:
                logging.exception("保存项目时出错:"); QMessageBox.critical(self, "保存失败", f"保存项目时出错:\n{e}"); self.update_status(f"错误：保存项目失败。")

    def load_project(self):
        if self.novel_data.unsaved_changes:
             reply = QMessageBox.question(self, "未保存的更改", "当前项目有未保存的更改...", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.No: return
        filepath, _ = QFileDialog.getOpenFileName(self, "加载小说项目", "", "JSON 文件 (*.json)")
        if filepath:
            try:
                temp_novel_data = NovelData()
                if temp_novel_data.load_from_file(filepath):
                    self.novel_data = temp_novel_data; self.update_ui_from_data(); self.update_status(f"项目已从 {filepath} 加载。")
                else:
                     QMessageBox.critical(self, "加载失败", f"无法从 {filepath} 加载项目..."); self.update_status("错误：加载项目失败。")
            except Exception as e:
                 logging.exception("加载项目时发生意外错误:"); QMessageBox.critical(self, "加载失败", f"加载项目时发生意外错误:\n{e}"); self.update_status("错误：加载项目时出错。")

    def closeEvent(self, event):
        if self.novel_data.unsaved_changes:
            reply = QMessageBox.question(self, "退出确认", "你有未保存的更改...", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
            if reply == QMessageBox.Yes: event.accept()
            elif reply == QMessageBox.No: event.ignore()
            else: event.ignore()
        else: event.accept()