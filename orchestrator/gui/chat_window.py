#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Chat Window (v2.0 Goldstandard)
DIREKTIVE: Echter Threading-Support (QThread) & Persistenz.

Features:
- Asynchrone AI-Antworten (Kein GUI-Freeze).
- Persistente Chat-History (JSON im Cache).
- Manuelles Löschen der History.
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextBrowser, QLineEdit, 
    QPushButton, QHBoxLayout, QLabel, QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QIcon, QAction

from orchestrator.utils.localization import get_instance as get_i18n

class ChatWorker(QThread):
    """
    Führt die AI-Anfrage im Hintergrund aus, damit die GUI responsive bleibt.
    """
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, ditto, question, history):
        super().__init__()
        self.ditto = ditto
        self.question = question
        self.history = history

    def run(self):
        try:
            if not self.ditto:
                raise Exception("AI Core (Ditto) not initialized.")
            
            # Hier läuft die teure Operation
            answer = self.ditto.ask_ditto(self.question, self.history)
            self.finished.emit(answer)
        except Exception as e:
            self.error.emit(str(e))

class ChatWindow(QWidget):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.framework = framework_manager
        self.ditto = framework_manager.ditto_manager
        self.history = []
        self.i18n = get_i18n()
        self.worker = None
        
        # Pfad für Chat-History
        self.history_file = Path(framework_manager.config.cache_dir) / "chat_history.json"
        
        self._init_ui()
        self._load_history()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header mit Clear-Button
        header_layout = QHBoxLayout()
        title = QLabel("Ditto AI Assistant")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title)
        
        self.btn_clear = QPushButton("🗑️ Clear History")
        self.btn_clear.clicked.connect(self._confirm_clear_history)
        self.btn_clear.setFixedWidth(120)
        header_layout.addWidget(self.btn_clear, alignment=Qt.AlignRight)
        
        layout.addLayout(header_layout)
        
        # Chat Display
        self.txt_display = QTextBrowser()
        self.txt_display.setOpenExternalLinks(True)
        layout.addWidget(self.txt_display)
        
        # Status Bar (Thinking...)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate (Ladebalken läuft hin und her)
        self.progress.setFixedHeight(5)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # Input Area
        input_layout = QHBoxLayout()
        self.txt_input = QLineEdit()
        self.txt_input.setPlaceholderText(self.i18n.t("chat.placeholder", "Ask Ditto about compilation errors..."))
        self.txt_input.returnPressed.connect(self.send_message)
        
        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.txt_input)
        input_layout.addWidget(self.btn_send)
        layout.addLayout(input_layout)

    def _add_message(self, text, is_user=False):
        color = "#aaffaa" if is_user else "#ccccff"
        sender = "You" if is_user else "Ditto"
        align = "right" if is_user else "left"
        
        html = f"""
        <div style='text-align: {align}; margin: 5px;'>
            <span style='font-weight: bold; color: {color};'>{sender}:</span><br>
            <span style='background-color: #333; padding: 5px; border-radius: 5px;'>{text}</span>
        </div>
        <hr style='border: 0; border-top: 1px solid #444;'>
        """
        self.txt_display.append(html)
        
        # Update internal history
        role = "user" if is_user else "assistant"
        self.history.append({"role": role, "content": text})
        
        # Auto-Save nach jeder Nachricht
        self._save_history()

    def send_message(self):
        text = self.txt_input.text().strip()
        if not text: return
        
        self.txt_input.clear()
        self._add_message(text, True)
        
        # UI Sperren und Ladebalken zeigen
        self._set_thinking(True)
        
        # Worker starten (Echter Thread!)
        self.worker = ChatWorker(self.ditto, text, self.history)
        self.worker.finished.connect(self._on_ai_response)
        self.worker.error.connect(self._on_ai_error)
        self.worker.start()

    def _on_ai_response(self, answer):
        self._set_thinking(False)
        self._add_message(answer, False)

    def _on_ai_error(self, error_msg):
        self._set_thinking(False)
        self._add_message(f"⚠️ Error: {error_msg}", False)

    def _set_thinking(self, active: bool):
        self.txt_input.setEnabled(not active)
        self.btn_send.setEnabled(not active)
        self.progress.setVisible(active)

    def _save_history(self):
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save chat history: {e}")

    def _load_history(self):
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.history = [] # Reset RAM history first
                        self.txt_display.clear()
                        for msg in data:
                            # Re-Render history
                            is_user = msg.get("role") == "user"
                            content = msg.get("content", "")
                            self._add_message(content, is_user)
            except Exception as e:
                print(f"Warning: Corrupt chat history: {e}")

    def _confirm_clear_history(self):
        reply = QMessageBox.question(self, "Clear History", 
                                   "Are you sure you want to delete the entire chat history?\nThis cannot be undone.",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.history = []
            self.txt_display.clear()
            self._save_history() # Leere Datei schreiben
            self._add_message("History cleared.", False)
