#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Benchmark Window
DIREKTIVE: Goldstandard. Resizable, Minimizable, Maximizable.
"""

import os
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QProgressBar, QFileDialog, 
    QGroupBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt, QProcess, QSize
from PySide6.QtGui import QFont, QIcon

class BenchmarkWindow(QMainWindow):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.framework_manager = framework_manager
        self.docker_manager = framework_manager.get_component("docker_client") # Via wrapper holen
        
        self.setWindowTitle("Model Benchmark & Validation")
        self.resize(900, 700)
        
        # WICHTIG: Fenster-Flags für volles Fenstermanagement
        self.setWindowFlags(
            Qt.Window | 
            Qt.WindowMinimizeButtonHint | 
            Qt.WindowMaximizeButtonHint | 
            Qt.WindowCloseButtonHint
        )
        
        self._init_ui()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # --- Settings Area ---
        settings_group = QGroupBox("Benchmark Configuration")
        settings_layout = QVBoxLayout(settings_group)
        
        # Model Selection
        model_layout = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setPlaceholderText("Select .gguf model file from output...")
        btn_browse = QPushButton("Browse Model")
        btn_browse.clicked.connect(self._browse_model)
        
        model_layout.addWidget(QLabel("Model:"))
        model_layout.addWidget(self.model_path_edit)
        model_layout.addWidget(btn_browse)
        settings_layout.addLayout(model_layout)
        
        # Options
        opts_layout = QHBoxLayout()
        self.chk_perf = QCheckBox("Performance (Tokens/Sec)")
        self.chk_perf.setChecked(True)
        self.chk_ppl = QCheckBox("Integrity (Perplexity/Smoke Test)")
        self.chk_ppl.setChecked(True)
        self.chk_report = QCheckBox("Generate Model Card (README.md)")
        self.chk_report.setChecked(True)
        
        opts_layout.addWidget(self.chk_perf)
        opts_layout.addWidget(self.chk_ppl)
        opts_layout.addWidget(self.chk_report)
        settings_layout.addLayout(opts_layout)
        
        layout.addWidget(settings_group)
        
        # --- Output Area ---
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        layout.addWidget(self.output_log)
        
        # --- Progress ---
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        
        # --- Actions ---
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start Benchmark")
        self.btn_start.setStyleSheet("background-color: #2d8a2d; color: white; font-weight: bold; padding: 8px;")
        self.btn_start.clicked.connect(self._start_benchmark)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _browse_model(self):
        # Start im Output Ordner
        start_dir = str(Path(self.framework_manager.info.installation_path) / "output")
        path, _ = QFileDialog.getOpenFileName(self, "Select Model", start_dir, "GGUF Models (*.gguf)")
        if path:
            self.model_path_edit.setText(path)

    def _start_benchmark(self):
        model_abs_path = self.model_path_edit.text()
        if not model_abs_path:
            QMessageBox.warning(self, "Error", "Please select a model first.")
            return
            
        self.btn_start.setEnabled(False)
        self.output_log.clear()
        self.progress.setRange(0, 0) # Indeterminate
        
        # Docker Execution Logic
        # Wir müssen den Pfad in den Container-Pfad mappen
        # Annahme: /output im Host ist /build-cache/output im Container
        
        try:
            # Pfad-Umrechnung (Host -> Container)
            # Dies ist tricky. Wir nutzen relative Pfade vom Framework Root
            root = Path(self.framework_manager.info.installation_path)
            try:
                rel_path = Path(model_abs_path).relative_to(root)
                # Im Container ist root = /build-cache (via Volume Mapping in docker-compose)
                # ABER: Im docker-compose mappen wir ./output:/build-cache/output
                # Wenn die Datei in output liegt:
                if str(rel_path).startswith("output"):
                    container_path = f"/build-cache/{rel_path.as_posix()}"
                else:
                    container_path = f"/build-cache/{rel_path.as_posix()}" # Generic try
            except ValueError:
                # Datei liegt außerhalb? Kopieren oder Error.
                QMessageBox.warning(self, "Path Error", "Model must be inside the framework directory (e.g. output/).")
                self.btn_start.setEnabled(True)
                self.progress.setRange(0, 100)
                return

            self.log(f"Starting benchmark for: {container_path}")
            
            # Trigger Docker Process
            # Wir nutzen QProcess um docker-compose exec aufzurufen
            self.proc = QProcess()
            self.proc.setProcessChannelMode(QProcess.MergedChannels)
            self.proc.readyReadStandardOutput.connect(self._handle_output)
            self.proc.finished.connect(self._on_finished)
            
            # Command construction
            # Nutzt das neue benchmark_module.sh
            # Wir müssen es temporär verfügbar machen oder davon ausgehen dass es im Image ist.
            # Da wir es ins Repo gelegt haben (targets/_template/modules), müssen wir sicherstellen,
            # dass es im Container unter /app/modules/ oder ähnlich liegt.
            # HACK: Wir injecten den Script-Call direkt oder kopieren es.
            # SAUBER: Wir kopieren das Script zur Laufzeit rein.
            
            script_content = f"/app/modules/benchmark_module.sh --model '{container_path}'"
            
            cmd = "docker-compose"
            args = ["exec", "-T", "rockchip-builder", "bash", "-c", script_content]
            
            self.proc.start(cmd, args)
            
        except Exception as e:
            self.log(f"Error starting benchmark: {e}")
            self.btn_start.setEnabled(True)

    def _handle_output(self):
        data = self.proc.readAllStandardOutput().data().decode()
        self.output_log.insertPlainText(data)
        self.output_log.verticalScrollBar().setValue(self.output_log.verticalScrollBar().maximum())

    def _on_finished(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.btn_start.setEnabled(True)
        self.log("\n=== Benchmark Completed ===")

    def log(self, msg):
        self.output_log.append(msg)

from PySide6.QtWidgets import QLineEdit # Fix imports if needed
