#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - GUI Dialogs (v2.0 Enterprise)
DIREKTIVE: Goldstandard UI Components.

Updates:
- Added SecretInputDialog for secure Keyring storage.
- Standardized dialog styling.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, 
    QDialogButtonBox, QMessageBox, QComboBox, 
    QWidget, QFormLayout
)
from PySide6.QtCore import Qt
from orchestrator.utils.localization import get_instance as get_i18n

class LanguageSelectionDialog(QDialog):
    """
    Initial Dialog to select the interface language.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Language Selection / Sprachauswahl")
        self.setModal(True)
        self.selected_lang = "en"
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel("Please select your language:\nBitte wählen Sie Ihre Sprache:")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        self.cb_lang = QComboBox()
        self.cb_lang.addItem("English", "en")
        self.cb_lang.addItem("Deutsch", "de")
        layout.addWidget(self.cb_lang)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def accept(self):
        self.selected_lang = self.cb_lang.currentData()
        super().accept()

class SecretInputDialog(QDialog):
    """
    Secure dialog to input API Keys and secrets.
    Stores directly to SecretsManager (Keyring), NOT config files.
    """
    def __init__(self, framework, secret_key: str, display_name: str, parent=None):
        super().__init__(parent)
        self.framework = framework
        self.secret_key = secret_key
        self.i18n = get_i18n()
        
        self.setWindowTitle(f"Security: {display_name}")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        info_lbl = QLabel(self.i18n.t("secrets.dialog_info", "This value will be encrypted and stored in your OS Keyring."))
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)
        
        form = QFormLayout()
        self.input_field = QLineEdit()
        self.input_field.setEchoMode(QLineEdit.Password)
        self.input_field.setPlaceholderText("sk-...")
        
        # Check if secret exists (visual hint only, never show the secret!)
        if self.framework.secrets_manager:
            exists = self.framework.secrets_manager.get_secret(secret_key)
            if exists:
                self.input_field.setPlaceholderText("******** (Stored)")
        
        form.addRow(display_name + ":", self.input_field)
        layout.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_secret)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def _save_secret(self):
        val = self.input_field.text().strip()
        if not val:
            QMessageBox.warning(self, "Error", "Secret cannot be empty.")
            return
            
        if self.framework.secrets_manager:
            success = self.framework.secrets_manager.set_secret(self.secret_key, val)
            if success:
                QMessageBox.information(self, "Success", "Secret stored securely in Keyring.")
                self.accept()
            else:
                QMessageBox.critical(self, "Error", "Failed to store secret via SecretsManager.")
        else:
            QMessageBox.critical(self, "Error", "SecretsManager is not initialized!")

class BuildConfirmDialog(QDialog):
    """
    Confirmation dialog before starting a build.
    """
    def __init__(self, target_name, model_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirm Build")
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Start conversion for:\nTarget: {target_name}\nModel: {model_name}"))
        
        buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
