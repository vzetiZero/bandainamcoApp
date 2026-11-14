"""Chạy API backend cho UI Next.js.

    python server.py                 # http://127.0.0.1:8787
    python server.py --port 9000 --reload

Không phụ thuộc Qt: chỉ dùng `app.domain`, `app.services` và các adapter
(`file_settings`, `checkout_store`, browser/).
"""
import argparse
import os
import sys


def _force_utf8():
    """Console Windows mặc định cp1252 — tiếng Nhật/tiếng Việt sẽ làm print ném lỗi."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    _force_utf8()
    parser = argparse.ArgumentParser(description="API backend (FastAPI) cho UI web/Electron")
    parser.add_argument("--host", default=os.environ.get("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8787")))
    parser.add_argument("--reload", action="store_true", help="Tự nạp lại khi sửa code")
    parser.add_argument("--no-browser", action="store_true",
                        help="Không tự mở trình duyệt tới http://localhost:3000")
    parser.add_argument("--kill-port", dest="kill_port", action="store_true", default=True,
                        help="Tự kill tiến trình cũ đang giữ cổng (mặc định bật)")
    parser.add_argument("--no-kill-port", dest="kill_port", action="store_false",
                        help="Không kill; báo lỗi nếu cổng đang bận")
    parser.add_argument("--pick-port", action="store_true",
                        help="Nếu kill xong vẫn bận thì tự nhảy sang cổng trống kế tiếp")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Thiếu FastAPI/uvicorn. Chạy: python -m pip install -r requirements.txt")
        return 1

    from tools import port_tools

    if args.kill_port:
        if args.pick_port:
            port = port_tools.pick_port(args.port, args.host)
        elif port_tools.free_port(args.port, args.host):
            port = args.port
        else:
            print("Cổng %d vẫn bị chiếm. Dùng --pick-port hoặc đổi --port." % args.port)
            return 1
    else:
        if not port_tools.can_bind(args.port, args.host):
            print("Cổng %d đang bị chiếm (--no-kill-port)." % args.port)
            return 1
        port = args.port

    if not args.no_browser and not os.environ.get("ELECTRON_RUN_AS_NODE"):
        try:
            import webbrowser

            webbrowser.open("http://localhost:3000")
        except Exception:  # noqa: BLE001 - mở browser là tiện ích, không bắt buộc
            pass

    print("API: http://%s:%d  (docs: /docs)" % (args.host, port))
    if args.reload:
        # Factory để uvicorn tự tạo app trong tiến trình con (không tạo ApiState 2 lần).
        uvicorn.run("api.app:create_app", factory=True, host=args.host, port=port,
                    reload=True)
    else:
        from api.app import create_app

        uvicorn.run(create_app(), host=args.host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())



