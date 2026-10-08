import requests
import json
import sys
import io
import re
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urlparse, parse_qs

# Fix encoding cho Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Cấu hình
API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
MEMBER_REGIST_URL = "https://parks2.bandainamco-am.co.jp/member_regist.html?request=edit"


def complete_parks2_handoff(session, headers, redirect_url, language):
    """Follow BANDAI NAMCO's offered later URL without creating a passkey."""
    query = parse_qs(urlparse(redirect_url or "").query)
    code = query.get("code", [""])[0]
    if not code:
        return False
    params = {
        "client_id": query.get("client_id", [""])[0] or CLIENT_ID,
        "backto": query.get("backto", [""])[0],
        "redirect_uri": query.get("redirect_uri", [""])[0] or REDIRECT_URI,
        "customize_id": query.get("customize_id", [""])[0],
    }
    params.update(code=code, language=language, cookie=json.dumps(session.cookies.get_dict()))
    handoff_headers = dict(headers)
    handoff_headers["X-Requested-With"] = "XMLHttpRequest"
    handoff_headers["Referer"] = redirect_url
    response = session.get(f"{API_URL}v3/passkey/info", params=params, headers=handoff_headers, timeout=30)
    data = response.json()
    if data.get("result") != "OK":
        return False
    for cookie in data.get("cookie", {}).values():
        name = cookie.get("name")
        if not name:
            continue
        domain = cookie.get("domain")
        path = cookie.get("path", "/")
        if "value" in cookie:
            kwargs = {"path": path}
            if domain:
                kwargs["domain"] = domain
            session.cookies.set(name, cookie["value"], **kwargs)
        else:
            for existing in list(session.cookies):
                if existing.name == name and (not domain or existing.domain == domain):
                    session.cookies.clear(domain=existing.domain, path=existing.path, name=name)
    next_url = data.get("data", {}).get("btn", {}).get("btn-next", {}).get("url")
    if not next_url:
        return False
    callback_headers = dict(headers)
    callback_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    callback_headers["Referer"] = redirect_url
    callback = session.get(next_url, headers=callback_headers, timeout=30, allow_redirects=True)
    return callback.status_code < 400 and "parks2.bandainamco-am.co.jp" in urlparse(callback.url).netloc

def extract_form_date_values(html):
    class DateFieldParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.values = {}
            self.active_select = None
            self.selected_option = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            name = (attrs.get("name") or "").lower()
            if tag.lower() == "input" and name in {"year", "month", "day"} and "value" in attrs:
                self.values[name] = (attrs.get("value") or "").strip()
            elif tag.lower() == "select" and name in {"year", "month", "day"}:
                self.active_select = name
                self.selected_option = None
            elif tag.lower() == "option" and self.active_select:
                option_value = attrs.get("value")
                if option_value is not None:
                    if self.active_select not in self.values:
                        self.values[self.active_select] = option_value.strip()
                    if "selected" in attrs:
                        self.selected_option = option_value.strip()

        def handle_endtag(self, tag):
            if tag.lower() == "select" and self.active_select:
                if self.selected_option is not None:
                    self.values[self.active_select] = self.selected_option
                self.active_select = None
                self.selected_option = None

    parser = DateFieldParser()
    parser.feed(html)
    return parser.values


