@echo off
cd /d "%~dp0"
title VoltSolar-Sim Pro Enterprise (Web Server HTML5)

echo ===================================================================
echo   VoltSolar-Sim Pro Enterprise: Simulator JTR ^& PLTS Atap On-Grid
echo   Web Dashboard Interaktif HTML5 / JavaScript + Flask REST API
echo   Projek Praktikum Pemrograman Dasar / Teknologi Rekayasa Elektro
echo ===================================================================
echo.

if exist "%~dp0.venv\Scripts\python.exe" goto START_SERVER

echo [!] Virtual environment (.venv) belum ada pada folder ini.
echo [*] Memulai proses instalasi ^& download library otomatis...
echo.

where python >nul 2>&1
if %ERRORLEVEL% equ 0 goto USE_PYTHON

where py >nul 2>&1
if %ERRORLEVEL% equ 0 goto USE_PY

echo ===================================================================
echo [ERROR] Python tidak terdeteksi pada komputer ini!
echo Silakan unduh dan instal Python dari: https://www.python.org/downloads/
echo PENTING: Saat instalasi, centang pilihan "Add python.exe to PATH".
echo ===================================================================
echo.
pause
exit /b 1

:USE_PYTHON
echo [1/3] Membuat virtual environment (.venv)...
python -m venv "%~dp0.venv"
goto INSTALL_REQUIREMENTS

:USE_PY
echo [1/3] Membuat virtual environment (.venv)...
py -3 -m venv "%~dp0.venv"
goto INSTALL_REQUIREMENTS

:INSTALL_REQUIREMENTS
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] Gagal membuat virtual environment.
    pause
    exit /b 1
)

echo.
echo [2/3] Mengunduh dan memasang library dari requirements.txt...
echo       (Hanya berlangsung sekali saat pertama kali diinstal)
echo       Harap tunggu hingga proses selesai...
echo.

"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Terjadi kesalahan saat mengunduh library. Pastikan internet aktif.
    pause
    exit /b 1
)

echo.
echo [*] Instalasi seluruh library selesai dengan sukses!
echo.

:START_SERVER
echo [3/3] Memulai Web Server HTML5 ^& Flask REST API...
echo -------------------------------------------------------------------
echo   Aplikasi Web berjalan pada: http://localhost:5000
echo   Browser Anda akan otomatis terbuka ke tampilan dashboard.
echo   JANGAN tutup jendela terminal ini selama menggunakan aplikasi.
echo -------------------------------------------------------------------
echo.

start "" http://localhost:5000
"%~dp0.venv\Scripts\python.exe" "%~dp0server.py"

echo.
echo Server telah berhenti.
pause
