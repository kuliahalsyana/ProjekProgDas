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

:: 1. Jika .venv sudah terpasang dan berfungsi, langsung jalankan server
if exist "%~dp0.venv\Scripts\python.exe" goto START_SERVER

echo [!] Virtual environment (.venv) belum ada pada folder ini.
echo [*] Memulai proses pendeteksian Python ^& konfigurasi otomatis...
echo.

:CHECK_PYTHON
set "PY_MODE="
set "PY_EXE="

:: 1. Uji apakah perintah 'python' aktif dan BUKAN alias palsu Microsoft Store
for /f "delims=" %%I in ('where python.exe 2^>nul') do (
    echo %%I | findstr /i /v "WindowsApps" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        "%%I" -c "import sys" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set "PY_EXE=%%I"
            goto CREATE_VENV
        )
    )
)

:: 2. Uji apakah Python Launcher 'py' terpasang
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

:: Jika Python belum ada sama sekali di komputer:
echo ===================================================================
echo [!] PERINGATAN: Python belum terinstal pada komputer ini!
echo -------------------------------------------------------------------
echo Sistem mendeteksi bahwa komputer ini belum memiliki Python atau
echo hanya memiliki pintasan Microsoft Store yang belum aktif.
echo.
echo Sistem dapat mengunduh dan memasang Python 3.11 secara OTOMATIS
echo langsung dari situs resmi python.org tanpa perlu konfigurasi rumit.
echo ===================================================================
echo.
set /p "AUTO_INSTALL=Apakah Anda ingin mengunduh & menginstal Python otomatis sekarang? (Y/T): "
if /i "!AUTO_INSTALL!"=="T" goto MANUAL_INSTRUCTIONS

echo.
echo [*] Memulai pengunduhan Python 3.11 resmi dari python.org...
echo     File installer: ~25 MB. Mohon tunggu beberapa saat...
set "PY_SETUP=%TEMP%\python_311_installer.exe"

:: Coba unduh via curl (bawaan Windows 10/11)
curl.exe -L -o "!PY_SETUP!" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" >nul 2>&1
if not exist "!PY_SETUP!" (
    :: Jika curl gagal, coba unduh via PowerShell bawaan Windows
    echo [*] Mencoba pengunduhan via PowerShell...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '$env:TEMP\python_311_installer.exe')" >nul 2>&1
)

if exist "!PY_SETUP!" (
    echo [*] Pengunduhan berhasil. Memasang Python 3.11 ke sistem...
    echo     (Pemasangan berjalan di latar belakang, mohon tunggu sekitar 1 menit)
    "!PY_SETUP!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_test=0
    del "!PY_SETUP!" >nul 2>&1
    
    timeout /t 6 >nul
    
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" (
            set "PY_EXE=%%D\python.exe"
            echo [*] Python 3.11 berhasil terpasang di: "!PY_EXE!"
            goto CREATE_VENV
        )
    )
) else (
    echo [ERROR] Gagal mengunduh installer Python otomatis.
)

:MANUAL_INSTRUCTIONS
echo.
echo ===================================================================
echo CARA INSTALASI MANUAL PYTHON (Sangat Mudah):
echo -------------------------------------------------------------------
echo 1. Buka browser: https://www.python.org/downloads/
echo 2. Unduh dan jalankan installer Python (versi 3.10 atau 3.11).
echo 3. PENTING: Pada jendela pertama instalasi, WAJIB CENTANG kotak bawah:
echo       [X] "Add python.exe to PATH"
echo 4. Klik "Install Now" hingga selesai.
echo 5. Setelah selesai, klik ganda kembali file run_app.bat ini.
echo ===================================================================
echo.
pause
exit /b 1

:CREATE_VENV
echo.
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
echo       Harap tunggu hingga proses download selesai...Ukuran File Sekitar 500MB
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
echo Pastikan Python telah terinstal dengan benar dan opsi "Add to PATH" dicentang.
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
