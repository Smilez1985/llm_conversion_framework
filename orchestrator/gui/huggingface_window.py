#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - HuggingFace Browser
DIREKTIVE: Goldstandard, PySide6 GUI, Threaded Search.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QComboBox, QMessageBox, QProgressBar, QAbstractItemView
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QBrush

# Import ModelManager via framework structure
# Note: In the actual window we get the manager instance from framework_manager
from orchestrator.Core.model_manager import ModelManager

class SearchWorker(QThread):
    """Background thread for API calls to prevent GUI freezing"""
    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, manager, query, sort, filter_tag):
        super().__init__()
        self.manager = manager
        self.query = query
        self.sort = sort
        self.filter_tag = filter_tag

    def run(self):
        try:
            # Aufruf der neuen search_huggingface_models Methode im ModelManager
            results = self.manager.search_huggingface_models(
                query=self.query,
                limit=50,
                sort=self.sort,
                filter_tag=self.filter_tag
            )
            self.results_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(str(e))

class HuggingFaceWindow(QMainWindow):
    """
    Browser window for Hugging Face Models.
    Allows searching, filtering, and selecting models for download.
    """
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hugging Face Model Browser")
        self.resize(1100, 700)
        
        # Wir nutzen den ModelManager aus dem Framework
        # Falls er dort noch nicht instanziiert ist (lazy loading), erstellen wir einen.
        if hasattr(framework_manager, 'model_manager') and framework_manager.model_manager:
             self.manager = framework_manager.model_manager
        else:
             # Fallback: Neu erstellen
             self.manager = ModelManager(framework_manager)
        
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # --- Top Bar ---
        header = QHBoxLayout()
        
        # Search Input
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search models (e.g. 'llama 3', 'mistral', 'granite')...")
        self.search_bar.returnPressed.connect(self._start_search)
        header.addWidget(self.search_bar, stretch=2)
        
        # Filter Type
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Tasks", "text-generation", "text-to-speech", "feature-extraction", "automatic-speech-recognition"])
        header.addWidget(self.filter_combo)
        
        # Sort Options
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Most Downloaded", "downloads")
        self.sort_combo.addItem("Most Likes", "likes")
        self.sort_combo.addItem("Recently Updated", "lastModified")
        header.addWidget(self.sort_combo)
        
        # Search Button
        self.btn_search = QPushButton("Search")
        self.btn_search.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        self.btn_search.clicked.connect(self._start_search)
        header.addWidget(self.btn_search)
        
        layout.addLayout(header)
        
        # --- Progress Bar (Hidden by default) ---
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate animation
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # --- Results Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Model ID", "Downloads", "Likes", "Task", "Tags"])
        
        # Styling
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch) # ID gets most space
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        layout.addWidget(self.table)
        
        # --- Bottom Action Bar ---
        bottom = QHBoxLayout()
        
        self.status_lbl = QLabel("Ready")
        bottom.addWidget(self.status_lbl)
        
        bottom.addStretch()
        
        self.btn_download = QPushButton("⬇️ Select for Build")
        self.btn_download.setToolTip("Use this model ID for the current build configuration")
        self.btn_download.setStyleSheet("background-color: #2d8a2d; color: white; font-weight: bold; padding: 8px 20px;")
        self.btn_download.clicked.connect(self._select_model)
        bottom.addWidget(self.btn_download)
        
        layout.addLayout(bottom)

    def _start_search(self):
        query = self.search_bar.text().strip()
        
        self.table.setRowCount(0)
        self.progress.setVisible(True)
        self.btn_search.setEnabled(False)
        self.status_lbl.setText("Searching Hugging Face Hub...")
        
        # Filter Logic
        tag = self.filter_combo.currentText()
        if tag == "All Tasks": tag = None
        
        sort_key = self.sort_combo.currentData()
        
        # Threading to keep UI responsive
        self.worker = SearchWorker(self.manager, query, sort_key, tag)
        self.worker.results_ready.connect(self._on_results)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_results(self, results):
        self.progress.setVisible(False)
        self.btn_search.setEnabled(True)
        self.status_lbl.setText(f"Found {len(results)} models.")
        
        self.table.setRowCount(0)
        for model in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # ID
            id_item = QTableWidgetItem(model.model_id)
            id_item.setFont(QFont("Segoe UI", 10, QFont.Bold))
            self.table.setItem(row, 0, id_item)
            
            # Downloads
            down_item = QTableWidgetItem(f"{model.downloads:,}")
            self.table.setItem(row, 1, down_item)
            
            # Likes
            self.table.setItem(row, 2, QTableWidgetItem(f"❤️ {model.likes}"))
            
            # Task
            self.table.setItem(row, 3, QTableWidgetItem(model.pipeline_tag))
            
            # Tags (Highlight quantization tags)
            tags_str = ", ".join([t for t in model.tags if t in ['gguf', 'safetensors', 'onnx'] or 'quant' in t])
            if not tags_str: 
                # Fallback: show first 3 tags if no specific tags found
                tags_str = ", ".join(model.tags[:3])
            
            self.table.setItem(row, 4, QTableWidgetItem(tags_str))

    def _on_error(self, err):
        self.progress.setVisible(False)
        self.btn_search.setEnabled(True)
        self.status_lbl.setText("Error occurred.")
        QMessageBox.critical(self, "API Error", f"Search failed:\n{err}")

    def _select_model(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Selection", "Please select a model from the list.")
            return
            
        model_id = self.table.item(row, 0).text()
        
        # Logic to return the selection to the main window
        reply = QMessageBox.question(
            self, "Select Model", 
            f"Do you want to use '{model_id}'?\n\n"
            "This will insert the Model ID into your Build Configuration.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Attempt to set text in parent window if it exists and has the field
            parent = self.parent()
            if parent and hasattr(parent, "model_name"):
                parent.model_name.setText(model_id)
                parent.log(f"Selected model from HF: {model_id}")
                self.close()
            else:
                # Fallback information if opened standalone
                QMessageBox.information(self, "Selected", f"Model ID '{model_id}' selected.\nPlease copy this to the Model field.")
