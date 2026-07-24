@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "BOOTSTRAP_PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10 or later is required.
        echo Install Python, then run this file again.
        pause
        exit /b 1
    )
    set "BOOTSTRAP_PYTHON=python"
)

%BOOTSTRAP_PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo Python 3.10 or later is required.
    echo Install a supported Python version, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local UUV Simulator environment...
    %BOOTSTRAP_PYTHON% -m venv ".venv"
    if errorlevel 1 (
        echo The local Python environment could not be created.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "from importlib.metadata import version; expected={'gradio':'6.16.0','matplotlib':'3.10.9','numpy':'2.4.4','pandas':'3.0.2','requests':'2.33.1'}; raise SystemExit(0 if all(version(name)==required for name, required in expected.items()) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Installing the UUV Simulator software packages...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
    if errorlevel 1 (
        echo Required software packages could not be installed.
        echo Check the internet connection and run this file again.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo The local environment uses an unsupported Python version.
    echo Delete the .venv folder, then run this file again.
    pause
    exit /b 1
)

echo Starting UUV Mission Planning and Energy Simulator...
echo The application will open in the default browser.
".venv\Scripts\python.exe" "app.py"

echo The UUV Simulator has stopped.
pause
