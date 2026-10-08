import requests
import json
import sys
import io
import re
from urllib.parse import urlparse, parse_qs

# Fix encoding cho Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Cáº¥u hÃ¬nh
API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
MEMBER_REGIST_URL = "https://parks2.bandainamco-am.co.jp/member_regist.html?request=edit"

def change_name(email, password, new_last_name, new_first_name=None, new_last_kana=None, new_first_kana=None, new_nickname=None):
    """
    Äá»•i tÃªn tÃ i khoáº£n NAMCO Parks
    
    Args:
        email: Email Ä‘Äƒng nháº­p
        password: Máº­t kháº©u
        new_last_name: Há» má»›i (Kanji) - báº¯t buá»™c
        new_first_name: TÃªn má»›i (Kanji) - tÃ¹y chá»n
        new_last_kana: Há» má»›i (Katakana) - tÃ¹y chá»n
        new_first_kana: TÃªn má»›i (Katakana) - tÃ¹y chá»n
        new_nickname: Biá»‡t danh má»›i - tÃ¹y chá»n
    
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
    print("Äá»”I TÃŠN TÃ€I KHOáº¢N NAMCO PARKS")
    print("=" * 60)

    # BÆ°á»›c 1: ÄÄƒng nháº­p
    print("\n[1/4] ÄÄƒng nháº­p...")
    
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
            return {"success": False, "message": f"ÄÄƒng nháº­p tháº¥t báº¡i: {response_data.get('msg', 'Unknown error')}"}
        
        print("    âœ“ ÄÄƒng nháº­p thÃ nh cÃ´ng")
        
        # Láº¥y cookies tá»« response
        if "cookie" in response_data:
            for key, cookie_data in response_data["cookie"].items():
                if "value" in cookie_data:
                    session.cookies.set(cookie_data["name"], cookie_data["value"])
        
    except Exception as e:
        return {"success": False, "message": f"Lá»—i Ä‘Äƒng nháº­p: {str(e)}"}

    # BÆ°á»›c 2: Láº¥y trang Ä‘á»•i thÃ´ng tin
    print("\n[2/4] Láº¥y trang Ä‘á»•i thÃ´ng tin...")
    
    try:
        response = session.get(MEMBER_REGIST_URL, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return {"success": False, "message": f"KhÃ´ng thá»ƒ truy cáº­p trang Ä‘á»•i thÃ´ng tin (Status: {response.status_code})"}
        
        html = response.text
        
        # Láº¥y cÃ¡c giÃ¡ trá»‹ hiá»‡n táº¡i
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
        
        print(f"    Há» hiá»‡n táº¡i: {current_last_name}")
        print(f"    TÃªn hiá»‡n táº¡i: {current_first_name}")
        print(f"    Há» (Katakana): {current_last_kana}")
        print(f"    TÃªn (Katakana): {current_first_kana}")
        print(f"    Nickname: {current_nickname}")
        
    except Exception as e:
        return {"success": False, "message": f"Lá»—i láº¥y trang: {str(e)}"}

    # BÆ°á»›c 3: Chuáº©n bá»‹ dá»¯ liá»‡u Ä‘á»•i tÃªn
    print("\n[3/4] Chuáº©n bá»‹ dá»¯ liá»‡u Ä‘á»•i tÃªn...")
    
    # Sá»­ dá»¥ng giÃ¡ trá»‹ má»›i hoáº·c giá»¯ giÃ¡ trá»‹ cÅ©
    final_last_name = new_last_name if new_last_name else current_last_name
    final_first_name = new_first_name if new_first_name else current_first_name
    final_last_kana = new_last_kana if new_last_kana else current_last_kana
    final_first_kana = new_first_kana if new_first_kana else current_first_kana
    final_nickname = new_nickname if new_nickname else current_nickname
    
    print(f"    Há» má»›i: {final_last_name}")
    print(f"    TÃªn má»›i: {final_first_name}")
    print(f"    Há» (Katakana) má»›i: {final_last_kana}")
    print(f"    TÃªn (Katakana) má»›i: {final_first_kana}")
    print(f"    Nickname má»›i: {final_nickname}")
    
    # TÃ¬m form action
    form_action = re.search(r'<form[^>]*action="([^"]*)"', html)
    if form_action:
        form_action = form_action.group(1)
        print(f"    Form action: {form_action}")
    else:
        form_action = MEMBER_REGIST_URL
        print(f"    Form action (default): {form_action}")
    
    # TÃ¬m táº¥t cáº£ hidden inputs
    hidden_inputs = re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html)
    
    # Chuáº©n bá»‹ form data
    form_data = {
        "L_NAME": final_last_name,
        "F_NAME": final_first_name,
        "L_KANA": final_last_kana,
        "F_KANA": final_first_kana,
        "NICKNAME": final_nickname,
    }
    
    # ThÃªm cÃ¡c hidden inputs
    for name, value in hidden_inputs:
        if name not in form_data:
            form_data[name] = value
    
    # ThÃªm cÃ¡c trÆ°á»ng trim
    form_data["jp.co.interfactory.framework.trim.L_NAME"] = ""
    form_data["jp.co.interfactory.framework.trim.F_NAME"] = ""
    form_data["jp.co.interfactory.framework.trim.L_KANA"] = ""
    form_data["jp.co.interfactory.framework.trim.F_KANA"] = ""
    form_data["jp.co.interfactory.framework.trim.NICKNAME"] = ""
    
    # TÃ¬m nÃºt submit
    submit_match = re.search(r'<input[^>]*type="submit"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', html)
    if submit_match:
        form_data[submit_match.group(1)] = submit_match.group(2)
        print(f"    Submit button: {submit_match.group(1)}={submit_match.group(2)}")
    
    # BÆ°á»›c 4: Gá»­i request Ä‘á»•i tÃªn
    print("\n[4/4] Gá»­i request Ä‘á»•i tÃªn...")
    
    try:
        # Cáº­p nháº­t headers cho form submit
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
        
        # Kiá»ƒm tra káº¿t quáº£
        if response.status_code == 200:
            # Kiá»ƒm tra xem cÃ³ thÃ´ng bÃ¡o lá»—i khÃ´ng
            if "error" in response.text.lower() or "ã‚¨ãƒ©ãƒ¼" in response.text:
                # TÃ¬m thÃ´ng bÃ¡o lá»—i
                error_match = re.search(r'class="[^"]*error[^"]*"[^>]*>([^<]*)<', response.text)
                if error_match:
                    return {"success": False, "message": f"Lá»—i: {error_match.group(1)}"}
            
            # Kiá»ƒm tra xem cÃ³ thÃ´ng bÃ¡o thÃ nh cÃ´ng khÃ´ng
            if "success" in response.text.lower() or "å®Œäº†" in response.text or "å¤‰æ›´" in response.text:
                return {"success": True, "message": "Äá»•i tÃªn thÃ nh cÃ´ng!"}
            
            # Náº¿u khÃ´ng rÃµ rÃ ng, giáº£ sá»­ thÃ nh cÃ´ng náº¿u status 200
            return {"success": True, "message": "Äá»•i tÃªn thÃ nh cÃ´ng! (cáº§n kiá»ƒm tra láº¡i)"}
        else:
            return {"success": False, "message": f"HTTP Error: {response.status_code}"}
        
    except Exception as e:
        return {"success": False, "message": f"Lá»—i gá»­i request: {str(e)}"}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Äá»•i tÃªn tÃ i khoáº£n NAMCO Parks")
    parser.add_argument("--email", required=True, help="Email Ä‘Äƒng nháº­p")
    parser.add_argument("--password", required=True, help="Máº­t kháº©u")
    parser.add_argument("--last-name", required=True, help="Há» má»›i (Kanji)")
    parser.add_argument("--first-name", help="TÃªn má»›i (Kanji)")
    parser.add_argument("--last-kana", help="Há» má»›i (Katakana)")
    parser.add_argument("--first-kana", help="TÃªn má»›i (Katakana)")
    parser.add_argument("--nickname", help="Biá»‡t danh má»›i")
    
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
        print("âœ“ THÃ€NH CÃ”NG!")
    else:
        print("âœ— THáº¤T Báº I!")
    print("=" * 60)
    print(result["message"])


if __name__ == "__main__":
    main()

