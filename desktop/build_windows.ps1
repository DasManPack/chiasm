$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
py -3.12 -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\pip.exe install -r requirements-build.txt
Remove-Item -Recurse -Force build,dist -ErrorAction SilentlyContinue
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --windowed --name Chiasm --icon ..\assets\icon.ico --add-data "melodex/assets/chiasm-mark.png;melodex/assets" --add-data "melodex/bundled_providers;melodex/bundled_providers" run.py
& .\.venv-build\Scripts\python.exe .\check_bundled_provider_payload.py .\dist\Chiasm
& .\.venv-build\Scripts\python.exe .\tools\check_qt_bundle.py .\dist\Chiasm
& .\.venv-build\Scripts\python.exe .\tools\audit_runtime_bundle.py .\dist\Chiasm --json-out .\dist\Chiasm-runtime-audit.json --markdown-out .\dist\Chiasm-runtime-audit.md
& .\.venv-build\Scripts\python.exe .\frozen_child_smoke.py .\dist\Chiasm\Chiasm.exe
Compress-Archive -Path dist\Chiasm\* -DestinationPath dist\Chiasm-Windows-portable.zip -Force