def change_name(email, password, new_last_name, new_first_name=None, new_last_kana=None, new_first_kana=None, new_nickname=None, new_dob=None):
    """
    Đổi tên tài khoản NAMCO Parks
    
    Args:
        email: Email đăng nhập
        password: Mật khẩu
        new_last_name: Họ mới (Kanji) - bắt buộc
        new_first_name: Tên mới (Kanji) - tùy chọn
        new_last_kana: Họ mới (Katakana) - tùy chọn
        new_first_kana: Tên mới (Katakana) - tùy chọn
        new_nickname: Biệt danh mới - tùy chọn
    
    Returns:
        dict: {success: bool, message: str}
    """
    
    session = requests.Session()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Origin": "https://account.bandainamcoid.com",
        "Referer": LOGIN_URL,
    }

    print("=" * 60)
    print("ĐỔI TÊN TÀI KHOẢN NAMCO PARKS")
    print("=" * 60)

    # Bước 1: Đăng nhập
    print("\n[1/4] Đăng nhập...")
    
    try:
        login_params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
        }
        session.get(LOGIN_URL, params=login_params, headers=headers, timeout=30)
        language = session.cookies.get("language", "ja")

        env_info = json.dumps({
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "lang": language,
            "plat": "Win32",
            "sw": 1920,
            "sh": 1080,
        }, separators=(',', ':'))

        login_data = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "backto": "",
            "customize_id": "",
            "login_id": email,
            "password": password,
            "env_info": env_info,
            "retention": 1,
            "language": language,
            "cookie": json.dumps({}),
            "prompt": "",
        }

        response = session.post(
            f"{API_URL}v3/login/idpw",
            data=login_data,
            headers=headers,
            timeout=30
        )
        
        response_data = response.json()
        
        if response_data.get("result") != "OK":
            return {"success": False, "message": f"Đăng nhập thất bại: {response_data.get('msg', 'Unknown error')}"}
        
        print("    ✓ Đăng nhập thành công")
        
        # Lấy cookies từ response
        if "cookie" in response_data:
            for key, cookie_data in response_data["cookie"].items():
                if "value" in cookie_data and cookie_data.get("name"):
                    kwargs = {k: cookie_data[k] for k in ("path", "domain") if cookie_data.get(k)}
                    session.cookies.set(cookie_data["name"], cookie_data["value"], **kwargs)

        if not complete_parks2_handoff(session, headers, response_data.get("redirect", ""), language):
            return {"success": False, "message": "Could not complete the Parks2 login handoff"}
        
    except Exception as e:
        return {"success": False, "message": f"Lỗi đăng nhập: {str(e)}"}

    # Bước 2: Lấy trang đổi thông tin
    print("\n[2/4] Lấy trang đổi thông tin...")
    
    try:
        response = session.get(MEMBER_REGIST_URL, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return {"success": False, "message": f"Không thể truy cập trang đổi thông tin (Status: {response.status_code})"}
        
        html = response.text
        
        # Lấy các giá trị hiện tại
        current_last_name = re.search(r'name="L_NAME"[^>]*value="([^"]*)"', html)
        current_first_name = re.search(r'name="F_NAME"[^>]*value="([^"]*)"', html)
        current_last_kana = re.search(r'name="L_KANA"[^>]*value="([^"]*)"', html)
        current_first_kana = re.search(r'name="F_KANA"[^>]*value="([^"]*)"', html)
        current_nickname = re.search(r'name="NICKNAME"[^>]*value="([^"]*)"', html)
        
        current_last_name = current_last_name.group(1) if current_last_name else ""
        current_first_name = current_first_name.group(1) if current_first_name else ""
        current_last_kana = current_last_kana.group(1) if current_last_kana else ""
        current_first_kana = current_first_kana.group(1) if current_first_kana else ""
        current_nickname = current_nickname.group(1) if current_nickname else ""
        
        print(f"    Họ hiện tại: {current_last_name}")
        print(f"    Tên hiện tại: {current_first_name}")
        print(f"    Họ (Katakana): {current_last_kana}")
        print(f"    Tên (Katakana): {current_first_kana}")
        print(f"    Nickname: {current_nickname}")
        
    except Exception as e:
        return {"success": False, "message": f"Lỗi lấy trang: {str(e)}"}

    # Bước 3: Chuẩn bị dữ liệu đổi tên
    print("\n[3/4] Chuẩn bị dữ liệu đổi tên...")
    
    # Sử dụng giá trị mới hoặc giữ giá trị cũ
    final_last_name = new_last_name if new_last_name else current_last_name
    final_first_name = new_first_name if new_first_name else current_first_name
    final_last_kana = new_last_kana if new_last_kana else current_last_kana
    final_first_kana = new_first_kana if new_first_kana else current_first_kana
    final_nickname = new_nickname if new_nickname else current_nickname
    
    print(f"    Họ mới: {final_last_name}")
    print(f"    Tên mới: {final_first_name}")
    print(f"    Họ (Katakana) mới: {final_last_kana}")
    print(f"    Tên (Katakana) mới: {final_first_kana}")
    print(f"    Nickname mới: {final_nickname}")
    
    # Tìm form action
    form_action = re.search(r'<form[^>]*action="([^"]*)"', html)
    if form_action:
        form_action = form_action.group(1)
        print(f"    Form action: {form_action}")
    else:
        form_action = MEMBER_REGIST_URL
        print(f"    Form action (default): {form_action}")
    
    # Tìm tất cả hidden inputs
    hidden_inputs = re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html)
    
    # Chuẩn bị form data
    form_data = {
        "L_NAME": final_last_name,
        "F_NAME": final_first_name,
        "L_KANA": final_last_kana,
        "F_KANA": final_first_kana,
        "NICKNAME": final_nickname,
    }
    
    # Thêm các hidden inputs
    for name, value in hidden_inputs:
        if name not in form_data:
            form_data[name] = value

    if new_dob:
        dob_parts = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", new_dob.strip())
        if not dob_parts:
            return {"success": False, "message": "Ngày sinh phải theo định dạng YYYY/MM/DD"}
        year, month, day = dob_parts.groups()
        form_data.update({"year": year, "month": month, "day": day})
    
    # Thêm các trường trim
    form_data["jp.co.interfactory.framework.trim.L_NAME"] = ""
    form_data["jp.co.interfactory.framework.trim.F_NAME"] = ""
    form_data["jp.co.interfactory.framework.trim.L_KANA"] = ""
    form_data["jp.co.interfactory.framework.trim.F_KANA"] = ""
    form_data["jp.co.interfactory.framework.trim.NICKNAME"] = ""
    if new_dob:
        form_data["jp.co.interfactory.framework.trim.year"] = ""
        form_data["jp.co.interfactory.framework.trim.month"] = ""
        form_data["jp.co.interfactory.framework.trim.day"] = ""
    
    # Tìm nút submit
    submit_match = re.search(r'<input[^>]*type="submit"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html)
    if submit_match:
        form_data[submit_match.group(1)] = submit_match.group(2)
        print(f"    Submit button: {submit_match.group(1)}={submit_match.group(2)}")
    
    # Bước 4: Gửi request đổi tên
    print("\n[4/4] Gửi request đổi tên...")
    
    try:
        # Cập nhật headers cho form submit
        form_headers = headers.copy()
        form_headers["Content-Type"] = "application/x-www-form-urlencoded"
        form_headers["Referer"] = MEMBER_REGIST_URL
        
        response = session.post(
            form_action,
            data=form_data,
            headers=form_headers,
            timeout=30
        )
        
        print(f"    Status: {response.status_code}")
        
        # Kiểm tra kết quả
        if response.status_code == 200:
            # Kiểm tra xem có thông báo lỗi không
            if "error" in response.text.lower() or "エラー" in response.text:
                # Tìm thông báo lỗi
                error_match = re.search(r'class="[^"]*error[^"]*"[^>]*>([^<]*)<', response.text)
                if error_match:
                    return {"success": False, "message": f"Lỗi: {error_match.group(1)}"}
            
            # Kiểm tra xem có thông báo thành công không
            if new_dob:
                try:
                    verify_response = session.get(MEMBER_REGIST_URL, headers=headers, timeout=30)
                except requests.RequestException as e:
                    return {"success": False, "message": f"Could not verify the date of birth after submission: {e}"}
                if verify_response.status_code != 200 or "member_regist.html" not in verify_response.url:
                    return {"success": False, "message": "Could not reload the edit form to verify the date of birth."}
                saved_fields = extract_form_date_values(verify_response.text)
                missing_fields = [field for field in ("year", "month", "day") if field not in saved_fields]
                if missing_fields:
                    return {
                        "success": False,
                        "message": "Could not verify the saved date: the reloaded edit page did not contain date controls ("
                        + ", ".join(missing_fields)
                        + "). Please reopen the account and check its profile before retrying.",
                    }
                try:
                    expected_date = tuple(int(part) for part in dob_parts.groups())
                    saved_date = tuple(int(saved_fields[field]) for field in ("year", "month", "day"))
                except (KeyError, ValueError):
                    return {"success": False, "message": "Could not verify the saved date because the server returned an invalid date value."}
                if saved_date != expected_date:
                    return {"success": False, "message": "The server did not save the new date of birth; local data was left unchanged."}
                return {"success": True, "message": "The server saved and verified the new date of birth."}

            if "success" in response.text.lower() or "完了" in response.text or "変更" in response.text:
                return {"success": True, "message": "Đổi tên thành công!"}
            
            # Nếu không rõ ràng, giả sử thành công nếu status 200
            return {"success": True, "message": "Đổi tên thành công! (cần kiểm tra lại)"}
        else:
            return {"success": False, "message": f"HTTP Error: {response.status_code}"}
        
    except Exception as e:
        return {"success": False, "message": f"Lỗi gửi request: {str(e)}"}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Đổi tên tài khoản NAMCO Parks")
    parser.add_argument("--email", required=True, help="Email đăng nhập")
    parser.add_argument("--password", required=True, help="Mật khẩu")
    parser.add_argument("--last-name", required=True, help="Họ mới (Kanji)")
    parser.add_argument("--first-name", help="Tên mới (Kanji)")
    parser.add_argument("--last-kana", help="Họ mới (Katakana)")
    parser.add_argument("--first-kana", help="Tên mới (Katakana)")
    parser.add_argument("--nickname", help="Biệt danh mới")
    
    args = parser.parse_args()
    
    result = change_name(
        email=args.email,
        password=args.password,
        new_last_name=args.last_name,
        new_first_name=args.first_name,
        new_last_kana=args.last_kana,
        new_first_kana=args.first_kana,
        new_nickname=args.nickname
    )
    
    print("\n" + "=" * 60)
    if result["success"]:
        print("✓ THÀNH CÔNG!")
    else:
        print("✗ THẤT BẠI!")
    print("=" * 60)
    print(result["message"])


if __name__ == "__main__":
    main()
