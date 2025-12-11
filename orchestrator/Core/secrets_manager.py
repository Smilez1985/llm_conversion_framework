#!/usr/bin/env python3
"""
LLM Cross-Compiler Framework - Enterprise Secrets Manager (v2.0)
DIREKTIVE: Goldstandard Security.
FEATURES:
  - OS-Keyring Integration (Windows Credential Locker / Linux Keyring)
  - PBKDF2 Key Derivation (HMAC-SHA256, 100k Iterations)
  - Audit Logging für Access-Events
  - Keine Speicherung des Master-Keys im Dateisystem!
"""

import os
import json
import base64
import logging
import platform
import getpass
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime

# Security Libs
try:
    import keyring
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

from orchestrator.utils.logging import get_logger

class SecurityError(Exception):
    """Kritischer Sicherheitsfehler"""
    pass

class SecretsManager:
    SERVICE_ID = "llm-conversion-framework"
    KEY_ID = "master-encryption-key"

    def __init__(self, config_dir: Path):
        self.logger = get_logger("SecretsManager")
        self.config_dir = config_dir
        self.secrets_file = config_dir / "secrets.store"
        self.audit_log_file = config_dir / "audit.log"
        self._cipher = None
        self._cache = {}

        if not SECURITY_AVAILABLE:
            raise SecurityError(
                "CRITICAL: 'cryptography' or 'keyring' missing. "
                "Install via: pip install cryptography keyring"
            )

        self._initialize_crypto()

    def _initialize_crypto(self):
        """
        Initialisiert die Krypto-Engine. 
        Versucht Key aus OS-Keyring zu laden oder generiert neuen.
        """
        try:
            # 1. Versuche Key aus dem OS-Keyring zu holen
            stored_key = keyring.get_password(self.SERVICE_ID, self.KEY_ID)

            if stored_key:
                self.logger.info("Master Key loaded from OS Keyring (Secure).")
                key_bytes = base64.urlsafe_b64decode(stored_key.encode())
            else:
                self.logger.warning("No Master Key found in Keyring. Generating new one...")
                # 2. Generiere neuen Key (Fernet kompatibel)
                # Wir nutzen hier PBKDF2 um aus zufälligen Bytes einen robusten Key zu machen
                salt = os.urandom(16)
                password = os.urandom(32) # In einer GUI Version könnte hier User-Input stehen
                
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key_bytes = base64.urlsafe_b64encode(kdf.derive(password))
                
                # Speichere im Keyring
                keyring.set_password(self.SERVICE_ID, self.KEY_ID, key_bytes.decode())
                self.logger.info("New Master Key generated and stored in OS Keyring.")

            self._cipher = Fernet(key_bytes)
            self._load_store()

        except Exception as e:
            self.logger.critical(f"Crypto Initialization Failed: {e}")
            raise SecurityError(f"Keystore Access Failed: {e}")

    def _audit_log(self, action: str, key_name: str, status: str):
        """Schreibt Audit-Trail für Compliance."""
        timestamp = datetime.now().isoformat()
        user = getpass.getuser()
        entry = f"[{timestamp}] USER={user} ACTION={action} KEY={key_name} STATUS={status}\n"
        
        try:
            with open(self.audit_log_file, "a") as f:
                f.write(entry)
        except Exception:
            pass # Audit Logging sollte App nicht crashen lassen, aber Warnung wert sein

    def set_secret(self, key: str, value: str) -> bool:
        """Verschlüsselt und speichert ein Secret."""
        if not self._cipher:
            return False
        
        try:
            encrypted_val = self._cipher.encrypt(value.encode()).decode()
            self._cache[key] = encrypted_val
            self._save_store()
            self._audit_log("WRITE", key, "SUCCESS")
            return True
        except Exception as e:
            self.logger.error(f"Encryption failed for {key}: {e}")
            self._audit_log("WRITE", key, f"FAILED: {e}")
            return False

    def get_secret(self, key: str) -> Optional[str]:
        """Entschlüsselt und liest ein Secret."""
        if not self._cipher or key not in self._cache:
            return None
        
        try:
            encrypted_val = self._cache[key]
            decrypted_val = self._cipher.decrypt(encrypted_val.encode()).decode()
            self._audit_log("READ", key, "SUCCESS")
            return decrypted_val
        except Exception as e:
            self.logger.error(f"Decryption failed for {key}: {e}")
            self._audit_log("READ", key, "DECRYPTION_FAIL - POSSIBLE TAMPERING")
            return None

    def list_secrets(self) -> list[str]:
        """Listet verfügbare Keys (nicht Values)."""
        return list(self._cache.keys())

    def _save_store(self):
        """Persistiert den verschlüsselten Store (JSON Blob)."""
        # Wir speichern nur die verschlüsselten Values auf Disk.
        # Ohne Keyring-Zugriff ist diese Datei wertlos.
        try:
            with open(self.secrets_file, "w") as f:
                json.dump(self._cache, f, indent=2)
            
            # Setze File Permissions (nur für den User lesbar)
            if platform.system() != "Windows":
                os.chmod(self.secrets_file, 0o600)
            
        except Exception as e:
            self.logger.error(f"Failed to save secrets store: {e}")

    def _load_store(self):
        """Lädt den Store."""
        if not self.secrets_file.exists():
            return
        
        try:
            with open(self.secrets_file, "r") as f:
                self._cache = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load secrets store: {e}")
            # Bei korruptem Store Backup erstellen? 
            # Hier vereinfacht: Cache bleibt leer.

if __name__ == "__main__":
    # Smoke Test
    logging.basicConfig(level=logging.INFO)
    tmp_dir = Path("temp_secrets_test")
    tmp_dir.mkdir(exist_ok=True)
    
    sm = SecretsManager(tmp_dir)
    print("Saving Secret...")
    sm.set_secret("api_token", "super-secret-value-123")
    
    print("Reading Secret...")
    val = sm.get_secret("api_token")
    print(f"Decrypted: {val}")
    
    if val == "super-secret-value-123":
        print("✅ TEST PASSED")
    else:
        print("❌ TEST FAILED")
