$ErrorActionPreference = "Stop"

python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\pyinstaller --onefile --windowed --name ProfitMap --paths src --hidden-import PySide6.QtSvg --hidden-import pyqtgraph main.py

Write-Host "ProfitMap.exe created in dist\"
