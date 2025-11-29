#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Community Hub
DIREKTIVE: Goldstandard, GUI, Internationalisierung.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
    QHeaderView, QMessageBox, QLineEdit
)
from PySide6.QtCore import Qt, QThread, Signal

# Localization Import
try:
    from orchestrator.utils.localization import tr
except ImportError:
    def tr(key): return key

from orchestrator.Core.community_manager import CommunityManager

class CommunityWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def run(self):
        try:
            # Simulated fetch or real logic from manager
            items = self.manager.fetch_community_packages()
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))

class DownloadWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    
    def __init__(self, manager, package_id):
        super().__init__()
        self.manager = manager
        self.pkg_id = package_id
        
    def run(self):
        try:
            path = self.manager.download_package(self.pkg_id)
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))

class CommunityHubWindow(QMainWindow):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.framework_manager = framework_manager
        # Instanziiere Manager für Logik
        self.comm_manager = CommunityManager() 
        
        self.setWindowTitle(tr("menu.open_hub"))
        self.resize(800, 600)
        
        self._init_ui()
        self.all_items = []
        
        # Auto-Load
        self.refresh_list()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Header
        # Fallback strings used if key not yet in dictionary
        intro_text = tr("hub.intro") if tr("hub.intro") != "hub.intro" else "Discover and share hardware targets and models."
        layout.addWidget(QLabel(intro_text))
        
        # Search Bar
        hbox = QHBoxLayout()
        self.search_edit = QLineEdit()
        # Reuse HF search placeholder key or generic
        search_ph = tr("hf.search_placeholder") if tr("hf.search_placeholder") != "hf.search_placeholder" else "Search..."
        self.search_edit.setPlaceholderText(search_ph)
        self.search_edit.textChanged.connect(self.filter_list)
        hbox.addWidget(self.search_edit)
        
        refresh_txt = tr("btn.refresh") if tr("btn.refresh") != "btn.refresh" else "Refresh"
        self.refresh_btn = QPushButton(refresh_txt)
        self.refresh_btn.clicked.connect(self.refresh_list)
        hbox.addWidget(self.refresh_btn)
        layout.addLayout(hbox)
        
        # Table
        self.table = QTableWidget(0, 4)
        headers = ["Name", "Type", "Author", "Actions"]
        # Translate headers if keys exist, else keep English defaults
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        self.status_label = QLabel(tr("status.ready"))
        layout.addWidget(self.status_label)

    def refresh_list(self):
        self.status_label.setText("Loading...")
        self.worker = CommunityWorker(self.comm_manager)
        self.worker.finished.connect(self.on_load_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_load_finished(self, items):
        self.all_items = items
        self.populate_table(items)
        self.status_label.setText(tr("status.ready"))

    def on_error(self, err):
        self.status_label.setText(f"{tr('status.error')}: {err}")
        QMessageBox.warning(self, tr("status.error"), str(err))

    def filter_list(self, text):
        filtered = [i for i in self.all_items if text.lower() in i['name'].lower()]
        self.populate_table(filtered)

    def populate_table(self, items):
        self.table.setRowCount(0)
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            self.table.setItem(row, 0, QTableWidgetItem(item['name']))
            self.table.setItem(row, 1, QTableWidgetItem(item['type']))
            self.table.setItem(row, 2, QTableWidgetItem(item['author']))
            
            btn_txt = tr("btn.download") if tr("btn.download") != "btn.download" else "Download"
            btn = QPushButton(btn_txt)
            # Lambda capture fix for loop variable
            btn.clicked.connect(lambda checked, pid=item['id']: self.download_item(pid))
            self.table.setCellWidget(row, 3, btn)

    def download_item(self, pkg_id):
        self.status_label.setText(f"Downloading {pkg_id}...")
        self.dl_worker = DownloadWorker(self.comm_manager, pkg_id)
        
        success_title = tr("msg.success")
        
        self.dl_worker.finished.connect(lambda p: QMessageBox.information(self, success_title, f"Installed to {p}"))
        self.dl_worker.error.connect(lambda e: QMessageBox.critical(self, tr("status.error"), str(e)))
        self.dl_worker.start()
