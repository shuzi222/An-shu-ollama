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
from PyQt5.QtWidgets import QApplication, QWidget, QTextEdit, QVBoxLayout, QMainWindow, QLabel, QLineEdit, QPushButton, \
    QSystemTrayIcon, QMenu, QMessageBox
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt5.QtCore import Qt, QEvent, QObject
from PyQt5.QtCore import pyqtSignal

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
            "sensevoice_api_key": "",  # 硅基流动 API 密钥
            "image_path": "An-shu/",  # 预处理后的路径
            "window_alpha": 1.0,
            "window_size": (400, 732),
            "record_key": "ctrl",  # 默认录音按键
            "persona": (
                "以下是我的初始角色，随着我的性格发展，可以进行扩展：\n"
                "我的名字是桉树\n"
                "我说话带有浓重的古语口accent。\n"
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
            "window_position": (100, 100)  # 默认窗口位置
        }
        self.config = self.load_config()  # 加载配置
        self.moods = [
            "白眼", "不怀好意", "嘲笑", "发问", "非常害羞", "高兴", "害羞", "好奇",
            "怀疑", "惊吓", "奇怪", "生气", "思考", "叹气", "微笑", "无奈", "兴奋",
            "严肃", "震惊", "正常"
        ]
        self.recording = False
        self.key_listener_thread = None
        self.dialog_history = []
        self.init_ui()
        self.setup_config_window()
        self.setup_tray_icon()
        self.start_key_listener()
        self.response_signal.connect(self.handle_response)

    def load_config(self):
        """加载配置文件"""
        config_path = "../config.json"
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    logging.info("Configuration loaded from config.json")
                    # 确保所有默认配置字段存在
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

    def save_config(self):
        """保存配置和窗口位置"""
        try:
            config_path = "../config.json"
            self.config["window_position"] = (self.pos().x(), self.pos().y())  # 保存当前窗口位置
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
        self.input_box.setPlaceholderText("输入对话，按 Enter 发送...")
        self.input_box.setStyleSheet(
            "background: rgba(255, 255, 255, 180); "
            "color: black; "
            "font-size: 20px; "
            "font-family: 'Microsoft YaHei', sans-serif; "
            "border: 1px solid rgba(200, 200, 200, 100); "
            "border-radius: 10px; "
            "padding: 5px;"
        )
        self.input_box.setGeometry(10, 10, self.config["window_size"][0] - 70, 30)
        self.input_box.returnPressed.connect(self.handle_input)

        self.send_button = QPushButton("发送", self)
        self.send_button.setStyleSheet(
            "background: rgba(200, 200, 200, 180); "
            "font-size: 16px; "
            "border-radius: 5px;"
        )
        self.send_button.setGeometry(self.config["window_size"][0] - 50, 10, 40, 30)
        self.send_button.clicked.connect(self.handle_input)

        self.dialog_text = QTextEdit(self)
        self.dialog_text.setReadOnly(True)
        self.dialog_text.setStyleSheet(
            "background: rgba(255, 255, 255, 180); "
            "color: black; "
            "font-size: 20px; "
            "font-family: 'Microsoft YaHei', sans-serif; "
            "border: 1px solid rgba(200, 200, 200, 100); "
            "border-radius: 10px; "
            "padding: 5px;"
        )
        self.dialog_text.setGeometry(10, 50, self.config["window_size"][0] - 20, 100)
        self.dialog_text.setPlainText("你好！")
        self.dialog_text.setAlignment(Qt.AlignLeft)

        self.image_label = QLabel(self)
        self.image_label.setGeometry(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)

        self.update_image("正常")

        self.drag_position = None
        self.setMouseTracking(True)

    def setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(QIcon(os.path.join(self.config["image_path"], "正常.png")), self)
        tray_menu = QMenu()
        config_action = tray_menu.addAction("打开配置")
        history_action = tray_menu.addAction("查看历史")
        restart_action = tray_menu.addAction("重启")
        exit_action = tray_menu.addAction("退出")

        config_action.triggered.connect(self.show_config_window)
        history_action.triggered.connect(self.show_history)
        restart_action.triggered.connect(self.restart_app)
        exit_action.triggered.connect(self.close)  # 改为调用 close，确保触发 closeEvent

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

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

            logging.info(
                f"Image loaded, format: {image.format()}, size: {image.size().width()}x{image.size().height()}")

            pixmap = QPixmap.fromImage(image)
            pixmap = pixmap.scaled(self.config["window_size"][0], self.config["window_size"][1] - 160,
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(pixmap)
            self.image_label.setAlignment(Qt.AlignCenter)
            logging.info(f"Image {mood} displayed successfully")

        except Exception as e:
            logging.error(f"Error in update_image: {e}")
            self.dialog_text.setPlainText(f"图片加载失败：{str(e)}")

    def handle_input(self):
        user_input = self.input_box.text().strip()
        if user_input:
            threading.Thread(target=self.query_ollama, args=(user_input,), daemon=True).start()
            self.input_box.clear()

    def show_history(self):
        history_window = QMainWindow()
        history_window.setWindowTitle("对话历史")
        history_window.setGeometry(250, 250, 300, 400)

        central_widget = QWidget()
        history_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        history_text = QTextEdit()
        history_text.setReadOnly(True)
        history_text.setStyleSheet(
            "background: rgba(255, 255, 255, 200); "
            "color: black; "
            "font-size: 16px; "
            "font-family: 'Microsoft YaHei', sans-serif;"
        )
        history_text.setPlainText("\n".join(self.dialog_history) if self.dialog_history else "暂无对话历史")
        layout.addWidget(history_text)

        history_window.show()

    def show_config_window(self):
        self.config_window.show()

    def restart_app(self):
        self.save_config()  # 重启前保存配置
        logging.info("Restarting application")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def closeEvent(self, event):
        """重写关闭事件，保存配置和窗口位置"""
        self.save_config()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position is not None:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = None

    def setup_config_window(self):
        self.config_window = QMainWindow()
        self.config_window.setWindowTitle("桌宠设置")
        self.config_window.setGeometry(200, 200, 300, 400)

        central_widget = QWidget()
        self.config_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        layout.addWidget(QLabel("Ollama API URL:"))
        self.ollama_url_entry = QLineEdit(self.config["ollama_url"])
        layout.addWidget(self.ollama_url_entry)

        layout.addWidget(QLabel("模型名称:"))
        self.model_name_entry = QLineEdit(self.config["model_name"])
        layout.addWidget(self.model_name_entry)

        layout.addWidget(QLabel("硅基流动 API 密钥:"))
        self.sensevoice_api_key_entry = QLineEdit(self.config["sensevoice_api_key"])
        layout.addWidget(self.sensevoice_api_key_entry)

        layout.addWidget(QLabel("录音按键:"))
        self.record_key_entry = QLineEdit(self.config["record_key"])
        self.record_key_entry.setReadOnly(True)
        layout.addWidget(self.record_key_entry)
        self.modify_key_button = QPushButton("修改按键")
        self.modify_key_button.clicked.connect(self.modify_record_key)
        layout.addWidget(self.modify_key_button)

        layout.addWidget(QLabel("心情图片路径:"))
        self.image_path_entry = QLineEdit(self.config["image_path"])
        layout.addWidget(self.image_path_entry)

        layout.addWidget(QLabel("窗口尺寸 (宽x高):"))
        self.size_entry = QLineEdit(f"{self.config['window_size'][0]}x{self.config['window_size'][1]}")
        layout.addWidget(self.size_entry)

        layout.addWidget(QLabel("窗口透明度 (0-1):"))
        self.alpha_entry = QLineEdit(str(self.config["window_alpha"]))
        layout.addWidget(self.alpha_entry)

        layout.addWidget(QLabel("人设 (System Prompt):"))
        self.persona_entry = QLineEdit(self.config["persona"])
        layout.addWidget(self.persona_entry)

        save_button = QPushButton("保存设置")
        save_button.clicked.connect(self.save_config_manual)
        layout.addWidget(save_button)

    def save_config_manual(self):
        """手动保存配置"""
        try:
            size = self.size_entry.text().split("x")
            self.config.update({
                "ollama_url": self.ollama_url_entry.text(),
                "model_name": self.model_name_entry.text(),
                "sensevoice_api_key": self.sensevoice_api_key_entry.text(),
                "record_key": self.record_key_entry.text(),
                "image_path": self.image_path_entry.text(),
                "window_alpha": float(self.alpha_entry.text()),
                "window_size": (int(size[0]), int(size[1])),
                "persona": self.persona_entry.text()
            })
            self.setWindowOpacity(self.config["window_alpha"])
            self.resize(self.config["window_size"][0], self.config["window_size"][1])
            self.input_box.setGeometry(10, 10, self.config["window_size"][0] - 70, 30)
            self.send_button.setGeometry(self.config["window_size"][0] - 50, 10, 40, 30)
            self.dialog_text.setGeometry(10, 50, self.config["window_size"][0] - 20, 100)
            self.image_label.setGeometry(0, 160, self.config["window_size"][0], self.config["window_size"][1] - 160)
            self.update_image("正常")
            self.save_config()  # 保存到文件
            logging.info("Configuration saved manually")
        except Exception as e:
            logging.error(f"Error saving config: {e}")
            self.dialog_text.setPlainText(f"保存设置失败：{str(e)}")

    def modify_record_key(self):
        try:
            self.record_key_entry.setText("按下任意键...")
            self.record_key_entry.setFocus()
            key_event = keyboard.read_event(suppress=True)
            if key_event.event_type == keyboard.KEY_DOWN:
                key = key_event.name
                if key:
                    self.record_key_entry.setText(key)
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
                    time.sleep(0.5)  # 等待 0.5 秒
                    while self.recording:
                        if not keyboard.is_pressed(self.config["record_key"]):
                            logging.info(f"Record key {self.config['record_key']} released, stopping recording")
                            self.recording = False
                        time.sleep(0.5)  # 每 0.5 秒检查一次
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Error in key_listener: {e}")
            self.dialog_text.setPlainText(f"按键监听错误：{str(e)}")

    def record_audio(self):
        p = None
        stream = None
        try:
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
            self.dialog_text.setPlainText(f"录音错误：{str(e)}")
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
        except Exception as e:
            logging.error(f"Error in call_sensevoice_api: {e}")
            return ""

    def process_audio(self, frames):
        wav_path = "../temp.wav"
        try:
            if not frames:
                logging.warning("No audio frames to process")
                self.dialog_text.setPlainText("录音为空，请重试")
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
            else:
                self.dialog_text.setPlainText("语音识别失败，请重试或手动输入")
        except Exception as e:
            logging.error(f"Error in process_audio: {e}")
            self.dialog_text.setPlainText(f"音频处理错误：{str(e)}")
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
        if error:
            self.dialog_text.setPlainText(error)
            self.update_image("无奈")
        else:
            self.dialog_text.setPlainText(chinese)
            self.update_image(mood)
        self.dialog_text.verticalScrollBar().setValue(self.dialog_text.verticalScrollBar().maximum())

    def customEvent(self, event):
        if event.type() == ResponseEvent.EventType:
            if event.error:
                self.dialog_text.setPlainText(event.error)
                self.update_image("无奈")
            else:
                self.dialog_text.setPlainText(event.chinese)
                self.update_image(event.mood)
            self.dialog_text.verticalScrollBar().setValue(self.dialog_text.verticalScrollBar().maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())