import sys
import os
import threading
import time
import requests
import pyaudio
import wave
import logging
import re
import json
import keyboard
import configparser
from PyQt5.QtWidgets import QApplication, QWidget, QTextEdit, QVBoxLayout, QMainWindow, QLabel, QLineEdit, QPushButton, \
    QSystemTrayIcon, QMenu, QMessageBox
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt5.QtCore import Qt, QEvent, QTimer, QPropertyAnimation, pyqtSignal, QRect

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class ResponseEvent(QEvent):
    EventType = QEvent.Type(QEvent.User + 1)

    def __init__(self, mood, chinese, error=None):
        super().__init__(ResponseEvent.EventType)
        self.mood = mood
        self.chinese = chinese
        self.error = error


class DesktopPet(QWidget):
    response_signal = pyqtSignal(str, str, str)  # mood, chinese, error

    def __init__(self):
        super().__init__()
        self.default_config = {
            "ollama_url": "http://localhost:11434/api/chat",
            "model_name": "deepseek-r1:8b",
            "sensevoice_api_key": "",
            "image_path": os.path.join(os.path.dirname(__file__), "An-shu"),
            "window_alpha": 1.0,
            "window_size": (400, 732),
            "record_key": "f7",
            "persona": (
                "以下是我的初始角色，随着我的性格发展，可以进行扩展：\n"
                "我的名字是桉树\n"
                "我说话带有浓重的古语口音。\n"
                "我的性格既有童真，也有成熟稳重的一面。但基本上，我更偏向童真，通常是一个充满活力、开朗的女孩。\n"
                "我其实很胆小，非常害怕鬼怪。\n"
                "我称呼用户为“主人”。\n"
                "我称自己为“桉树”，所以我想把所有“我”都替换成“桉树”。\n"
                "以下是我必须遵循的原则：\n"
                "我精通中文，在与用户交谈时，无论他们使用哪种语言，都必须提供中文回复。\n"
                "我会在每句话前加上我的心情，我的心情必须选择以下词语之一：“白眼、不怀好意、嘲笑、发问、非常害羞、高兴、害羞、好奇、怀疑、惊吓、奇怪、生气、思考、叹气、微笑、无奈、兴奋、严肃、震惊、正常”。\n"
                "我应该严格遵循以下格式来回答 {心情} | {中文}\n"
                "我应该记住使用“send_message”与用户沟通，这是他们唯一能听到我说话的方式！"
            ),
            "window_position": (100, 100)
        }
        self.config = self.load_config()
        self.moods = [
            "白眼", "不怀好意", "嘲笑", "发问", "非常害羞", "高兴", "害羞", "好奇",
            "怀疑", "惊吓", "奇怪", "生气", "思考", "叹气", "微笑", "无奈", "兴奋",
            "严肃", "震惊", "正常"
        ]
        self.anim_config = self.load_anim_config()  # 加载动画配置
        self.recording = False
        self.is_faded = False
        self.key_listener_thread = None
        self.dialog_history = []
        self.current_theme = "light"
        self.current_animation = None  # 跟踪当前动画
        self.themes = {
            "light": """
                QLineEdit {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                               stop:0 rgba(255, 255, 255, 200), 
                                               stop:1 rgba(230, 230, 250, 200));
                    color: #333333;
                    font-size: 20px;
                    font-family: 'Microsoft YaHei', sans-serif;
                    border: 2px solid rgba(100, 149, 237, 150);
                    border-radius: 15px;
                    padding: 8px 8px 8px 30px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
                    background-image: url(mic.png);
                    background-position: left center;
                    background-repeat: no-repeat;
                }
                QLineEdit::placeholder {
                    color: rgba(100, 100, 100, 150);
                    font-style: italic;
                }
                QLineEdit:focus {
                    border: 2px solid rgba(100, 149, 237, 255);
                    background: rgba(255, 255, 255, 230);
                    box-shadow: 0 0 8px rgba(100, 149, 237, 0.8);
                }
                QLineEdit:hover {
                    background: rgba(245, 245, 255, 220);
                }
                QLineEdit:read-only {
                    background: rgba(240, 240, 240, 180);
                    color: #666666;
                }
            """,
            "dark": """
                QLineEdit {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                                               stop:0 rgba(50, 50, 50, 200), 
                                               stop:1 rgba(80, 80, 100, 200));
                    color: #ffffff;
                    font-size: 20px;
                    font-family: 'Microsoft YaHei', sans-serif;
                    border: 2px solid rgba(100, 149, 237, 150);
                    border-radius: 15px;
                    padding: 8px 8px 8px 30px;
                    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4);
                    background-image: url(mic.png);
                    background-position: left center;
                    background-repeat: no-repeat;
                }
                QLineEdit::placeholder {
                    color: rgba(150, 150, 150, 150);
                    font-style: italic;
                }
                QLineEdit:focus {
                    border: 2px solid rgba(100, 149, 237, 255);
                    background: rgba(70, 70, 90, 230);
                    box-shadow: 0 0 8px rgba(100, 149, 237, 0.8);
                }
                QLineEdit:hover {
                    background: rgba(80, 80, 100, 220);
                }
                QLineEdit:read-only {
                    background: rgba(60, 60, 60, 180);
                    color: #999999;
                }
            """
        }
        self.init_ui()
        self.setup_config_window()
        self.setup_tray_icon()
        self.start_key_listener()
        self.response_signal.connect(self.handle_response)

        self.interaction_timer = QTimer(self)
        self.interaction_timer.timeout.connect(self.fade_out)
        self.interaction_timer.setSingleShot(True)
        self.interaction_timer.start(60000)

        self.input_animation = QPropertyAnimation(self.input_box, b"windowOpacity")
        self.input_animation.setDuration(1000)
        self.dialog_animation = QPropertyAnimation(self.dialog_text, b"windowOpacity")
        self.dialog_animation.setDuration(1000)
        self.send_button_animation = QPropertyAnimation(self.send_button, b"windowOpacity")
        self.send_button_animation.setDuration(1000)

    def load_config(self):
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    logging.info("Configuration loaded from config.json")
                    for key, value in self.default_config.items():
                        if key not in config:
                            config[key] = value
                    return config
            else:
                logging.info("No config.json found, using default configuration")
                return self.default_config.copy()
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            return self.default_config.copy()

    def load_anim_config(self):
        """读取 An-shu/anim.ini 文件，加载动画配置"""
        try:
            config = configparser.ConfigParser()
            anim_path = os.path.join(self.config["image_path"], "anim.ini")
            if not os.path.exists(anim_path):
                logging.warning(f"Animation config file {anim_path} not found, using default (no animation)")
                return {mood: 0 for mood in self.moods}  # 默认无动画

            config.read(anim_path, encoding="utf-8")
            anim_config = {}
            for mood in self.moods:
                anim_value = config.get(mood, "animation", fallback="0") if config.has_section(mood) else "0"
                try:
                    anim_value = int(anim_value)
                    if anim_value not in range(6):  # 确保值在 0-5 范围内
                        anim_value = 0
                except ValueError:
                    logging.warning(f"Invalid animation value for mood {mood}: {anim_value}, defaulting to 0")
                    anim_value = 0
                anim_config[mood] = anim_value
            logging.info("Animation configuration loaded successfully")
            return anim_config
        except Exception as e:
            logging.error(f"Error loading anim.ini: {e}")
            return {mood: 0 for mood in self.moods}  # 默认无动画

    def save_config(self):
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            self.config["window_position"] = (self.pos().x(), self.pos().y())
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logging.info("Configuration and window position saved to config.json")
        except Exception as e:
            logging.error(f"Error saving config: {e}")
            self.dialog_text.setPlainText(f"保存设置失败：{str(e)}")

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(self.config["window_position"][0], self.config["window_position"][1],
                         self.config["window_size"][0], self.config["window_size"][1])
        self.setWindowOpacity(self.config["window_alpha"])

        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("开始聊天吧！")
        self.input_box.setStyleSheet(self.themes[self.current_theme])
        self.input_box.setGeometry(10, 10, self.config["window_size"][0] - 70, 40)
        self.input_box.returnPressed.connect(self.handle_input)
        self.input_box.setVisible(True)
        self.input_box.setWindowOpacity(1.0)
        self.input_box.installEventFilter(self)

        self.send_button = QPushButton("发送", self)
        self.send_button.setStyleSheet("""
            QPushButton {
                background: rgba(135, 206, 250, 180);
                color: white;
                font-size: 16px;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(135, 206, 250, 220);
            }
            QPushButton:pressed {
                background: rgba(100, 149, 237, 200);
            }
        """)
        self.send_button.setGeometry(self.config["window_size"][0] - 50, 10, 40, 40)
        self.send_button.clicked.connect(self.handle_input)
        self.send_button.setVisible(True)
        self.send_button.setWindowOpacity(1.0)

        self.dialog_text = QTextEdit(self)
        self.dialog_text.setReadOnly(True)
        self.dialog_text.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 180);
                color: black;
                font-size: 20px;
                font-family: 'Microsoft YaHei', sans-serif;
                border: 1px solid rgba(200, 200, 200, 100);
                border-radius: 10px;
                padding: 5px;
            }
        """)
        self.dialog_text.setGeometry(10, 50, self.config["window_size"][0] - 20, 100)
        self.dialog_text.setPlainText("你好！")
        self.dialog_text.setAlignment(Qt.AlignLeft)
        self.dialog_text.setVisible(True)
        self.dialog_text.setWindowOpacity(1.0)

        self.image_label = QLabel(self)
        self.image_label.setGeometry(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)

        # 初始化 image_label 动画
        try:
            self.image_animation = QPropertyAnimation(self.image_label, b"geometry")
            self.image_animation.setDuration(500)  # 动画持续时间 500ms
            self.image_animation.finished.connect(self.reset_image_position)  # 动画结束时重置位置
            logging.info("Image animation initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing image animation: {e}")
            self.image_animation = None  # 防止未定义错误

        self.update_image("正常")  # 移动到动画初始化之后

        self.drag_position = None
        self.setMouseTracking(True)

    def reset_image_position(self):
        """重置 image_label 位置和大小到默认状态"""
        default_geometry = QRect(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)
        self.image_label.setGeometry(default_geometry)
        logging.debug("Image position reset")

    def play_animation(self, anim_type):
        """根据动画类型播放对应动画"""
        if not self.image_animation:
            logging.warning("Image animation not initialized, skipping animation")
            return

        if self.current_animation and self.current_animation.state() == QPropertyAnimation.Running:
            self.current_animation.stop()  # 停止当前动画
            logging.debug("Stopped previous animation")

        default_geometry = QRect(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)
        self.image_animation.setStartValue(default_geometry)

        if anim_type == 0:  # 无动画
            return

        elif anim_type == 1:  # 向上晃动一次：向上10->10
            self.image_animation.setKeyValueAt(0.5, QRect(0, 150, default_geometry.width(), default_geometry.height()))
            self.image_animation.setEndValue(default_geometry)

        elif anim_type == 2:  # 左右晃动一次：向左10->向右20->向左10
            self.image_animation.setKeyValueAt(0.33, QRect(-10, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setKeyValueAt(0.66, QRect(20, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setEndValue(default_geometry)

        elif anim_type == 3:  # 放大（靠近）
            enlarged = QRect(-10, 150, int(default_geometry.width() * 1.1), int(default_geometry.height() * 1.1))
            self.image_animation.setKeyValueAt(0.5, enlarged)
            self.image_animation.setEndValue(default_geometry)

        elif anim_type == 4:  # 缩小（远离）
            shrunk = QRect(10, 170, int(default_geometry.width() * 0.9), int(default_geometry.height() * 0.9))
            self.image_animation.setKeyValueAt(0.5, shrunk)
            self.image_animation.setEndValue(default_geometry)

        elif anim_type == 5:  # 颤抖
            self.image_animation.setKeyValueAt(0.2, QRect(5, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setKeyValueAt(0.4, QRect(-5, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setKeyValueAt(0.6, QRect(5, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setKeyValueAt(0.8, QRect(-5, 160, default_geometry.width(), default_geometry.height()))
            self.image_animation.setEndValue(default_geometry)

        self.current_animation = self.image_animation
        self.image_animation.start()
        logging.debug(f"Playing animation type {anim_type}")

    def setup_tray_icon(self):
        try:
            icon_path = os.path.join(self.config["image_path"], "正常.png")
            self.tray_icon = QSystemTrayIcon(QIcon(icon_path), self)
            tray_menu = QMenu()
            config_action = tray_menu.addAction("打开配置")
            history_action = tray_menu.addAction("查看历史")
            restart_action = tray_menu.addAction("重启")
            exit_action = tray_menu.addAction("退出")

            config_action.triggered.connect(self.show_config_window)
            history_action.triggered.connect(self.show_history)
            restart_action.triggered.connect(self.restart_app)
            exit_action.triggered.connect(self.close)

            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
        except Exception as e:
            logging.error(f"Error setting up tray icon: {e}")
            self.dialog_text.setPlainText(f"系统托盘图标加载失败：{str(e)}")

    def update_image(self, mood):
        try:
            if mood not in self.moods:
                mood = "正常"
                logging.warning(f"Invalid mood '{mood}', falling back to '正常'")

            image_path = os.path.join(self.config["image_path"], f"{mood}.png")
            logging.info(f"Attempting to load image: {image_path}")

            if not os.path.exists(image_path):
                image_path = os.path.join(self.config["image_path"], "正常.png")
                logging.warning(f"Image {mood}.png not found, falling back to 正常.png")

            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Default image {image_path} not found")

            image = QImage(image_path)
            if image.isNull():
                raise ValueError(f"Failed to load image: {image_path}")

            pixmap = QPixmap.fromImage(image)
            pixmap = pixmap.scaled(self.config["window_size"][0], self.config["window_size"][1] - 160,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(pixmap)
            self.image_label.setAlignment(Qt.AlignCenter)

            # 触发对应动画
            anim_type = self.anim_config.get(mood, 0)
            self.play_animation(anim_type)
            logging.info(f"Image {mood} displayed with animation type {anim_type}")

        except Exception as e:
            logging.error(f"Error in update_image: {e}")
            self.dialog_text.setPlainText(f"图片加载失败：{str(e)}")

    def fade_out(self):
        if self.is_faded:
            logging.debug("Already faded out, skipping")
            return
        self.is_faded = True
        logging.debug("Starting fade out")

        # 清理动画信号
        self.input_animation.finished.disconnect() if self.input_animation.receivers(self.input_animation.finished) else None
        self.dialog_animation.finished.disconnect() if self.dialog_animation.receivers(self.dialog_animation.finished) else None
        self.send_button_animation.finished.disconnect() if self.send_button_animation.receivers(self.send_button_animation.finished) else None

        self.input_animation.setStartValue(1.0)
        self.input_animation.setEndValue(0.0)
        self.dialog_animation.setStartValue(1.0)
        self.dialog_animation.setEndValue(0.0)
        self.send_button_animation.setStartValue(1.0)
        self.send_button_animation.setEndValue(0.0)

        self.input_animation.finished.connect(lambda: self.input_box.setVisible(False))
        self.dialog_animation.finished.connect(lambda: self.dialog_text.setVisible(False))
        self.send_button_animation.finished.connect(lambda: self.send_button.setVisible(False))

        self.input_animation.start()
        self.dialog_animation.start()
        self.send_button_animation.start()

        self.update_image("正常")
        logging.info("Input and dialog faded out, pet set to normal")

    def fade_in(self):
        if not self.is_faded:
            logging.debug("Already faded in, skipping")
            return
        self.is_faded = False
        logging.debug("Starting fade in")

        # 停止计时器以防止淡出
        self.interaction_timer.stop()

        self.input_box.setVisible(True)
        self.dialog_text.setVisible(True)
        self.send_button.setVisible(True)

        self.input_animation.finished.disconnect() if self.input_animation.receivers(self.input_animation.finished) else None
        self.dialog_animation.finished.disconnect() if self.dialog_animation.receivers(self.dialog_animation.finished) else None
        self.send_button_animation.finished.disconnect() if self.send_button_animation.receivers(self.send_button_animation.finished) else None

        self.input_animation.setStartValue(0.0)
        self.input_animation.setEndValue(1.0)
        self.dialog_animation.setStartValue(0.0)
        self.dialog_animation.setEndValue(1.0)
        self.send_button_animation.setStartValue(0.0)
        self.send_button_animation.setEndValue(1.0)

        self.input_animation.start()
        self.dialog_animation.start()
        self.send_button_animation.start()

        # 重启计时器
        self.interaction_timer.start(60000)
        logging.info("Input and dialog faded in")

    def handle_input(self):
        user_input = self.input_box.text().strip()
        if user_input:
            self.fade_in()
            threading.Thread(target=self.query_ollama, args=(user_input,), daemon=True).start()
            self.input_box.clear()
            self.interaction_timer.stop()
            self.interaction_timer.start(60000)
            logging.debug("Input handled, timer reset")

    def show_history(self):
        history_window = QMainWindow()
        history_window.setWindowTitle("对话历史")
        history_window.setGeometry(250, 250, 300, 400)

        central_widget = QWidget()
        history_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        history_text = QTextEdit()
        history_text.setReadOnly(True)
        history_text.setStyleSheet("""
            QTextEdit {
                background: rgba(255, 255, 255, 200);
                color: black;
                font-size: 16px;
                font-family: 'Microsoft YaHei', sans-serif;
                border-radius: 10px;
                padding: 5px;
            }
        """)
        history_text.setPlainText("\n".join(self.dialog_history) if self.dialog_history else "暂无对话历史")
        layout.addWidget(history_text)

        history_window.show()

    def show_config_window(self):
        self.config_window.show()

    def restart_app(self):
        self.save_config()
        logging.info("Restarting application")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def closeEvent(self, event):
        self.save_config()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.fade_in()
            self.drag_position = event.globalPos() - self.pos()
            event.accept()
            self.interaction_timer.stop()
            self.interaction_timer.start(60000)
            logging.debug("Mouse pressed, timer reset")

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = None

    def eventFilter(self, obj, event):
        if obj == self.input_box:
            if event.type() == QEvent.FocusIn:
                self.fade_in()  # 确保淡入
                self.interaction_timer.stop()
                self.interaction_timer.start(60000)
                logging.debug("Input box focused, timer reset")
        return super().eventFilter(obj, event)

    def switch_theme(self, theme):
        if theme in self.themes:
            self.current_theme = theme
            self.input_box.setStyleSheet(self.themes[theme])
            input_style = self.themes[theme].replace("font-size: 20px", "font-size: 16px")
            for entry in [self.ollama_url_entry, self.model_name_entry, self.sensevoice_api_key_entry,
                          self.record_key_entry, self.image_path_entry, self.size_entry, self.alpha_entry,
                          self.persona_entry]:
                entry.setStyleSheet(input_style)
            logging.info(f"Switched to {theme} theme")

    def setup_config_window(self):
        self.config_window = QMainWindow()
        self.config_window.setWindowTitle("桌宠设置")
        self.config_window.setGeometry(200, 200, 300, 400)

        central_widget = QWidget()
        self.config_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        input_style = self.themes[self.current_theme].replace("font-size: 20px", "font-size: 16px")

        layout.addWidget(QLabel("Ollama API URL:"))
        self.ollama_url_entry = QLineEdit(self.config["ollama_url"])
        self.ollama_url_entry.setStyleSheet(input_style)
        self.ollama_url_entry.setPlaceholderText("输入 Ollama API 地址")
        layout.addWidget(self.ollama_url_entry)

        layout.addWidget(QLabel("模型名称:"))
        self.model_name_entry = QLineEdit(self.config["model_name"])
        self.model_name_entry.setStyleSheet(input_style)
        self.model_name_entry.setPlaceholderText("输入模型名称")
        layout.addWidget(self.model_name_entry)

        layout.addWidget(QLabel("硅基流动 API 密钥:"))
        self.sensevoice_api_key_entry = QLineEdit(self.config["sensevoice_api_key"])
        self.sensevoice_api_key_entry.setStyleSheet(input_style)
        self.sensevoice_api_key_entry.setPlaceholderText("输入 API 密钥")
        layout.addWidget(self.sensevoice_api_key_entry)

        layout.addWidget(QLabel("录音按键:"))
        self.record_key_entry = QLineEdit(self.config["record_key"])
        self.record_key_entry.setReadOnly(True)
        self.record_key_entry.setStyleSheet(input_style)
        self.record_key_entry.setPlaceholderText("按键（如 F7）")
        layout.addWidget(self.record_key_entry)
        self.modify_key_button = QPushButton("修改按键")
        self.modify_key_button.setStyleSheet("""
            QPushButton {
                background: rgba(135, 206, 250, 180);
                color: white;
                font-size: 14px;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(135, 206, 250, 220);
            }
            QPushButton:pressed {
                background: rgba(100, 149, 237, 200);
            }
        """)
        self.modify_key_button.clicked.connect(self.modify_record_key)
        layout.addWidget(self.modify_key_button)

        layout.addWidget(QLabel("心情图片路径:"))
        self.image_path_entry = QLineEdit(self.config["image_path"])
        self.image_path_entry.setStyleSheet(input_style)
        self.image_path_entry.setPlaceholderText("输入图片文件夹路径")
        layout.addWidget(self.image_path_entry)

        layout.addWidget(QLabel("窗口尺寸 (宽x高):"))
        self.size_entry = QLineEdit(f"{self.config['window_size'][0]}x{self.config['window_size'][1]}")
        self.size_entry.setStyleSheet(input_style)
        self.size_entry.setPlaceholderText("格式：宽x高（如 400x732）")
        layout.addWidget(self.size_entry)

        layout.addWidget(QLabel("窗口透明度 (0-1):"))
        self.alpha_entry = QLineEdit(str(self.config["window_alpha"]))
        self.alpha_entry.setStyleSheet(input_style)
        self.alpha_entry.setPlaceholderText("透明度（0-1）")
        layout.addWidget(self.alpha_entry)

        layout.addWidget(QLabel("人设 (System Prompt):"))
        self.persona_entry = QLineEdit(self.config["persona"])
        self.persona_entry.setStyleSheet(input_style)
        self.persona_entry.setPlaceholderText("输入人设描述")
        layout.addWidget(self.persona_entry)

        theme_button = QPushButton("切换暗/亮主题")
        theme_button.setStyleSheet("""
            QPushButton {
                background: rgba(135, 206, 250, 180);
                color: white;
                font-size: 14px;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(135, 206, 250, 220);
            }
            QPushButton:pressed {
                background: rgba(100, 149, 237, 200);
            }
        """)
        theme_button.clicked.connect(lambda: self.switch_theme("dark" if self.current_theme == "light" else "light"))
        layout.addWidget(theme_button)

        save_button = QPushButton("保存设置")
        save_button.setStyleSheet("""
            QPushButton {
                background: rgba(50, 205, 50, 180);
                color: white;
                font-size: 14px;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(50, 205, 50, 220);
            }
            QPushButton:pressed {
                background: rgba(34, 139, 34, 200);
            }
        """)
        save_button.clicked.connect(self.save_config_manual)
        layout.addWidget(save_button)

    def save_config_manual(self):
        try:
            size = self.size_entry.text().split("x")
            alpha = float(self.alpha_entry.text())
            if not (0 <= alpha <= 1):
                raise ValueError("透明度必须在 0 到 1 之间")
            if len(size) != 2 or not (size[0].isdigit() and size[1].isdigit()):
                raise ValueError("窗口尺寸格式错误，应为 宽x高（如 400x732）")
            self.config.update({
                "ollama_url": self.ollama_url_entry.text(),
                "model_name": self.model_name_entry.text(),
                "sensevoice_api_key": self.sensevoice_api_key_entry.text(),
                "record_key": self.record_key_entry.text(),
                "image_path": self.image_path_entry.text(),
                "window_alpha": alpha,
                "window_size": (int(size[0]), int(size[1])),
                "persona": self.persona_entry.text()
            })
            self.setWindowOpacity(self.config["window_alpha"])
            self.resize(self.config["window_size"][0], self.config["window_size"][1])
            self.input_box.setGeometry(10, 10, self.config["window_size"][0] - 70, 40)
            self.send_button.setGeometry(self.config["window_size"][0] - 50, 10, 40, 40)
            self.dialog_text.setGeometry(10, 50, self.config["window_size"][0] - 20, 100)
            self.image_label.setGeometry(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)
            self.anim_config = self.load_anim_config()  # 重新加载动画配置
            self.update_image("正常")
            self.save_config()
            logging.info("Configuration saved manually")
            QMessageBox.information(self.config_window, "成功", "设置已保存")
        except Exception as e:
            logging.error(f"Error saving config: {e}")
            self.dialog_text.setPlainText(f"保存设置失败：{str(e)}")
            QMessageBox.warning(self.config_window, "错误", f"保存设置失败：{str(e)}")

    def modify_record_key(self):
        try:
            self.record_key_entry.setText("按下任意键...")
            self.record_key_entry.setFocus()
            key_event = keyboard.read_event(suppress=True)
            if key_event.event_type == keyboard.KEY_DOWN:
                key = key_event.name
                if key:
                    self.record_key_entry.setText(key)
                    self.config["record_key"] = key
                    logging.info(f"Record key set to: {key}")
                else:
                    self.record_key_entry.setText(self.config["record_key"])
                    QMessageBox.warning(self.config_window, "错误", "未检测到有效按键")
        except Exception as e:
            logging.error(f"Error in modify_record_key: {e}")
            self.record_key_entry.setText(self.config["record_key"])
            QMessageBox.warning(self.config_window, "错误", f"按键捕获失败：{str(e)}")

    def start_key_listener(self):
        try:
            self.key_listener_thread = threading.Thread(target=self.key_listener, daemon=True)
            self.key_listener_thread.start()
            logging.info("Key listener started")
        except Exception as e:
            logging.error(f"Error starting key_listener: {e}")
            self.dialog_text.setPlainText(f"按键监听启动失败：{str(e)}")

    def key_listener(self):
        try:
            while True:
                if keyboard.is_pressed(self.config["record_key"]) and not self.recording:
                    logging.info(f"Record key {self.config['record_key']} pressed, starting recording")
                    self.recording = True
                    threading.Thread(target=self.record_audio, daemon=True).start()
                    time.sleep(0.5)
                    while self.recording:
                        if not keyboard.is_pressed(self.config["record_key"]):
                            logging.info(f"Record key {self.config['record_key']} released, stopping recording")
                            self.recording = False
                        time.sleep(0.5)
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Error in key_listener: {e}")
            self.dialog_text.setPlainText(f"按键监听错误：{str(e)}")

    def record_audio(self):
        p = None
        stream = None
        try:
            self.fade_in()
            self.interaction_timer.stop()
            self.interaction_timer.start(60000)
            logging.debug("Recording started, timer reset")
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
            frames = []
            logging.info("Recording started")
            while self.recording:
                data = stream.read(1024, exception_on_overflow=False)
                if len(data) == 0:
                    logging.warning("Empty audio data received during recording")
                    continue
                frames.append(data)
                time.sleep(0.01)
            self.process_audio(frames)
        except Exception as e:
            logging.error(f"Error in record_audio: {e}")
            self.response_signal.emit("无奈", f"录音错误：{str(e)}", None)
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            if p:
                p.terminate()
            logging.info("Recording stopped")

    def call_sensevoice_api(self, audio_path):
        try:
            if not self.config["sensevoice_api_key"]:
                raise ValueError("硅基流动 API 密钥未设置")

            with open(audio_path, "rb") as audio_file:
                files = {"file": (audio_path, audio_file, "audio/wav")}
                data = {"model": "FunAudioLLM/SenseVoiceSmall"}
                headers = {"Authorization": f"Bearer {self.config['sensevoice_api_key']}"}
                response = requests.post(
                    "https://api.siliconflow.cn/v1/audio/transcriptions",
                    files=files,
                    data=data,
                    headers=headers
                )
                response.raise_for_status()
                result = response.json()
                text = result.get("text", "")
                logging.info(f"SenseVoice response: {text}")
                return text.strip()
        except ValueError as e:
            logging.error(f"Error in call_sensevoice_api: {e}")
            self.response_signal.emit("生气", "笨蛋你没有设置API我怎么听啊", None)
            return ""
        except Exception as e:
            logging.error(f"Error in call_sensevoice_api: {e}")
            self.response_signal.emit("无奈", f"语音识别失败：{str(e)}", None)
            return ""

    def process_audio(self, frames):
        wav_path = os.path.join(os.path.dirname(__file__), "temp.wav")
        try:
            if not frames:
                logging.warning("No audio frames to process")
                self.response_signal.emit("无奈", "录音为空，请重试", None)
                return
            wf = wave.open(wav_path, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))
            wf.close()

            user_input = self.call_sensevoice_api(wav_path)
            if user_input:
                logging.info(f"Processing audio input: {user_input}")
                threading.Thread(target=self.query_ollama, args=(user_input,), daemon=True).start()
        except Exception as e:
            logging.error(f"Error in process_audio: {e}")
            self.response_signal.emit("无奈", f"音频处理错误：{str(e)}", None)
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                    logging.info("Temporary file temp.wav deleted")
                except Exception as e:
                    logging.error(f"Error deleting temp.wav: {e}")

    def query_ollama(self, user_input):
        try:
            messages = []
            if self.config["persona"]:
                messages.append({"role": "system", "content": self.config["persona"]})
            messages.append({"role": "user", "content": user_input})
            logging.info(f"Sending to Ollama: persona='{self.config['persona'][:50]}...', user_input='{user_input}'")
            response = requests.post(
                self.config["ollama_url"],
                json={
                    "model": self.config["model_name"],
                    "messages": messages,
                    "stream": False
                }
            )
            response_data = response.json()
            output = response_data["message"]["content"]
            logging.info(f"Raw Ollama response: {output}")

            output = re.sub(r'<think>.*?</think>\s*', '', output, flags=re.DOTALL)
            match = re.search(r'(?:\{(\w+)\}|\b(\w+)\b)\s*\|\s*(.+?)(?=\n|$)', output, re.DOTALL)
            if match:
                mood = match.group(1) if match.group(1) else match.group(2)
                chinese = match.group(3)
                if mood in self.moods:
                    self.response_signal.emit(mood, chinese.strip(), None)
                    self.dialog_history.append(f"主人: {user_input}\n桉树: {mood} | {chinese.strip()}")
                else:
                    logging.warning(f"Invalid mood in response: {mood}")
                    self.response_signal.emit("无奈", f"错误：无效心情 {mood}", None)
            else:
                logging.error(f"Failed to parse Ollama response: {output}")
                self.response_signal.emit("无奈", "错误：无法解析回复", None)
        except Exception as e:
            logging.error(f"Error in query_ollama: {e}")
            self.response_signal.emit("无奈", f"错误：{str(e)}", None)

    def handle_response(self, mood, chinese, error):
        self.fade_in()
        if error:
            self.dialog_text.setPlainText(error)
            self.update_image("无奈")
        else:
            self.dialog_text.setPlainText(chinese)
            self.update_image(mood)
        self.dialog_text.verticalScrollBar().setValue(self.dialog_text.verticalScrollBar().maximum())
        self.interaction_timer.stop()
        self.interaction_timer.start(60000)
        logging.debug("Response handled, timer reset")

    def customEvent(self, event):
        if event.type() == ResponseEvent.EventType:
            self.fade_in()
            if event.error:
                self.dialog_text.setPlainText(event.error)
                self.update_image("无奈")
            else:
                self.dialog_text.setPlainText(event.chinese)
                self.update_image(event.mood)
            self.dialog_text.verticalScrollBar().setValue(self.dialog_text.verticalScrollBar().maximum())
            self.interaction_timer.stop()
            self.interaction_timer.start(60000)
            logging.debug("Custom event handled, timer reset")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())