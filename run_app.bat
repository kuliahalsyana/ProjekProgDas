@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title VoltSolar-Sim Pro Enterprise (Web Server HTML5)

echo ===================================================================
echo   VoltSolar-Sim Pro Enterprise: Simulator JTR ^& PLTS Atap On-Grid
echo   Web Dashboard Interaktif HTML5 / JavaScript + Flask REST API
echo   Projek Praktikum Pemrograman Dasar / Teknologi Rekayasa Elektro
echo ===================================================================
echo.

:: 1. Jika .venv sudah terpasang, langsung jalankan server
if exist "%~dp0.venv\Scripts\python.exe" goto START_SERVER

echo [!] Virtual environment (.venv) belum ada pada folder ini.
echo [*] Memulai proses pendeteksian Python ^& instalasi otomatis...
echo.

:CHECK_PYTHON
set "PY_MODE="
set "PY_EXE="

:: Uji apakah perintah 'python' aktif dan BUKAN alias palsu Microsoft Store
python -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY_MODE=python"
    goto CREATE_VENV
)

:: Uji apakah Python Launcher 'py' terpasang
py -3 -c "import sys" >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set "PY_MODE=py"
    goto CREATE_VENV
)

:: Pindai lokasi instalasi Python umum pada sistem Windows
for /d %%D in (
    "%LOCALAPPDATA%\Programs\Python\Python3*"
    "C:\Program Files\Python3*"
    "C:\Program Files (x86)\Python3*"
    "C:\Python3*"
    "C:\Program Files\KiCad\*"
    "%USERPROFILE%\miniconda3"
    "%USERPROFILE%\anaconda3"
    "C:\ProgramData\miniconda3"
    "C:\ProgramData\anaconda3"
) do (
    if not defined PY_EXE (
        if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import sys" >nul 2>&1
            if !ERRORLEVEL! equ 0 set "PY_EXE=%%D\python.exe"
        )
        if exist "%%D\bin\python.exe" (
            "%%D\bin\python.exe" -c "import sys" >nul 2>&1
            if !ERRORLEVEL! equ 0 set "PY_EXE=%%D\bin\python.exe"
        )
    )
)

if defined PY_EXE goto CREATE_VENV

:: 4. Jika Python belum terdeteksi sama sekali, coba gunakan winget bila ada
where winget >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo [!] Python belum terdeteksi pada sistem Windows Anda.
    echo [*] Fitur Windows Package Manager (winget) tersedia pada PC ini.
    echo.
    set /p "INSTALL_CHOICE=Apakah Anda ingin menginstal Python 3.11 secara otomatis via winget? (Y/T): "
    if /i "!INSTALL_CHOICE!"=="Y" (
        echo.
        echo [*] Mengunduh dan menginstal Python 3.11 dari python.org...
        winget install Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
        echo [*] Menunggu penyelesaian instalasi...
        timeout /t 6 >nul
        goto CHECK_PYTHON
    )
)

echo ===================================================================
echo [ERROR] Python belum terinstal atau tidak terdeteksi pada PC ini!
echo -------------------------------------------------------------------
echo Penyebab yang sering terjadi di Windows 10/11:
echo 1. Windows mendeteksi pintasan Microsoft Store (WindowsApps alias).
echo 2. Python belum diinstal atau opsi "Add python.exe to PATH" lupa dicentang.
echo.
echo CARA MENGATASI (PILIH SALAH SATU):
echo.
echo Opsi 1 (Unduh Installer Resmi - Sangat Direkomendasikan):
echo   1. Buka browser: https://www.python.org/downloads/
echo   2. Unduh dan jalankan installer Python (versi 3.10 atau 3.11).
echo   3. PENTING: Di awal jendela instalasi, WAJIB CENTANG kotak:
echo      [X] "Add python.exe to PATH"
echo   4. Klik "Install Now", lalu klik ganda kembali run_app.bat ini.
echo.
echo Opsi 2 (Matikan Pintasan Palsu Microsoft Store):
echo   1. Buka Settings Windows (Tekan Win + I).
echo   2. Masuk ke: Apps ^> Advanced app settings ^> App execution aliases.
echo   3. Matikan (Off) tombol switch untuk "App Installer (python.exe)".
echo ===================================================================
echo.
pause
exit /b 1

:CREATE_VENV
echo [1/3] Membuat virtual environment (.venv)...
if defined PY_EXE goto MAKE_VENV_EXE
if "!PY_MODE!"=="py" goto MAKE_VENV_PY
if "!PY_MODE!"=="python" goto MAKE_VENV_PYTHON
goto VENV_FAIL

:MAKE_VENV_EXE
echo       Interpreter terdeteksi: "!PY_EXE!"
"!PY_EXE!" -m venv "%~dp0.venv"
goto CHECK_VENV_STATUS

:MAKE_VENV_PY
echo       Interpreter terdeteksi: py -3
py -3 -m venv "%~dp0.venv"
goto CHECK_VENV_STATUS

:MAKE_VENV_PYTHON
echo       Interpreter terdeteksi: python
python -m venv "%~dp0.venv"
goto CHECK_VENV_STATUS

:CHECK_VENV_STATUS
if not exist "%~dp0.venv\Scripts\python.exe" goto VENV_FAIL

echo.
echo [2/3] Mengunduh dan memasang library otomatis dari requirements.txt...
echo       (Proses ini hanya berlangsung sekali saat pertama kali diinstal)
echo       Harap tunggu hingga proses download selesai... Besar file sekitar 500MB
echo.

"%~dp0.venv\Scripts\python.exe" -m pip install --upgrade pip
"%~dp0.venv\Scripts\pip.exe" install -r "%~dp0requirements.txt"

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Terjadi kesalahan saat mengunduh library. Pastikan koneksi internet aktif.
    pause
    exit /b 1
)

echo.
echo [*] Seluruh library sistem tenaga listrik berhasil dipasang!
echo.
goto START_SERVER

:VENV_FAIL
echo.
echo [ERROR] Gagal membuat virtual environment (.venv).
echo Silakan buka CMD dan jalankan: python -m venv .venv
pause
exit /b 1

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