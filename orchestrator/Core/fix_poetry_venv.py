#!/usr/bin/env python3
"""
Poetry/VENV Fix Script für LLM Cross-Compiler Framework
DIREKTIVE: Goldstandard, vollständig, professionell geschrieben.

Korrigiert die Poetry/VENV-Konfiguration in builder.py:
- POETRY_VIRTUALENVS_CREATE=false → true
- POETRY_VENV_IN_PROJECT=false → true  
- poetry config virtualenvs.create false → true
- Fügt VENV-Aktivierung in Dockerfile hinzu

Robuste if-not-exist Abfragen und Backup-Erstellung.
"""

import os
import sys
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict
import argparse


class PoetryVenvFixer:
    """
    Korrektur-Tool für Poetry/VENV-Konfiguration in Docker-Builds.
    
    Behebt die fehlerhafte "kein VENV in Docker" Philosophie und
    implementiert die korrekte "VENV auch in Docker" Architektur.
    """
    
    def __init__(self, framework_root: Path = None):
        """
        Initialize the fixer.
        
        Args:
            framework_root: Root directory of the framework (auto-detect if None)
        """
        self.framework_root = framework_root or self._find_framework_root()
        if not self.framework_root:
            raise RuntimeError("Framework root directory not found")
        
        self.builder_py_path = self.framework_root / "orchestrator" / "Core" / "builder.py"
        self.backup_dir = self.framework_root / "backups" / f"poetry_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Fixes to apply
        self.fixes = [
            {
                "name": "ENV POETRY_VIRTUALENVS_CREATE",
                "pattern": r'ENV POETRY_VENV_IN_PROJECT=false',
                "replacement": 'ENV POETRY_VIRTUALENVS_CREATE=true'
            },
            {
                "name": "ENV POETRY_VENV_IN_PROJECT", 
                "pattern": r'ENV POETRY_VIRTUALENVS_CREATE=.*',
                "replacement": 'ENV POETRY_VENV_IN_PROJECT=true'
            },
            {
                "name": "Poetry config virtualenvs.create",
                "pattern": r'poetry config virtualenvs\.create false',
                "replacement": 'poetry config virtualenvs.create true'
            },
            {
                "name": "Poetry install with venv",
                "pattern": r'&& poetry install --no-dev --no-interaction --no-ansi',
                "replacement": '&& poetry install --no-dev --no-interaction --no-ansi \\\n    && echo "VENV created at $(poetry env info --path)"'
            }
        ]
    
    def _find_framework_root(self) -> Path:
        """Find framework root directory by looking for key files"""
        current_path = Path.cwd()
        
        # Look for framework indicators
        indicators = [
            "orchestrator",
            "pyproject.toml",
            "framework.py"
        ]
        
        # Search up the directory tree
        for path in [current_path] + list(current_path.parents):
            if any((path / indicator).exists() for indicator in indicators):
                return path
        
        # Check common locations
        common_locations = [
            Path.home() / "llm-cross-compiler-framework",
            Path("/workspace/llm-framework"),
            Path(".")
        ]
        
        for location in common_locations:
            if location.exists() and any((location / indicator).exists() for indicator in indicators):
                return location
        
        return None
    
    def validate_environment(self) -> bool:
        """
        Validate that the environment is ready for fixes.
        
        Returns:
            bool: True if environment is valid
        """
        print("🔍 Validating environment...")
        
        # Check if framework root exists
        if not self.framework_root.exists():
            print(f"❌ Framework root not found: {self.framework_root}")
            return False
        
        print(f"✅ Framework root found: {self.framework_root}")
        
        # Check if builder.py exists
        if not self.builder_py_path.exists():
            print(f"❌ builder.py not found: {self.builder_py_path}")
            return False
        
        print(f"✅ builder.py found: {self.builder_py_path}")
        
        # Check if builder.py is writable
        if not os.access(self.builder_py_path, os.W_OK):
            print(f"❌ builder.py is not writable: {self.builder_py_path}")
            return False
        
        print("✅ builder.py is writable")
        
        # Check file size (should be substantial)
        file_size = self.builder_py_path.stat().st_size
        if file_size < 10000:  # Less than 10KB seems too small
            print(f"⚠️  builder.py seems unusually small: {file_size} bytes")
            response = input("Continue anyway? (y/N): ")
            if response.lower() != 'y':
                return False
        
        print(f"✅ builder.py size: {file_size} bytes")
        
        return True
    
    def create_backup(self) -> bool:
        """
        Create backup of current builder.py.
        
        Returns:
            bool: True if backup successful
        """
        print("💾 Creating backup...")
        
        try:
            # Create backup directory
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy builder.py to backup
            backup_file = self.backup_dir / "builder.py"
            shutil.copy2(self.builder_py_path, backup_file)
            
            print(f"✅ Backup created: {backup_file}")
            return True
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            return False
    
    def analyze_current_state(self) -> Dict[str, bool]:
        """
        Analyze current state of builder.py to see what needs fixing.
        
        Returns:
            dict: Analysis results
        """
        print("🔍 Analyzing current state...")
        
        with open(self.builder_py_path, 'r') as f:
            content = f.read()
        
        issues = {}
        
        for fix in self.fixes:
            # Check if the issue exists
            if re.search(fix["pattern"], content):
                issues[fix["name"]] = True
                print(f"🔧 Issue found: {fix['name']}")
            else:
                issues[fix["name"]] = False
                print(f"✅ Already correct: {fix['name']}")
        
        return issues
    
    def apply_fixes(self, dry_run: bool = False) -> Tuple[bool, List[str]]:
        """
        Apply all Poetry/VENV fixes to builder.py.
        
        Args:
            dry_run: If True, only show what would be changed
            
        Returns:
            tuple: (success, list of applied fixes)
        """
        print(f"🔧 {'Dry run - showing changes' if dry_run else 'Applying fixes'}...")
        
        with open(self.builder_py_path, 'r') as f:
            content = f.read()
        
        original_content = content
        applied_fixes = []
        
        for fix in self.fixes:
            if re.search(fix["pattern"], content):
                old_content = content
                content = re.sub(fix["pattern"], fix["replacement"], content)
                
                if content != old_content:
                    applied_fixes.append(fix["name"])
                    print(f"✅ Applied fix: {fix['name']}")
                    
                    if dry_run:
                        # Show the change
                        old_lines = old_content.splitlines()
                        new_lines = content.splitlines()
                        for i, (old_line, new_line) in enumerate(zip(old_lines, new_lines)):
                            if old_line != new_line:
                                print(f"  Line {i+1}:")
                                print(f"    - {old_line}")
                                print(f"    + {new_line}")
                                break
        
        # Add VENV activation to modules if not present
        venv_activation = self._generate_venv_activation_fix(content)
        if venv_activation and "VENV activation" not in content:
            content = self._add_venv_activation_instructions(content)
            applied_fixes.append("VENV activation instructions")
            print("✅ Added VENV activation instructions")
        
        if not dry_run and content != original_content:
            try:
                with open(self.builder_py_path, 'w') as f:
                    f.write(content)
                print(f"✅ Changes written to {self.builder_py_path}")
                return True, applied_fixes
            except Exception as e:
                print(f"❌ Failed to write changes: {e}")
                return False, []
        
        return True, applied_fixes
    
    def _generate_venv_activation_fix(self, content: str) -> str:
        """Generate VENV activation instructions for Dockerfile"""
        return '''
# VENV Activation Instructions for 4-Module Pipeline:
# Each module script should start with:
# #!/bin/bash
# source /workspace/.venv/bin/activate
# 
# This ensures all Python commands use the Poetry-managed VENV
# with correct PyTorch wheels and AI framework dependencies.
'''
    
    def _add_venv_activation_instructions(self, content: str) -> str:
        """Add VENV activation instructions to Dockerfile generation"""
        # Find the place to insert VENV activation (after Poetry install)
        insert_point = content.find('"&& poetry install --no-dev --no-interaction --no-ansi"')
        
        if insert_point != -1:
            # Find the end of that line
            line_end = content.find('\n', insert_point)
            if line_end != -1:
                venv_comment = '''
        
        # Add VENV activation for 4-module pipeline
        dockerfile_lines.extend([
            "",
            "# Configure VENV for module execution",
            "RUN echo 'source /workspace/.venv/bin/activate' > /workspace/activate_venv.sh \\\\",
            "    && chmod +x /workspace/activate_venv.sh",
            "",
            "# Ensure modules source VENV",
            "RUN sed -i '2i source /workspace/.venv/bin/activate' /workspace/modules/*.sh",
            ""
        ])
'''
                content = content[:line_end] + venv_comment + content[line_end:]
        
        return content
    
    def verify_fixes(self) -> bool:
        """
        Verify that all fixes were applied correctly.
        
        Returns:
            bool: True if all fixes are in place
        """
        print("🔍 Verifying fixes...")
        
        with open(self.builder_py_path, 'r') as f:
            content = f.read()
        
        all_good = True
        
        # Check for correct VENV configuration
        correct_patterns = [
            r'POETRY_VIRTUALENVS_CREATE=true',
            r'POETRY_VENV_IN_PROJECT=true',
            r'poetry config virtualenvs\.create true'
        ]
        
        for pattern in correct_patterns:
            if not re.search(pattern, content):
                print(f"❌ Missing correct pattern: {pattern}")
                all_good = False
            else:
                print(f"✅ Found correct pattern: {pattern}")
        
        # Check for incorrect patterns (should be gone)
        incorrect_patterns = [
            r'POETRY_VIRTUALENVS_CREATE=false',
            r'POETRY_VENV_IN_PROJECT=false',
            r'poetry config virtualenvs\.create false'
        ]
        
        for pattern in incorrect_patterns:
            if re.search(pattern, content):
                print(f"❌ Still found incorrect pattern: {pattern}")
                all_good = False
        
        if all_good:
            print("✅ All fixes verified successfully!")
        else:
            print("❌ Some fixes need attention")
        
        return all_good
    
    def run_fix(self, dry_run: bool = False, force: bool = False) -> bool:
        """
        Run the complete fix process.
        
        Args:
            dry_run: Show changes without applying
            force: Skip confirmations
            
        Returns:
            bool: True if successful
        """
        print("🚀 Starting Poetry/VENV Fix Process")
        print("=" * 50)
        
        # Step 1: Validate environment
        if not self.validate_environment():
            print("❌ Environment validation failed")
            return False
        
        # Step 2: Analyze current state
        issues = self.analyze_current_state()
        issues_found = sum(issues.values())
        
        if issues_found == 0:
            print("✅ No issues found - builder.py is already correct!")
            return True
        
        print(f"🔧 Found {issues_found} issues to fix")
        
        # Step 3: Confirm with user (unless force)
        if not force and not dry_run:
            print("\nThe following changes will be made:")
            for fix_name, needs_fix in issues.items():
                if needs_fix:
                    print(f"  - Fix {fix_name}")
            
            response = input("\nProceed with fixes? (y/N): ")
            if response.lower() != 'y':
                print("❌ Aborted by user")
                return False
        
        # Step 4: Create backup (unless dry run)
        if not dry_run:
            if not self.create_backup():
                print("❌ Backup failed - aborting")
                return False
        
        # Step 5: Apply fixes
        success, applied_fixes = self.apply_fixes(dry_run=dry_run)
        
        if not success:
            print("❌ Fix application failed")
            return False
        
        if dry_run:
            print(f"🔍 Dry run completed - {len(applied_fixes)} fixes would be applied")
            return True
        
        # Step 6: Verify fixes
        if not self.verify_fixes():
            print("❌ Fix verification failed")
            return False
        
        print("🎉 Poetry/VENV fixes completed successfully!")
        print(f"📁 Backup available at: {self.backup_dir}")
        print(f"🔧 Applied {len(applied_fixes)} fixes")
        
        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Fix Poetry/VENV configuration in LLM Cross-Compiler Framework"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Show what would be changed without applying fixes"
    )
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--framework-root",
        type=Path,
        help="Path to framework root directory (auto-detect if not specified)"
    )
    
    args = parser.parse_args()
    
    try:
        fixer = PoetryVenvFixer(framework_root=args.framework_root)
        success = fixer.run_fix(dry_run=args.dry_run, force=args.force)
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()