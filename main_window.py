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
from prompt_loader import get_prompt # 使用 prompt_loader.py 中的函数

# 配置日志
log_format = '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=log_format) # 使用 DEBUG 级别

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
            if result.startswith("错误："): # 假设客户端在出错时返回此前缀
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
        font = QFont("Microsoft YaHei", 14) # 可修改为你系统支持的字体
        self.text_edit.setFont(font)
        self.layout.addWidget(self.text_edit)
        if editable:
            self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            self.button_box.accepted.connect(self.accept)
            self.button_box.rejected.connect(self.reject)
            save_button = self.button_box.button(QDialogButtonBox.Save)
            if save_button:
                save_button.setText("保存并关闭")
        else:
            self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
            self.button_box.clicked.connect(self.reject)
        self.layout.addWidget(self.button_box)
        self.setLayout(self.layout)

    def get_text(self) -> str:
        return self.text_edit.toPlainText()


# --- Chapter Blueprint Editor Dialog ---
class ChapterBlueprintEditor(QDialog):
    """用于编辑单个章节蓝图详情的对话框。"""
    def __init__(self, chapter_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑 第 {chapter_data.get('number', '?')} 章 蓝图")
        self.setMinimumWidth(500)
        self.data = chapter_data.copy() # 操作副本
        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.title_edit = QLineEdit(self.data.get('title', ''))
        self.summary_edit = QTextEdit(self.data.get('summary', ''))
        self.summary_edit.setAcceptRichText(False)
        self.summary_edit.setMinimumHeight(100)
        self.role_edit = QLineEdit(self.data.get('role', ''))
        self.purpose_edit = QLineEdit(self.data.get('purpose', ''))
        self.suspense_edit = QLineEdit(self.data.get('suspense_level', ''))
        self.foreshadowing_edit = QLineEdit(self.data.get('foreshadowing', ''))
        self.twist_edit = QLineEdit(self.data.get('plot_twist_level', ''))
        self.characters_edit = QLineEdit(self.data.get('characters_involved', ''))
        self.items_edit = QLineEdit(self.data.get('key_items', ''))
        self.location_edit = QLineEdit(self.data.get('scene_location', ''))
        self.time_edit = QLineEdit(self.data.get('time_constraint', ''))
        form_layout.addRow("章节号:", QLabel(str(self.data.get('number', '?'))))
        form_layout.addRow("标题:", self.title_edit)
        form_layout.addRow("本章简述:", self.summary_edit)
        form_layout.addRow("本章定位:", self.role_edit)
        form_layout.addRow("核心作用:", self.purpose_edit)
        form_layout.addRow("悬念密度:", self.suspense_edit)
        form_layout.addRow("伏笔操作:", self.foreshadowing_edit)
        form_layout.addRow("认知颠覆:", self.twist_edit)
        form_layout.addRow("涉及角色:", self.characters_edit)
        form_layout.addRow("关键物品:", self.items_edit)
        form_layout.addRow("场景地点:", self.location_edit)
        form_layout.addRow("时间限制:", self.time_edit)
        self.layout.addLayout(form_layout)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        save_button = self.button_box.button(QDialogButtonBox.Save)
        if save_button:
             save_button.setText("保存更改")
        self.layout.addWidget(self.button_box)
        self.setLayout(self.layout)

    def get_data(self) -> Dict[str, Any]:
        """返回更新后的章节数据字典。"""
        self.data['title'] = self.title_edit.text().strip()
        self.data['summary'] = self.summary_edit.toPlainText().strip()
        self.data['role'] = self.role_edit.text().strip()
        self.data['purpose'] = self.purpose_edit.text().strip()
        self.data['suspense_level'] = self.suspense_edit.text().strip()
        self.data['foreshadowing'] = self.foreshadowing_edit.text().strip()
        self.data['plot_twist_level'] = self.twist_edit.text().strip()
        self.data['characters_involved'] = self.characters_edit.text().strip()
        self.data['key_items'] = self.items_edit.text().strip()
        self.data['scene_location'] = self.location_edit.text().strip()
        self.data['time_constraint'] = self.time_edit.text().strip()
        return self.data

# --- 主窗口 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 小说写作助手 (Gemini)")
        self.setGeometry(100, 100, 1200, 800)
        try:
            self.gemini_client = GeminiClient()
        except Exception as e:
            QMessageBox.critical(self, "初始化错误", f"无法初始化 Gemini 客户端: {e}\n请确保 API 密钥正确且网络连接正常。程序即将退出。")
            sys.exit(1)
        self.novel_data = NovelData()
        self.generation_thread: Optional[GenerationThread] = None
        self.last_chunk_start: Optional[int] = None
        self.regen_pending_data: Optional[Dict[str, Any]] = None
        self.setup_ui()
        self.connect_signals()
        self.update_ui_from_data()
        self.update_status("就绪.")

    def setup_ui(self):
        """创建和布局 UI 控件。"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.setup_menu_bar()
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
        self.chapters_spinbox.setRange(1, 1000)
        self.chapters_spinbox.setValue(self.novel_data.target_chapters)
        self.words_spinbox = QSpinBox()
        self.words_spinbox.setRange(500, 10000)
        self.words_spinbox.setSingleStep(100)
        self.words_spinbox.setValue(self.novel_data.words_per_chapter)
        setup_form_layout.addRow("小说主题:", self.topic_input)
        setup_form_layout.addRow("小说类型:", self.genre_input)
        setup_form_layout.addRow("目标章节数:", self.chapters_spinbox)
        setup_form_layout.addRow("每章目标字数:", self.words_spinbox)
        setup_input_group.setLayout(setup_form_layout)
        setup_layout.addWidget(setup_input_group)
        self.generate_core_seed_button = QPushButton("1. 生成核心种子 (雪花第1层)")
        setup_layout.addWidget(self.generate_core_seed_button)
        self.core_seed_display = QTextEdit()
        self.core_seed_display.setReadOnly(True)  # 初始只读
        self.core_seed_display.setPlaceholderText("此处显示生成的故事核心种子，生成或加载后可编辑...")
        setup_layout.addWidget(QLabel("核心种子:"))
        setup_layout.addWidget(self.core_seed_display)
        setup_layout.addStretch()

        # --- 2. 角色 & 世界观 & 情节 选项卡 ---
        self.cdwp_tab = QWidget()
        self.tab_widget.addTab(self.cdwp_tab, "角色 & 世界 & 情节")
        cdwp_layout = QVBoxLayout(self.cdwp_tab)
        cdwp_splitter = QSplitter(Qt.Horizontal)
        cdwp_left_widget = QWidget()
        cdwp_left_layout = QVBoxLayout(cdwp_left_widget)
        self.cdwp_user_guidance_input = QTextEdit()
        self.cdwp_user_guidance_input.setPlaceholderText("可选：在此输入对角色、世界观或情节的具体指导...")
        self.cdwp_user_guidance_input.setFixedHeight(100)
        self.generate_chars_button = QPushButton("2. 生成角色动力学")
        self.generate_world_button = QPushButton("3. 生成世界构建矩阵")
        self.generate_plot_button = QPushButton("4. 生成情节架构")
        self.create_char_state_button = QPushButton("初始化角色状态文档")
        cdwp_left_layout.addWidget(QLabel("用户指导 (可选):"))
        cdwp_left_layout.addWidget(self.cdwp_user_guidance_input)
        cdwp_left_layout.addWidget(self.generate_chars_button)
        cdwp_left_layout.addWidget(self.generate_world_button)
        cdwp_left_layout.addWidget(self.generate_plot_button)
        cdwp_left_layout.addWidget(self.create_char_state_button)
        cdwp_left_layout.addStretch()
        cdwp_right_tabs = QTabWidget()
        self.char_display = QTextEdit()
        self.char_display.setReadOnly(True)
        self.world_display = QTextEdit()
        self.world_display.setReadOnly(True)
        self.plot_display = QTextEdit()
        self.plot_display.setReadOnly(True)
        self.char_state_display_tab = QTextEdit()
        self.char_state_display_tab.setReadOnly(True)
        self.char_state_display_tab.setPlaceholderText("角色状态文档将在此显示...")
        cdwp_right_tabs.addTab(self.char_display, "角色动力学")
        cdwp_right_tabs.addTab(self.world_display, "世界构建")
        cdwp_right_tabs.addTab(self.plot_display, "情节架构")
        cdwp_right_tabs.addTab(self.char_state_display_tab, "角色状态")
        cdwp_splitter.addWidget(cdwp_left_widget)
        cdwp_splitter.addWidget(cdwp_right_tabs)
        cdwp_splitter.setSizes([300, 700])
        cdwp_layout.addWidget(cdwp_splitter)

        # --- 3. 章节蓝图 选项卡 ---
        self.blueprint_tab = QWidget()
        self.tab_widget.addTab(self.blueprint_tab, "章节蓝图")
        blueprint_layout = QVBoxLayout(self.blueprint_tab)
        blueprint_control_group = QGroupBox("生成控制")
        blueprint_control_main_layout = QVBoxLayout(blueprint_control_group)
        guidance_layout = QHBoxLayout()
        self.blueprint_user_guidance_input = QLineEdit()
        self.blueprint_user_guidance_input.setPlaceholderText("可选：对后续章节生成的额外指导...")
        guidance_layout.addWidget(QLabel("用户指导:"))
        guidance_layout.addWidget(self.blueprint_user_guidance_input)
        blueprint_control_main_layout.addLayout(guidance_layout)
        full_gen_layout = QHBoxLayout()
        self.generate_blueprint_button = QPushButton("生成章节蓝图 (全部 - 覆盖!)")
        full_gen_layout.addWidget(self.generate_blueprint_button)
        full_gen_layout.addStretch()
        blueprint_control_main_layout.addLayout(full_gen_layout)
        chunk_gen_layout = QHBoxLayout()
        self.start_chapter_spinbox = QSpinBox()
        self.start_chapter_spinbox.setMinimum(1)
        self.end_chapter_spinbox = QSpinBox()
        self.end_chapter_spinbox.setMinimum(1)
        self.generate_chunked_blueprint_button = QPushButton("生成/覆盖指定范围蓝图")
        chunk_gen_layout.addWidget(QLabel("从第"))
        chunk_gen_layout.addWidget(self.start_chapter_spinbox)
        chunk_gen_layout.addWidget(QLabel("章 到 第"))
        chunk_gen_layout.addWidget(self.end_chapter_spinbox)
        chunk_gen_layout.addWidget(QLabel("章"))
        chunk_gen_layout.addWidget(self.generate_chunked_blueprint_button)
        chunk_gen_layout.addStretch()
        blueprint_control_main_layout.addLayout(chunk_gen_layout)
        regen_layout = QHBoxLayout()
        self.regen_start_spinbox = QSpinBox()
        self.regen_start_spinbox.setMinimum(1)
        self.regenerate_blueprint_button = QPushButton("从指定章重新生成后续蓝图 (覆盖后续!)")
        regen_layout.addWidget(QLabel("从第"))
        regen_layout.addWidget(self.regen_start_spinbox)
        regen_layout.addWidget(QLabel("章开始重新生成后续:"))
        regen_layout.addWidget(self.regenerate_blueprint_button)
        regen_layout.addStretch()
        blueprint_control_main_layout.addLayout(regen_layout)
        blueprint_layout.addWidget(blueprint_control_group)
        list_group = QGroupBox("章节目录")
        list_layout = QVBoxLayout(list_group)
        list_controls_layout = QHBoxLayout()
        self.total_chapters_label = QLabel("当前总章节数: 0")
        self.load_selected_blueprint_button = QPushButton("加载选中项到写作区")  # 新增按钮
        list_controls_layout.addWidget(self.total_chapters_label)
        list_controls_layout.addStretch()
        list_controls_layout.addWidget(self.load_selected_blueprint_button)  # 添加按钮到布局
        list_layout.addLayout(list_controls_layout)
        self.chapter_list_widget = QListWidget()
        self.chapter_list_widget.setToolTip("双击条目可编辑蓝图详情")  # 提示编辑方式
        list_layout.addWidget(self.chapter_list_widget)
        blueprint_layout.addWidget(list_group, 1)  # 列表区域可伸展

        # --- 4. 章节写作 选项卡 ---
        self.writing_tab = QWidget()
        self.tab_widget.addTab(self.writing_tab, "章节写作")
        writing_layout = QVBoxLayout(self.writing_tab)
        writing_splitter = QSplitter(Qt.Vertical)
        writing_top_widget = QWidget()
        writing_top_layout = QVBoxLayout(writing_top_widget)
        chapter_selection_layout = QHBoxLayout()
        self.chapter_select_spinbox = QSpinBox()
        self.chapter_select_spinbox.setMinimum(1)
        self.load_chapter_button = QPushButton("加载章节数据")
        self.current_chapter_info_display = QLabel("请选择章节并点击加载...")
        self.current_chapter_info_display.setWordWrap(True)
        chapter_selection_layout.addWidget(QLabel("当前写作章节:"))
        chapter_selection_layout.addWidget(self.chapter_select_spinbox)
        chapter_selection_layout.addWidget(self.load_chapter_button)
        chapter_selection_layout.addWidget(self.current_chapter_info_display, 1)
        writing_top_layout.addLayout(chapter_selection_layout)
        self.writing_user_guidance_input = QTextEdit()
        self.writing_user_guidance_input.setPlaceholderText("针对本章写作的具体指导...")
        self.writing_user_guidance_input.setMaximumHeight(80)
        writing_top_layout.addWidget(QLabel("用户指导 (本章):"))
        writing_top_layout.addWidget(self.writing_user_guidance_input)
        knowledge_layout = QHBoxLayout()
        self.summarize_recent_button = QPushButton("生成当前章节摘要")
        self.search_knowledge_button = QPushButton("生成知识库关键词")
        self.filter_knowledge_button = QPushButton("过滤知识库内容")
        knowledge_layout.addWidget(self.summarize_recent_button)
        knowledge_layout.addWidget(self.search_knowledge_button)
        knowledge_layout.addWidget(self.filter_knowledge_button)
        knowledge_layout.addStretch()
        writing_top_layout.addLayout(knowledge_layout)
        context_display_layout = QHBoxLayout()
        summary_kn_group = QGroupBox("上下文参考")
        summary_kn_layout = QFormLayout(summary_kn_group)
        self.short_summary_display = QTextEdit()
        self.short_summary_display.setReadOnly(True)
        self.short_summary_display.setMaximumHeight(100)
        self.short_summary_display.setPlaceholderText("当前章节摘要...")
        summary_kn_layout.addRow("章节摘要:", self.short_summary_display)
        self.knowledge_keywords_display = QLineEdit()
        self.knowledge_keywords_display.setReadOnly(True)
        self.knowledge_keywords_display.setPlaceholderText("知识库关键词...")
        summary_kn_layout.addRow("知识关键词:", self.knowledge_keywords_display)
        self.knowledge_input_text = QTextEdit()
        self.knowledge_input_text.setPlaceholderText("在此粘贴或输入相关知识库文本...")
        self.knowledge_input_text.setMaximumHeight(100)
        summary_kn_layout.addRow("知识库输入:", self.knowledge_input_text)
        self.filtered_knowledge_display = QTextEdit()
        self.filtered_knowledge_display.setReadOnly(True)
        self.filtered_knowledge_display.setMaximumHeight(100)
        self.filtered_knowledge_display.setPlaceholderText("过滤后的知识库内容...")
        summary_kn_layout.addRow("过滤后知识:", self.filtered_knowledge_display)
        context_display_layout.addWidget(summary_kn_group)
        other_context_scroll = QScrollArea()
        other_context_scroll.setWidgetResizable(True)
        other_context_widget = QWidget()
        other_context_layout = QVBoxLayout(other_context_widget)
        # **** 修改控件和标签以反映累积摘要 ****
        self.prev_cumulative_summary_display = QTextEdit()  # <--- 重命名变量
        self.prev_cumulative_summary_display.setReadOnly(True)
        self.prev_cumulative_summary_display.setMaximumHeight(150)
        self.prev_cumulative_summary_display.setPlaceholderText("加载章节后显示前文章节的累积摘要...")
        other_context_layout.addWidget(QLabel("前文章节累积摘要:"))  # <--- 修改标签文本
        other_context_layout.addWidget(self.prev_cumulative_summary_display)  # <--- 使用新变量名
        # **************************************
        self.prev_excerpt_display = QTextEdit()
        self.prev_excerpt_display.setReadOnly(True)
        self.prev_excerpt_display.setMaximumHeight(100)
        self.prev_excerpt_display.setPlaceholderText("前章结尾段落...")
        other_context_layout.addWidget(QLabel("前章结尾:"))
        other_context_layout.addWidget(self.prev_excerpt_display)
        self.char_state_display_writing = QTextEdit()
        self.char_state_display_writing.setReadOnly(True)
        self.char_state_display_writing.setMaximumHeight(200)
        self.char_state_display_writing.setPlaceholderText("当前角色状态...")
        other_context_layout.addWidget(QLabel("角色状态:"))
        other_context_layout.addWidget(self.char_state_display_writing)
        other_context_layout.addStretch()
        other_context_scroll.setWidget(other_context_widget)
        context_display_layout.addWidget(other_context_scroll)
        writing_top_layout.addLayout(context_display_layout)
        writing_splitter.addWidget(writing_top_widget)
        writing_bottom_widget = QWidget()
        writing_bottom_layout = QVBoxLayout(writing_bottom_widget)
        button_layout_group = QHBoxLayout()
        self.generate_draft_button = QPushButton("生成本章草稿")
        self.save_draft_button = QPushButton("保存草稿到数据")
        self.view_fullscreen_button = QPushButton("放大查看/编辑")
        button_layout_group.addWidget(self.generate_draft_button)
        button_layout_group.addWidget(self.save_draft_button)
        button_layout_group.addWidget(self.view_fullscreen_button)
        button_layout_group.addStretch()
        writing_bottom_layout.addLayout(button_layout_group)
        self.chapter_text_edit = QTextEdit()
        self.chapter_text_edit.setPlaceholderText("生成的章节草稿将显示在此处...")
        font = QFont("Microsoft YaHei", 11)
        self.chapter_text_edit.setFont(font)
        writing_bottom_layout.addWidget(self.chapter_text_edit)
        update_button_layout = QHBoxLayout()
        # **** 修改按钮文本和变量名 ****
        self.update_cumulative_summary_button = QPushButton("更新本章累积摘要")  # <--- 修改文本和变量名
        self.update_char_state_button = QPushButton("更新角色状态")
        update_button_layout.addWidget(self.update_cumulative_summary_button)  # <--- 使用新变量名
        # ****************************
        update_button_layout.addWidget(self.update_char_state_button)
        update_button_layout.addStretch()
        writing_bottom_layout.addLayout(update_button_layout)
        writing_splitter.addWidget(writing_bottom_widget)
        writing_splitter.setSizes([450, 550])
        writing_layout.addWidget(writing_splitter)

        # --- 5. 角色导入 Tab ---
        self.import_tab = QWidget()
        self.tab_widget.addTab(self.import_tab, "角色导入")
        import_layout = QVBoxLayout(self.import_tab)
        self.import_text_input = QTextEdit()
        self.import_text_input.setPlaceholderText("在此粘贴包含角色信息的小说文本...")
        self.import_analyze_button = QPushButton("分析并生成角色状态")
        self.import_result_display = QTextEdit()
        self.import_result_display.setReadOnly(True)
        self.import_result_display.setPlaceholderText("分析后的角色状态将在此显示...")
        self.import_replace_button = QPushButton("用分析结果替换当前角色状态")
        import_layout.addWidget(QLabel("粘贴文本:"))
        import_layout.addWidget(self.import_text_input, 1)
        import_layout.addWidget(self.import_analyze_button)
        import_layout.addWidget(QLabel("分析结果:"))
        import_layout.addWidget(self.import_result_display, 1)
        import_layout.addWidget(self.import_replace_button)

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
        self.core_seed_display.textChanged.connect(self.on_core_seed_edited)  # 核心种子编辑
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
        self.regenerate_blueprint_button.clicked.connect(self.on_regenerate_blueprint)
        self.chapter_list_widget.itemDoubleClicked.connect(self.on_edit_chapter_blueprint)  # 双击编辑蓝图
        self.load_selected_blueprint_button.clicked.connect(self.on_load_selected_blueprint_for_writing)  # 加载按钮
        # 章节写作
        self.load_chapter_button.clicked.connect(self.on_load_chapter_data)
        self.summarize_recent_button.clicked.connect(self.on_summarize_recent_chapters)
        self.search_knowledge_button.clicked.connect(self.on_search_knowledge)
        self.filter_knowledge_button.clicked.connect(self.on_filter_knowledge)
        self.generate_draft_button.clicked.connect(self.on_generate_chapter_draft)
        self.save_draft_button.clicked.connect(self.on_save_chapter_draft)
        self.view_fullscreen_button.clicked.connect(self.on_view_fullscreen)
        # **** 修改信号连接 ****
        self.update_cumulative_summary_button.clicked.connect(self.on_update_cumulative_summary)  # <--- 修改
        # *******************
        self.update_char_state_button.clicked.connect(self.on_update_character_state)
        # 角色导入
        self.import_analyze_button.clicked.connect(self.on_import_analyze_characters)
        self.import_replace_button.clicked.connect(self.on_import_replace_state)
        # 标记未保存
        self.topic_input.textChanged.connect(self.mark_unsaved);
        self.genre_input.textChanged.connect(self.mark_unsaved)
        self.chapters_spinbox.valueChanged.connect(self.mark_unsaved);
        self.words_spinbox.valueChanged.connect(self.mark_unsaved)
        self.chapter_text_edit.textChanged.connect(self.mark_unsaved);
        self.writing_user_guidance_input.textChanged.connect(self.mark_unsaved)
        self.cdwp_user_guidance_input.textChanged.connect(self.mark_unsaved);
        self.blueprint_user_guidance_input.textChanged.connect(self.mark_unsaved)
        self.knowledge_input_text.textChanged.connect(self.mark_unsaved);
        self.import_text_input.textChanged.connect(self.mark_unsaved)

    # --- 核心种子和未保存状态处理 ---
    def on_core_seed_edited(self):
        """核心种子文本框编辑时调用"""
        if not self.core_seed_display.isReadOnly():
            new_text = self.core_seed_display.toPlainText()
            if self.novel_data.core_seed != new_text:
                self.novel_data.core_seed = new_text
                self.mark_unsaved()
                logging.debug("Core seed updated by user edit.")

    def mark_unsaved(self):
        """标记项目存在未保存的更改，并在窗口标题添加星号。"""
        if not self.novel_data.unsaved_changes:
             self.novel_data.unsaved_changes = True
             self.setWindowTitle(self.windowTitle().replace(" *", "") + " *")

    def unmark_unsaved(self):
        """标记项目为已保存状态，并移除窗口标题的星号。"""
        if self.novel_data.unsaved_changes:
            self.novel_data.unsaved_changes = False
            title = self.windowTitle()
            if title.endswith(" *"):
                self.setWindowTitle(title[:-2])

    # --- 辅助函数 ---
    def update_status(self, message: str):
        """更新状态栏消息并记录日志。"""
        logging.info(f"状态: {message}")
        self.statusBar().showMessage(message)

    def _save_text_to_project_file(self, filename: str, content: Optional[str]):
        """
        辅助函数：将文本内容保存到项目根目录下的 'project_files' 子目录中。
        """
        if not content:
            logging.info(f"跳过保存 '{filename}' 因为内容为空。")
            return True # 内容为空不是错误

        save_directory = "project_files" # 子目录名称
        base_path = os.path.dirname(os.path.abspath(sys.argv[0])) # 程序运行目录
        full_save_path = os.path.join(base_path, save_directory)
        filepath = os.path.join(full_save_path, filename)

        try:
            os.makedirs(full_save_path, exist_ok=True) # 确保目录存在
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logging.info(f"成功保存 '{filename}' 到 {filepath}")
            return True
        except Exception as e:
            logging.exception(f"保存文件 '{filename}' 到 {filepath} 时出错:")
            QMessageBox.critical(self, "文件保存失败", f"保存 {filename} 时出错:\n{e}")
            return False


    def run_generation_task(self, prompt_name: str, format_dict: dict, task_id: str):
        """启动一个后台生成任务，增加对缺失键的默认值处理和格式化错误捕获。"""
        if self.generation_thread and self.generation_thread.isRunning():
            QMessageBox.warning(self, "请稍候", "另一个生成任务正在进行中..."); return
        try:
            prompt_template = get_prompt(prompt_name)
            if prompt_template.startswith("错误："):
                 QMessageBox.critical(self, "加载提示词错误", prompt_template)
                 self.update_status(f"错误：加载提示词 {prompt_name} 失败。"); self.set_buttons_enabled(True)
                 return

            processed_format_dict = {k: (v if v is not None else "") for k, v in format_dict.items()}

            # **** 为关键占位符提供默认值 ****
            default_values = { # Ensure all keys used in *any* prompt are here
                'novel_number': '?', 'chapter_number': '?', 'chapter_title': '（无标题）', 'chapter_role': '（未定义）',
                'chapter_purpose': '（未定义）', 'suspense_level': '（未定义）', 'foreshadowing': '（未定义）',
                'plot_twist_level': '（未定义）', 'chapter_summary': '（无简述）', 'characters_involved': '（未指定）',
                'key_items': '（未指定）', 'scene_location': '（未指定）', 'time_constraint': '（未指定）',
                'next_chapter_number': '?', 'next_chapter_title': '（未定义）', 'next_chapter_role': '（未定义）',
                'next_chapter_purpose': '（未定义）', 'next_chapter_suspense_level': '（未定义）',
                'next_chapter_foreshadowing': '（未定义）', 'next_chapter_plot_twist_level': '（未定义）',
                'next_chapter_summary': '（无简述）', 'next_chapter_characters_involved': '（未指定）',
                'next_chapter_key_items': '（未指定）', 'next_chapter_scene_location': '（未指定）',
                'next_chapter_time_constraint': '（未指定）', 'previous_cumulative_summary': '（无）',
                'previous_chapter_full_text': '（无）', 'previous_chapter_excerpt': '（无）', 'character_state': '（无）',
                'short_summary': '（无）', 'filtered_context': '（无）', 'combined_text': '（无）',
                'novel_setting': '（设定信息缺失）', 'word_number': '未知', 'user_guidance': '',
                'chapter_info': '（章节信息缺失）', 'topic': '（未设置）', 'genre': '（未设置）',
                'number_of_chapters': '?', 'novel_architecture': '（架构信息缺失）',
                'previous_chapters_summary': '（无）', 'chapter_list': '（无）', 'n': '?', 'm': '?',
                'old_state': '（无）', 'content': '', 'retrieved_texts': '',
                'current_chapter_number': '?', 'previous_chapter_number': '?', 'current_chapter_text': '',
            }

            final_format_dict = default_values.copy()
            final_format_dict.update(processed_format_dict)
            final_format_dict = {k: (v if v is not None else default_values.get(k, "")) for k, v in final_format_dict.items()}
            # **************************************************

            logging.debug(f"--- Formatting prompt '{prompt_name}' (task: {task_id}) ---")
            logging.debug(f"Final format dict keys for format: {list(final_format_dict.keys())}")

            # **** Add specific try-except around format ****
            try:
                final_prompt = prompt_template.format(**final_format_dict)
                logging.debug(f"Formatted Prompt (first 500 chars): {final_prompt[:500]}...")
            except KeyError as e_format:
                logging.error(f"格式化提示词 '{prompt_name}' 时最终失败，缺少键: {e_format}", exc_info=True)
                logging.error(f"Dictionary causing formatting error: {final_format_dict}")
                QMessageBox.critical(self, "内部格式化错误", f"准备提示词 '{prompt_name}' 时内部错误，缺少信息: {e_format}\n请检查日志获取详细信息。")
                self.update_status(f"错误：内部格式化提示词 {prompt_name} 失败。"); self.set_buttons_enabled(True)
                return # Stop execution
            except Exception as e_format_other:
                logging.error(f"格式化提示词 '{prompt_name}' 时发生意外错误: {e_format_other}", exc_info=True)
                logging.error(f"Dictionary causing formatting error: {final_format_dict}")
                QMessageBox.critical(self, "内部格式化错误", f"准备提示词 '{prompt_name}' 时发生意外错误: {e_format_other}\n请检查日志获取详细信息。")
                self.update_status(f"错误：内部格式化提示词 {prompt_name} 时出错。"); self.set_buttons_enabled(True)
                return # Stop execution
            # ***********************************************

            self.update_status(f"正在生成 {task_id}...")
            self.set_buttons_enabled(False)
            self.generation_thread = GenerationThread(self.gemini_client, final_prompt, task_id)
            self.generation_thread.generation_complete.connect(self.handle_generation_complete)
            self.generation_thread.generation_error.connect(self.handle_generation_error)
            self.generation_thread.finished.connect(self.on_generation_finished)
            self.generation_thread.start()
            logging.info(f"Generation thread for task '{task_id}' started.")

        except Exception as e: # Catch other potential errors before formatting
            logging.exception(f"准备生成任务 '{task_id}' 时发生错误:")
            QMessageBox.critical(self, "错误", f"准备生成任务 '{task_id}' 时出错: {e}")
            self.update_status(f"错误：任务 {task_id} 准备时出错。"); self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        """启用或禁用大部分生成/操作按钮。"""
        excluded_buttons = ["保存项目", "加载项目", "退出"]
        for button in self.findChildren(QPushButton):
            if button.text() not in excluded_buttons:
                button.setEnabled(enabled)
        if hasattr(self, 'import_result_display') and hasattr(self, 'import_replace_button'):
             has_content = bool(self.import_result_display.toPlainText().strip())
             self.import_replace_button.setEnabled(has_content and enabled)
        if hasattr(self, 'load_selected_blueprint_button'): # 控制蓝图加载按钮
             self.load_selected_blueprint_button.setEnabled(enabled)

    def handle_generation_complete(self, result: str, task_id: str):
        """处理后台任务成功返回的结果。"""
        self.update_status(f"任务 {task_id} 完成。")
        try:
            if task_id == "core_seed":
                self.novel_data.core_seed = result
                try:
                    self.core_seed_display.textChanged.disconnect(self.on_core_seed_edited)
                except TypeError:
                    pass
                self.core_seed_display.setText(result)
                self.core_seed_display.setReadOnly(False)
                self.core_seed_display.textChanged.connect(self.on_core_seed_edited)
                self.mark_unsaved()
            elif task_id == "character_dynamics":
                self.novel_data.character_dynamics = result
                self.char_display.setText(result)
                self.mark_unsaved()
                QMessageBox.information(self, "下一步", "角色动力学已生成。")
            elif task_id == "world_building":
                self.novel_data.world_building = result
                self.world_display.setText(result)
                self.mark_unsaved()
            elif task_id == "plot_architecture":
                self.novel_data.plot_architecture = result
                self.plot_display.setText(result)
                self.mark_unsaved()
            elif task_id == "create_character_state":
                self.novel_data.character_state = result
                self.char_state_display_tab.setText(result)
                self.char_state_display_writing.setText(result)
                self.mark_unsaved()
                if self._save_text_to_project_file("character_state.txt", result):
                    self.update_status("角色状态已初始化并保存到 TXT。")
                    QMessageBox.information(self, "成功", "角色状态已初始化并保存到 TXT。")
                else:
                    self.update_status("角色状态已初始化（TXT 保存失败）。")
            elif task_id == "chapter_blueprint":
                self.novel_data.update_chapter_list(result, is_chunked=False)
                self.update_chapter_list_widget()
                self.update_chapter_select_spinbox_range()
                self.mark_unsaved()
            elif task_id == "chapter_blueprint_chunk":
                start_chapter = self.last_chunk_start
                if start_chapter is None: logging.error("分块蓝图结果无起始章节号！"); return
                self.novel_data.update_chapter_list(result, is_chunked=True, start_chapter=start_chapter)
                self.update_chapter_list_widget()
                self.update_chapter_select_spinbox_range()
                self.last_chunk_start = None
                self.mark_unsaved()
            elif task_id == "written_chapters_summary_for_regen":
                if not self.regen_pending_data: logging.error("收到摘要但无挂起数据"); QMessageBox.critical(self, "内部错误", "处理摘要时错误"); self.regen_pending_data = None; return
                written_summary = result
                logging.info("摘要已生成。")
                self.update_status("摘要已生成，准备生成后续蓝图..."); QApplication.processEvents()
                start_chapter = self.regen_pending_data['start_chapter']
                total_chapters = self.regen_pending_data['total_chapters']
                guidance = self.regen_pending_data['guidance']
                self.novel_data.chapter_list = [ch for ch in self.novel_data.chapter_list if ch.get('number', -1) < start_chapter]
                self.update_chapter_list_widget(); QApplication.processEvents()
                existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_chapter)
                novel_architecture = f"核心种子: {self.novel_data.core_seed or 'N/A'}..."
                format_dict = { "user_guidance": guidance, "novel_architecture": novel_architecture, "previous_chapters_summary": written_summary, "chapter_list": existing_list_str, "number_of_chapters": total_chapters, "n": start_chapter, "m": total_chapters, }
                self.run_generation_task("chunked_chapter_blueprint", format_dict, "chapter_blueprint_regenerate")
            elif task_id == "chapter_blueprint_regenerate":
                try:
                    new_chapters = self.novel_data._parse_chapter_list_string(result)
                    if not new_chapters: logging.warning("重生成蓝图解析为空"); QMessageBox.warning(self, "生成警告", "AI未能生成有效后续蓝图")
                    else:
                         self.novel_data.chapter_list.extend(new_chapters)
                         self.novel_data.chapter_list.sort(key=lambda x: x.get('number', float('inf')))
                         logging.info(f"重生成：添加{len(new_chapters)}新蓝图")
                         self.update_chapter_list_widget(); self.update_chapter_select_spinbox_range(); self.mark_unsaved()
                         QMessageBox.information(self, "成功", "已重生成后续蓝图")
                except Exception as e: logging.exception("处理重生成蓝图结果时出错:"); QMessageBox.critical(self, "处理错误", f"处理重生成蓝图结果出错:\n{e}")
                finally: self.regen_pending_data = None
            elif task_id == "summarize_recent":
                summary_content = result
                if "当前章节摘要:" in result:
                    try: summary_content = result.split("当前章节摘要:", 1)[1].strip()
                    except IndexError: pass
                self.novel_data.current_chapter_short_summary = summary_content
                self.short_summary_display.setText(summary_content)
            elif task_id == "knowledge_search":
                self.novel_data.knowledge_keywords = result
                self.knowledge_keywords_display.setText(result)
                QMessageBox.information(self, "提示", "知识库关键词已生成...")
            elif task_id == "knowledge_filter":
                self.novel_data.filtered_knowledge = result
                self.filtered_knowledge_display.setText(result)
            elif task_id == "chapter_draft":
                self.chapter_text_edit.setText(result)
                QMessageBox.information(self, "提示", "章节草稿已生成...")
            elif task_id == "summary_update": # 更新累积摘要处理
                current_chapter_num = self.novel_data.current_chapter_writing
                if current_chapter_num is not None:
                    self.novel_data.cumulative_summaries[current_chapter_num] = result # 存储结果
                    self.mark_unsaved() # 标记项目已修改
                    self.update_status(f"第 {current_chapter_num} 章累积摘要已更新。")
                    QMessageBox.information(self, "成功", f"第 {current_chapter_num} 章的累积摘要已更新。")
                else:
                    logging.error("更新累积摘要时无法获取当前章节号！")
                    QMessageBox.warning(self, "内部错误", "更新累积摘要时出错。")
            elif task_id == "update_character_state":
                state_content = result; self.novel_data.character_state = state_content
                self.char_state_display_tab.setText(state_content); self.char_state_display_writing.setText(state_content)
                self.mark_unsaved()
                if self._save_text_to_project_file("character_state.txt", state_content):
                    self.update_status("角色状态已更新并保存到 TXT。"); QMessageBox.information(self, "成功", "角色状态已更新并保存到 TXT。")
                else:
                    self.update_status("角色状态已更新（TXT 保存失败）。")
            elif task_id == "character_import_analyze":
                self.import_result_display.setText(result);
                if result and result.strip(): self.import_replace_button.setEnabled(True)
                else: self.import_replace_button.setEnabled(False); QMessageBox.information(self, "分析完成", "角色状态分析完成。")
            else:
                logging.warning(f"收到未知任务ID '{task_id}'")
        except Exception as e:
            logging.exception(f"处理任务 {task_id} 结果时出错:")
            QMessageBox.critical(self, "处理结果错误", f"处理任务 {task_id} 结果出错:\n{e}")

    def handle_generation_error(self, error_message: str, task_id: str):
        """处理后台任务失败的情况。"""
        self.update_status(f"任务 {task_id} 失败。")
        QMessageBox.critical(self, f"生成错误 ({task_id})", f"生成过程中发生错误:\n{error_message}")
        self.last_chunk_start = None;
        if task_id == "written_chapters_summary_for_regen": self.regen_pending_data = None; logging.error("摘要生成失败，重生成中止。")
        elif task_id == "chapter_blueprint_regenerate": self.regen_pending_data = None; QMessageBox.warning(self, "生成失败", "重生成后续蓝图失败。")

    def on_generation_finished(self):
        """后台任务完成后（无论成功或失败）调用。"""
        if not self.regen_pending_data:
            self.set_buttons_enabled(True)
            self.update_status("就绪.")
        else:
            logging.info("Generation finished, but regen pending.")
            self.set_buttons_enabled(False)
        self.generation_thread = None

    # --- UI 更新与槽函数 ---
    def update_blueprint_spinbox_ranges(self, max_chapters: Optional[int] = None):
        """更新章节蓝图选项卡中 SpinBox 的范围。"""
        if max_chapters is None:
            max_chapters = self.novel_data.target_chapters
        safe_max = max(1, max_chapters)
        self.start_chapter_spinbox.setMaximum(safe_max)
        self.end_chapter_spinbox.setMaximum(safe_max)
        self.regen_start_spinbox.setMaximum(safe_max)
        if self.end_chapter_spinbox.value() > safe_max:
            self.end_chapter_spinbox.setValue(safe_max)
        if self.start_chapter_spinbox.value() > safe_max:
            self.start_chapter_spinbox.setValue(safe_max)
        if self.regen_start_spinbox.value() > safe_max:
            self.regen_start_spinbox.setValue(safe_max)

    def update_chapter_select_spinbox_range(self):
         """更新章节写作选项卡中章节选择 SpinBox 的范围。"""
         max_chap = len(self.novel_data.chapter_list)
         self.chapter_select_spinbox.setMaximum(max_chap if max_chap > 0 else 1)

    def update_ui_from_data(self):
        """使用 self.novel_data 中的数据更新整个 UI 显示。"""
        logging.info("--- update_ui_from_data ---")
        current_topic = self.novel_data.topic or ""
        current_genre = self.novel_data.genre or ""
        current_target_chapters = self.novel_data.target_chapters
        current_words_per_chapter = self.novel_data.words_per_chapter
        current_core_seed = self.novel_data.core_seed or ""
        current_char_dynamics = self.novel_data.character_dynamics or ""
        current_world_building = self.novel_data.world_building or ""
        current_plot_architecture = self.novel_data.plot_architecture or ""
        current_char_state = self.novel_data.character_state or ""
        # 更新项目设置 Tab
        self.topic_input.setText(current_topic)
        self.genre_input.setText(current_genre)
        self.chapters_spinbox.setRange(1, 1000)
        self.chapters_spinbox.setValue(current_target_chapters)
        self.words_spinbox.setRange(500, 10000)
        self.words_spinbox.setValue(current_words_per_chapter)
        try:
            self.core_seed_display.textChanged.disconnect(self.on_core_seed_edited)
        except TypeError:
            pass
        self.core_seed_display.setText(current_core_seed)
        self.core_seed_display.setReadOnly(not bool(current_core_seed))
        self.core_seed_display.textChanged.connect(self.on_core_seed_edited)
        # 更新角色&世界&情节 Tab
        self.char_display.setText(current_char_dynamics)
        self.world_display.setText(current_world_building)
        self.plot_display.setText(current_plot_architecture)
        self.char_state_display_tab.setText(current_char_state)
        # 更新章节蓝图 Tab
        self.update_chapter_list_widget()
        self.update_blueprint_spinbox_ranges(current_target_chapters)
        default_end_chunk = min(10, current_target_chapters) if current_target_chapters > 0 else 1
        self.end_chapter_spinbox.setValue(max(1, default_end_chunk))
        self.regen_start_spinbox.setValue(1)
        # 更新章节写作 Tab
        self.update_chapter_select_spinbox_range()
        self.current_chapter_info_display.setText("请选择章节并点击加载...")
        self.short_summary_display.clear()
        self.knowledge_keywords_display.clear()
        self.knowledge_input_text.clear()
        self.filtered_knowledge_display.clear()
        self.prev_cumulative_summary_display.clear() # 清空累积摘要区
        self.prev_excerpt_display.clear()
        self.char_state_display_writing.setText(current_char_state) # 加载角色状态
        self.chapter_text_edit.clear()
        self.writing_user_guidance_input.clear()
        # 更新角色导入 Tab
        self.import_text_input.clear()
        self.import_result_display.clear()
        self.import_replace_button.setEnabled(False)
        # 重置状态
        self.novel_data.current_chapter_writing = None
        self.unmark_unsaved()
        self.update_status("项目数据已加载/刷新。")
        logging.info("--- update_ui_from_data end ---")

    def update_chapter_list_widget(self):
        """更新章节蓝图列表控件显示。"""
        self.chapter_list_widget.clear()
        count = len(self.novel_data.chapter_list)
        self.total_chapters_label.setText(f"当前总章节数: {count}")
        if not self.novel_data.chapter_list:
            self.chapter_list_widget.addItem("暂无章节蓝图"); return
        for chapter_index, chapter in enumerate(self.novel_data.chapter_list):
            num = chapter.get('number', '?'); title = chapter.get('title', '未知标题'); summary = chapter.get('summary', '无简述')
            display_text = f"第 {num} 章 - {title}\n  └ {summary}"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, chapter_index) # 存储列表索引
            self.chapter_list_widget.addItem(item)

    # --- 槽函数 (按钮点击处理) ---
    def on_generate_core_seed(self):
        """处理生成核心种子按钮点击事件。"""
        topic = self.topic_input.text().strip()
        genre = self.genre_input.text().strip()
        num_chapters = self.chapters_spinbox.value()
        word_num = self.words_spinbox.value()
        if not topic or not genre:
            QMessageBox.warning(self, "信息不足", "请输入小说主题和类型。"); return
        self.novel_data.topic = topic; self.novel_data.genre = genre
        self.novel_data.target_chapters = num_chapters; self.novel_data.words_per_chapter = word_num
        format_dict = { "topic": topic, "genre": genre, "number_of_chapters": num_chapters, "word_number": word_num, }
        self.core_seed_display.setReadOnly(True)
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
         if not self.novel_data.core_seed or not self.novel_data.character_dynamics or not self.novel_data.world_building: QMessageBox.warning(self, "缺少前提", "请先生成核心种子、角色、世界观。"); return
         format_dict = { "user_guidance": self.cdwp_user_guidance_input.toPlainText(), "core_seed": self.novel_data.core_seed, "character_dynamics": self.novel_data.character_dynamics, "world_building": self.novel_data.world_building, }
         self.run_generation_task("plot_architecture", format_dict, "plot_architecture")

    def on_create_character_state(self):
        if not self.novel_data.character_dynamics: QMessageBox.warning(self, "缺少前提", "请先生成角色动力学。"); return
        format_dict = { "character_dynamics": self.novel_data.character_dynamics }
        self.run_generation_task("create_character_state", format_dict, "create_character_state")

    def on_generate_chapter_blueprint(self):
        if not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        if self.novel_data.chapter_list:
             if QMessageBox.question(self, "确认覆盖", "将完全覆盖现有蓝图。\n确定吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
        novel_architecture = (f"核心种子: {self.novel_data.core_seed or 'N/A'}...\n角色体系: {self.novel_data.character_dynamics or 'N/A'}...\n世界观: {self.novel_data.world_building or 'N/A'}...\n情节架构: {self.novel_data.plot_architecture or 'N/A'}...")
        format_dict = {"user_guidance": self.blueprint_user_guidance_input.text(), "novel_architecture": novel_architecture, "number_of_chapters": self.novel_data.target_chapters}
        self.run_generation_task("chapter_blueprint", format_dict, "chapter_blueprint")

    def on_generate_chunked_blueprint(self):
        if not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        start_chapter = self.start_chapter_spinbox.value(); end_chapter = self.end_chapter_spinbox.value()
        if start_chapter > end_chapter: QMessageBox.warning(self, "输入错误", "起始章节号不能大于结束章节号。"); return
        if any(start_chapter <= ch.get('number', -1) <= end_chapter for ch in self.novel_data.chapter_list):
             if QMessageBox.question(self, "确认覆盖", f"将覆盖或替换 {start_chapter}-{end_chapter} 章蓝图。\n确定吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
        self.last_chunk_start = start_chapter; existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_chapter); novel_architecture = (f"核心种子: {self.novel_data.core_seed or 'N/A'}...\n情节架构: {self.novel_data.plot_architecture or 'N/A'}...")
        format_dict = { "user_guidance": self.blueprint_user_guidance_input.text(), "novel_architecture": novel_architecture, "previous_chapters_summary": "(此模式不使用已写内容摘要)", "number_of_chapters": self.novel_data.target_chapters, "chapter_list": existing_list_str, "n": start_chapter, "m": end_chapter }
        self.run_generation_task("chunked_chapter_blueprint", format_dict, "chapter_blueprint_chunk")

    def on_regenerate_blueprint(self):
        if not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少前提", "请先生成情节架构。"); return
        if self.regen_pending_data: QMessageBox.warning(self, "请稍候", "正在处理重新生成任务。"); return
        start_regen_chapter = self.regen_start_spinbox.value(); total_target_chapters = self.novel_data.target_chapters
        if start_regen_chapter <= 0: QMessageBox.warning(self, "输入错误", "起始章节号必须>0。"); return
        if start_regen_chapter > total_target_chapters + 1: QMessageBox.warning(self, "输入错误", f"起始章节号不能大于目标章节数 {total_target_chapters} + 1。"); return
        if start_regen_chapter == 1:
             if QMessageBox.question(self, "确认操作", "从第 1 章开始重新生成将覆盖所有蓝图。\n确定吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes: self.on_generate_chapter_blueprint()
             return
        last_chapter_to_summarize = start_regen_chapter - 1; combined_text_to_summarize = self.novel_data.get_combined_text_last_n_chapters(current_chapter_number=start_regen_chapter, n=last_chapter_to_summarize )
        if not combined_text_to_summarize or combined_text_to_summarize == "无前续章节内容.":
            if QMessageBox.question(self, "无已写内容", f"未找到 1-{last_chapter_to_summarize} 章正文。\n是否仍要尝试仅基于旧蓝图生成后续？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
            logging.info(f"重新生成（无内容摘要）：从第 {start_regen_chapter} 章开始。"); self.novel_data.chapter_list = [ch for ch in self.novel_data.chapter_list if ch.get('number', -1) < start_regen_chapter]; self.update_chapter_list_widget(); QApplication.processEvents(); existing_list_str = self.novel_data.get_chapter_list_string_for_prompt(end_chapter_exclusive=start_regen_chapter); novel_architecture = f"核心种子: {self.novel_data.core_seed or 'N/A'}..."
            format_dict = { "user_guidance": self.blueprint_user_guidance_input.text(), "novel_architecture": novel_architecture, "previous_chapters_summary": "无 (未找到先前章节正文)", "chapter_list": existing_list_str, "number_of_chapters": total_target_chapters, "n": start_regen_chapter, "m": total_target_chapters, }; self.run_generation_task("chunked_chapter_blueprint", format_dict, "chapter_blueprint_regenerate"); return
        if QMessageBox.question(self, "确认重新生成", f"将基于 1-{last_chapter_to_summarize} 章正文生成摘要，并重写后续蓝图。\n确定吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
        self.regen_pending_data = { 'start_chapter': start_regen_chapter, 'total_chapters': total_target_chapters, 'guidance': self.blueprint_user_guidance_input.text() }; summary_format_dict = { "combined_chapters_text": combined_text_to_summarize }; self.update_status(f"正在为前 {last_chapter_to_summarize} 章生成剧情摘要..."); self.run_generation_task("summarize_written_chapters", summary_format_dict, "written_chapters_summary_for_regen")

    def on_edit_chapter_blueprint(self, item: QListWidgetItem):
        chapter_index = item.data(Qt.UserRole);
        if chapter_index is None or not isinstance(chapter_index, int) or chapter_index >= len(self.novel_data.chapter_list): QMessageBox.warning(self, "错误", "无法获取章节数据索引。"); return
        try:
            original_data = self.novel_data.chapter_list[chapter_index]; editor = ChapterBlueprintEditor(original_data, self); result = editor.exec_()
            if result == QDialog.Accepted:
                updated_data = editor.get_data()
                if updated_data != original_data: self.novel_data.chapter_list[chapter_index] = updated_data; num = updated_data.get('number', '?'); title = updated_data.get('title', '未知标题'); summary = updated_data.get('summary', '无简述'); display_text = f"第 {num} 章 - {title}\n  └ {summary}"; item.setText(display_text); self.mark_unsaved(); self.update_status(f"第 {num} 章蓝图已更新。"); logging.info(f"Chapter blueprint {num} updated.")
        except IndexError: QMessageBox.critical(self, "内部错误", f"无法找到索引 {chapter_index}。"); logging.error(f"IndexError: {chapter_index}")
        except Exception as e: QMessageBox.critical(self, "编辑错误", f"编辑蓝图时出错: {e}"); logging.exception(f"Error editing blueprint: {chapter_index}")

    def on_load_selected_blueprint_for_writing(self):
        selected_items = self.chapter_list_widget.selectedItems();
        if not selected_items: QMessageBox.information(self, "提示", "请先选择一个章节。"); return
        if len(selected_items) > 1: QMessageBox.information(self, "提示", "请只选择一个章节。"); return
        item = selected_items[0]; chapter_index = item.data(Qt.UserRole)
        if chapter_index is None or not isinstance(chapter_index, int) or chapter_index >= len(self.novel_data.chapter_list): QMessageBox.warning(self, "错误", "无法获取章节数据索引。"); return
        try:
            chapter_data = self.novel_data.chapter_list[chapter_index]; chapter_number = chapter_data.get('number')
            if chapter_number is None: QMessageBox.warning(self, "错误", "选中的章节缺少编号。"); return
            writing_tab_index = -1;
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "章节写作": writing_tab_index = i; break
            if writing_tab_index != -1: self.tab_widget.setCurrentIndex(writing_tab_index)
            else: logging.warning("未找到'章节写作'选项卡。")
            self.chapter_select_spinbox.setValue(chapter_number); self.on_load_chapter_data(); self.update_status(f"已加载第 {chapter_number} 章到写作区。")
        except IndexError: QMessageBox.critical(self, "内部错误", f"无法找到索引 {chapter_index}。"); logging.error(f"IndexError on load: {chapter_index}")
        except Exception as e: QMessageBox.critical(self, "加载错误", f"加载章节时出错: {e}"); logging.exception(f"Error loading chapter for writing: {chapter_index}")

    def on_load_chapter_data(self):
        """加载选定章节的数据到写作选项卡的各个字段。"""
        chapter_number = self.chapter_select_spinbox.value()
        logging.info(f"--- 开始加载第 {chapter_number} 章数据 ---")
        self.novel_data.current_chapter_writing = chapter_number
        logging.debug(f"设置 novel_data.current_chapter_writing = {chapter_number}")
        current_chapter_info = self.novel_data.get_chapter_info(chapter_number)
        if not current_chapter_info:
            QMessageBox.warning(self, "错误", f"未找到第 {chapter_number} 章的蓝图信息。")
            self.current_chapter_info_display.setText(f"错误：未找到第 {chapter_number} 章信息")
            self.chapter_text_edit.clear()
            self.short_summary_display.clear()
            self.knowledge_keywords_display.clear()
            self.filtered_knowledge_display.clear()
            self.prev_excerpt_display.clear()
            self.prev_cumulative_summary_display.clear() # 清空累积摘要显示
            self.writing_user_guidance_input.clear()
            return
        logging.debug(f"找到第 {chapter_number} 章蓝图信息: {current_chapter_info.get('title')}")
        info_text = (f"第 {chapter_number} 章《{current_chapter_info.get('title', 'N/A')}》\n"
                     f"定位: {current_chapter_info.get('role', 'N/A')}, 作用: {current_chapter_info.get('purpose', 'N/A')}, 悬念: {current_chapter_info.get('suspense_level', 'N/A')}\n"
                     f"伏笔: {current_chapter_info.get('foreshadowing', 'N/A')}, 颠覆: {current_chapter_info.get('plot_twist_level', 'N/A')}\n简述: {current_chapter_info.get('summary', 'N/A')}\n"
                     f"角色: {current_chapter_info.get('characters_involved', 'N/A')}, 物品: {current_chapter_info.get('key_items', 'N/A')}, 地点: {current_chapter_info.get('scene_location', 'N/A')}, 时间: {current_chapter_info.get('time_constraint', 'N/A')}")
        self.current_chapter_info_display.setText(info_text)
        draft_text = self.novel_data.chapter_texts.get(chapter_number, "")
        logging.debug(f"加载章节草稿 (前50字符): {draft_text[:50]}...")
        try:
            self.chapter_text_edit.textChanged.disconnect(self.mark_unsaved)
        except TypeError:
            pass
        self.chapter_text_edit.setText(draft_text)
        self.chapter_text_edit.textChanged.connect(self.mark_unsaved)
        self.novel_data.current_chapter_short_summary = None; self.novel_data.knowledge_keywords = None; self.novel_data.filtered_knowledge = None
        self.short_summary_display.clear(); self.knowledge_keywords_display.clear(); self.filtered_knowledge_display.clear(); self.writing_user_guidance_input.clear(); logging.debug("已清除章节相关的临时摘要/知识库字段。")
        # **** 加载 N-1 章的累积摘要 ****
        prev_cumulative_summary_text = self.novel_data.get_previous_cumulative_summary(chapter_number)
        self.prev_cumulative_summary_display.setText(prev_cumulative_summary_text or "无前文章节累积摘要。")
        # ****************************
        prev_excerpt_text = self.novel_data.get_previous_chapter_excerpt(chapter_number)
        char_state_text = self.novel_data.character_state or ""
        self.prev_excerpt_display.setText(prev_excerpt_text)
        self.char_state_display_writing.setText(char_state_text)
        logging.debug("上下文显示已更新")
        self.update_status(f"已加载第 {chapter_number} 章数据。"); logging.info(f"--- 第 {chapter_number} 章数据加载完毕 ---")

    def _get_current_chapter_context(self, require_next_chapter=False) -> Optional[dict]:
        """获取当前写作章节所需的所有上下文信息。"""
        logging.debug(f"_get_current_chapter_context called, require_next_chapter={require_next_chapter}")
        chapter_number = self.novel_data.current_chapter_writing
        if chapter_number is None: QMessageBox.warning(self, "错误", "请先选择并加载一个要操作的章节。"); return None
        logging.debug(f"获取上下文，当前章节号: {chapter_number}")
        current_info = self.novel_data.get_chapter_info(chapter_number)
        if not current_info: QMessageBox.warning(self, "错误", f"无法获取第 {chapter_number} 章的蓝图信息。"); return None
        if not isinstance(current_info, dict):
            logging.error(f"Chapter {chapter_number} blueprint data is not dict: {type(current_info)}")
            QMessageBox.critical(self, "内部错误", f"章节 {chapter_number} 蓝图数据格式错误。"); return None
        logging.debug(f"Current chapter info obtained: {current_info}")

        next_info = self.novel_data.get_chapter_info(chapter_number + 1); next_chapter_data = {}
        if require_next_chapter and not next_info: QMessageBox.warning(self, "缺少信息", f"无法获取下一章节（第 {chapter_number + 1} 章）蓝图..."); logging.warning(f"_get_current_chapter_context: Required next chapter info missing."); return None
        elif next_info:
            if not isinstance(next_info, dict): logging.error(f"Next chapter {chapter_number + 1} data is not dict: {type(next_info)}")
            else: next_chapter_data = next_info; logging.debug(f"Next chapter info obtained: {next_chapter_data}")
        else: logging.debug(f"Next chapter {chapter_number + 1} info not found.")

        combined_text_value = self.novel_data.get_combined_text_last_n_chapters(chapter_number)
        previous_excerpt_value = self.novel_data.get_previous_chapter_excerpt(chapter_number)
        prev_chapter_number = chapter_number - 1
        previous_chapter_full_text = self.novel_data.chapter_texts.get(prev_chapter_number, "无前文章节正文。")
        previous_cumulative_summary = self.novel_data.get_previous_cumulative_summary(chapter_number)

        context = {
            "chapter_number": chapter_number, "novel_number": chapter_number,
            "chapter_info": f"蓝图：第{chapter_number}章 - {current_info.get('title', '')}\n{current_info.get('summary', '')}",
            "word_number": self.novel_data.words_per_chapter, "novel_setting": f"核心:{self.novel_data.core_seed or 'N/A'}...",
            "user_guidance": self.writing_user_guidance_input.toPlainText(), "retrieved_texts": self.knowledge_input_text.toPlainText(),
            "previous_chapter_excerpt": previous_excerpt_value, "character_state": self.novel_data.character_state or "无",
            "combined_text": combined_text_value, "short_summary": self.novel_data.current_chapter_short_summary or "无", "filtered_context": self.novel_data.filtered_knowledge or "无",
            "previous_chapter_full_text": previous_chapter_full_text,
            "previous_cumulative_summary": previous_cumulative_summary or "无",
            "previous_chapter_number": prev_chapter_number if prev_chapter_number >= 1 else 0,
            "next_chapter_number": next_chapter_data.get('number'),
        }
        context.update(current_info) # Safely add all keys from current chapter info
        context.update({f"next_chapter_{k}": v for k, v in next_chapter_data.items()}) # Add all keys for next chapter

        logging.debug(f"上下文准备完毕 for chapter {chapter_number}")
        return context

    def on_summarize_recent_chapters(self):
        logging.info("--- 尝试生成当前章节摘要 ---")
        context = self._get_current_chapter_context(require_next_chapter=True)
        if not context: logging.warning("获取上下文失败"); return
        self.run_generation_task("summarize_recent_chapters", context, "summarize_recent")

    def on_search_knowledge(self):
         context = self._get_current_chapter_context();
         if not context: return;
         if not self.novel_data.current_chapter_short_summary: QMessageBox.information(self, "提示", "建议先生成当前章节摘要。");
         self.run_generation_task("knowledge_search", context, "knowledge_search")

    def on_filter_knowledge(self):
        context = self._get_current_chapter_context();
        if not context: return; knowledge_input = self.knowledge_input_text.toPlainText().strip();
        if not knowledge_input: QMessageBox.warning(self, "缺少内容", "请粘贴需过滤文本。"); return; context["retrieved_texts"] = knowledge_input; self.run_generation_task("knowledge_filter", context, "knowledge_filter")

    def on_generate_chapter_draft(self):
        logging.info("--- 开始生成章节草稿 ---")
        context = self._get_current_chapter_context(require_next_chapter=True)
        if not context: logging.error("无法获取生成草稿上下文。"); return

        chapter_number = self.novel_data.current_chapter_writing
        if chapter_number is None: logging.error("内部错误：章节号丢失。"); QMessageBox.critical(self,"内部错误","无法确定当前章节号。"); return

        logging.debug(f"为第 {chapter_number} 章准备生成草稿。")
        if chapter_number == 1:
            prompt_name = "first_chapter_draft";
            if not self.novel_data.core_seed or not self.novel_data.character_dynamics or not self.novel_data.world_building or not self.novel_data.plot_architecture: QMessageBox.warning(self, "缺少设定", "生成第一章需完整设定。"); return
        else:
            prompt_name = "next_chapter_draft";
            if context.get("previous_chapter_full_text", "").startswith("无前文") or context.get("previous_chapter_full_text", "").startswith("未找到"): QMessageBox.warning(self, "信息缺失", f"未找到上一章({chapter_number-1})完整正文。")
        logging.info(f"使用提示词: {prompt_name}")
        logging.debug(f"传递给 run_generation_task 的 context keys: {list(context.keys())}")
        self.run_generation_task(prompt_name, context, "chapter_draft")

    def on_save_chapter_draft(self):
        """将当前章节写作区域的文本保存到 novel_data 和 TXT 文件。"""
        chapter_number_being_saved = self.novel_data.current_chapter_writing
        if chapter_number_being_saved is None: QMessageBox.warning(self, "错误", "未指定当前编辑章节。"); return
        draft_text = self.chapter_text_edit.toPlainText(); self.novel_data.chapter_texts[chapter_number_being_saved] = draft_text; self.mark_unsaved()
        self.update_status(f"第 {chapter_number_being_saved} 章草稿已保存到内存。")
        txt_save_success = False
        try:
            chapter_info = self.novel_data.get_chapter_info(chapter_number_being_saved); chapter_title = chapter_info.get('title', f'章节_{chapter_number_being_saved}') if chapter_info else f'章节_{chapter_number_being_saved}'
            sanitized_title = re.sub(r'[\\/*?:"<>|]', '', chapter_title); sanitized_title = re.sub(r'\s+', '_', sanitized_title).strip('_');
            if not sanitized_title: sanitized_title = f'章节_{chapter_number_being_saved}'
            filename = f"{str(chapter_number_being_saved).zfill(3)}_{sanitized_title}.txt"; save_directory = "chapters"; base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
            full_save_path = os.path.join(base_path, save_directory); os.makedirs(full_save_path, exist_ok=True); filepath = os.path.join(full_save_path, filename)
            with open(filepath, 'w', encoding='utf-8') as f: f.write(draft_text)
            logging.info(f"章节 {chapter_number_being_saved} 已保存为 TXT: {filepath}"); self.update_status(f"第 {chapter_number_being_saved} 章草稿已保存到内存和 TXT。"); txt_save_success = True
            QMessageBox.information(self, "保存成功", f"第 {chapter_number_being_saved} 章草稿已保存到内存和TXT。")
        except Exception as e:
            logging.exception(f"保存第 {chapter_number_being_saved} 章TXT出错:"); QMessageBox.critical(self, "TXT 保存失败", f"保存第 {chapter_number_being_saved} 章TXT出错:\n{e}"); QMessageBox.information(self, "保存提示", f"第 {chapter_number_being_saved} 章草稿已保存到内存，但TXT保存失败。")

    def on_view_fullscreen(self):
        current_text = self.chapter_text_edit.toPlainText(); chapter_number = self.novel_data.current_chapter_writing; title = f"第 {chapter_number} 章 预览/编辑" if chapter_number else "章节预览/编辑"; make_editable = True
        viewer_dialog = FullScreenViewer(current_text, self, window_title=title, editable=make_editable); result = viewer_dialog.exec_()
        if make_editable and result == QDialog.Accepted:
            edited_text = viewer_dialog.get_text();
            if edited_text != current_text:
                try: self.chapter_text_edit.textChanged.disconnect(self.mark_unsaved)
                except TypeError: pass; self.chapter_text_edit.setText(edited_text); self.chapter_text_edit.textChanged.connect(self.mark_unsaved); self.mark_unsaved(); self.update_status("已从放大窗口更新草稿，请记得保存。")

    def on_update_cumulative_summary(self):
        """更新当前章节的累积摘要。"""
        chapter_number = self.novel_data.current_chapter_writing
        if chapter_number is None: QMessageBox.warning(self, "错误", "请先加载章节。"); return
        chapter_text = self.novel_data.chapter_texts.get(chapter_number)
        if chapter_text is None: QMessageBox.warning(self, "缺少内容", f"第 {chapter_number} 章文本未保存。"); return
        previous_cumulative_summary = self.novel_data.get_previous_cumulative_summary(chapter_number)
        prev_chapter_number = chapter_number - 1
        if prev_chapter_number < 1: prev_chapter_number = 0
        format_dict = {
            "current_chapter_text": chapter_text,
            "previous_cumulative_summary": previous_cumulative_summary,
            "current_chapter_number": chapter_number,
            "previous_chapter_number": prev_chapter_number
        }
        logging.info(f"请求更新第 {chapter_number} 章的累积摘要。")
        self.run_generation_task("summary_update", format_dict, "summary_update")

    def on_update_character_state(self):
        chapter_number = self.novel_data.current_chapter_writing;
        if chapter_number is None: QMessageBox.warning(self, "错误", "请先加载章节。"); return
        chapter_text = self.novel_data.chapter_texts.get(chapter_number);
        if chapter_text is None: QMessageBox.warning(self, "缺少内容", f"第 {chapter_number} 章文本未保存。"); return
        current_character_state = self.novel_data.character_state;
        if not current_character_state: QMessageBox.warning(self, "缺少内容", "角色状态文档不存在。"); return
        format_dict = { "chapter_text": chapter_text, "old_state": current_character_state }; self.run_generation_task("update_character_state", format_dict, "update_character_state")

    def on_import_analyze_characters(self):
        content_to_analyze = self.import_text_input.toPlainText().strip();
        if not content_to_analyze: QMessageBox.warning(self, "缺少内容", "请粘贴文本。"); return
        self.run_generation_task("character_import", format_dict={"content": content_to_analyze}, task_id="character_import_analyze")

    def on_import_replace_state(self):
        analyzed_state = self.import_result_display.toPlainText().strip();
        if not analyzed_state: QMessageBox.warning(self, "没有结果", "分析结果为空。"); return
        if QMessageBox.question(self, "确认替换", "确定替换角色状态文档吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.novel_data.character_state = analyzed_state; self.char_state_display_tab.setText(analyzed_state); self.char_state_display_writing.setText(analyzed_state); self.mark_unsaved()
            if self._save_text_to_project_file("character_state.txt", analyzed_state): self.update_status("角色状态已替换并保存到 TXT。"); QMessageBox.information(self, "替换成功", "角色状态文档已更新并保存到 TXT 文件。")
            else: self.update_status("角色状态已替换（TXT 保存失败）。")
            self.import_replace_button.setEnabled(False)

    def save_project(self):
        if not self.novel_data.topic and not self.novel_data.core_seed and not self.novel_data.chapter_list and not self.novel_data.chapter_texts and not self.novel_data.cumulative_summaries: QMessageBox.information(self, "无需保存", "项目内容为空。"); return
        default_filename = f"{self.novel_data.topic or '未命名项目'}.json"; safe_filename = "".join([c for c in default_filename if c.isalnum() or c in (' ', '.', '_', '-')]).rstrip(); safe_filename = safe_filename.replace(" ", "_")
        filepath, _ = QFileDialog.getSaveFileName(self, "保存小说项目", safe_filename, "JSON 文件 (*.json)");
        if filepath:
            try:
                if not filepath.lower().endswith('.json'): filepath += '.json'
                self.novel_data.save_to_file(filepath); self.update_status(f"项目已保存到 {filepath}"); self.unmark_unsaved()
            except Exception as e: logging.exception("保存项目出错:"); QMessageBox.critical(self, "保存失败", f"保存项目出错:\n{e}"); self.update_status("错误：保存失败。")
    def load_project(self):
        if self.novel_data.unsaved_changes:
             if QMessageBox.question(self, "未保存更改", "加载将丢失未保存更改。\n确定吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.No: return
        filepath, _ = QFileDialog.getOpenFileName(self, "加载小说项目", "", "JSON 文件 (*.json)");
        if filepath:
            try:
                temp_novel_data = NovelData();
                if temp_novel_data.load_from_file(filepath): self.novel_data = temp_novel_data; self.update_ui_from_data(); self.update_status(f"项目已从 {filepath} 加载。"); self.last_chunk_start = None; self.regen_pending_data = None
                else: QMessageBox.critical(self, "加载失败", f"无法从 {filepath} 加载项目。"); self.update_status("错误：加载失败。")
            except Exception as e: logging.exception("加载项目意外错误:"); QMessageBox.critical(self, "加载失败", f"加载项目意外错误:\n{e}"); self.update_status("错误：加载出错。")
    def closeEvent(self, event):
        if self.novel_data.unsaved_changes:
            reply = QMessageBox.question(self, "退出确认", "有未保存更改。\n是否保存？", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel);
            if reply == QMessageBox.Save:
                self.save_project();
                if not self.novel_data.unsaved_changes:
                    event.accept()
                else:
                    event.ignore()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# --- 程序入口 ---
if __name__ == '__main__':
     app = QApplication(sys.argv); main_win = MainWindow(); main_win.show(); sys.exit(app.exec_())