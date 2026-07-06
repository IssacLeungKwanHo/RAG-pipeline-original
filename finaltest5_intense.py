import sys
import os
import logging
os.environ["PATH"] += os.pathsep + "/opt/homebrew/bin:/opt/homebrew/opt/poppler/bin"
import glob
import speech_recognition as sr
from gtts import gTTS
from pygame import mixer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextBrowser, QTextEdit, QPushButton, QComboBox, QLabel,
                             QInputDialog, QMessageBox, QLineEdit)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont, QPixmap, QTextCursor, QMovie
from datetime import datetime
from ver2_test5_std import setup_local_chatbot
from virtual_pet2 import VirtualPet
from alarm_clock import TimerDialog
from music_therapy_new import MusicTherapyDialog

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Set the base directory to the location of the script
BASE_DIR = "/Users/issacleung/ollama_trial"
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")
os.makedirs(RESOURCES_DIR, exist_ok=True)

class ChatWorker(QThread):
    response_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, query_function, user_input):
        super().__init__()
        self.query_function = query_function
        self.user_input = user_input

    def run(self):
        try:
            response = self.query_function(self.user_input)
            self.response_signal.emit(response)
        except Exception as e:
            self.error_signal.emit(str(e))

class ChatInput(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return:
            if event.modifiers() & Qt.ShiftModifier:
                self.insertPlainText("\n")
            else:
                self.main_window.send_message()
        else:
            super().keyPressEvent(event)

class ADHDChatbotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADHD Chatbot")
        self.setGeometry(100, 100, 800, 600)

        # Initialize pygame mixer for TTS playback
        try:
            mixer.init()
        except Exception as e:
            logging.warning(f"Pygame mixer initialization failed: {str(e)}")
            QMessageBox.warning(self, "Warning", "Pygame mixer failed to initialize. TTS may not work.")

        # Main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Top layout (Title with icon, Pet Button, Timer Button, Music Button)
        self.top_layout = QHBoxLayout()

        # Title with AI icon and music GIF placeholder
        self.title_layout = QHBoxLayout()
        self.icon_label = QLabel()
        pixmap_path = os.path.join(BASE_DIR, "aiicon.png")
        if os.path.exists(pixmap_path):
            pixmap = QPixmap(pixmap_path)
            self.icon_label.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio))
        else:
            logging.warning("AI icon not found")
        self.title_label = QLabel("ADHD Chatbot")
        self.title_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.title_layout.addWidget(self.icon_label)
        self.title_layout.addWidget(self.title_label)

        # Music GIF label (initially hidden)
        self.music_gif_label = QLabel()
        music_gif_path = os.path.join(BASE_DIR, "music.gif")
        if os.path.exists(music_gif_path):
            self.music_movie = QMovie(music_gif_path)
            self.music_movie.setScaledSize(QSize(40, 40))
            self.music_gif_label.setMovie(self.music_movie)
            self.music_gif_label.setVisible(False)
        else:
            logging.warning("Music GIF not found")
        self.title_layout.addWidget(self.music_gif_label)

        self.top_layout.addLayout(self.title_layout)
        self.top_layout.addStretch()

        # Buttons layout for Pet, Timer, Music
        self.buttons_layout = QHBoxLayout()

        # Pet button
        self.pet_button = QPushButton()
        pet_icon_path = os.path.join(BASE_DIR, "pet_icon.png")
        if os.path.exists(pet_icon_path):
            self.pet_button.setIcon(QIcon(pet_icon_path))
        else:
            logging.warning("Pet icon not found")
        self.pet_button.setIconSize(QSize(40, 40))
        self.pet_button.setFixedSize(60, 60)
        self.pet_button.setToolTip("Toggle Virtual Pet")
        self.pet_button.clicked.connect(self.toggle_pet)
        self.buttons_layout.addWidget(self.pet_button)

        # Timer button
        self.timer_button = QPushButton()
        timer_icon_path = os.path.join(BASE_DIR, "timer_icon.png")
        if os.path.exists(timer_icon_path):
            self.timer_button.setIcon(QIcon(timer_icon_path))
        else:
            logging.warning("Timer icon not found")
        self.timer_button.setIconSize(QSize(40, 40))
        self.timer_button.setFixedSize(60, 60)
        self.timer_button.setToolTip("Open Timer")
        self.timer_button.clicked.connect(self.open_timer_dialog)
        self.buttons_layout.addWidget(self.timer_button)

        # Music button
        self.music_button = QPushButton()
        music_icon_path = os.path.join(BASE_DIR, "music_note.jpg")
        if os.path.exists(music_icon_path):
            self.music_button.setIcon(QIcon(music_icon_path))
        else:
            logging.warning("Music icon not found")
        self.music_button.setIconSize(QSize(40, 40))
        self.music_button.setFixedSize(60, 60)
        self.music_button.setToolTip("Open Music Therapy")
        self.music_button.clicked.connect(self.open_music_dialog)
        self.buttons_layout.addWidget(self.music_button)

        self.top_layout.addLayout(self.buttons_layout)
        self.main_layout.addLayout(self.top_layout)

        # Controls layout (User Type, Model Selection, Theme Toggle, Clear Button)
        self.controls_layout = QHBoxLayout()
        left_controls = QHBoxLayout()

        # User type selection
        self.user_type_label = QLabel("User Type:")
        self.user_type_label.setFont(QFont("Arial", 12))
        left_controls.addWidget(self.user_type_label)

        self.user_type_combo = QComboBox()
        self.user_type_combo.addItems(["Student", "Parent"])
        self.user_type_combo.setFont(QFont("Arial", 12))
        self.user_type_combo.setFixedWidth(150)
        self.user_type_combo.setToolTip("Select User Type: Student or Parent")
        self.user_type_combo.currentTextChanged.connect(self.check_parent_password)
        left_controls.addWidget(self.user_type_combo)

        # Model selection
        self.model_label = QLabel("AI Model:")
        self.model_label.setFont(QFont("Arial", 12))
        left_controls.addWidget(self.model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "llama3.1:8b",
            "llama3.2:3b",
            "deepseek-r1:8b",
            "deepseek-r1:7b",
            "gemma3n:e4b",
            "gemma3:4b",
            "mistral:7b",
            "qwen3:4b",
            "qwen3:8b"
        ])
        self.model_combo.setFont(QFont("Arial", 12))
        self.model_combo.setFixedWidth(150)
        self.model_combo.setToolTip("Select AI Model")
        self.model_combo.currentTextChanged.connect(self.change_model)
        left_controls.addWidget(self.model_combo)

        self.controls_layout.addLayout(left_controls)
        self.controls_layout.addStretch()

        # Theme toggle button
        self.theme_button = QPushButton("Switch to Dark Mode")
        self.theme_button.setFont(QFont("Arial", 12))
        self.theme_button.setToolTip("Toggle Theme: Day/Night Mode")
        self.theme_button.clicked.connect(self.toggle_theme)
        self.controls_layout.addWidget(self.theme_button)

        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.setFont(QFont("Arial", 12))
        self.clear_button.setToolTip("Clear Chat History")
        self.clear_button.clicked.connect(self.clear_chat)
        self.controls_layout.addWidget(self.clear_button)

        self.main_layout.addLayout(self.controls_layout)

        # Chat area (with overlay for clap GIF)
        self.chat_area = QWidget()
        self.chat_area_layout = QVBoxLayout(self.chat_area)
        self.chat_area_layout.setContentsMargins(0, 0, 0, 0)

        # Chat display
        self.chat_display = QTextBrowser()
        self.chat_display.setFont(QFont("Arial", 14))
        self.chat_display.setHtml("")
        self.chat_display.setOpenLinks(False)
        self.chat_area_layout.addWidget(self.chat_display)

        # Overlay label for clap GIF
        self.clap_gif_label = QLabel(self.chat_display)
        self.clap_gif_label.setAlignment(Qt.AlignCenter)
        clap_gif_path = os.path.join(BASE_DIR, "clap.gif")
        if os.path.exists(clap_gif_path):
            self.clap_movie = QMovie(clap_gif_path)
            self.clap_movie.setScaledSize(QSize(300, 300))
            self.clap_gif_label.setMovie(self.clap_movie)
        else:
            logging.warning("Clap GIF not found")
        self.clap_gif_label.setVisible(False)
        self.clap_gif_label.setStyleSheet("background: transparent;")
        self.clap_gif_label.setGeometry(0, 0, self.chat_display.width(), self.chat_display.height())

        self.main_layout.addWidget(self.chat_area)

        # Input area layout
        self.input_layout = QHBoxLayout()
        self.input_layout.setSpacing(10)

        self.input_area = ChatInput(self)
        self.input_area.setFont(QFont("Arial", 14))
        self.input_area.setFixedHeight(60)
        self.input_area.setAcceptRichText(False)
        self.input_layout.addWidget(self.input_area)

        # Voice input button
        self.voice_input_button = QPushButton()
        voice_icon_path = os.path.join(BASE_DIR, "voice_icon.png")
        if os.path.exists(voice_icon_path):
            self.voice_input_button.setIcon(QIcon(voice_icon_path))
        else:
            logging.warning("Voice icon not found")
        self.voice_input_button.setIconSize(QSize(30, 30))
        self.voice_input_button.setFixedSize(40, 40)
        self.voice_input_button.setToolTip("Record Voice Input")
        self.voice_input_button.clicked.connect(self.record_voice_input)
        self.input_layout.addWidget(self.voice_input_button)

        self.send_button = QPushButton("Send")
        self.send_button.setFont(QFont("Arial", 14))
        self.send_button.setFixedHeight(60)
        self.send_button.setToolTip("Send Message")
        self.send_button.clicked.connect(self.send_message)
        self.input_layout.addWidget(self.send_button)

        self.main_layout.addLayout(self.input_layout)

        # Virtual pet setup
        self.pet = None
        self.pet_visible = False
        self.pet_dir = os.path.join(BASE_DIR, "pet2")
        self.idle_gifs = glob.glob(os.path.join(self.pet_dir, 'idle_*.gif'))
        self.walking_gifs = glob.glob(os.path.join(self.pet_dir, 'walk_*.gif'))
        self.reaction_gifs = glob.glob(os.path.join(self.pet_dir, 'reaction_*.gif'))
        if not self.walking_gifs:
            self.walking_gifs = self.idle_gifs
        if not self.reaction_gifs:
            self.reaction_gifs = self.idle_gifs

        # Password for parents mode
        self.parents_password = "parent123"
        self.is_parent_authenticated = False

        # Theme state
        self.is_dark_mode = False

        # Apply initial stylesheet (day mode)
        self.apply_stylesheet()

        # Initialize speech recognizer
        try:
            self.recognizer = sr.Recognizer()
        except Exception as e:
            logging.warning(f"Speech recognizer initialization failed: {str(e)}")
            QMessageBox.warning(self, "Warning", "Speech recognition failed to initialize. Voice input may not work.")

        # Store AI responses for TTS
        self.ai_responses = []

        # Initialize chatbot *after* UI setup
        self.current_model = "llama3.1:8b"  # Default model
        self.initialize_chatbot()

    def initialize_chatbot(self):
        try:
            self.student_query_engine, self.parents_query_engine, self.query_local_mistral, self.student_prompt, self.parents_prompt = setup_local_chatbot(self.current_model)
        except Exception as e:
            logging.error(f"Failed to initialize chatbot: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to initialize chatbot: {str(e)}\n\nPlease ensure Ollama is running and the model '{self.current_model}' is pulled. Check logs for details.")
            self.chat_display.append(f"<b>Error:</b> Failed to initialize chatbot. Please check the logs and restart the app.<br><br>")
            # Set fallbacks to avoid further errors
            self.student_query_engine = None
            self.parents_query_engine = None
            self.query_local_mistral = None
            self.student_prompt = ""
            self.parents_prompt = ""
            
    def change_model(self):
        self.current_model = self.model_combo.currentText()
        self.chat_display.append(f"<i>Switched to model: {self.current_model}</i>")
        logging.info(f"Switching to model: {self.current_model}")
        self.initialize_chatbot()

    def resizeEvent(self, event):
        self.clap_gif_label.setGeometry(0, 0, self.chat_display.width(), self.chat_display.height())
        super().resizeEvent(event)

    def apply_stylesheet(self):
        if self.is_dark_mode:
            stylesheet = """
                QMainWindow { background-color: #2b2b2b; }
                QLabel { color: #ffffff; }
                QTextBrowser {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    padding: 5px;
                }
                QTextEdit {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #007bff;
                    color: #ffffff;
                    border: none;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton:hover { background-color: #0056b3; }
                QComboBox {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    padding: 5px;
                }
                QComboBox QAbstractItemView {
                    background-color: #3c3c3c;
                    color: #ffffff;
                    border: 1px solid #555555;
                    selection-background-color: #007bff;
                    selection-color: #ffffff;
                }
                QPushButton#petButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#petButton:hover { background-color: #555555; }
                QPushButton#timerButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#timerButton:hover { background-color: #555555; }
                QPushButton#musicButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#musicButton:hover { background-color: #555555; }
                QPushButton#voiceInputButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 20px;
                }
                QPushButton#voiceInputButton:hover { background-color: #555555; }
            """
            self.theme_button.setText("Switch to Day Mode")
        else:
            stylesheet = """
                QMainWindow { background-color: #e0e0e0; }
                QLabel { color: #000000; }
                QTextBrowser {
                    background-color: #f5f5f5;
                    color: #000000;
                    border: 1px solid #cccccc;
                    border-radius: 5px;
                    padding: 5px;
                }
                QTextEdit {
                    background-color: #f5f5f5;
                    color: #000000;
                    border: 1px solid #cccccc;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #007bff;
                    color: #ffffff;
                    border: none;
                    border-radius: 5px;
                    padding: 5px;
                }
                QPushButton:hover { background-color: #0056b3; }
                QComboBox {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #cccccc;
                    border-radius: 5px;
                    padding: 5px;
                }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    color: #000000;
                    border: 1px solid #cccccc;
                    selection-background-color: #007bff;
                    selection-color: #ffffff;
                }
                QPushButton#petButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#petButton:hover { background-color: #cccccc; }
                QPushButton#timerButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#timerButton:hover { background-color: #cccccc; }
                QPushButton#musicButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 30px;
                }
                QPushButton#musicButton:hover { background-color: #cccccc; }
                QPushButton#voiceInputButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 20px;
                }
                QPushButton#voiceInputButton:hover { background-color: #cccccc; }
            """
            self.theme_button.setText("Switch to Dark Mode")
        self.setStyleSheet(stylesheet)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_stylesheet()

    def check_parent_password(self):
        current_mode = self.user_type_combo.currentText()
        logging.debug(f"Checking parent password, current mode: {current_mode}, authenticated: {self.is_parent_authenticated}")
        if current_mode == "Parent":
            dialog = QInputDialog()
            dialog.setTextEchoMode(QLineEdit.Password)
            password, ok = dialog.getText(self, "Parent Mode", "Enter password for Parents Mode:")
            if ok and password == self.parents_password:
                self.is_parent_authenticated = True
                self.chat_display.append("<i>Switched to Parents Mode.</i>")
                logging.info("Successfully authenticated for Parents Mode.")
            else:
                self.is_parent_authenticated = False
                self.chat_display.append("<i>Incorrect password. Reverting to Student Mode.</i>")
                logging.warning("Incorrect password entered for Parents Mode.")
                QMessageBox.warning(self, "Error", "Incorrect password.")
                self.user_type_combo.blockSignals(True)
                self.user_type_combo.setCurrentText("Student")
                self.user_type_combo.blockSignals(False)
        else:
            self.is_parent_authenticated = False
            self.chat_display.append("<i>Switched to Student Mode.</i>")
            logging.info("Switched to Student Mode.")

    def record_voice_input(self):
        try:
            with sr.Microphone() as source:
                self.chat_display.append("<i>Listening...</i>")
                QApplication.processEvents()
                audio = self.recognizer.listen(source)
                text = self.recognizer.recognize_google(audio)
                self.input_area.setText(text)
                self.chat_display.append(f"<i>Recognized: {text}</i>")
        except Exception as e:
            self.chat_display.append(f"<i>Speech recognition error: {str(e)}</i>")
            logging.error(f"Speech recognition error: {str(e)}")

    def play_response(self, response_index):
        try:
            response_text = self.ai_responses[response_index]
            tts = gTTS(text=response_text, lang='en')
            tts_file = os.path.join(RESOURCES_DIR, "response.mp3")
            tts.save(tts_file)
            mixer.music.load(tts_file)
            mixer.music.play()
        except Exception as e:
            logging.error(f"TTS playback error: {str(e)}")
            QMessageBox.warning(self, "Warning", f"TTS playback failed: {str(e)}")

    def send_message(self):
        user_input = self.input_area.toPlainText().strip()
        if not user_input:
            return

        logging.debug(f"Sending message, mode: {self.user_type_combo.currentText()}, authenticated: {self.is_parent_authenticated}, model: {self.current_model}")
        if self.user_type_combo.currentText() == "Parent" and not self.is_parent_authenticated:
            self.chat_display.append("<i>Please authenticate for Parents Mode.</i>")
            self.check_parent_password()
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.append(f'<b>You ({timestamp}):</b> {user_input}')
        self.input_area.clear()

        query_engine = self.parents_query_engine if self.user_type_combo.currentText() == "Parent" else self.student_query_engine
        self.chat_display.append(f"<i>User: {self.user_type_combo.currentText()}, Model: {self.current_model}</i>")
        self.chat_display.append("<i>Processing...</i>")

        self.worker = ChatWorker(lambda x: self.query_local_mistral(query_engine, x), user_input)
        self.worker.response_signal.connect(self.display_response)
        self.worker.error_signal.connect(self.display_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def display_response(self, response):
        timestamp = datetime.now().strftime("%H:%M:%S")
        response_index = len(self.ai_responses)
        self.ai_responses.append(response)
        voice_icon_path = os.path.join(BASE_DIR, "voice_icon.png")
        voice_icon_html = f'<a href="play_response_{response_index}"><img src="{voice_icon_path}" width="24" height="24" style="vertical-align:middle; margin-left:5px;"></a>' if os.path.exists(voice_icon_path) else ""
        new_message = f'<b>Chatbot ({timestamp}, {self.current_model}):</b> {response} {voice_icon_html}<br><br>'
        self.chat_display.append(new_message)
        self.chat_display.moveCursor(QTextCursor.End)

    def display_error(self, error):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.append(f'<b>Error ({timestamp}, {self.current_model}):</b> {error}')
        self.chat_display.moveCursor(QTextCursor.End)

    def clear_chat(self):
        self.chat_display.clear()
        self.ai_responses = []

    def toggle_pet(self):
        if not self.pet_visible:
            if self.idle_gifs:
                try:
                    self.pet = VirtualPet(self.idle_gifs, self.walking_gifs, self.reaction_gifs)
                    self.pet.show()
                    self.pet_visible = True
                except Exception as e:
                    logging.error(f"Virtual pet initialization failed: {str(e)}")
                    QMessageBox.warning(self, "Warning", f"Failed to initialize virtual pet: {str(e)}")
            else:
                logging.warning("No pet GIFs found")
                QMessageBox.warning(self, "Warning", "No pet GIFs found")
        else:
            try:
                self.pet.hide()
                self.pet.deleteLater()
                self.pet = None
                self.pet_visible = False
            except Exception as e:
                logging.error(f"Error hiding virtual pet: {str(e)}")

    def open_timer_dialog(self):
        try:
            timer_dialog = TimerDialog(self)
            timer_dialog.timer.Finished.connect(self.show_clap_gif)
            timer_dialog.exec_()
        except Exception as e:
            logging.error(f"Timer dialog error: {str(e)}")
            QMessageBox.warning(self, "Warning", f"Failed to open timer dialog: {str(e)}")

    def open_music_dialog(self):
        try:
            music_dialog = MusicTherapyDialog(self)
            music_dialog.playing.connect(self.show_music_gif)
            music_dialog.stopped.connect(self.hide_music_gif)
            music_dialog.exec_()
        except Exception as e:
            logging.error(f"Music dialog error: {str(e)}")
            QMessageBox.warning(self, "Warning", f"Failed to open music dialog: {str(e)}")

    def show_music_gif(self):
        if hasattr(self, 'music_movie'):
            self.music_gif_label.setVisible(True)
            self.music_movie.start()

    def hide_music_gif(self):
        if hasattr(self, 'music_movie'):
            self.music_gif_label.setVisible(False)
            self.music_movie.stop()

    def show_clap_gif(self):
        if hasattr(self, 'clap_movie'):
            self.clap_gif_label.setVisible(True)
            self.clap_movie.start()
            QTimer.singleShot(5000, self.hide_clap_gif)

    def hide_clap_gif(self):
        if hasattr(self, 'clap_movie'):
            self.clap_gif_label.setVisible(False)
            self.clap_movie.stop()
    

# Add these methods to the ADHDChatbotApp class:

    def strip_thinking(self, response, model):
        # Model-specific patterns for thinking processes observed in Excel responses
        thinking_patterns = {
            'deepseek-r1:8b': ["Okay, the user is asking", "Okay, so I'm trying to figure out"],  # Long thinking blocks
            'deepseek-r1:7b': ["Okay, the user is dealing with"], 
            'gemma3n:e4b': ["Okay, the user is struggling with"], 
            'gemma3:4b': ["Okay, so I'm trying to figure out"],
            'qwen3:4b': ["Okay, the user is dealing with"],
            'qwen3:8b': ["Okay, the user is struggling with"],
            # Add others if needed; llama and mistral seem clean from Excel
        }
        
        patterns = thinking_patterns.get(model, [])
        for pattern in patterns:
            if pattern in response:
                idx = response.find(pattern)
                if idx >= 0:
                    # Find the end of thinking, often before direct address like "It sounds" or "I'm really sorry"
                    end_patterns = ["Okay, let's break down", "It sounds", "I'm really sorry", "I’m really sorry"]
                    for end_pattern in end_patterns:
                        end_idx = response.find(end_pattern, idx)
                        if end_idx > idx:
                            return response[end_idx:].strip()
                    # Fallback: cut after the thinking block (approximate)
                    return response[response.rfind("\n", idx) + 1:].strip()
        return response.strip()

    def markdown_to_html(self, text):
        import re
        # Basic Markdown to HTML conversion for QTextBrowser
        # Bold: **text** -> <b>text</b>
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        
        # Split into lines
        lines = text.split('\n')
        result = []
        in_ol = False
        in_ul = False
        para_lines = []  # To collect consecutive non-empty lines into one paragraph
        
        for line in lines:
            stripped = line.strip()
            
            # Skip unnecessary --- lines
            if stripped in ['---', '----', '-----', '--', '==', '===']:
                continue
            
            if stripped:
                if re.match(r'^\d+\.', stripped):
                    # Flush any pending paragraph
                    if para_lines:
                        result.append('<p>' + ' '.join(para_lines) + '</p>')
                        para_lines = []
                    if not in_ol:
                        if in_ul:
                            result.append('</ul>')
                            in_ul = False
                        result.append('<ol>')
                        in_ol = True
                    item = re.sub(r'^\d+\.\s*', '', stripped)
                    result.append(f'<li>{item}</li>')
                elif re.match(r'^\*', stripped):
                    # Flush any pending paragraph
                    if para_lines:
                        result.append('<p>' + ' '.join(para_lines) + '</p>')
                        para_lines = []
                    if not in_ul:
                        if in_ol:
                            result.append('</ol>')
                            in_ol = False
                        result.append('<ul>')
                        in_ul = True
                    item = re.sub(r'^\*\s*', '', stripped)
                    result.append(f'<li>{item}</li>')
                else:
                    # Collect non-list line into paragraph
                    para_lines.append(stripped)
            else:
                # Empty line: Flush pending paragraph and end lists if active
                if para_lines:
                    result.append('<p>' + ' '.join(para_lines) + '</p>')
                    para_lines = []
                if in_ol:
                    result.append('</ol>')
                    in_ol = False
                if in_ul:
                    result.append('</ul>')
                    in_ul = False
                # No <br> added here to avoid extra skips; <p> margins handle spacing
        
        # Flush any remaining paragraph or close lists
        if para_lines:
            result.append('<p>' + ' '.join(para_lines) + '</p>')
        if in_ol:
            result.append('</ol>')
        if in_ul:
            result.append('</ul>')
        
        return ''.join(result)

    # Modify display_response method:
    def display_response(self, response):
        # Strip any thinking process
        response = self.strip_thinking(response, self.current_model)
        
        # Convert to HTML
        formatted_response = self.markdown_to_html(response)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        response_index = len(self.ai_responses)
        self.ai_responses.append(response)  # Store raw for TTS
        voice_icon_path = os.path.join(BASE_DIR, "voice_icon.png")
        voice_icon_html = f'<a href="play_response_{response_index}"><img src="{voice_icon_path}" width="24" height="24" style="vertical-align:middle; margin-left:5px;"></a>' if os.path.exists(voice_icon_path) else ""
        new_message = f'<b>Chatbot ({timestamp}, {self.current_model}):</b> {formatted_response} {voice_icon_html}<br><br>'
        self.chat_display.append(new_message)
        self.chat_display.moveCursor(QTextCursor.End)

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = ADHDChatbotApp()
        window.show()
        window.chat_display.anchorClicked.connect(
            lambda url: window.play_response(int(url.toString().split('_')[-1]))
        )
        sys.exit(app.exec_())
    except Exception as e:
        logging.error(f"Application failed to start: {str(e)}")
        raise