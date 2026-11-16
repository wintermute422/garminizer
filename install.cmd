@echo off
rem Garminizer installer for Windows: double-click this file.
rem It downloads install.ps1 from the Garminizer repository and runs it in PowerShell.
rem Docker Desktop must be installed. Details: docs/installation.md
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/wintermute422/garminizer/main/install.ps1 | iex"
echo.
pause
