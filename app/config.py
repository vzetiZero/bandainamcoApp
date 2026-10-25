"""Hằng số mạng và đường dẫn dùng chung cho toàn ứng dụng."""
import json
import os


API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
PARKS2_HOST = "https://parks2.bandainamco-am.co.jp"
PARKS2_DOMAIN = "parks2.bandainamco-am.co.jp"
ACCOUNT_ORIGIN = "https://account.bandainamcoid.com"
# Cookie language phải đặt ở miền gốc: account-api là subdomain khác với
# account, đặt cookie theo account sẽ không gửi tới account-api.
ACCOUNT_COOKIE_DOMAIN = ".bandainamcoid.com"
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(APP_ROOT, "icons")
DATA_FILE = "accounts_data.json"
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
