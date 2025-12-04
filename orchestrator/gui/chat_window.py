#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Chat Interface
DIREKTIVE: Goldstandard, GUI, UX.

Zweck:
Interaktives Chat-Fenster für Ditto.
Erlaubt dem User, Fragen an das RAG-System zu stellen ("Warum dieser Treiber?").
Integriert Visuals (Avatare) und Session-Management.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QIcon, QPixmap, QTextCursor, QColor

from orchestrator.utils.localization import tr

class ChatBubble(QFrame):
    """Custom Widget for a single chat message."""
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Style
        color = "#007acc" if is_user else "#404040"
        align = "right" if is_user else "left"
        border_radius = "15px"
        
        self.setStyleSheet(f"""
            ChatBubble {{
                background-color: {color};
                border-radius: {border_radius};
                border: 1px solid #555;
            }}
            QLabel {{
                color: white;
                font-size: 13px;
                background: transparent;
            }}
        """)
        
        self.lbl = QLabel(text)
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl)

class ChatWindow(QWidget):
    """
    Main Chat Widget. Can be docked or standalone.
    """
    def __init__(self, ditto_manager, parent=None):
        super().__init__(parent)
        self.ditto = ditto_manager
        self.history = [] # For LLM Context
        
        self._init_ui()
        
        # Initial Greeting
        QTimer.singleShot(500, lambda: self.add_message("Hi! I am Ditto. I can help you with hardware flags, SDK versions, and build errors. Just ask!", False))

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- Header / Toolbar ---
        header = QHBoxLayout()
        
        # Avatar (Small)
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setFixedSize(40, 40)
        self._update_avatar("default")
        header.addWidget(self.lbl_avatar)
        
        header.addWidget(QLabel("<b>Ditto AI Expert</b>"))
        header.addStretch()
        
        # Clear Context Button
        btn_clear = QPushButton("🧹")
        btn_clear.setToolTip("Clear Chat History / Context")
        btn_clear.setFixedSize(30, 30)
        btn_clear.clicked.connect(self.reset_session)
        header.addWidget(btn_clear)
        
        layout.addLayout(header)
        
        # --- Chat Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.addStretch() # Push messages to bottom
        
        self.scroll_area.setWidget(self.chat_container)
        layout.addWidget(self.scroll_area)
        
        # --- Input Area ---
        input_box = QHBoxLayout()
        
        self.txt_input = QLineEdit()
        self.txt_input.setPlaceholderText("Ask about drivers, flags, or errors...")
        self.txt_input.returnPressed.connect(self.send_message)
        input_box.addWidget(self.txt_input)
        
        self.btn_send = QPushButton("➤")
        self.btn_send.setFixedSize(40, 30)
        self.btn_send.clicked.connect(self.send_message)
        input_box.addWidget(self.btn_send)
        
        layout.addLayout(input_box)

    def _update_avatar(self, state):
        """Helper to set the mini avatar icon."""
        # Assuming assets are in parent's root or known path
        # For simplicity we assume 'assets/' relative to CWD
        map_state = {
            "default": "ditto.png",
            "think": "ditto_think.png",
            "error": "ditto_fail.png"
        }
        path = Path("assets") / map_state.get(state, "ditto.png")
        if path.exists():
             self.lbl_avatar.setPixmap(QPixmap(str(path)).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def send_message(self):
        text = self.txt_input.text().strip()
        if not text: return
        
        # 1. User Message
        self.add_message(text, True)
        self.txt_input.clear()
        self.txt_input.setEnabled(False)
        
        # 2. Process in Background (Simulated here via Timer to not block UI)
        # In real implementation, use a QThread/Worker!
        self._set_thinking(True)
        
        # Quick hack for responsiveness: Using QTimer to decouple execution
        QTimer.singleShot(100, lambda: self._process_ai_response(text))

    def _process_ai_response(self, text):
        """Calls Ditto Manager to get answer."""
        try:
            if self.ditto:
                answer = self.ditto.ask_ditto(text, self.history)
            else:
                answer = "Ditto Manager not connected. Offline mode."
                
            self.add_message(answer, False)
            
            # Update History
            self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": answer})
            
            # Context Management (Simple Rolling Window)
            if len(self.history) > 20:
                self.history = self.history[-10:] # Keep last 5 turns
                
        except Exception as e:
            self.add_message(f"Error: {str(e)}", False)
            self._update_avatar("error")
            
        finally:
            self.txt_input.setEnabled(True)
            self.txt_input.setFocus()
            self._set_thinking(False)

    def _set_thinking(self, thinking: bool):
        if thinking:
            self._update_avatar("think")
            self.setWindowTitle("Ditto is thinking...")
        else:
            self._update_avatar("default")
            self.setWindowTitle("Ditto AI Expert")

    def add_message(self, text: str, is_user: bool):
        bubble = ChatBubble(text, is_user)
        self.chat_layout.addWidget(bubble)
        
        # Auto Scroll
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def reset_session(self):
        """Clears history and UI."""
        self.history = []
        # Remove all widgets from layout (except stretch)
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.add_message("Context cleared. How can I help?", False)
