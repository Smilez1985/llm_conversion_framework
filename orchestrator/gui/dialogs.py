#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Dialogs
DIREKTIVE: Goldstandard, GUI-Komponenten.
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QComboBox, QLineEdit, QLabel, QPushButton, QApplication,
    QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QWidget
)
from PySide6.QtCore import Qt

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
            # Clean URL for testing (remove .git suffix for HTTP check if needed)
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


class AIConfigurationDialog(QDialog):
    """Dialog to configure AI Provider and Model for Ditto."""
    
    PROVIDERS = {
        "OpenAI": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "Anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        "Google VertexAI": ["gemini-1.5-pro", "gemini-1.0-pro"],
        "Mistral": ["mistral-large-latest", "mistral-medium", "mistral-small"],
        "Ollama (Local)": ["llama3", "mistral", "gemma", "codellama"],
        "LocalAI / OpenAI Compatible": ["local-model"]
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure AI Agent (Ditto)")
        self.setMinimumWidth(500)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Provider Selection ---
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.PROVIDERS.keys())
        self.provider_combo.currentTextChanged.connect(self._update_models)
        form.addRow("AI Provider:", self.provider_combo)
        
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True) # Allow custom models
        form.addRow("Model:", self.model_combo)
        
        layout.addLayout(form)
        
        # --- Credentials / Endpoint ---
        self.stack = QStackedWidget()
        
        # Page 1: API Key (Cloud)
        self.page_cloud = QWidget()
        cloud_layout = QFormLayout(self.page_cloud)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        cloud_layout.addRow("API Key:", self.api_key_edit)
        self.stack.addWidget(self.page_cloud)
        
        # Page 2: Local URL (Ollama/LocalAI)
        self.page_local = QWidget()
        local_layout = QFormLayout(self.page_local)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText("http://localhost:11434")
        local_layout.addRow("Base URL:", self.base_url_edit)
        self.stack.addWidget(self.page_local)
        
        layout.addWidget(self.stack)
        
        # Trigger initial update
        self._update_models(self.provider_combo.currentText())
        
        # --- Buttons ---
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        
        self.btn_ok = QPushButton("Save Configuration")
        self.btn_ok.setStyleSheet("background-color: #6a0dad; color: white; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        
        layout.addLayout(btns)

    def _update_models(self, provider):
        self.model_combo.clear()
        models = self.PROVIDERS.get(provider, [])
        self.model_combo.addItems(models)
        
        # Switch stack based on provider type
        if "Local" in provider or "Compatible" in provider:
            self.stack.setCurrentWidget(self.page_local)
        else:
            self.stack.setCurrentWidget(self.page_cloud)

    def get_config(self):
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        config = {
            "provider": provider,
            "model": model
        }
        
        if self.stack.currentWidget() == self.page_cloud:
            config["api_key"] = self.api_key_edit.text()
            config["base_url"] = None
        else:
            config["api_key"] = "sk-dummy" # Local usually needs a dummy key
            config["base_url"] = self.base_url_edit.text()
            
        return config
