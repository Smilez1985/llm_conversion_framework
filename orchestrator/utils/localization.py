#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Localization Manager
DIREKTIVE: Goldstandard, Internationalisierung (I18n).

Zweck:
Zentrale Verwaltung aller UI-Texte. Ermöglicht Umschaltung zur Laufzeit.
Hält Dictionaries für Deutsch und Englisch vor.
"""

from PySide6.QtCore import QObject, Signal

class LocalizationManager(QObject):
    """
    Verwaltet Übersetzungen und Sprachstatus.
    Singelton-Pattern-Nutzung empfohlen.
    """
    language_changed = Signal(str) # Signalisiert Sprachwechsel an UI-Komponenten

    # Das Wörterbuch
    # Key-Format: "context.element"
    TRANSLATIONS = {
        "en": {
            # General
            "app.title": "LLM Cross-Compiler Framework",
            "btn.cancel": "Cancel",
            "btn.save": "Save",
            "btn.ok": "OK",
            "btn.close": "Close",
            "status.ready": "Ready",
            "status.error": "Error",
            
            # Main Window
            "menu.file": "File",
            "menu.tools": "Tools",
            "menu.community": "Community",
            "menu.language": "Language",
            "menu.exit": "Exit",
            "menu.import_profile": "Import Hardware Profile...",
            "menu.create_module": "Create New Module...",
            "menu.audit": "Audit Docker Image...",
            "menu.open_hub": "Open Community Hub",
            "menu.update": "Check for Updates",
            "tab.build": "Build & Monitor",
            "tab.sources": "Sources & Config",
            "grp.build_config": "Build Configuration",
            "lbl.model": "Model:",
            "lbl.target": "Target:",
            "lbl.task": "Task:",
            "lbl.quant": "Quant:",
            "btn.browse_hf": "Browse HF",
            "chk.gpu": "Use GPU",
            "chk.autobench": "Auto-Benchmark",
            "btn.start": "Start Build",
            "btn.bench": "Bench",
            "grp.progress": "Build Progress",
            
            # Wizard
            "wiz.title": "Module Creation Wizard",
            "wiz.intro.title": "Welcome",
            "wiz.intro.text": "This wizard helps you create a new hardware target definition.\nPlease choose how to proceed.",
            "wiz.grp.ai": "✨ AI Auto-Discovery (Recommended)",
            "wiz.lbl.ai_info": "Upload 'target_hardware_config.txt'. Ditto will analyze it.",
            "wiz.btn.import_std": "⚡ Standard Import",
            "wiz.btn.import_ai": "🤖 AI Auto-Discovery",
            "wiz.btn.config_ai": "⚙️ Configure AI",
            "wiz.page.hardware": "Hardware Info",
            "wiz.page.docker": "Docker Env",
            "wiz.page.flags": "Compiler Flags",
            "wiz.page.summary": "Summary",
            
            # Dialogs
            "dlg.lang.title": "Select Language / Sprache wählen",
            "dlg.lang.info": "Please select your preferred interface language.",
            "dlg.token.title": "Authentication Required",
            "dlg.token.info": "The model is gated. Please enter your Hugging Face Token.",
            
            # Messages
            "msg.success": "Success",
            "msg.failed": "Failed",
            "msg.restart_required": "Restart might be required for some changes."
        },
        "de": {
            # General
            "app.title": "LLM Cross-Compiler Framework",
            "btn.cancel": "Abbrechen",
            "btn.save": "Speichern",
            "btn.ok": "OK",
            "btn.close": "Schließen",
            "status.ready": "Bereit",
            "status.error": "Fehler",
            
            # Main Window
            "menu.file": "Datei",
            "menu.tools": "Werkzeuge",
            "menu.community": "Community",
            "menu.language": "Sprache",
            "menu.exit": "Beenden",
            "menu.import_profile": "Hardware-Profil importieren...",
            "menu.create_module": "Neues Modul erstellen...",
            "menu.audit": "Docker Image Audit...",
            "menu.open_hub": "Community Hub öffnen",
            "menu.update": "Auf Updates prüfen",
            "tab.build": "Bauen & Überwachen",
            "tab.sources": "Quellen & Konfiguration",
            "grp.build_config": "Build Konfiguration",
            "lbl.model": "Modell:",
            "lbl.target": "Ziel (Target):",
            "lbl.task": "Aufgabe:",
            "lbl.quant": "Quantisierung:",
            "btn.browse_hf": "HF Durchsuchen",
            "chk.gpu": "GPU nutzen",
            "chk.autobench": "Auto-Benchmark",
            "btn.start": "Build starten",
            "btn.bench": "Benchmark",
            "grp.progress": "Fortschritt",
            
            # Wizard
            "wiz.title": "Modul-Erstellungs-Assistent",
            "wiz.intro.title": "Willkommen",
            "wiz.intro.text": "Dieser Assistent hilft beim Erstellen eines neuen Hardware-Ziels.\nBitte wählen Sie das Vorgehen.",
            "wiz.grp.ai": "✨ AI Auto-Erkennung (Empfohlen)",
            "wiz.lbl.ai_info": "Laden Sie 'target_hardware_config.txt' hoch. Ditto analysiert sie.",
            "wiz.btn.import_std": "⚡ Standard Import",
            "wiz.btn.import_ai": "🤖 AI Auto-Discovery",
            "wiz.btn.config_ai": "⚙️ AI Konfigurieren",
            "wiz.page.hardware": "Hardware Infos",
            "wiz.page.docker": "Docker Umgebung",
            "wiz.page.flags": "Compiler Flags",
            "wiz.page.summary": "Zusammenfassung",
            
            # Dialogs
            "dlg.lang.title": "Sprache wählen / Select Language",
            "dlg.lang.info": "Bitte wählen Sie Ihre bevorzugte Sprache.",
            "dlg.token.title": "Authentifizierung erforderlich",
            "dlg.token.info": "Das Modell ist geschützt. Bitte Hugging Face Token eingeben.",
            
            # Messages
            "msg.success": "Erfolg",
            "msg.failed": "Fehlgeschlagen",
            "msg.restart_required": "Neustart für einige Änderungen erforderlich."
        }
    }

    def __init__(self, initial_lang="en"):
        super().__init__()
        self.current_lang = initial_lang if initial_lang in self.TRANSLATIONS else "en"

    def set_language(self, lang_code: str):
        """Setzt die Sprache und feuert das Change-Signal."""
        if lang_code in self.TRANSLATIONS:
            self.current_lang = lang_code
            self.language_changed.emit(lang_code)

    def get_text(self, key: str) -> str:
        """Gibt den übersetzten Text für einen Key zurück."""
        # Fallback auf Englisch, falls Key im Deutschen fehlt
        text = self.TRANSLATIONS.get(self.current_lang, {}).get(key)
        if text is None:
            text = self.TRANSLATIONS.get("en", {}).get(key, f"[{key}]")
        return text

# Globale Instanz (wird in main.py initialisiert)
_instance = None

def get_instance(initial_lang="en") -> LocalizationManager:
    global _instance
    if _instance is None:
        _instance = LocalizationManager(initial_lang)
    return _instance

# Helper für einfachen Zugriff (wie Qt's tr())
def tr(key: str) -> str:
    if _instance:
        return _instance.get_text(key)
    return key
