@echo off
rem Garminizer installer for Windows: double-click this file.
rem It downloads install.ps1 from the Garminizer repository and runs it in PowerShell.
rem Docker Desktop must be installed. Details: docs/installation.md
rem
rem Download first, then run the file: antivirus software blocks command lines that pipe a
rem download straight into PowerShell, even for harmless scripts.
setlocal
if not defined GARMINIZER_INSTALLER_URL set "GARMINIZER_INSTALLER_URL=https://raw.githubusercontent.com/wintermute422/garminizer/main/install.ps1"
set "GZ_SCRIPT=%TEMP%\garminizer-install.ps1"
curl.exe -fsSL -o "%GZ_SCRIPT%" "%GARMINIZER_INSTALLER_URL%"
if errorlevel 1 (
  echo Could not download the Garminizer installer. Check your internet connection and try again.
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%GZ_SCRIPT%"
  del "%GZ_SCRIPT%" >nul 2>nul
)
echo.
pause
