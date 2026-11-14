"""Tiện ích cổng TCP: kiểm tra, tìm tiến trình đang giữ, và giải phóng cổng.

Dùng cho API và launcher: nếu cổng đang bị tiến trình cũ giữ (ví dụ lần chạy trước
chưa thoát), ta kill đúng tiến trình đó rồi mới bind, thay vì đổi cổng và để lại
một server "mồ côi" phục vụ code cũ.

Windows: `netstat -ano` + `taskkill`. POSIX: `lsof`/`ss` + `SIGKILL`.
"""
import os
import platform
import socket
import subprocess
import time


def port_open(port, host="127.0.0.1", timeout=0.4):
    """True nếu có tiến trình đang listen trên cổng."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((host, port)) == 0


def can_bind(port, host="127.0.0.1"):
    """True nếu bind được (cổng trống)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _windows_pids(port):
    """PID đang LISTEN trên cổng (Windows)."""
    pids = set()
    try:
        output = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                                text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return pids
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or "LISTENING" not in line.upper():
            continue
        local, pid = parts[1], parts[-1]
        if local.rsplit(":", 1)[-1] == str(port) and pid.isdigit():
            pids.add(int(pid))
    return pids


def _posix_pids(port):
    pids = set()
    for command in (["lsof", "-ti", "tcp:%d" % port], ["fuser", "%d/tcp" % port]):
        try:
            output = subprocess.run(command, capture_output=True, text=True,
                                    timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for token in output.split():
            if token.strip().isdigit():
                pids.add(int(token.strip()))
        if pids:
            break
    return pids


def pids_on_port(port):
    """Danh sách PID đang giữ cổng (bỏ PID của chính tiến trình này)."""
    pids = _windows_pids(port) if platform.system() == "Windows" else _posix_pids(port)
    return sorted(pid for pid in pids if pid not in (0, 4, os.getpid()))


def kill_pid(pid, on_log=print):
    """Kill một tiến trình (kèm cây con). Trả True nếu lệnh thành công."""
    if pid in (0, 4, os.getpid()):
        return False
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                                    capture_output=True, text=True, timeout=20)
            ok = result.returncode == 0
        else:
            os.kill(pid, 9)
            ok = True
    except (OSError, subprocess.SubprocessError) as exc:
        on_log("Không kill được PID %s: %s" % (pid, exc))
        return False
    if ok:
        on_log("Đã kill tiến trình cũ PID %s (đang giữ cổng)" % pid)
    return ok


def free_port(port, host="127.0.0.1", on_log=print, wait_seconds=6.0):
    """Giải phóng cổng: kill tiến trình đang giữ. Trả True khi cổng đã trống."""
    if can_bind(port, host):
        return True
    pids = pids_on_port(port)
    if not pids:
        on_log("Cổng %d đang bị chiếm nhưng không xác định được PID" % port)
        return False
    for pid in pids:
        kill_pid(pid, on_log=on_log)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if can_bind(port, host):
            return True
        time.sleep(0.25)
    return can_bind(port, host)


def pick_port(preferred, host="127.0.0.1", on_log=print, attempts=20):
    """Giải phóng `preferred`; nếu vẫn bận thì lấy cổng trống kế tiếp."""
    if free_port(preferred, host, on_log=on_log):
        return preferred
    for offset in range(1, attempts + 1):
        candidate = preferred + offset
        if can_bind(candidate, host):
            on_log("Cổng %d vẫn bận — dùng cổng %d" % (preferred, candidate))
            return candidate
    raise RuntimeError("Không tìm được cổng trống quanh %d" % preferred)
