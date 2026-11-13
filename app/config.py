"""Hằng số mạng và đường dẫn dùng chung cho toàn ứng dụng."""
import json
import os


API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
PARKS2_HOST = "https://parks2.bandainamco-am.co.jp"
PARKS2_DOMAIN = "parks2.bandainamco-am.co.jp"
# Parks2 có form đăng nhập riêng (không phải BNID) dùng cùng email/mật khẩu nhưng
# là hệ thống phiên khác. Khi BNID khoá đăng nhập, form này vẫn vào được
# member_mypage - đủ để đọc và sửa hồ sơ.
PARKS2_LOGIN_URL = (PARKS2_HOST + "/login.html"
                    "?request=redirect_logon&redirectTo=member_mypage.html")
PARKS2_TOP_LOGIN_URL = PARKS2_HOST + "/top_login.html"
ACCOUNT_ORIGIN = "https://account.bandainamcoid.com"
# Cookie language phải đặt ở miền gốc: account-api là subdomain khác với
# account, đặt cookie theo account sẽ không gửi tới account-api.
ACCOUNT_COOKIE_DOMAIN = ".bandainamcoid.com"
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(APP_ROOT, "icons")
DATA_FILE = "accounts_data.json"
# Cấu hình giao diện/proxy lưu cạnh app (INI) để copy thư mục dự án sang máy
# khác vẫn giữ nguyên; lần đầu chạy sẽ chuyển giá trị cũ từ registry sang.
SETTINGS_FILE = os.path.join(APP_ROOT, "ui_settings.ini")
PROXY_FORMAT_HINT = "ip:port:username:pass"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# env_info là thông tin thiết bị mà JS của site tự lấy từ navigator.userAgentData
# (getEnvInfo() trong webauthn-client.js). Site chỉ chấp nhận đúng 2 trường này;
# gửi sai dạng khiến server trả result=NG và redirect về error.html.
ENV_INFO = json.dumps({"mobile": False, "platform": "Windows"}, separators=(",", ":"))

# Kiểm tra nhiều tài khoản chạy đồng thời; 5 là mức đủ nhanh mà không dồn request
# quá nhiều vào site/proxy.
DEFAULT_CONCURRENCY = 5
MAX_CONCURRENCY = 10

# ============================================================
# TRÌNH DUYỆT TỰ ĐỘNG (Playwright CDP + chrome-devtools-mcp)
# ============================================================
# Mỗi tài khoản có một Chrome riêng: profile riêng (cookie/phiên tách biệt),
# cổng remote-debugging riêng và proxy riêng. Nhờ cổng đó, chrome-devtools-mcp
# gắn được vào đúng cửa sổ của đúng tài khoản để dò selector/chụp snapshot.
BROWSER_PROFILE_DIR = os.path.join(APP_ROOT, "browser_profiles")
BROWSER_ARTIFACTS_DIR = os.path.join(APP_ROOT, "browser_artifacts")
BROWSER_RECIPES_DIR = os.path.join(APP_ROOT, "recipes")
BROWSER_RECIPE_FILE = os.path.join(BROWSER_RECIPES_DIR, "parks2_campaign.json")
# Chrome cần user-data-dir khác mặc định mới chịu mở --remote-debugging-port;
# profile riêng của từng tài khoản đã thoả điều kiện đó.
BROWSER_CDP_BASE_PORT = 9400
BROWSER_NAV_TIMEOUT = 45000      # ms, chờ một lần điều hướng
BROWSER_ACTION_TIMEOUT = 15000   # ms, chờ một phần tử/hành động
DEFAULT_BROWSER_PARALLEL = 1
MAX_BROWSER_PARALLEL = 3
# Chrome thật trên máy: dùng channel "chrome" nên UA/fingerprint là của trình
# duyệt thật, không bịa header.
CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
)
# Server MCP đã cài bằng `npm i -g chrome-devtools-mcp`; đặt biến môi trường
# CHROME_DEVTOOLS_MCP_JS để trỏ tới bản khác (hoặc dùng shim npx).
CHROME_DEVTOOLS_MCP_JS = os.environ.get("CHROME_DEVTOOLS_MCP_JS", "")
CHROME_DEVTOOLS_MCP_NPM_PACKAGE = "chrome-devtools-mcp"

# Hồ sơ đặt hàng + thẻ thanh toán người dùng nhập trong tab Cấu hình: file riêng,
# git-ignored, từng giá trị mã hoá bằng DPAPI của Windows (xem checkout_store.py).
CHECKOUT_FILE = os.path.join(APP_ROOT, "checkout_profile.json")

# ============================================================
# API / UI WEB (Next.js)
# ============================================================
# Bản web lưu tuỳ chọn ở JSON riêng (không cần Qt); lần đầu sẽ chép giá trị từ
# `ui_settings.ini` của bản desktop để không mất danh sách chiến dịch.
WEB_SETTINGS_FILE = os.path.join(APP_ROOT, "web_settings.json")
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8787"))
# Cho phép origin của Next.js dev server gọi API.
API_CORS_ORIGINS = os.environ.get(
    "API_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000").split(",")
