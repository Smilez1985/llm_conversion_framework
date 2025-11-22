#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Dialogs
DIREKTIVE: Goldstandard, GUI-Komponenten.
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QComboBox, QLineEdit, QLabel, QPushButton, QApplication
)

class AddSourceDialog(QDialog):
    """Dialog to add a new source repository to project_sources.yml"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Source Repository")
        self.setMinimumWidth(500)
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        self.section_edit = QComboBox()
        self.section_edit.addItems(["core", "rockchip_npu", "voice_tts", "models", "custom"])
        self.section_edit.setEditable(True)
        form.addRow("Category (Section):", self.section_edit)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., my_special_tool")
        form.addRow("Name (Key):", self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/username/repo.git")
        form.addRow("Git URL:", self.url_edit)
        
        layout.addLayout(form)
        
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        btns = QHBoxLayout()
        self.test_btn = QPushButton("Test URL")
        self.test_btn.clicked.connect(self.test_url)
        btns.addWidget(self.test_btn)
        
        self.save_btn = QPushButton("Add Source")
        self.save_btn.clicked.connect(self.accept)
        self.save_btn.setEnabled(False)
        btns.addWidget(self.save_btn)
        
        layout.addLayout(btns)
        
    def test_url(self):
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText("Please enter a URL.")
            self.status_label.setStyleSheet("color: orange")
            return
            
        self.status_label.setText("Testing connection...")
        self.status_label.setStyleSheet("color: black")
        QApplication.processEvents()
        
        try:
            # Clean URL for testing (remove .git suffix for HTTP check if needed, though GitHub supports both)
            test_url = url
            if url.endswith('.git'): 
                test_url = url[:-4]

            response = requests.head(test_url, timeout=5, allow_redirects=True)
            
            if response.status_code < 400:
                self.status_label.setText("✅ URL is valid and reachable.")
                self.status_label.setStyleSheet("color: green")
                self.save_btn.setEnabled(True)
            else:
                self.status_label.setText(f"❌ URL returned status: {response.status_code}")
                self.status_label.setStyleSheet("color: red")
        except Exception as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)}")
            self.status_label.setStyleSheet("color: red")

    def get_data(self):
        return {
            "section": self.section_edit.currentText(),
            "name": self.name_edit.text(),
            "url": self.url_edit.text()
        }
