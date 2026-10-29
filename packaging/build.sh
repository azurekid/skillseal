#!/usr/bin/env bash
# Build the standalone skillseal folder (no Python needed to run it) into dist/skillseal/.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m PyInstaller --version >/dev/null 2>&1 || python -m pip install --quiet "pyinstaller>=6.10"
starter="$(python -c 'from pathlib import Path; print(Path("examples/starter").resolve().as_posix())')"
python -m PyInstaller --noconfirm --clean --onedir --console --name skillseal \
  --add-data "$starter:skillseal/resources/starter" \
  --collect-data sigstore --collect-submodules sigstore --collect-submodules model_signing \
  --distpath dist --workpath build/pyinstaller --specpath build/pyinstaller \
  packaging/entry.py
