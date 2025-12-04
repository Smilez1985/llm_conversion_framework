#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Dialogs
DIREKTIVE: Goldstandard, GUI-Komponenten, Internationalisierung.

Updates v2.0.0:
- Added HealingDialog for Self-Healing (Error Analysis Presentation).
- Maintained all v1.7 features (Deployment, URL Input, Chat Config).
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QComboBox, QLineEdit, QLabel, QPushButton, QApplication,
    QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QWidget,
    QTextEdit, QMessageBox, QPlainTextEdit, QCheckBox, QSpinBox
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
        
        rag_text = "Enable Local Knowledge Base (RAG) [Experimental]"
        if tr("dlg.ai.enable_rag") != "dlg.ai.enable_rag":
            rag_text = tr("dlg.ai.enable_rag")
            
        self.chk_rag = QCheckBox(rag_text)
        self.chk_rag.setToolTip(
            "Downloads and starts Qdrant Vector DB (~50MB).\n"
            "Enables Ditto to search local documentation instead of guessing."
        )
        rag_layout.addWidget(self.chk_rag)
        
        # --- NEW v2.0.0: Offline Mode & Telemetry ---
        self.chk_offline = QCheckBox("Force Offline Mode (Use Tiny Models)")
        self.chk_offline.setToolTip("Uses local transformers models instead of APIs. Requires download.")
        rag_layout.addWidget(self.chk_offline)
        
        self.chk_telemetry = QCheckBox("Enable Anonymous Error Reporting (GitHub)")
        self.chk_telemetry.setToolTip("Helps us improve the framework by creating Issues on crash.")
        rag_layout.addWidget(self.chk_telemetry)
        
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
            "enable_rag_knowledge": self.chk_rag.isChecked(),
            "offline_mode": self.chk_offline.isChecked(),
            "enable_telemetry": self.chk_telemetry.isChecked()
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
        text = self.editor.toPlainText()
        self.final_data = [s.strip() for s in text.split("---SEPARATOR---") if s.strip()]
        self.accept()

