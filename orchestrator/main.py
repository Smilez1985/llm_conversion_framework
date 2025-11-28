#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Main Entry Point
DIREKTIVE: Goldstandard, Startup Logic, I18n.
"""

import sys
import os
import yaml
from pathlib import Path
from PySide6.QtWidgets import QApplication, QDialog

# Adjust path to ensure modules are found
current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

from orchestrator.gui.main_window import MainOrchestrator
from orchestrator.gui.dialogs import LanguageSelectionDialog
from orchestrator.utils.localization import get_instance as get_i18n
from orchestrator.Core.config_manager import ConfigManager

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Cross-Compiler")
    
    # Determine App Root
    # If running as script: orchestrator/main.py -> parent is orchestrator -> parent is root
    app_root = Path(__file__).resolve().parent.parent
    
    # 1. Load Config (Lightweight) to check Language
    # We use a temporary ConfigManager instance just for reading the language preference
    config_dir = app_root / "configs"
    cfg_mgr = ConfigManager(config_dir=config_dir)
    cfg_mgr.load_configuration()
    
    language = cfg_mgr.get("language")
    
    # 2. First Run / Language Selection
    if not language:
        # Initialize I18n with default English for the dialog
        get_i18n("en")
        
        dlg = LanguageSelectionDialog()
        if dlg.exec() == QDialog.Accepted:
            language = dlg.selected_lang
            
            # Persist Language Selection
            # Wir schreiben direkt in die User-Config, um die Einstellung zu merken
            try:
                config_file = config_dir / "config.yml"
                data = {}
                
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        data = yaml.safe_load(f) or {}
                
                data["language"] = language
                
                with open(config_file, 'w') as f:
                    yaml.dump(data, f)
                    
            except Exception as e:
                print(f"Warning: Could not save language preference: {e}")
        else:
            # User cancelled
            sys.exit(0)
    
    # 3. Initialize Global Localization
    get_i18n(language)
    
    # 4. Start Main GUI
    window = MainOrchestrator(app_root)
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
