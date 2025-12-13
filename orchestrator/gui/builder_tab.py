#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Builder Tab (v2.3 Enterprise)
DIREKTIVE: Goldstandard GUI Component. No Mocks. Real AI.

Der Haupt-Tab für die Konfiguration und den Start von Builds.
Integriert:
- Hardware-Probing (target_hardware_config.txt)
- AI-Driven Optimization (Via DittoManager -> ask_ditto)
- Sprite-Animationen für visuelles Feedback (Thinking, Reading, Success)
"""

import os
import re
import json
import platform
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QGroupBox, QCheckBox, 
    QMessageBox, QFileDialog, QStackedWidget,
    QTextEdit, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRect
from PySide6.QtGui import QPixmap

# Core Imports
from orchestrator.Core.orchestrator import BuildRequest, WorkflowType, PriorityLevel, OptimizationLevel, ModelFormat

# --- WORKERS ---

class ProbeWorker(QThread):
    """Führt das Hardware-Probe Skript im echten System aus."""
    finished = Signal(bool, str)
    
    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path
        
    def run(self):
        try:
            # Platform specific execution
            if platform.system() == "Windows":
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(self.script_path)]
            else:
                cmd = ["bash", str(self.script_path)]
                
            # Run blocking to ensure file is written
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.finished.emit(True, "Probe execution successful.")
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, f"Probe failed (Exit {e.returncode}):\n{e.stderr}")
        except Exception as e:
            self.finished.emit(False, str(e))

class AIOptimizerWorker(QThread):
    """
    Nutzt den echten DittoManager (DittoCoder), um Build-Flags zu ermitteln.
    KEINE MOCKS.
    """
    finished = Signal(bool, dict, str)
    
    def __init__(self, ditto_manager, model_info, target_info, use_rag):
        super().__init__()
        self.ditto = ditto_manager
        self.model = model_info
        self.target = target_info
        self.use_rag = use_rag
        
    def run(self):
        if not self.ditto:
            self.finished.emit(False, {}, "Ditto Manager not initialized.")
            return

        try:
            # Prompt Engineering für strukturierte Ausgabe
            prompt = (
                f"Act as an Embedded Build Engineer. "
                f"I need the optimal build configuration for Model: '{self.model}' on Hardware Profile: '{self.target}'.\n"
                f"Constraints: High Performance, Low Latency.\n"
                f"Analyze the hardware capabilities (NPU, GPU, RAM) if known.\n\n"
                f"RETURN ONLY A JSON OBJECT with these keys (no markdown, no text):\n"
                f"{{\n"
                f'  "quantization": "Q4_K_M" | "Q5_K_M" | "Q8_0" | "F16",\n'
                f'  "format": "GGUF" | "ONNX" | "TFLITE" | "RKNN",\n'
                f'  "optimization": "BALANCED" | "SPEED" | "SIZE" | "AGGRESSIVE",\n'
                f'  "reasoning": "Short explanation"\n'
                f"}}"
            )
            
            # --- REAL CALL TO DITTO ---
            # Wir nutzen ask_ditto, das RAG und History-Komprimierung intern handhabt.
            response_text = self.ditto.ask_ditto(prompt, [])
            # --------------------------

            # Robustes JSON Parsing (falls das LLM doch Markdown sendet)
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                clean_json = json_match.group(0)
                config = json.loads(clean_json)
                self.finished.emit(True, config, config.get("reasoning", "Optimization done."))
            else:
                self.finished.emit(False, {}, f"Invalid AI Response (No JSON found): {response_text[:100]}...")
            
        except Exception as e:
            self.finished.emit(False, {}, f"AI Error: {str(e)}")

# --- WIDGETS ---

class SpriteAnimationWidget(QLabel):
    """
    Handhabt Sprite-Sheets (Horizontal Strips) für Ditto-Animationen.
    """
    def __init__(self, image_path: Path, frame_count: int, interval: int = 150, parent=None):
        super().__init__(parent)
        self.frame_count = frame_count
        self.interval = interval
        self.current_frame = 0
        
        self.setFixedSize(120, 120)
        self.setAlignment(Qt.AlignCenter)
        
        if image_path.exists():
            self.sprite_sheet = QPixmap(str(image_path))
        else:
            self.setText("IMG MISSING")
            self.sprite_sheet = QPixmap(1,1) # Dummy
            
        self.total_width = self.sprite_sheet.width()
        self.frame_width = self.total_width // frame_count if frame_count > 0 else 1
        self.frame_height = self.sprite_sheet.height()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_frame)
        self._update_frame()

    def start(self):
        if not self.timer.isActive(): self.timer.start(self.interval)

    def stop(self):
        self.timer.stop()

    def _update_frame(self):
        if self.frame_width <= 1: return
        x = self.current_frame * self.frame_width
        frame = self.sprite_sheet.copy(QRect(x, 0, self.frame_width, self.frame_height))
        self.setPixmap(frame.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.current_frame = (self.current_frame + 1) % self.frame_count

class BuilderTab(QWidget):
    def __init__(self, framework_manager, parent=None):
        super().__init__(parent)
        self.framework = framework_manager
        self.assets_dir = Path(framework_manager.info.installation_path) / "assets"
        self._init_ui()
        
    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # --- LEFT COLUMN: CONTROLS ---
        left_col = QVBoxLayout()
        
        # 1. SOURCE
        src_group = QGroupBox("1. Source Model")
        src_layout = QFormLayout()
        
        self.model_input = QComboBox()
        self.model_input.setEditable(True)
        self.model_input.setPlaceholderText("HuggingFace ID or Path")
        # Defaults for quick testing
        self.model_input.addItems(["meta-llama/Llama-3.2-3B-Instruct", "mistralai/Mistral-7B-v0.3"])
        
        browse_btn = QPushButton("📂")
        browse_btn.setFixedWidth(40)
        browse_btn.clicked.connect(self._browse_model)
        
        row_model = QHBoxLayout()
        row_model.addWidget(self.model_input)
        row_model.addWidget(browse_btn)
        
        src_layout.addRow("Model:", row_model)
        src_group.setLayout(src_layout)
        left_col.addWidget(src_group)
        
        # 2. TARGET
        tgt_group = QGroupBox("2. Target Hardware")
        tgt_layout = QVBoxLayout()
        
        self.target_combo = QComboBox()
        self._refresh_targets()
        
        h_layout = QHBoxLayout()
        self.scan_btn = QPushButton("🔍 Auto-Detect (Probe)")
        self.scan_btn.clicked.connect(self._run_probe)
        h_layout.addWidget(QLabel("Profile:"))
        h_layout.addWidget(self.target_combo, 1)
        h_layout.addWidget(self.scan_btn)
        
        tgt_layout.addLayout(h_layout)
        tgt_group.setLayout(tgt_layout)
        left_col.addWidget(tgt_group)
        
        # 3. AI OPTIMIZER
        ai_group = QGroupBox("3. AI Optimization (Ditto)")
        ai_layout = QVBoxLayout()
        
        self.chk_ai = QCheckBox("Enable Ditto AI Optimization")
        self.chk_rag = QCheckBox("Use RAG Knowledge Base")
        self.chk_rag.setEnabled(False)
        self.chk_ai.toggled.connect(self.chk_rag.setEnabled)
        
        self.btn_optimize = QPushButton("✨ Ask Ditto for Config")
        self.btn_optimize.setEnabled(False)
        self.chk_ai.toggled.connect(self.btn_optimize.setEnabled)
        self.btn_optimize.clicked.connect(self._run_ai_optimizer)
        
        ai_layout.addWidget(self.chk_ai)
        ai_layout.addWidget(self.chk_rag)
        ai_layout.addWidget(self.btn_optimize)
        ai_group.setLayout(ai_layout)
        left_col.addWidget(ai_group)
        
        # 4. BUILD CONFIG
        build_group = QGroupBox("4. Build Configuration")
        build_layout = QFormLayout()
        
        self.quant_combo = QComboBox()
        self.quant_combo.addItems(["Q4_K_M", "Q5_K_M", "Q8_0", "F16"])
        
        self.format_combo = QComboBox()
        self.format_combo.addItems(["GGUF", "ONNX", "TFLITE", "RKNN"])
        
        self.opt_combo = QComboBox()
        self.opt_combo.addItems(["BALANCED", "SPEED", "SIZE", "AGGRESSIVE"])
        
        self.chk_gpu = QCheckBox("Use Host GPU for Build Process")
        if platform.system() == "Linux": self.chk_gpu.setChecked(True)
        
        build_layout.addRow("Quantization:", self.quant_combo)
        build_layout.addRow("Format:", self.format_combo)
        build_layout.addRow("Optimization:", self.opt_combo)
        build_layout.addRow("", self.chk_gpu)
        
        build_group.setLayout(build_layout)
        left_col.addWidget(build_group)
        
        # START BUTTON
        self.btn_start = QPushButton("🚀 Start Build Pipeline")
        self.btn_start.setMinimumHeight(50)
        self.btn_start.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; font-size: 14px;")
        self.btn_start.clicked.connect(self._submit_build)
        left_col.addWidget(self.btn_start)
        
        left_col.addStretch()
        main_layout.addLayout(left_col, 2)
        
        # --- RIGHT COLUMN: STATUS & AVATAR ---
        right_col = QVBoxLayout()
        
        # Avatar Stack
        self.avatar_stack = QStackedWidget()
        self.avatar_stack.setFixedSize(120, 120)
        self._init_avatars()
        
        av_container = QWidget()
        av_layout = QHBoxLayout(av_container)
        av_layout.addStretch()
        av_layout.addWidget(self.avatar_stack)
        av_layout.addStretch()
        right_col.addWidget(av_container)
        
        # Log
        right_col.addWidget(QLabel("Builder Log:"))
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("font-family: Consolas; background: #222; color: #0f0;")
        right_col.addWidget(self.log_area)
        
        main_layout.addLayout(right_col, 3)

    def _init_avatars(self):
        states = {
            "default": ("Ditto.png", False, 1),
            "think": ("ditto_think.png", True, 4),
            "read": ("ditto_read.png", True, 6),
            "success": ("ditto_success.png", False, 1),
            "fail": ("ditto_fail.png", False, 1)
        }
        self.avatars = {}
        for state, (fname, is_anim, frames) in states.items():
            path = self.assets_dir / fname
            if is_anim:
                wid = SpriteAnimationWidget(path, frames)
            else:
                wid = QLabel()
                if path.exists():
                    wid.setPixmap(QPixmap(str(path)).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    wid.setText(state)
                wid.setAlignment(Qt.AlignCenter)
            self.avatar_stack.addWidget(wid)
            self.avatars[state] = wid
        self.avatar_stack.setCurrentWidget(self.avatars["default"])

    def _set_state(self, state):
        if state in self.avatars:
            curr = self.avatar_stack.currentWidget()
            if isinstance(curr, SpriteAnimationWidget): curr.stop()
            
            new_wid = self.avatars[state]
            self.avatar_stack.setCurrentWidget(new_wid)
            if isinstance(new_wid, SpriteAnimationWidget): new_wid.start()

    def _log(self, msg):
        self.log_area.append(f"> {msg}")

    # --- LOGIC ---

    def _refresh_targets(self):
        self.target_combo.clear()
        tm = self.framework.get_component("target_manager")
        if tm:
            for t in tm.list_targets():
                self.target_combo.addItem(f"{t.get('name')} ({t.get('architecture')})", t.get('id'))

    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Model", "", "Models (*.bin *.gguf *.safetensors);;All Files (*)")
        if path: self.model_input.setCurrentText(path)

    def _run_probe(self):
        self._set_state("read")
        self._log("Starting Hardware Probe...")
        self.scan_btn.setEnabled(False)
        
        script = Path(self.framework.info.installation_path) / "scripts" / ("hardware_probe.ps1" if platform.system() == "Windows" else "hardware_probe.sh")
        
        self.probe_worker = ProbeWorker(script)
        self.probe_worker.finished.connect(self._on_probe_finished)
        self.probe_worker.start()

    def _on_probe_finished(self, success, msg):
        self.scan_btn.setEnabled(True)
        if success:
            self._log("Probe finished. Reading config...")
            self._load_probe_config()
        else:
            self._set_state("fail")
            self._log(f"Probe Error: {msg}")

    def _load_probe_config(self):
        config = Path("target_hardware_config.txt")
        if not config.exists():
            self._set_state("fail")
            self._log("Error: target_hardware_config.txt not found.")
            return
            
        tm = self.framework.get_component("target_manager")
        if tm:
            data = tm.import_hardware_profile(config)
            match = tm.find_matching_target(data)
            
            self._log(f"Detected Hardware: {data.get('CPU_MODEL', 'Unknown')}")
            
            if match:
                idx = self.target_combo.findData(match)
                if idx >= 0: 
                    self.target_combo.setCurrentIndex(idx)
                    self._set_state("success")
                    self._log(f"✅ Auto-Selected Profile: {match}")
                else:
                    self._log(f"⚠️ Matched ID {match} but not in list.")
            else:
                self._set_state("default")
                self._log("No matching profile found in database.")

    def _run_ai_optimizer(self):
        ditto = self.framework.get_component("ditto_manager")
        if not ditto:
            QMessageBox.critical(self, "Error", "Ditto Manager not loaded.")
            return
            
        self._set_state("think")
        self._log("Asking Ditto for optimal settings...")
        self.btn_optimize.setEnabled(False)
        
        self.ai_worker = AIOptimizerWorker(
            ditto, 
            self.model_input.currentText(),
            self.target_combo.currentText(),
            self.chk_rag.isChecked()
        )
        self.ai_worker.finished.connect(self._on_ai_finished)
        self.ai_worker.start()

    def _on_ai_finished(self, success, config, msg):
        self.btn_optimize.setEnabled(True)
        if success:
            self._set_state("success")
            self._log(f"Ditto Recommendation:\n{msg}")
            
            # Apply Config
            if "quantization" in config:
                idx = self.quant_combo.findText(config["quantization"])
                if idx >= 0: self.quant_combo.setCurrentIndex(idx)
            if "format" in config:
                idx = self.format_combo.findText(config["format"])
                if idx >= 0: self.format_combo.setCurrentIndex(idx)
            if "optimization" in config:
                idx = self.opt_combo.findText(config["optimization"])
                if idx >= 0: self.opt_combo.setCurrentIndex(idx)
        else:
            self._set_state("fail")
            self._log(f"AI Failed: {msg}")

    def _submit_build(self):
        # Fire & Forget submission logic
        req = BuildRequest(
            request_id="",
            workflow_type=WorkflowType.SIMPLE_CONVERSION,
            priority=PriorityLevel.NORMAL,
            models=[self.model_input.currentText()],
            targets=[self.target_combo.currentData()],
            target_formats=[ModelFormat[self.format_combo.currentText()]],
            optimization_level=OptimizationLevel[self.opt_combo.currentText()],
            quantization_options=[self.quant_combo.currentText()],
            parallel_builds=True,
            output_base_dir=self.framework.config.output_dir,
            description="Builder Tab Job",
            use_gpu=self.chk_gpu.isChecked()
        )
        
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            rid = loop.run_until_complete(self.framework.orchestrator.submit_build_request(req))
            loop.close()
            self._set_state("success")
            self._log(f"Job Submitted! ID: {rid}")
            QMessageBox.information(self, "Success", f"Job {rid} started.")
        except Exception as e:
            self._set_state("fail")
            self._log(f"Submission Error: {e}")
