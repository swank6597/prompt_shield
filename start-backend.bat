@echo off
REM start-backend.bat
REM Double-click this file to launch the PromptShield backend API.
REM It calls the PowerShell script which handles venv, deps, and uvicorn.

powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0start-backend.ps1"
pause
