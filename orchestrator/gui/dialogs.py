#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Dialogs
DIREKTIVE: Goldstandard, GUI-Komponenten, Internationalisierung.

Updates v1.5.0:
- AIConfigurationDialog: Checkbox für 'Local Knowledge Base' (RAG) hinzugefügt.
- Layout-Optimierungen für bessere UX.
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QComboBox, QLineEdit, QLabel, QPushButton, QApplication,
    QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QWidget,
    QTextEdit, QMessageBox, QPlainTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

# Import Localization Helper
try:
    from orchestrator.utils.localization import tr
except ImportError:
    def tr(key): return key

class AddSourceDialog(QDialog):
    """Dialog to add a new source repository to project_sources.yml"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.source.title"))
        self.setMinimumWidth(500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        self.section_edit = QComboBox()
        self.section_edit.addItems(["core", "rockchip_npu", "nvidia_jetson", "hailo_ai", "intel_npu", "models", "custom"])
        self.section_edit.setEditable(True)
        form.addRow(tr("dlg.source.category"), self.section_edit)
        
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., my_special_tool")
        form.addRow(tr("dlg.source.name"), self.name_edit)
        
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/username/repo.git")
        form.addRow(tr("dlg.source.url"), self.url_edit)
        
        layout.addLayout(form)
        
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        btns = QHBoxLayout()
        self.test_btn = QPushButton(tr("dlg.source.btn_test"))
        self.test_btn.clicked.connect(self.test_url)
        btns.addWidget(self.test_btn)
        
        self.save_btn = QPushButton(tr("btn.save"))
        self.save_btn.clicked.connect(self.accept)
        self.save_btn.setEnabled(False)
        btns.addWidget(self.save_btn)
        
        layout.addLayout(btns)
        
    def test_url(self):
        url = self.url_edit.text().strip()
        if not url:
            self.status_label.setText(tr("dlg.source.err_url_empty"))
            self.status_label.setStyleSheet("color: orange")
            return
            
        self.status_label.setText(tr("dlg.source.testing"))
        self.status_label.setStyleSheet("color: black")
        QApplication.processEvents()
        
        try:
            test_url = url[:-4] if url.endswith('.git') else url
            response = requests.head(test_url, timeout=5, allow_redirects=True)
            
            if response.status_code < 400:
                self.status_label.setText(tr("dlg.source.success"))
                self.status_label.setStyleSheet("color: green")
                self.save_btn.setEnabled(True)
            else:
                self.status_label.setText(f"{tr('dlg.source.err_status')}: {response.status_code}")
                self.status_label.setStyleSheet("color: red")
        except Exception as e:
            self.status_label.setText(f"{tr('dlg.source.err_connect')}: {str(e)}")
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
        self.setWindowTitle(tr("dlg.ai.title"))
        self.setMinimumWidth(500)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Provider & Model ---
        grp_model = QGroupBox("Model Selection")
        form = QFormLayout(grp_model)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.PROVIDERS.keys())
        self.provider_combo.currentTextChanged.connect(self._update_models)
        form.addRow(tr("dlg.ai.provider"), self.provider_combo)
        
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow(tr("dlg.ai.model"), self.model_combo)
        layout.addWidget(grp_model)
        
        # --- Authentication ---
        grp_auth = QGroupBox("Authentication")
        auth_layout = QVBoxLayout(grp_auth)
        self.stack = QStackedWidget()
        
        # Page 1: API Key
        self.page_cloud = QWidget()
        cloud_layout = QFormLayout(self.page_cloud)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        cloud_layout.addRow(tr("dlg.ai.api_key"), self.api_key_edit)
        self.stack.addWidget(self.page_cloud)
        
        # Page 2: Local URL
        self.page_local = QWidget()
        local_layout = QFormLayout(self.page_local)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText("http://localhost:11434")
        local_layout.addRow(tr("dlg.ai.base_url"), self.base_url_edit)
        self.stack.addWidget(self.page_local)
        
        auth_layout.addWidget(self.stack)
        layout.addWidget(grp_auth)
        
        # --- RAG / Knowledge Base (NEW v1.5.0) ---
        grp_rag = QGroupBox("Expert Knowledge (RAG)")
        rag_layout = QVBoxLayout(grp_rag)
        
        # Checkbox with explicit text (fallback logic if translation missing)
        rag_text = "Enable Local Knowledge Base (RAG) [Experimental]"
        if tr("dlg.ai.enable_rag") != "dlg.ai.enable_rag":
            rag_text = tr("dlg.ai.enable_rag")
            
        self.chk_rag = QCheckBox(rag_text)
        self.chk_rag.setToolTip(
            "Downloads and starts Qdrant Vector DB (~50MB).\n"
            "Enables Ditto to search local documentation instead of guessing."
        )
        rag_layout.addWidget(self.chk_rag)
        
        layout.addWidget(grp_rag)
        
        self._update_models(self.provider_combo.currentText())
        
        # --- Buttons ---
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("btn.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        
        self.btn_ok = QPushButton(tr("btn.save"))
        self.btn_ok.setStyleSheet("background-color: #6a0dad; color: white; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        btns.addWidget(self.btn_ok)
        
        layout.addLayout(btns)

    def _update_models(self, provider):
        self.model_combo.clear()
        models = self.PROVIDERS.get(provider, [])
        self.model_combo.addItems(models)
        if "Local" in provider or "Compatible" in provider:
            self.stack.setCurrentWidget(self.page_local)
        else:
            self.stack.setCurrentWidget(self.page_cloud)

    def get_config(self):
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        config = {
            "provider": provider, 
            "model": model,
            "enable_rag_knowledge": self.chk_rag.isChecked()
        }
        
        if self.stack.currentWidget() == self.page_cloud:
            config["api_key"] = self.api_key_edit.text()
            config["base_url"] = None
        else:
            config["api_key"] = "sk-dummy"
            config["base_url"] = self.base_url_edit.text()
        return config

class AskTokenDialog(QDialog):
    """Dialog to ask for Hugging Face Token for gated models."""
    
    def __init__(self, model_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dlg.token.title"))
        self.setMinimumWidth(450)
        self.token = None
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel(tr("dlg.token.info").format(model=model_id))
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        # Link Button
        link_btn = QPushButton(tr("dlg.token.get_key"))
        link_btn.setFlat(True)
        link_btn.setStyleSheet("color: #4da6ff; text-align: left; font-weight: bold;")
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://huggingface.co/settings/tokens")))
        layout.addWidget(link_btn)
        
        form = QFormLayout()
        self.token_edit = QTextEdit()
        self.token_edit.setPlaceholderText("Paste your HF_TOKEN here...")
        self.token_edit.setMaximumHeight(60)
        form.addRow(tr("dlg.token.label"), self.token_edit)
        layout.addLayout(form)
        
        btns = QHBoxLayout()
        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.cancel_btn)
        
        self.ok_btn = QPushButton(tr("dlg.token.btn_auth"))
        self.ok_btn.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.ok_btn.clicked.connect(self.save_and_accept)
        btns.addWidget(self.ok_btn)
        
        layout.addLayout(btns)
        
    def save_and_accept(self):
        text = self.token_edit.toPlainText().strip()
        if text:
            self.token = text
            self.accept()
        else:
            self.token_edit.setPlaceholderText(tr("dlg.token.err_empty"))

class LanguageSelectionDialog(QDialog):
    """Startup dialog to select language."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Language / Sprache wählen")
        self.selected_lang = "en"
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Please select your language:\nBitte wählen Sie Ihre Sprache:"))
        
        btn_en = QPushButton("🇺🇸 English")
        btn_en.clicked.connect(lambda: self.select("en"))
        layout.addWidget(btn_en)
        
        btn_de = QPushButton("🇩🇪 Deutsch")
        btn_de.clicked.connect(lambda: self.select("de"))
        layout.addWidget(btn_de)
        
    def select(self, lang):
        self.selected_lang = lang
        self.accept()

class DatasetReviewDialog(QDialog):
    """
    Human-in-the-Loop Dialog.
    Allows the user to review and edit AI-generated calibration data before saving.
    """
    def __init__(self, data_list, domain, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Review Dataset: {domain}")
        self.resize(600, 500)
        self.final_data = []
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel(f"Ditto AI generated {len(data_list)} samples for '{domain}'.\nPlease review and edit if necessary:"))
        
        self.editor = QPlainTextEdit()
        # Join list to text for editing (one item per block)
        # We use a separator for clarity
        self.editor.setPlainText("\n\n---SEPARATOR---\n\n".join(data_list))
        layout.addWidget(self.editor)
        
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("btn.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton(tr("btn.save"))
        self.btn_save.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.btn_save.clicked.connect(self.save_data)
        btns.addWidget(self.btn_save)
        
        layout.addLayout(btns)
        
    def save_data(self):
        # Split back to list
        text = self.editor.toPlainText()
        self.final_data = [s.strip() for s in text.split("---SEPARATOR---") if s.strip()]
        self.accept()
