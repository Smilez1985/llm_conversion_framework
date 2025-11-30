#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Secrets Manager
DIREKTIVE: Goldstandard, Enterprise Security.

Zweck:
Verwaltet sensible Daten (API-Keys, Tokens) verschlüsselt.
Verhindert, dass Secrets im Klartext in der Config-Datei landen.
"""

import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional

# Wir benötigen 'cryptography' für Fernet (AES)
# Falls nicht installiert, Fallback auf Warnung (sollte in pyproject.toml sein)
try:
    from cryptography.fernet import Fernet
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False

from orchestrator.utils.logging import get_logger

class SecretsManager:
    """
    Verwaltet verschlüsselte Secrets.
    Speichert einen lokalen Master-Key und nutzt diesen für AES-256 Encryption.
    """
    
    def __init__(self, config_dir: Path):
        self.logger = get_logger(__name__)
        self.config_dir = config_dir
        self.secrets_file = config_dir / "secrets.enc"
        self.key_file = config_dir / "master.key"
        self.cipher = None
        
        if not ENCRYPTION_AVAILABLE:
            self.logger.critical("Module 'cryptography' not found. Secrets will NOT be encrypted!")
            self.logger.critical("Please run: pip install cryptography")
        else:
            self._init_crypto()

    def _init_crypto(self):
        """Initialisiert den Crypto-Provider und lädt/erstellt den Key."""
        try:
            if not self.key_file.exists():
                self._generate_key()
            
            # Key laden
            with open(self.key_file, "rb") as f:
                key = f.read()
            
            self.cipher = Fernet(key)
            
        except Exception as e:
            self.logger.error(f"Failed to initialize crypto engine: {e}")
            # Fail-Safe: Cipher bleibt None, Zugriff auf Secrets wird verweigert

    def _generate_key(self):
        """Erstellt einen neuen Master-Key und sichert ihn."""
        self.logger.info("Generating new Master Key for secrets...")
        key = Fernet.generate_key()
        
        # Key speichern
        with open(self.key_file, "wb") as f:
            f.write(key)
        
        # Dateirechte einschränken (Nur Owner darf lesen/schreiben) - Wichtig für Linux
        try:
            if os.name == 'posix':
                os.chmod(self.key_file, 0o600)
        except Exception:
            pass

    def set_secret(self, key: str, value: str) -> bool:
        """Verschlüsselt und speichert ein Secret."""
        if not self.cipher:
            self.logger.error("Encryption unavailable. Cannot save secret.")
            return False
            
        try:
            # 1. Bestehende Secrets laden
            secrets = self._load_store()
            
            # 2. Wert verschlüsseln
            encrypted_val = self.cipher.encrypt(value.encode()).decode()
            
            # 3. Speichern
            secrets[key] = encrypted_val
            self._save_store(secrets)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set secret '{key}': {e}")
            return False

    def get_secret(self, key: str) -> Optional[str]:
        """Lädt und entschlüsselt ein Secret."""
        if not self.cipher:
            return None
            
        try:
            secrets = self._load_store()
            encrypted_val = secrets.get(key)
            
            if not encrypted_val:
                return None
                
            # Entschlüsseln
            decrypted_val = self.cipher.decrypt(encrypted_val.encode()).decode()
            return decrypted_val
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve secret '{key}': {e}")
            return None

    def delete_secret(self, key: str) -> bool:
        """Löscht ein Secret permanent."""
        try:
            secrets = self._load_store()
            if key in secrets:
                del secrets[key]
                self._save_store(secrets)
            return True
        except Exception:
            return False

    def _load_store(self) -> dict:
        """Lädt den verschlüsselten Store von Disk."""
        if not self.secrets_file.exists():
            return {}
        try:
            with open(self.secrets_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_store(self, data: dict):
        """Schreibt den Store auf Disk."""
        with open(self.secrets_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Rechte setzen
        try:
            if os.name == 'posix':
                os.chmod(self.secrets_file, 0o600)
        except Exception:
            pass
