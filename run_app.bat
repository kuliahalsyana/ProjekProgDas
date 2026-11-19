@echo off
setlocal
cd /d "%~dp0"
title VoltSolar-Sim Pro Enterprise (Web Server HTML5)

echo ===================================================================
echo   VoltSolar-Sim Pro Enterprise: Simulator JTR & PLTS Atap On-Grid
echo   Web Dashboard Interaktif HTML5 / JavaScript + Flask REST API
echo   Projek Praktikum Pemrograman Dasar / Teknologi Rekayasa Elektro
echo ===================================================================
echo.
echo [1/3] Memeriksa virtual environment Python...

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment tidak ditemukan di:
    echo         %~dp0.venv\Scripts\python.exe
    echo.
    echo Silakan hubungi Kelompok 1 atau jalankan instalasi ulang.
    echo.
    pause
    exit /b 1
)

echo [2/3] Virtual environment OK!
echo [3/3] Memulai Web Server HTML5 & Flask REST API...
echo.
echo -------------------------------------------------------------------
echo   Aplikasi Web berjalan pada: http://localhost:5000
echo   Browser Anda akan otomatis terbuka ke tampilan HTML5.
echo   JANGAN tutup jendela terminal ini selama menggunakan aplikasi.
echo -------------------------------------------------------------------
echo.

start "" http://localhost:5000

"%~dp0.venv\Scripts\python.exe" "%~dp0server.py"

echo.
echo Server telah berhenti.
pause
