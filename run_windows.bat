@echo off
setlocal
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Follow START_HERE.txt first.
  pause
  exit /b 1
)
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 app:app
