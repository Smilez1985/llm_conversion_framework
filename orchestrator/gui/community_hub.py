#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Hub Window
DIREKTIVE: Goldstandard, PySide6 GUI.
"""

import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QMessageBox, QProgressBar, QDialog, QFileDialog, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

from orchestrator.Core.community_manager import CommunityManager

class CommunityHubWindow(QMainWindow):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Community Module Hub")
        self.resize(1000, 600)
        self.manager = CommunityManager(framework_manager)
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Header
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Suche...")
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search)
        
        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self._load_data)
        top.addWidget(btn_refresh)
        layout.addLayout(top)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Select", "Status", "Name", "Arch", "Description"])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        
        # Actions
        bottom = QHBoxLayout()
        btn_contrib = QPushButton("📤 Upload My Target")
        btn_contrib.clicked.connect(self._contribute)
        bottom.addWidget(btn_contrib)
        
        bottom.addStretch()
        
        btn_install = QPushButton("⬇️ Install Selected")
        btn_install.setStyleSheet("background-color: #2d8a2d; color: white; font-weight: bold;")
        btn_install.clicked.connect(self._install)
        bottom.addWidget(btn_install)
        layout.addLayout(bottom)

    def _load_data(self):
        self.modules = self.manager.scan_modules()
        self.table.setRowCount(0)
        for mod in self.modules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setData(Qt.UserRole, mod.id)
            
            if mod.is_installed:
                chk.setFlags(Qt.NoItemFlags)
                stat = "✅ Installed"
                color = QColor("#4CAF50")
            else:
                stat = "Available"
                color = QColor("#ffffff")
                
            stat_item = QTableWidgetItem(stat)
            stat_item.setForeground(QBrush(color))
            
            self.table.setItem(row, 0, chk)
            self.table.setItem(row, 1, stat_item)
            self.table.setItem(row, 2, QTableWidgetItem(mod.name))
            self.table.setItem(row, 3, QTableWidgetItem(mod.architecture))
            self.table.setItem(row, 4, QTableWidgetItem(mod.description))

    def _filter(self, text):
        for r in range(self.table.rowCount()):
            match = False
            for c in [2, 3, 4]:
                if text.lower() in self.table.item(r, c).text().lower(): match = True
            self.table.setRowHidden(r, not match)

    def _install(self):
        to_install = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.Checked:
                to_install.append(self.table.item(r, 0).data(Qt.UserRole))
        
        if not to_install: return
        
        count = 0
        for mid in to_install:
            try:
                if self.manager.install_module(mid): count += 1
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        
        QMessageBox.showinfo(self, "Fertig", f"{count} Module installiert.")
        self._load_data()

    def _contribute(self):
        path = QFileDialog.getExistingDirectory(self, "Target Ordner wählen", str(self.manager.targets_dir))
        if path:
            try:
                zip_file = self.manager.prepare_contribution(path, "CommunityUser")
                QMessageBox.information(self, "Success", f"Paket erstellt:\n{zip_file}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
