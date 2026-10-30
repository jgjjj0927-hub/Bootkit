@echo off
REM language: batch, file: build_efi_windows.bat
setlocal

if "%EDK2_DIR%"=="" set EDK2_DIR=C:\edk2
set REPO_ROOT=%~dp0..
set PKG_SRC=%REPO_ROOT%\QackLockerPkg

if not exist "%EDK2_DIR%" (
    echo EDK2 not found at %EDK2_DIR%
    echo Clone it first: git clone --recurse-submodules https://github.com/tianocore/edk2.git C:\edk2
    exit /b 1
)

cd /d "%EDK2_DIR%"
call edksetup.bat Rebuild

if exist "%EDK2_DIR%\QackLockerPkg" rmdir "%EDK2_DIR%\QackLockerPkg"
mklink /D "%EDK2_DIR%\QackLockerPkg" "%PKG_SRC%"

build -p QackLockerPkg\QackLockerPkg.dsc -a X64 -t VS2019 -b RELEASE

set OUT=%EDK2_DIR%\Build\QackLockerPkg\RELEASE_VS2019\X64\QackLockerEfi.efi
if not exist "%OUT%" (
    echo Build failed: %OUT% not found
    exit /b 1
)

copy /Y "%OUT%" "%REPO_ROOT%\bootx64.efi"
echo Built: %REPO_ROOT%\bootx64.efi
