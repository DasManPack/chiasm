#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-build.txt
rm -rf build dist
pyinstaller --noconfirm --windowed --name Chiasm --icon ../assets/icon.png --add-data "melodex/assets/chiasm-mark.png:melodex/assets" --add-data "melodex/bundled_providers:melodex/bundled_providers" run.py
python tools/set_macos_bundle_version.py dist/Chiasm.app
python check_bundled_provider_payload.py dist/Chiasm.app
python tools/audit_qt_dependencies.py dist/Chiasm.app \
  --json-out dist/Chiasm-qt-audit-before.json \
  --markdown-out dist/Chiasm-qt-audit-before.md
python tools/prune_qt_bundle.py dist/Chiasm.app \
  --json-out dist/Chiasm-qt-prune.json \
  --markdown-out dist/Chiasm-qt-prune.md
python tools/audit_qt_dependencies.py dist/Chiasm.app \
  --json-out dist/Chiasm-qt-audit.json \
  --markdown-out dist/Chiasm-qt-audit.md
if command -v codesign >/dev/null; then
  codesign --force --deep --sign - dist/Chiasm.app
fi
python tools/check_qt_bundle.py dist/Chiasm.app
python tools/audit_runtime_bundle.py dist/Chiasm.app \
  --json-out dist/Chiasm-runtime-audit.json \
  --markdown-out dist/Chiasm-runtime-audit.md
python frozen_child_smoke.py "dist/Chiasm.app/Contents/MacOS/Chiasm"
mkdir -p dist/release
cp -R dist/Chiasm.app dist/release/ 2>/dev/null || true
if command -v hdiutil >/dev/null && [ -d dist/Chiasm.app ]; then
  rm -f dist/Chiasm.dmg
  for attempt in 1 2 3; do
    if hdiutil create -volname Chiasm -srcfolder dist/Chiasm.app -ov -format UDZO dist/Chiasm.dmg; then
      break
    fi
    if [ "$attempt" -eq 3 ]; then
      echo "hdiutil failed after 3 attempts" >&2
      exit 1
    fi
    echo "hdiutil create failed (attempt $attempt); retrying…" >&2
    sleep $((attempt * 3))
  done
fi

if [ -f dist/Chiasm.dmg ]; then
  python tools/report_bundle_size.py dist/Chiasm.app \
    --archive dist/Chiasm.dmg \
    --json-out dist/Chiasm-bundle-size.json \
    --markdown-out dist/Chiasm-bundle-size.md
else
  python tools/report_bundle_size.py dist/Chiasm.app \
    --json-out dist/Chiasm-bundle-size.json \
    --markdown-out dist/Chiasm-bundle-size.md
fi
