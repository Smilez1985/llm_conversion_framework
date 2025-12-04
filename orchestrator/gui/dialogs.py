#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Dialogs
DIREKTIVE: Goldstandard, GUI-Komponenten, Internationalisierung.

Updates v2.0.0:
- Enhanced AIConfigurationDialog to support Native/Offline Model management.
- Integrated Model Download Worker for Tiny Models.
- Maintained Deployment, Healing, and URL Input dialogs.
"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QComboBox, QLineEdit, QLabel, QPushButton, QApplication,
    QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QWidget,
    QTextEdit, QMessageBox, QPlainTextEdit, QCheckBox, QSpinBox, QProgressBar
)
from PySide6.QtCore import Qt, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices, QColor

# Import Localization Helper
try:
    from orchestrator.utils.localization import tr
except ImportError:
    def tr(key): return key

# --- WORKER FOR MODEL DOWNLOAD ---
class TinyModelDownloadWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, model_manager, model_key):
        super().__init__()
        self.manager = model_manager
        self.model_key = model_key

    def run(self):
        try:
            path = self.manager.download_tiny_model(self.model_key)
            if path:
                self.finished.emit(path)
            else:
                self.error.emit("Download failed (check logs).")
        except Exception as e:
            self.error.emit(str(e))

# --- DIALOGS ---

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
    """
    Dialog to configure AI Provider and Model for Ditto.
    v2.0.0: Supports Native/Offline Tiny Models Management.
    """
    
    PROVIDERS = {
        "OpenAI": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
        "Anthropic": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        "Google VertexAI": ["gemini-1.5-pro", "gemini-1.0-pro"],
        "Mistral": ["mistral-large-latest", "mistral-medium", "mistral-small"],
        "Ollama (Local)": ["llama3", "mistral", "gemma", "codellama"],
        "LocalAI / OpenAI Compatible": ["local-model"],
        "Native / Offline (Tiny Models)": [] # Populated dynamically
    }

    def __init__(self, parent=None, framework_manager=None):
        super().__init__(parent)
        self.framework = framework_manager
        self.setWindowTitle(tr("dlg.ai.title"))
        self.setMinimumWidth(600)
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
        self.model_combo.currentTextChanged.connect(self._check_offline_status)
        form.addRow(tr("dlg.ai.model"), self.model_combo)
        layout.addWidget(grp_model)
        
        # --- Configuration Stack ---
        grp_auth = QGroupBox("Configuration")
        auth_layout = QVBoxLayout(grp_auth)
        self.stack = QStackedWidget()
        
        # Page 1: Cloud API Key
        self.page_cloud = QWidget()
        cloud_layout = QFormLayout(self.page_cloud)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        cloud_layout.addRow(tr("dlg.ai.api_key"), self.api_key_edit)
        self.stack.addWidget(self.page_cloud)
        
        # Page 2: Local URL (Ollama/LocalAI)
        self.page_local = QWidget()
        local_layout = QFormLayout(self.page_local)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setText("http://localhost:11434")
        local_layout.addRow(tr("dlg.ai.base_url"), self.base_url_edit)
        self.stack.addWidget(self.page_local)
        
        # Page 3: Native Offline (Tiny Models)
        self.page_offline = QWidget()
        offline_layout = QVBoxLayout(self.page_offline)
        
        self.lbl_offline_status = QLabel("Select a model above.")
        offline_layout.addWidget(self.lbl_offline_status)
        
        self.btn_download_model = QPushButton("⬇️ Download Model (Required for Offline)")
        self.btn_download_model.clicked.connect(self.download_selected_tiny_model)
        offline_layout.addWidget(self.btn_download_model)
        
        self.dl_progress = QProgressBar()
        self.dl_progress.setVisible(False)
        self.dl_progress.setRange(0, 0) # Infinite
        offline_layout.addWidget(self.dl_progress)
        
        self.stack.addWidget(self.page_offline)
        
        auth_layout.addWidget(self.stack)
        layout.addWidget(grp_auth)
        
        # --- RAG / Features ---
        grp_rag = QGroupBox("Advanced Features")
        rag_layout = QVBoxLayout(grp_rag)
        
        self.chk_rag = QCheckBox("Enable Local Knowledge Base (RAG)")
        self.chk_rag.setToolTip("Downloads Qdrant (~50MB) for documentation search.")
        rag_layout.addWidget(self.chk_rag)
        
        self.chk_telemetry = QCheckBox("Enable Anonymous Error Reporting")
        self.chk_telemetry.setToolTip("Help us improve by sending crash reports via GitHub Issues.")
        rag_layout.addWidget(self.chk_telemetry)
        
        layout.addWidget(grp_rag)
        
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
        
        # Init
        self._update_models(self.provider_combo.currentText())

    def _update_models(self, provider):
        self.model_combo.clear()
        
        if "Native" in provider:
            # Fetch from ModelManager if available
            if self.framework and hasattr(self.framework, 'model_manager'):
                tiny_models = self.framework.model_manager.get_available_tiny_models()
                self.model_combo.addItems(list(tiny_models.keys()))
            else:
                self.model_combo.addItem("Error: ModelManager not loaded")
            self.stack.setCurrentWidget(self.page_offline)
        
        elif "Local" in provider or "Compatible" in provider:
            models = self.PROVIDERS.get(provider, [])
            self.model_combo.addItems(models)
            self.stack.setCurrentWidget(self.page_local)
            
        else:
            models = self.PROVIDERS.get(provider, [])
            self.model_combo.addItems(models)
            self.stack.setCurrentWidget(self.page_cloud)
            
        self._check_offline_status()

    def _check_offline_status(self):
        """Checks if the selected tiny model is installed."""
        if self.stack.currentWidget() != self.page_offline:
            return
            
        model_key = self.model_combo.currentText()
        if not model_key or not self.framework: return
        
        is_installed = self.framework.model_manager.is_tiny_model_installed(model_key)
        
        if is_installed:
            self.lbl_offline_status.setText(f"✅ {model_key} is ready for offline use.")
            self.lbl_offline_status.setStyleSheet("color: green; font-weight: bold;")
            self.btn_download_model.setEnabled(False)
            self.btn_download_model.setText("Installed")
        else:
            self.lbl_offline_status.setText(f"⚠️ {model_key} not found locally.")
            self.lbl_offline_status.setStyleSheet("color: orange; font-weight: bold;")
            self.btn_download_model.setEnabled(True)
            self.btn_download_model.setText(f"⬇️ Download {model_key}")

    def download_selected_tiny_model(self):
        model_key = self.model_combo.currentText()
        self.btn_download_model.setEnabled(False)
        self.dl_progress.setVisible(True)
        self.lbl_offline_status.setText(f"Downloading {model_key}... please wait.")
        
        self.worker = TinyModelDownloadWorker(self.framework.model_manager, model_key)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.error.connect(self.on_download_error)
        self.worker.start()

    def on_download_finished(self, path):
        self.dl_progress.setVisible(False)
        self._check_offline_status()
        QMessageBox.information(self, "Download Complete", f"Model saved to:\n{path}")

    def on_download_error(self, err):
        self.dl_progress.setVisible(False)
        self.btn_download_model.setEnabled(True)
        self.lbl_offline_status.setText("❌ Download failed.")
        QMessageBox.critical(self, "Error", f"Failed to download model:\n{err}")

    def get_config(self):
        provider = self.provider_combo.currentText()
        model = self.model_combo.currentText()
        
        config = {
            "provider": provider, 
            "model": model,
            "enable_rag_knowledge": self.chk_rag.isChecked(),
            "enable_telemetry": self.chk_telemetry.isChecked(),
            "offline_mode": ("Native" in provider)
        }
        
        if "Native" in provider:
            config["preferred_tiny_model"] = model
            
        if self.stack.currentWidget() == self.page_cloud:
            config["api_key"] = self.api_key_edit.text()
        else:
            config["api_key"] = "sk-dummy" # Dummy for local
            if self.stack.currentWidget() == self.page_local:
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
    """Dialog to configure SSH deployment."""
    def __init__(self, parent=None, default_ip=""):
        super().__init__(parent)
        self.setWindowTitle("Deploy to Target Device")
        self.setMinimumWidth(450)
        self.credentials = {}
        self._init_ui(default_ip)
        
    def _init_ui(self, default_ip):
        layout = QVBoxLayout(self)
        info = QLabel("<b>Zero-Dependency Deployment</b><br>Transfer the Golden Artifact via SSH.<br><i>Note: Passwords are RAM only.</i>")
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
            QMessageBox.warning(self, "Input Error", "IP and Username required.")
            return
        self.credentials = {"ip": ip, "user": user, "password": self.pass_edit.text(), "path": self.path_edit.text().strip()}
        self.accept()
        
    def get_credentials(self): return self.credentials

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
        
        header = QLabel("🏥 <b>Diagnosis Report</b>")
        header.setStyleSheet("font-size: 16px;")
        layout.addWidget(header)
        
        grp_error = QGroupBox("Problem Detected")
        l_err = QVBoxLayout(grp_error)
        l_err.addWidget(QLabel(f"<b>Summary:</b> {self.proposal.error_summary}"))
        l_err.addWidget(QLabel(f"<b>Root Cause:</b> {self.proposal.root_cause}"))
        layout.addWidget(grp_error)
        
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
        
        conf_color = "green" if self.proposal.confidence_score > 0.8 else "orange"
        lbl_conf = QLabel(f"Confidence Score: {self.proposal.confidence_score*100:.1f}%")
        lbl_conf.setStyleSheet(f"color: {conf_color}; font-weight: bold;")
        layout.addWidget(lbl_conf)
        
        btns = QHBoxLayout()
        self.btn_ignore = QPushButton("Ignore")
        self.btn_ignore.clicked.connect(self.reject)
        btns.addWidget(self.btn_ignore)
        
        self.btn_apply = QPushButton("🚑 Apply Fix")
        self.btn_apply.setStyleSheet("background-color: #2ea043; color: white; font-weight: bold;")
        self.btn_apply.clicked.connect(self.accept)
        btns.addWidget(self.btn_apply)
        
        layout.addLayout(btns)