class URLInputDialog(QDialog):
    """Dialog to input Documentation URLs for Deep Ingest (v1.6.0)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deep Ingest - Documentation Source")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Deep Ingest:</b> Learn from external documentation."))
        layout.addWidget(QLabel("Enter URLs to official documentation (PDF or Website). Ditto will crawl, chunk and memorize them."))
        
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("https://docs.rock-chips.com/rk3588_manual\nhttps://wiki.banana-pi.org/...\n/path/to/local/specs.pdf")
        layout.addWidget(self.text_edit)
        
        grp_opts = QGroupBox("Crawler Settings")
        form = QFormLayout(grp_opts)
        
        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(1, 10); self.spin_depth.setValue(2)
        form.addRow("Crawl Depth:", self.spin_depth)
        
        self.spin_pages = QSpinBox()
        self.spin_pages.setRange(1, 500); self.spin_pages.setValue(50)
        form.addRow("Max Pages:", self.spin_pages)
        layout.addWidget(grp_opts)
        
        self.chk_disclaimer = QCheckBox("I confirm that I am authorized to access/crawl these URLs and comply with their ToS/robots.txt.")
        self.chk_disclaimer.setStyleSheet("color: red; font-weight: bold;")
        self.chk_disclaimer.toggled.connect(self._validate)
        layout.addWidget(self.chk_disclaimer)
        
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("btn.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        
        self.btn_start = QPushButton("Start Deep Ingest")
        self.btn_start.setStyleSheet("background-color: #6a0dad; color: white; font-weight: bold;")
        self.btn_start.clicked.connect(self.accept)
        self.btn_start.setEnabled(False)
        btns.addWidget(self.btn_start)
        layout.addLayout(btns)
        
    def _validate(self):
        has_text = bool(self.text_edit.toPlainText().strip())
        is_checked = self.chk_disclaimer.isChecked()
        self.btn_start.setEnabled(has_text and is_checked)
        
    def get_urls(self):
        raw = self.text_edit.toPlainText()
        return [u.strip() for u in raw.split('\n') if u.strip()]
        
    def get_options(self):
        return {"depth": self.spin_depth.value(), "max_pages": self.spin_pages.value()}

class DeploymentDialog(QDialog):
    """
    Dialog to configure SSH deployment to a target device.
    Security: Credentials stay in RAM, never saved to disk.
    """
    def __init__(self, parent=None, default_ip=""):
        super().__init__(parent)
        self.setWindowTitle("Deploy to Target Device")
        self.setMinimumWidth(450)
        self.credentials = {}
        
        self._init_ui(default_ip)
        
    def _init_ui(self, default_ip):
        layout = QVBoxLayout(self)
        
        info = QLabel("<b>Zero-Dependency Deployment</b><br>"
                      "Transfer the Golden Artifact to your edge device via SSH.<br>"
                      "<i>Note: Passwords are never stored on disk.</i>")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        grp = QGroupBox("Connection Details")
        form = QFormLayout(grp)
        
        self.ip_edit = QLineEdit(default_ip)
        self.ip_edit.setPlaceholderText("192.168.1.x")
        form.addRow("Target IP:", self.ip_edit)
        
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("root / pi / rock")
        form.addRow("Username:", self.user_edit)
        
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("******")
        form.addRow("Password:", self.pass_edit)
        
        self.path_edit = QLineEdit("/opt/llm_deploy")
        form.addRow("Remote Path:", self.path_edit)
        
        layout.addWidget(grp)
        
        btns = QHBoxLayout()
        self.btn_cancel = QPushButton(tr("btn.cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        
        self.btn_deploy = QPushButton("Deploy Artifact")
        self.btn_deploy.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.btn_deploy.clicked.connect(self.validate_and_accept)
        btns.addWidget(self.btn_deploy)
        
        layout.addLayout(btns)
        
    def validate_and_accept(self):
        ip = self.ip_edit.text().strip()
        user = self.user_edit.text().strip()
        
        if not ip or not user:
            QMessageBox.warning(self, "Input Error", "IP Address and Username are required.")
            return
            
        self.credentials = {
            "ip": ip,
            "user": user,
            "password": self.pass_edit.text(),
            "path": self.path_edit.text().strip()
        }
        self.accept()
        
    def get_credentials(self):
        return self.credentials

# --- NEW v2.0.0: Healing Dialog ---
class HealingDialog(QDialog):
    """
    'The Doctor's Report'.
    Displays AI-driven diagnosis and proposed fixes for build errors.
    """
    def __init__(self, proposal, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Self-Healing Diagnosis")
        self.setMinimumWidth(500)
        self.proposal = proposal
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header with Icon (Mental image: Doctor/First Aid)
        header = QLabel("🏥 <b>Diagnosis Report</b>")
        header.setStyleSheet("font-size: 16px;")
        layout.addWidget(header)
        
        # Error Summary
        grp_error = QGroupBox("Problem Detected")
        l_err = QVBoxLayout(grp_error)
        l_err.addWidget(QLabel(f"<b>Summary:</b> {self.proposal.error_summary}"))
        l_err.addWidget(QLabel(f"<b>Root Cause:</b> {self.proposal.root_cause}"))
        layout.addWidget(grp_error)
        
        # Fix
        grp_fix = QGroupBox("Proposed Solution")
        l_fix = QVBoxLayout(grp_fix)
        
        target_str = "TARGET DEVICE (SSH)" if self.proposal.is_remote_fix else "HOST CONTAINER"
        l_fix.addWidget(QLabel(f"<b>Context:</b> {target_str}"))
        
        self.txt_command = QTextEdit()
        self.txt_command.setPlainText(self.proposal.fix_command)
        self.txt_command.setReadOnly(True)
        self.txt_command.setMaximumHeight(80)
        l_fix.addWidget(self.txt_command)
        
        layout.addWidget(grp_fix)
        
        # Confidence
        conf_color = "green" if self.proposal.confidence_score > 0.8 else "orange"
        lbl_conf = QLabel(f"Confidence Score: {self.proposal.confidence_score*100:.1f}%")
        lbl_conf.setStyleSheet(f"color: {conf_color}; font-weight: bold;")
        layout.addWidget(lbl_conf)
        
        # Buttons
        btns = QHBoxLayout()
        self.btn_ignore = QPushButton("Ignore")
        self.btn_ignore.clicked.connect(self.reject)
        btns.addWidget(self.btn_ignore)
        
        self.btn_apply = QPushButton("🚑 Apply Fix")
        self.btn_apply.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.btn_apply.clicked.connect(self.accept)
        btns.addWidget(self.btn_apply)
        
        layout.addLayout(btns)
