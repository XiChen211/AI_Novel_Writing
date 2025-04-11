# main.py
# -*- coding: utf-8 -*-
import sys
from PyQt5.QtWidgets import QApplication
from main_window import MainWindow
import logging

if __name__ == '__main__':
    # 配置日志记录
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler("novel_assistant.log", encoding='utf-8'), # 输出到文件
                            logging.StreamHandler() # 同时输出到控制台
                        ])
    logging.info("应用程序启动...")

    app = QApplication(sys.argv)

    # 你可以在这里设置全局样式表
    # app.setStyleSheet("""
    #     QPushButton { padding: 5px; }
    #     QLineEdit { padding: 3px; }
    #     QTextEdit { border: 1px solid #ccc; }
    # """)

    main_win = MainWindow()
    main_win.show()

    logging.info("主窗口已显示。")
    sys.exit(app.exec_())