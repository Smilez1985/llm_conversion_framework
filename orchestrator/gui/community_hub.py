#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Hub GUI
DIREKTIVE: Goldstandard, PySide6.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, 
    QTableWidgetItem, QHeaderView, QCheckBox, 
    QMessageBox, QProgressBar, QDialog, QFileDialog,
    QAbstractItemView
)
from PySide6.QtCore import Qt, QSize, Signal, Slot
from PySide6.QtGui import QIcon, QColor, QBrush

from orchestrator.Core.community_manager import CommunityManager, CommunityModule

class CommunityHubWindow(QMainWindow):
    """
    Das Hauptfenster für den Community Hub.
    """
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Community Module Hub")
        self.resize(1000, 700)
        
        self.manager = CommunityManager(framework_manager)
        self.modules: list[CommunityModule] = []
        
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # --- Header / Search ---
        header_layout = QHBoxLayout()
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Suche nach Hardware, Architektur oder Name...")
        self.search_bar.textChanged.connect(self._filter_table)
        header_layout.addWidget(self.search_bar)
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self._load_data)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        # --- Module Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Select", "Status", "Name", "Architecture", "Description", "Author"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch) # Desc stretch
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        layout.addWidget(self.table)
        
        # --- Action Bar ---
        action_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("Select All Available")
        self.select_all_btn.clicked.connect(self._select_all_available)
        action_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("Deselect All")
        self.select_none_btn.clicked.connect(self._deselect_all)
        action_layout.addWidget(self.select_none_btn)
        
        action_layout.addStretch()
        
        self.contribute_btn = QPushButton("📤 Contribute My Target")
        self.contribute_btn.setStyleSheet("background-color: #505050; color: white;")
        self.contribute_btn.clicked.connect(self._open_contribute_wizard)
        action_layout.addWidget(self.contribute_btn)
        
        self.install_btn = QPushButton("⬇️ Install Selected")
        self.install_btn.setStyleSheet("background-color: #2d8a2d; color: white; font-weight: bold; padding: 5px 15px;")
        self.install_btn.clicked.connect(self._install_selected)
        action_layout.addWidget(self.install_btn)
        
        layout.addLayout(action_layout)
        
        # --- Status Bar ---
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

    def _load_data(self):
        """Lädt Module neu"""
        self.status_bar.showMessage("Loading community modules...")
        self.modules = self.manager.scan_modules()
        self._populate_table(self.modules)
        self.status_bar.showMessage(f"Loaded {len(self.modules)} modules.")

    def _populate_table(self, modules):
        self.table.setRowCount(0)
        for mod in modules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            if mod.is_installed:
                chk_item.setCheckState(Qt.Unchecked)
                chk_item.setFlags(Qt.NoItemFlags) # Disable interaction if installed
                chk_item.setToolTip("Bereits installiert")
            else:
                chk_item.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, chk_item)
            
            # Status
            status_text = "✅ Installed" if mod.is_installed else "Available"
            status_item = QTableWidgetItem(status_text)
            if mod.is_installed:
                status_item.setForeground(QBrush(QColor("#4CAF50")))
            self.table.setItem(row, 1, status_item)
            
            # Data
            self.table.setItem(row, 2, QTableWidgetItem(mod.name))
            self.table.setItem(row, 3, QTableWidgetItem(mod.architecture))
            self.table.setItem(row, 4, QTableWidgetItem(mod.description))
            self.table.setItem(row, 5, QTableWidgetItem(mod.author))
            
            # Store ID in first item
            chk_item.setData(Qt.UserRole, mod.id)

    def _filter_table(self, text):
        """Filtert die Tabelle basierend auf Suche"""
        text = text.lower()
        for row in range(self.table.rowCount()):
            match = False
            # Suche in Name (Col 2), Arch (Col 3), Desc (Col 4)
            for col in [2, 3, 4]:
                item = self.table.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def _select_all_available(self):
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                item = self.table.item(row, 0)
                if item.flags() & Qt.ItemIsEnabled:
                    item.setCheckState(Qt.Checked)

    def _deselect_all(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.flags() & Qt.ItemIsEnabled:
                item.setCheckState(Qt.Unchecked)

    def _install_selected(self):
        selected_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.checkState() == Qt.Checked:
                selected_ids.append(item.data(Qt.UserRole))
        
        if not selected_ids:
            QMessageBox.information(self, "Info", "Bitte wählen Sie mindestens ein Modul aus.")
            return

        confirm = QMessageBox.question(
            self, "Installieren", 
            f"Möchten Sie {len(selected_ids)} Module installieren?\n\n"
            "Hinweis: Existierende Benutzer-Module werden NICHT überschrieben.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            success_count = 0
            errors = []
            
            progress = QDialog(self)
            progress.setWindowTitle("Installing...")
            progress.setFixedSize(300, 100)
            p_bar = QProgressBar(progress)
            p_bar.setGeometry(20, 20, 260, 20)
            p_bar.setMaximum(len(selected_ids))
            progress.show()
            
            for i, mod_id in enumerate(selected_ids):
                try:
                    if self.manager.install_module(mod_id):
                        success_count += 1
                    else:
                        errors.append(f"{mod_id} (Skipped/Exists)")
                except Exception as e:
                    errors.append(f"{mod_id} ({str(e)})")
                p_bar.setValue(i + 1)
                QApplication.processEvents()
            
            progress.close()
            
            msg = f"Installation abgeschlossen.\n\nErfolgreich: {success_count}"
            if errors:
                msg += f"\nFehler/Übersprungen:\n" + "\n".join(errors)
            
            QMessageBox.information(self, "Result", msg)
            self._load_data() # Refresh table

    def _open_contribute_wizard(self):
        """Öffnet Dialog zum Hochladen eigener Module"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Wähle dein Target Modul Ordner aus", 
            str(self.manager.targets_dir)
        )
        
        if dir_path:
            # Simple author prompt
            author, ok = QLineEdit.getText(self, "Contributor Name", "Bitte gib deinen Namen/Handle für die Credits an:")
            if not ok or not author: return

            try:
                zip_path = self.manager.prepare_contribution(dir_path, author)
                
                QMessageBox.information(
                    self, "Contribution Ready",
                    f"✅ Modul erfolgreich gepackt!\n\n"
                    f"Datei: {zip_path}\n\n"
                    "Nächster Schritt: Erstelle einen Pull Request auf GitHub und lade diese ZIP-Datei hoch.\n"
                    "(Ein Browserfenster zum Repo wird geöffnet)"
                )
                
                import webbrowser
                webbrowser.open("https://github.com/Smilez1985/llm_conversion_framework/pulls")
                
                # Show file in explorer
                import subprocess, os
                if sys.platform == 'win32':
                    subprocess.run(['explorer', '/select,', str(zip_path)])
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Contribution fehlgeschlagen:\n{e}")
