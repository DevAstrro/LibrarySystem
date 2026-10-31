@echo off
setlocal
echo WARNING: Only use on a trusted school network with administrator approval.
echo Do not expose this application to the public internet.
.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 app:app
