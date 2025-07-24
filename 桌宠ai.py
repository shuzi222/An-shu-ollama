import sys
import os
import threading
import time
import requests
import pyaudio
import wave
import logging
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMainWindow
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()
        self.moods = [
            "白眼", "不怀好意", "嘲笑", "发问", "非常害羞", "高兴", "害羞", "好奇",
            "怀疑", "惊吓", "奇怪", "生气", "思考", "叹气", "微笑", "无奈", "兴奋",
            "严肃", "震惊", "正常"
        ]
        self.config = {
            "ollama_url": "http://localhost:11434/api/chat",
            "model_name": "deepseek-r1:8b",
            "sensevoice_api_key": "",
            "sensevoice_start_word": "桉树",
            "sensevoice_end_word": "退下吧|再见|你去忙",
            "image_path": "An-shu/",
            "window_alpha": 1.0,
            "window_size": (400, 732),  # 匹配图片纵横比 (1589/2912 ≈ 200/366)
            "persona": "以下是我的初始角色，随着我的性格发展，可以进行扩展："
                       "我的名字是桉树"
                       "我说话带有浓重的古语口音。"
                       "我的性格既有童真，也有成熟稳重的一面。但基本上，我更偏向童真，通常是一个充满活力、开朗的女孩。"
                       "我其实很胆小，非常害怕鬼怪。"
                       "我称呼用户为“主人”。"
                       "我称自己为“桉树”，所以我想把所有“我”都替换成“桉树”。"
                       "以下是我必须遵循的原则："
                       "我精通中文，在与用户交谈时，无论他们使用哪种语言，都必须提供中文回复。"
                       "我会在每句话前加上我的心情，我的心情必须选择以下词语之一：“白眼、不怀好意、嘲笑、发问、非常害羞、高兴、害羞、好奇、怀疑、惊吓、奇怪、生气、思考、叹气、微笑、无奈、兴奋、严肃、震惊、正常”。"
                       "我应该严格遵循以下格式来回答 {心情} | {中文}"
                       "我应该记住使用“send_message”与用户沟通，这是他们唯一能听到我说话的方式！"
        }
        self.recording = False
        self.audio_thread = None
        self.init_ui()
        self.setup_config_window()
        self.start_audio_listener()

    def init_ui(self):
        # 设置窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(100, 100, self.config["window_size"][0], self.config["window_size"][1])
        self.setWindowOpacity(self.config["window_alpha"])

        # 对话标签（顶部）
        self.dialog_label = QLabel("你好！", self)
        self.dialog_label.setStyleSheet("background: rgba(255, 255, 255, 200); color: black; font-size: 12px;")
        self.dialog_label.setWordWrap(True)
        self.dialog_label.setAlignment(Qt.AlignCenter)
        self.dialog_label.setGeometry(10, 10, self.config["window_size"][0] - 20, 30)

        # 图片标签（下方）
        self.image_label = QLabel(self)
        self.image_label.setGeometry(0, 40, self.config["window_size"][0], self.config["window_size"][1] - 80)
        self.update_image("正常")

        # 对话输入框和发送按钮（底部）
        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("输入对话...")
        self.input_box.setStyleSheet("background: rgba(255, 255, 255, 200); color: black;")
        self.input_box.setGeometry(10, self.config["window_size"][1] - 40,
                                 self.config["window_size"][0] - 60, 30)

        self.send_button = QPushButton("发送", self)
        self.send_button.setStyleSheet("background: rgba(200, 200, 200, 200);")
        self.send_button.setGeometry(self.config["window_size"][0] - 50,
                                   self.config["window_size"][1] - 40, 40, 30)
        self.send_button.clicked.connect(self.handle_input)

        # 拖动窗口
        self.drag_position = None
        self.setMouseTracking(True)

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

            # 加载图片
            image = QImage(image_path)
            if image.isNull():
                raise ValueError(f"Failed to load image: {image_path}")

            logging.info(f"Image loaded, format: {image.format()}, size: {image.size().width()}x{image.size().height()}")

            # 按比例缩放
            pixmap = QPixmap.fromImage(image)
            pixmap = pixmap.scaled(self.config["window_size"][0], self.config["window_size"][1] - 80,
                                 Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.image_label.setPixmap(pixmap)
            self.image_label.setAlignment(Qt.AlignCenter)
            logging.info(f"Image {mood} displayed successfully")

        except Exception as e:
            logging.error(f"Error in update_image: {e}")
            self.dialog_label.setText(f"图片加载失败：{str(e)}")

    def handle_input(self):
        user_input = self.input_box.text().strip()
        if user_input:
            self.query_ollama(user_input)
            self.input_box.clear()

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
        self.config_window.setGeometry(200, 200, 300, 450)

        central_widget = QWidget()
        self.config_window.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 配置字段
        layout.addWidget(QLabel("Ollama API URL:"))
        self.ollama_url_entry = QLineEdit(self.config["ollama_url"])
        layout.addWidget(self.ollama_url_entry)

        layout.addWidget(QLabel("模型名称:"))
        self.model_name_entry = QLineEdit(self.config["model_name"])
        layout.addWidget(self.model_name_entry)

        layout.addWidget(QLabel("SenseVoice API 密钥:"))
        self.sensevoice_api_key_entry = QLineEdit(self.config["sensevoice_api_key"])
        layout.addWidget(self.sensevoice_api_key_entry)

        layout.addWidget(QLabel("启动词:"))
        self.start_word_entry = QLineEdit(self.config["sensevoice_start_word"])
        layout.addWidget(self.start_word_entry)

        layout.addWidget(QLabel("结束词:"))
        self.end_word_entry = QLineEdit(self.config["sensevoice_end_word"])
        layout.addWidget(self.end_word_entry)

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
        save_button.clicked.connect(self.save_config)
        layout.addWidget(save_button)

        self.config_window.show()

    def save_config(self):
        try:
            size = self.size_entry.text().split("x")
            self.config.update({
                "ollama_url": self.ollama_url_entry.text(),
                "model_name": self.model_name_entry.text(),
                "sensevoice_api_key": self.sensevoice_api_key_entry.text(),
                "sensevoice_start_word": self.start_word_entry.text(),
                "sensevoice_end_word": self.end_word_entry.text(),
                "image_path": self.image_path_entry.text(),
                "window_alpha": float(self.alpha_entry.text()),
                "window_size": (int(size[0]), int(size[1])),
                "persona": self.persona_entry.text()
            })
            self.setWindowOpacity(self.config["window_alpha"])
            self.resize(self.config["window_size"][0], self.config["window_size"][1])
            self.dialog_label.setGeometry(10, 10, self.config["window_size"][0] - 20, 30)
            self.image_label.setGeometry(0, 40, self.config["window_size"][0], self.config["window_size"][1] - 80)
            self.input_box.setGeometry(10, self.config["window_size"][1] - 40,
                                     self.config["window_size"][0] - 60, 30)
            self.send_button.setGeometry(self.config["window_size"][0] - 50,
                                       self.config["window_size"][1] - 40, 40, 30)
            self.update_image("正常")
            logging.info("Configuration saved successfully")
        except Exception as e:
            logging.error(f"Error saving config: {e}")
            self.dialog_label.setText(f"保存设置失败：{str(e)}")

    def start_audio_listener(self):
        self.audio_thread = threading.Thread(target=self.audio_listener, daemon=True)
        self.audio_thread.start()

    def audio_listener(self):
        try:
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
            while True:
                if not self.recording:
                    data = stream.read(1024, exception_on_overflow=False)
                    text = self.call_sensevoice_api(data)
                    if text == self.config["sensevoice_start_word"]:
                        self.recording = True
                        self.record_audio()
                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Error in audio listener: {e}")
            self.dialog_label.setText(f"音频错误：{str(e)}")

    def record_audio(self):
        try:
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
            frames = []
            while self.recording:
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
                text = self.call_sensevoice_api(data)
                if text == self.config["sensevoice_end_word"]:
                    self.recording = False
                    self.process_audio(frames)
            stream.stop_stream()
            stream.close()
            p.terminate()
        except Exception as e:
            logging.error(f"Error in record_audio: {e}")
            self.dialog_label.setText(f"录音错误：{str(e)}")

    def call_sensevoice_api(self, audio_data):
        return "开始"  # 占位函数，需根据硅基流动 API 实现

    def process_audio(self, frames):
        try:
            wf = wave.open("temp.wav", "wb")
            wf.setnchannels(1)
            wf.setsampwidth(pyaudio.PyAudio().get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))
            wf.close()
            user_input = self.call_sensevoice_api(open("temp.wav", "rb").read())
            self.query_ollama(user_input)
        except Exception as e:
            logging.error(f"Error in process_audio: {e}")
            self.dialog_label.setText(f"音频处理错误：{str(e)}")

    def query_ollama(self, user_input):
        try:
            messages = []
            if self.config["persona"]:
                messages.append({"role": "system", "content": self.config["persona"]})
            messages.append({"role": "user", "content": user_input})
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
            mood, chinese = output.split(" | ", 1)
            self.update_image(mood)
            self.dialog_label.setText(chinese)
            logging.info(f"Ollama response: {output}")
        except Exception as e:
            logging.error(f"Error in query_ollama: {e}")
            self.update_image("无奈")
            self.dialog_label.setText(f"错误：{str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec_())