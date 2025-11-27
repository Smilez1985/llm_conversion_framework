#!/bin/bash
# setup_linux.sh - Headless Setup for LLM Framework
# Checks and installs Docker Engine if missing.
# Reference: https://get.docker.com

set -e

echo ">> [Setup] Checking System Requirements..."

# 1. Check Docker Existence
if ! command -v docker &> /dev/null; then
    echo ">> [Setup] Docker not found. Starting auto-installation..."
    
    # Download & Install via Official Script
    echo ">> [Setup] Downloading get-docker.sh..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    
    echo ">> [Setup] Running Installer (requires sudo)..."
    # Wir nutzen sh, das Skript fordert sudo bei Bedarf an
    sh get-docker.sh
    
    rm get-docker.sh
    echo ">> [Setup] Docker installation completed."
    
    # 2. Group Permissions (User Logic)
    echo ">> [Setup] Adding user '$USER' to 'docker' group..."
    sudo usermod -aG docker "$USER"
    
    echo "------------------------------------------------------------------------"
    echo "✅ Setup finished."
    echo "⚠️  CRITICAL: You must log out and log back in for group changes to apply."
    echo "   Alternative for current shell: 'newgrp docker'"
    echo "------------------------------------------------------------------------"
    
    # Versuch, die Gruppe für diesen Lauf zu aktivieren (funktioniert nur in Subshell)
    # newgrp docker
else
    echo "✅ [Setup] Docker is already installed."
fi

# 3. Verify Access
if ! docker info &> /dev/null; then
    echo "⚠️  [Setup] Docker is installed, but you don't have permissions."
    echo "   Trying to fix group membership..."
    sudo usermod -aG docker "$USER"
    echo "   Please run 'newgrp docker' or re-login to fix this."
    # Optional: Fail here if we want strict checking
    # exit 1
fi

# 4. Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "⚠️  [Setup] 'docker compose' plugin not found. Please install docker-compose-plugin."
fi
