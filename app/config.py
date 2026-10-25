"""Hằng số mạng và đường dẫn dùng chung cho toàn ứng dụng."""
import json


API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
DATA_FILE = "accounts_data.json"
PROXY_FORMAT_HINT = "ip:port:username:pass"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
# env_info là thông tin thiết bị mà JS của site tự lấy từ navigator.userAgentData
# (getEnvInfo() trong webauthn-client.js). Site chỉ chấp nhận đúng 2 trường này;
# gửi sai dạng khiến server trả result=NG và redirect về error.html.
ENV_INFO = json.dumps({"mobile": False, "platform": "Windows"}, separators=(",", ":"))
