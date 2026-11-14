"""Một file khởi động chung: API Python + cửa sổ Electron.

    python start.py                 # build UI nếu cần, giải phóng cổng, mở app
    python start.py --rebuild        # build lại UI tĩnh trước khi mở
    python start.py --port 8787      # cổng API mong muốn (bị chiếm thì kill rồi dùng lại)
    python start.py --web            # chỉ chạy API (dùng UI web ở Next dev)
    python start.py --dev-ui         # Next dev server + Electron trỏ vào đó

Cổng: nếu cổng API đang bị tiến trình cũ giữ, `tools.port_tools` kill đúng PID đó rồi
bind lại; nếu vẫn bận thì tự nhảy sang cổng trống kế tiếp (`--no-pick-port` để tắt).
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
DESKTOP = ROOT / "desktop"
OUT_INDEX = WEB / "out" / "index.html"
IS_WINDOWS = os.name == "nt"
NPM = "npm.cmd" if IS_WINDOWS else "npm"

# Nguồn UI: nếu file nguồn mới hơn bản build thì build lại.
SOURCE_GLOBS = ("app", "components", "lib", "theme.js", "next.config.mjs", "package.json")


def log(message):
    print(message, flush=True)


def force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ============================================================
# KIỂM TRA PHỤ THUỘC
# ============================================================
def ensure_python_deps():
    missing = []
    for module, package in (("fastapi", "fastapi"), ("uvicorn", "uvicorn[standard]")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        log("[setup] cài đặt %s ..." % ", ".join(missing))
        subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)
    try:
        __import__("playwright")
    except ImportError:
        log("[cảnh báo] thiếu Playwright — phần chạy chiến dịch bằng Chrome sẽ không dùng được")
        log("           cài bằng: python -m pip install playwright")


def run_npm(cwd, args, label):
    log("[setup] %s: %s %s" % (label, NPM, " ".join(args)))
    result = subprocess.run([NPM, *args], cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit("[lỗi] '%s' thất bại trong %s" % (" ".join(args), cwd))
    return result


def ensure_node_modules(cwd, label):
    if (cwd / "node_modules").exists():
        return
    log("[setup] chưa có node_modules trong %s — chạy npm install" % label)
    run_npm(cwd, ["install", "--no-fund", "--no-audit"], label)


def ensure_electron_binary():
    """npm có thể chặn postinstall của electron ⇒ phải tự tải binary."""
    electron_dir = DESKTOP / "node_modules" / "electron"
    if not electron_dir.exists():
        return False
    exe = electron_dir / "dist" / ("electron.exe" if IS_WINDOWS else "electron")
    if exe.exists():
        return True
    log("[setup] tải binary Electron (postinstall bị npm chặn) ...")
    install_js = electron_dir / "install.js"
    if install_js.exists():
        node = shutil.which("node")
        if node:
            subprocess.run([node, str(install_js)], cwd=str(electron_dir), check=False)
    if exe.exists():
        return True
    # Dự phòng: giải nén từ cache zip có sẵn.
    cache_root = Path(os.environ.get("LOCALAPPDATA", "")) / "electron" / "Cache"
    if cache_root.exists():
        zips = sorted(cache_root.glob("*/electron-v*-win32-x64.zip"),
                      key=lambda item: item.stat().st_size, reverse=True)
        if zips:
            log("[setup] giải nén %s" % zips[0].name)
            shutil.unpack_archive(str(zips[0]), str(electron_dir / "dist"), "zip")
    return exe.exists()


def electron_command():
    exe = DESKTOP / "node_modules" / "electron" / "dist" / (
        "electron.exe" if IS_WINDOWS else "electron")
    if exe.exists():
        return [str(exe), str(DESKTOP)]
    npx = shutil.which("npx")
    if npx:
        return [npx, "electron", str(DESKTOP)]
    return []


# ============================================================
# BUILD UI
# ============================================================
def newest_source_mtime():
    latest = 0.0
    for name in SOURCE_GLOBS:
        target = WEB / name
        if not target.exists():
            continue
        paths = [target] if target.is_file() else [
            path for path in target.rglob("*")
            if path.is_file() and "node_modules" not in path.parts and ".next" not in path.parts
        ]
        for path in paths:
            latest = max(latest, path.stat().st_mtime)
    return latest


def build_ui(force=False):
    if not force and OUT_INDEX.exists() and OUT_INDEX.stat().st_mtime >= newest_source_mtime():
        log("[build] dùng bản UI tĩnh có sẵn (web/out)")
        return
    log("[build] build UI tĩnh (next build → web/out) ...")
    run_npm(WEB, ["run", "build"], "build UI")
    if not OUT_INDEX.exists():
        raise SystemExit("[lỗi] build xong nhưng không thấy web/out/index.html")
    log("[build] xong")


# ============================================================
# API
# ============================================================
def api_alive(base, timeout=1.5):
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_api(base, seconds=45):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if api_alive(base):
            return True
        time.sleep(0.4)
    return False


def child_env(api_base=""):
    """Bỏ ELECTRON_RUN_AS_NODE — nếu còn, Electron sẽ chạy như Node và không mở cửa sổ."""
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["PYTHONIOENCODING"] = "utf-8"
    if api_base:
        env["API_BASE"] = api_base
    return env


def start_api(port):
    command = [sys.executable, str(ROOT / "server.py"), "--no-browser",
               "--port", str(port), "--no-kill-port"]
    log("[api] %s" % " ".join(command))
    return subprocess.Popen(command, cwd=str(ROOT), env=child_env())


def stop_process(process, label="tiến trình"):
    if process is None or process.poll() is not None:
        return
    log("[stop] đóng %s (pid %s)" % (label, process.pid))
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                           capture_output=True, timeout=20)
        else:
            process.terminate()
            process.wait(timeout=8)
    except (OSError, subprocess.SubprocessError):
        pass


# ============================================================
# MAIN
# ============================================================
def main():
    force_utf8()
    from tools import port_tools

    parser = argparse.ArgumentParser(description="Khởi động NAMCO Account Manager (API + Electron)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8787")))
    parser.add_argument("--rebuild", action="store_true", help="Build lại UI tĩnh trước khi mở")
    parser.add_argument("--web", action="store_true", help="Chỉ chạy API (mở UI web riêng)")
    parser.add_argument("--dev-ui", action="store_true",
                        help="Chạy Next dev server (:3000) và trỏ Electron vào đó")
    parser.add_argument("--no-pick-port", action="store_true",
                        help="Không tự nhảy cổng khi cổng mong muốn vẫn bận sau khi kill")
    args = parser.parse_args()

    ensure_python_deps()

    api_process = None
    ui_process = None
    electron_process = None

    # ---- cổng API: kill tiến trình cũ rồi bind lại ----
    if args.no_pick_port:
        if not port_tools.free_port(args.port, on_log=log):
            raise SystemExit("[lỗi] cổng %d vẫn bị chiếm" % args.port)
        api_port = args.port
    else:
        api_port = port_tools.pick_port(args.port, on_log=log)
    api_base = "http://127.0.0.1:%d" % api_port

    try:
        api_process = start_api(api_port)
        if not wait_api(api_base):
            raise SystemExit("[lỗi] API không khởi động được trên %s (xem log phía trên)" % api_base)
        log("[api] sẵn sàng: %s" % api_base)

        if args.web:
            log("[web] UI web: chạy `cd web && npm run dev` rồi mở http://localhost:3000")
            log("[web] Nhấn Ctrl+C để dừng API.")
            while api_process.poll() is None:
                time.sleep(1)
            return 0

        ensure_node_modules(WEB, "web")
        if args.dev_ui:
            ui_process = subprocess.Popen([NPM, "run", "dev"], cwd=str(WEB), env=child_env())
            log("[ui] Next dev: http://localhost:3000")
        else:
            build_ui(force=args.rebuild)

        ensure_node_modules(DESKTOP, "desktop")
        if not ensure_electron_binary():
            raise SystemExit("[lỗi] không có binary Electron. Chạy: cd desktop && npm install")
        command = electron_command()
        if not command:
            raise SystemExit("[lỗi] không tìm thấy Electron")

        env = child_env(api_base)
        if args.dev_ui:
            env["UI_URL"] = "http://localhost:3000"
        log("[ui] mở Electron%s" % (" (dev UI)" if args.dev_ui else ""))
        electron_process = subprocess.Popen(command, cwd=str(ROOT), env=env)
        log("[ui] Electron pid %s — đóng cửa sổ để thoát." % electron_process.pid)
        returncode = electron_process.wait()
        log("[ui] Electron đã đóng (exit %s)" % returncode)
        return 0
    except KeyboardInterrupt:
        log("\n[stop] nhận Ctrl+C")
        return 0
    finally:
        stop_process(electron_process, "Electron")
        stop_process(ui_process, "Next dev")
        stop_process(api_process, "API")


if __name__ == "__main__":
    sys.exit(main())
