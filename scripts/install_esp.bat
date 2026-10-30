@echo off
REM language: batch, file: install_esp.bat
REM Manual ESP install (for testing without exe).
setlocal

set REPO_ROOT=%~dp0..

if not exist "%REPO_ROOT%\bootx64.efi" (
    echo bootx64.efi not found. Build first.
    exit /b 1
)

REM Unmount S: if already mounted
mountvol S: /d >nul 2>&1

mountvol S: /s
if not exist S:\ (
    echo Failed to mount ESP. Run as admin.
    exit /b 1
)

if not exist S:\EFI\QackLocker mkdir S:\EFI\QackLocker

copy /Y "%REPO_ROOT%\bootx64.efi" S:\EFI\QackLocker\bootx64.efi
copy /Y "%REPO_ROOT%\dist\locker_button.exe" S:\EFI\QackLocker\locker.exe

REM Register BootOrder via bcdedit (Windows-side, no UEFI needed)
for /f "tokens=2 delims={}" %%G in ('bcdedit /copy {bootmgr} /d "QackLocker"') do set GUID={%%G}
bcdedit /set %GUID% path \EFI\QackLocker\bootx64.efi
bcdedit /set %GUID% device partition=S:
bcdedit /set {fwbootmgr} displayorder %GUID% /addfirst

echo Installed. Reboot to trigger.
mountvol S: /d
