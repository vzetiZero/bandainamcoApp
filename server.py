"""Chạy API backend cho UI Next.js.

    python server.py                 # http://127.0.0.1:8787
    python server.py --port 9000 --reload

Không cần PySide6: API chỉ dùng `app.domain`, `app.services` và các adapter
không-Qt (`file_settings`, `checkout_store`, browser/).
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
    parser = argparse.ArgumentParser(description="API backend (FastAPI) cho UI web")
    parser.add_argument("--host", default=os.environ.get("API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8787")))
    parser.add_argument("--reload", action="store_true", help="Tự nạp lại khi sửa code")
    parser.add_argument("--no-browser", action="store_true",
                        help="Không tự mở trình duyệt tới http://localhost:3000")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Thiếu FastAPI/uvicorn. Chạy: python -m pip install -r requirements.txt")
        return 1

    if not args.no_browser:
        try:
            import webbrowser

            webbrowser.open("http://localhost:3000")
        except Exception:  # noqa: BLE001 - mở browser là tiện ích, không bắt buộc
            pass

    print("API: http://%s:%d  (docs: /docs)" % (args.host, args.port))
    if args.reload:
        uvicorn.run("api.app:app", host=args.host, port=args.port, reload=True)
    else:
        from api.app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())

