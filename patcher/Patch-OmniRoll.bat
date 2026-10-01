@echo off
rem Double-click to patch. Pass -AllowSessionAttempt or -Restore to forward them to the PowerShell script.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Patch-OmniRoll.ps1" %*
pause
