#!/usr/bin/env python3
"""LLM Cross-Compiler Framework - Windows Installer"""
import os
import sys
import shutil
import subprocess
import time
import threading
import tempfile
import hashlib
import argparse 
from pathlib import Path
import requests 

try: import winreg
except: winreg = None
try: import tkinter as tk; from tkinter import ttk, messagebox; from tkinter.scrolledtext import ScrolledText
except: sys.exit(1)

INSTALL_APP_NAME = "LLM-Builder"
MSVC_REDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
MSVC_REDIST_FILENAME = "vc_redist.x64.exe"

# FIX: Listen statt Sets verwenden, um Type-Errors bei Addition zu vermeiden
IGNORED_NAMES = [".gitignore", ".gitattributes", ".venv", "venv", "env", "__pycache__", "dist", "build", ".spec", "tmp", "temp", ".git"]
IGNORED_EXTENSIONS = [".pyc", ".pyd", ".spec"]

def _is_msvc_installed():
    if not winreg: return False
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", 0, winreg.KEY_READ)
        i, _ = winreg.QueryValueEx(key, "Installed"); winreg.CloseKey(key); return i == 1
    except: return False

def _should_copy(src, dst):
    if not dst.exists(): return True
    return src.stat().st_size != dst.stat().st_size

def _sync(src, dst, cb, cnt):
    dst.mkdir(parents=True, exist_ok=True)
    for i in src.iterdir():
        if i.name in IGNORED_NAMES or i.suffix in IGNORED_EXTENSIONS: continue
        s, d = i, dst / i.name
        if s.is_dir(): _sync(s, d, cb, cnt)
        elif _should_copy(s, d):
            try: shutil.copy2(s, d); cnt[0] += 1
            except Exception as e: cb(f"Err {s.name}: {e}")

def install_app(dst, sc, cb, prog):
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
    dst.mkdir(parents=True, exist_ok=True)
    prog(10, "Syncing Files...")
    _sync(root, dst, cb, [0])
    prog(80, "Updating Launcher...")
    l_src = Path(sys.executable).parent / f"{INSTALL_APP_NAME}.exe" if getattr(sys, 'frozen', False) else root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if not l_src.exists(): l_src = root / "dist" / f"{INSTALL_APP_NAME}.exe"
    if l_src.exists():
        try: shutil.copy2(l_src, dst / f"{INSTALL_APP_NAME}.exe")
        except: pass
    i_src = root / f"{INSTALL_APP_NAME}.ico"
    if i_src.exists(): shutil.copy
