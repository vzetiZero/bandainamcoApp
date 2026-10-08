import sys
import json
import os
import requests
import time
import re
from html import unescape
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QProgressBar, QStatusBar, QMenuBar, QMenu, QToolBar,
    QSplitter, QFrame, QComboBox, QCheckBox, QDialog,
    QDialogButtonBox, QFormLayout, QTabWidget, QGroupBox,
    QScrollArea, QSizePolicy, QSpacerItem, QAbstractItemView,
    QTableWidgetItem, QHeaderView, QMenu, QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QPoint
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPalette, QLinearGradient, QBrush, QPainter

from icon_helper import load_svg_icon, AppIcons

# ============================================================
# Cáº¤U HÃŒNH
# ============================================================
API_URL = "https://account-api.bandainamcoid.com/"
LOGIN_URL = "https://account.bandainamcoid.com/login.html"
CLIENT_ID = "namcoparks_onlinestore"
REDIRECT_URI = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
DATA_FILE = "accounts_data.json"


def fetch_edit_profile(session, headers):
    """Read profile fields from the member edit page using the authenticated session."""
    url = "https://parks2.bandainamco-am.co.jp/member_regist.html?request=edit"
    try:
        response = session.get(url, headers=headers, timeout=30)
    except requests.RequestException:
        return {}
    if response.status_code != 200:
        return {}

    field_map = {
        "L_NAME": "last_name_kanji", "F_NAME": "first_name_kanji",
        "L_KANA": "last_name_kana", "F_KANA": "first_name_kana",
        "NICKNAME": "nickname", "ZIP": "postal_code", "POSTAL_CODE": "postal_code",
        "PREF": "prefecture", "CITY": "city", "ADDRESS": "address_number",
        "BUILDING": "building", "TEL": "phone", "PHONE": "phone",
        "BIRTHDAY": "dob", "DOB": "dob", "SEX": "gender", "GENDER": "gender",
    }
    profile = {}
    for match in re.finditer(r'<(?:input|textarea)\b([^>]*)>(?:([^<]*)</textarea>)?', response.text, re.I):
        attrs = match.group(1)
        name = re.search(r'\bname=["\']([^"\']+)', attrs, re.I)
        value = re.search(r'\bvalue=["\']([^"\']*)', attrs, re.I)
        if name and name.group(1).upper() in field_map:
            raw_value = value.group(1) if value else (match.group(2) or "")
            profile[field_map[name.group(1).upper()]] = unescape(raw_value)
    for match in re.finditer(r'<select\b([^>]*)>(.*?)</select>', response.text, re.I | re.S):
        name = re.search(r'name=["\']([^"\']+)', match.group(1), re.I)
        selected = re.search(r'<option\b([^>]*)>(.*?)</option>', match.group(2), re.I | re.S)
        if name and name.group(1).upper() in field_map and selected:
            value = re.search(r'value=["\']([^"\']*)', selected.group(1), re.I)
            profile[field_map[name.group(1).upper()]] = unescape(value.group(1) if value else re.sub(r'<[^>]+>', '', selected.group(2)).strip())
    return profile


def fetch_member_profile(session, headers):
    """Read the profile summary shown on the authenticated member mypage."""
    url = "https://parks2.bandainamco-am.co.jp/member_mypage.html"
    try:
        response = session.get(url, headers=headers, timeout=30)
    except requests.RequestException:
        return fetch_edit_profile(session, headers)
    if response.status_code != 200 or "member_mypage" not in response.url:
        return fetch_edit_profile(session, headers)

    html = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', response.text, flags=re.I | re.S)
    text = unescape(re.sub(r'<[^>]+>', ' ', html))
    text = re.sub(r'\s+', ' ', text)
    profile = {}

    def read_after(label):
        match = re.search(re.escape(label) + r'\s*[:ï¼š]?\s*([^|]{1,100}?)(?=\s+(?:æ°å|ãƒ‹ãƒƒã‚¯ãƒãƒ¼ãƒ |ç”Ÿå¹´æœˆæ—¥|æ€§åˆ¥|ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹|ãƒãƒ³ãƒ€ã‚¤ãƒŠãƒ ã‚³ID|ãƒã‚¤ãƒ³ãƒˆè¦ç´„|éƒµä¾¿ç•ªå·|éƒ½é“åºœçœŒ|å¸‚åŒºç”ºæ‘|ä¸ç›®ãƒ»ç•ªåœ°|ãƒ“ãƒ«ãƒ»ãƒžãƒ³ã‚·ãƒ§ãƒ³å|é›»è©±ç•ªå·|â– |ç¾åœ¨ã®ãƒã‚¤ãƒ³ãƒˆ)|$)', text)
        return match.group(1).strip() if match else ""

    name = read_after("æ°åï¼ˆæ¼¢å­—ï¼‰")
    name_parts = name.split()
    if name_parts:
        profile["last_name_kanji"] = name_parts[0]
        if len(name_parts) > 1:
            profile["first_name_kanji"] = " ".join(name_parts[1:])
    name = read_after("æ°åï¼ˆã‚«ãƒŠï¼‰")
    name_parts = name.split()
    if name_parts:
        profile["last_name_kana"] = name_parts[0]
        if len(name_parts) > 1:
            profile["first_name_kana"] = " ".join(name_parts[1:])

    labels = {
        "ãƒ‹ãƒƒã‚¯ãƒãƒ¼ãƒ ": "nickname", "ç”Ÿå¹´æœˆæ—¥": "dob", "æ€§åˆ¥": "gender",
        "ãƒ¡ãƒ¼ãƒ«ã‚¢ãƒ‰ãƒ¬ã‚¹": "email", "éƒµä¾¿ç•ªå·": "postal_code",
        "éƒ½é“åºœçœŒ": "prefecture", "å¸‚åŒºç”ºæ‘": "city", "ä¸ç›®ãƒ»ç•ªåœ°": "address_number",
        "ãƒ“ãƒ«ãƒ»ãƒžãƒ³ã‚·ãƒ§ãƒ³åãƒ»": "building", "é›»è©±ç•ªå·": "phone",
        "ç¾åœ¨ã®ãƒã‚¤ãƒ³ãƒˆ": "current_points", "ãƒãƒ³ãƒ€ã‚¤ãƒŠãƒ ã‚³ID": "bandai_namco_id_status",
        "ãƒã‚¤ãƒ³ãƒˆè¦ç´„": "points_terms_status",
    }
    for label, key in labels.items():
        value = read_after(label)
        if key == "building":
            value = re.sub(r'^éƒ¨å±‹ç•ªå·\s*', '', value)
        if value:
            profile[key] = value
    if profile:
        return profile
    return fetch_edit_profile(session, headers)


def inspect_login_handoff(session, headers, redirect_url, language):
    """Inspect the read-only passkey handoff and report when Parks2 needs approval."""
    query = parse_qs(urlparse(redirect_url or "").query)
    code = query.get("code", [""])[0]
    if not code:
        return {}
    params = {key: query.get(key, [""])[0] for key in ("client_id", "backto", "redirect_uri", "customize_id")}
    params.update({"code": code, "language": language, "cookie": json.dumps(session.cookies.get_dict())})
    request_headers = dict(headers)
    request_headers["X-Requested-With"] = "XMLHttpRequest"
    request_headers["Referer"] = redirect_url
    try:
        response = session.get(f"{API_URL}v3/passkey/info", params=params, headers=request_headers, timeout=30)
        data = response.json()
    except (requests.RequestException, ValueError):
        return {"profile_fetch_status": "Could not complete the Parks2 login handoff"}
    if data.get("result") != "OK":
        return {"profile_fetch_status": "Could not complete the Parks2 login handoff"}
    result = {}
    details = data.get("data", {})
    gadata = details.get("gadata", {}) if isinstance(details, dict) else {}
    if gadata.get("birthday"):
        result["dob"] = gadata["birthday"]
    if gadata.get("gender") is not None:
        result["gender_code"] = str(gadata["gender"])
    approval = details.get("view", {}).get("approval", {}) if isinstance(details, dict) else {}
    if approval.get("flag"):
        result["profile_fetch_status"] = "Bandai Namco approval is required to continue"
    elif data.get("redirect") or data.get("redirect_no-cache"):
        result["profile_fetch_status"] = "Login handoff continues in the browser"
    return result

# ============================================================
# WORKER THREAD CHO ÄÄ‚NG NHáº¬P
# ============================================================
class LoginWorker(QThread):
    """Thread thá»±c hiá»‡n Ä‘Äƒng nháº­p Ä‘á»ƒ khÃ´ng block UI"""
    result_ready = Signal(str, bool, str)  # email, success, message
    profile_ready = Signal(str, dict)
    progress = Signal(int)

    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password
        self._is_running = True

    def run(self):
        try:
            self.progress.emit(10)
            session = requests.Session()
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                "Origin": "https://account.bandainamcoid.com",
                "Referer": LOGIN_URL,
            }

            self.progress.emit(30)
            
            # Láº¥y cookies
            login_params = {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
            }
            session.get(LOGIN_URL, params=login_params, headers=headers, timeout=30)
            language = session.cookies.get("language", "ja")

            self.progress.emit(50)
            
            # ÄÄƒng nháº­p
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
                "login_id": self.email,
                "password": self.password,
                "env_info": env_info,
                "retention": 1,
                "language": language,
                "cookie": json.dumps({}),
                "prompt": "",
            }

            self.progress.emit(70)
            
            response = session.post(
                f"{API_URL}v3/login/idpw",
                data=login_data,
                headers=headers,
                timeout=30
            )
            
            self.progress.emit(90)
            
            response_data = response.json()
            
            if response_data.get("result") == "OK":
                for cookie_data in response_data.get("cookie", {}).values():
                    if cookie_data.get("name") and "value" in cookie_data:
                        session.cookies.set(cookie_data["name"], cookie_data["value"])
                profile = {"email": self.email, "password": self.password}
                handoff = inspect_login_handoff(session, headers, response_data.get("redirect", ""), language)
                profile.update(handoff)
                if profile.get("profile_fetch_status") != "Bandai Namco approval is required to continue":
                    profile.update(fetch_member_profile(session, headers))
                profile.setdefault("status", "Chua kiem tra")
                profile.setdefault("last_check", None)
                self.profile_ready.emit(self.email, profile)
                profile.setdefault("status", "ChÆ°a kiá»ƒm tra")
                profile.setdefault("last_check", None)
                self.result_ready.emit(self.email, True, "ÄÄƒng nháº­p thÃ nh cÃ´ng")
            else:
                error_msg = response_data.get("msg", "Lá»—i khÃ´ng xÃ¡c Ä‘á»‹nh")
                self.result_ready.emit(self.email, False, f"ÄÄƒng nháº­p tháº¥t báº¡i: {error_msg}")
            
            self.progress.emit(100)
            
        except Exception as e:
            self.result_ready.emit(self.email, False, f"Lá»—i: {str(e)}")

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD CHO KIá»‚M TRA NHIá»€U TÃ€I KHOáº¢N
# ============================================================
class BatchCheckWorker(QThread):
    """Thread kiá»ƒm tra nhiá»u tÃ i khoáº£n cÃ¹ng lÃºc"""
    result_ready = Signal(str, bool, str)  # email, success, message
    progress = Signal(int, int)  # current, total
    finished_checking = Signal()

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts  # list of (email, password)
        self._is_running = True

    def run(self):
        total = len(self.accounts)
        for i, (email, password) in enumerate(self.accounts):
            if not self._is_running:
                break
            
            self.progress.emit(i + 1, total)
            
            try:
                session = requests.Session()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                    "Origin": "https://account.bandainamcoid.com",
                    "Referer": LOGIN_URL,
                }

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
                
                if response_data.get("result") == "OK":
                    self.result_ready.emit(email, True, "âœ“ Hoáº¡t Ä‘á»™ng")
                else:
                    error_msg = response_data.get("msg", "Lá»—i")
                    self.result_ready.emit(email, False, f"âœ— {error_msg}")
                
            except Exception as e:
                self.result_ready.emit(email, False, f"âœ— Lá»—i: {str(e)}")
            
            # Delay nhá» Ä‘á»ƒ trÃ¡nh bá»‹ block
            time.sleep(0.5)
        
        self.finished_checking.emit()

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# DIALOG THÃŠM TÃ€I KHOáº¢N
# ============================================================
class AddAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ThÃªm tÃ i khoáº£n")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        layout.setVerticalSpacing(12)
        
        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("email@example.com")
        layout.addRow("Email:", self.email_input)
        
        # Máº­t kháº©u
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("â€¢â€¢â€¢â€¢â€¢â€¢â€¢â€¢")
        layout.addRow("Máº­t kháº©u:", self.password_input)
        
        self.show_password = QCheckBox("Hiá»‡n máº­t kháº©u")
        self.show_password.toggled.connect(self.toggle_password_visibility)
        layout.addRow("", self.show_password)
        
        # Há» (Kanji)
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("Há» (Kanji) - báº¯t buá»™c")
        layout.addRow("Há» (Kanji) *:", self.last_name_input)
        
        # TÃªn (Kanji) - First name in Kanji
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("TÃªn (Kanji)")
        layout.addRow("TÃªn (Kanji):", self.first_name_input)
        
        # Há» (Katakana)
        self.last_kana_input = QLineEdit()
        self.last_kana_input.setPlaceholderText("Há» (Katakana)")
        layout.addRow("Há» (Katakana):", self.last_kana_input)
        
        # TÃªn (Katakana)
        self.first_kana_input = QLineEdit()
        self.first_kana_input.setPlaceholderText("TÃªn (Katakana)")
        layout.addRow("TÃªn (Katakana):", self.first_kana_input)
        
        # Biá»‡t danh
        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("Biá»‡t danh")
        layout.addRow("Biá»‡t danh:", self.nickname_input)
        
        # NgÃ y sinh
        self.dob_input = QLineEdit()
        self.dob_input.setPlaceholderText("DD/MM/YYYY")
        layout.addRow("NgÃ y sinh:", self.dob_input)
        
        # Giá»›i tÃ­nh
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["", "Nam", "Ná»¯", "KhÃ¡c"])
        layout.addRow("Giá»›i tÃ­nh:", self.gender_combo)
        
        # MÃ£ bÆ°u Ä‘iá»‡n
        self.postal_code_input = QLineEdit()
        self.postal_code_input.setPlaceholderText("8618006")
        layout.addRow("MÃ£ bÆ°u Ä‘iá»‡n:", self.postal_code_input)
        
        # Tá»‰nh
        self.prefecture_input = QLineEdit()
        self.prefecture_input.setPlaceholderText("Tá»‰nh Kumamoto")
        layout.addRow("Tá»‰nh:", self.prefecture_input)
        
        # ÄÃ´ thá»‹/Quáº­n/Huyá»‡n
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("ç†Šæœ¬å¸‚åŒ—åŒºé¾ç”°")
        layout.addRow("ÄÃ´ thá»‹/Quáº­n:", self.city_input)
        
        # Sá»‘ nhÃ /Äá»‹a chá»‰ chi tiáº¿t
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("8ä¸ç›® 3-303å·")
        layout.addRow("Sá»‘ nhÃ /Äá»‹a chá»‰:", self.address_input)
        
        # Sá»‘ Ä‘iá»‡n thoáº¡i
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09012345678")
        layout.addRow("Sá»‘ Ä‘iá»‡n thoáº¡i:", self.phone_input)
        
        # NÃºt
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def toggle_password_visibility(self, checked):
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

    def get_data(self):
        return {
            "email": self.email_input.text().strip(),
            "password": self.password_input.text().strip(),
            "last_name": self.last_name_input.text().strip(),
            "first_name": self.first_name_input.text().strip(),
            "last_kana": self.last_kana_input.text().strip(),
            "first_kana": self.first_kana_input.text().strip(),
            "nickname": self.nickname_input.text().strip(),
            "dob": self.dob_input.text().strip(),
            "gender": self.gender_combo.currentText(),
            "postal_code": self.postal_code_input.text().strip(),
            "prefecture": self.prefecture_input.text().strip(),
            "city": self.city_input.text().strip(),
            "address": self.address_input.text().strip(),
            "phone": self.phone_input.text().strip(),
        }


# ============================================================
# DIALOG Äá»”I TÃŠN - Chá»‰ Ä‘á»•i TÃªn (Kanji)
# ============================================================
class ChangeNameDialog(QDialog):
    def __init__(self, parent=None, current_first_name=""):
        super().__init__(parent)
        self.setWindowTitle("Äá»•i TÃªn (Kanji)")
        self.setMinimumWidth(400)
        self.current_first_name = current_first_name
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        layout.setVerticalSpacing(12)
        
        # ThÃ´ng tin hiá»‡n táº¡i
        info_label = QLabel(f"TÃªn hiá»‡n táº¡i (Kanji): {self.current_first_name}")
        info_label.setStyleSheet("color: #666; font-size: 11px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;")
        layout.addRow(info_label)
        
        layout.addRow("", QLabel(""))  # Spacer
        
        # Chá»‰ cho phÃ©p Ä‘á»•i TÃªn (Kanji)
        self.first_name_input = QLineEdit(self.current_first_name)
        self.first_name_input.setPlaceholderText("TÃªn má»›i (Kanji)")
        layout.addRow("TÃªn má»›i (Kanji) *:", self.first_name_input)
        
        # NÃºt
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return {
            "first_name": self.first_name_input.text().strip(),
        }


# ============================================================
# WORKER THREAD CHO Äá»”I TÃŠN
# ============================================================
class ChangeNameWorker(QThread):
    """Thread thá»±c hiá»‡n Ä‘á»•i tÃªn Ä‘á»ƒ khÃ´ng block UI"""
    result_ready = Signal(str, bool, str)  # email, success, message
    progress = Signal(int)

    def __init__(self, email, password, name_data):
        super().__init__()
        self.email = email
        self.password = password
        self.name_data = name_data
        self._is_running = True

    def run(self):
        try:
            # Import change_name module
            from change_name import change_name
            
            self.progress.emit(10)
            
            result = change_name(
                email=self.email,
                password=self.password,
                new_last_name="",  # KhÃ´ng Ä‘á»•i há»
                new_first_name=self.name_data.get("first_name", ""),
                new_last_kana="",  # KhÃ´ng Ä‘á»•i há» kana
                new_first_kana="",  # KhÃ´ng Ä‘á»•i tÃªn kana
                new_nickname=""     # KhÃ´ng Ä‘á»•i nickname
            )
            
            self.progress.emit(100)
            self.result_ready.emit(self.email, result["success"], result["message"])
            
        except Exception as e:
            self.result_ready.emit(self.email, False, f"Lá»—i: {str(e)}")

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# MAIN WINDOW
# ============================================================
class AccountDetailsDialog(QDialog):
    """Display saved profile data; only the Kanji given name is editable."""
    FIELDS = [
        ("email", "Email"), ("password", "Password"),
        ("last_name_kanji", "Há» (Kanji)"), ("first_name_kanji", "TÃªn (Kanji)"),
        ("last_name_kana", "Há» (Kana)"), ("first_name_kana", "TÃªn (Kana)"),
        ("nickname", "Nickname"), ("dob", "NgÃ y sinh"), ("gender", "Giá»›i tÃ­nh"),
        ("postal_code", "MÃ£ bÆ°u Ä‘iá»‡n"), ("prefecture", "Tá»‰nh"), ("city", "ThÃ nh phá»‘"),
        ("address_number", "Äá»‹a chá»‰"), ("building", "TÃ²a nhÃ "), ("phone", "Äiá»‡n thoáº¡i"),
        ("current_points", "Äiá»ƒm hiá»‡n táº¡i"), ("bandai_namco_id_status", "Bandai Namco ID"),
        ("points_terms_status", "Äiá»u khoáº£n Ä‘iá»ƒm"),
        ("profile_fetch_status", "Tráº¡ng thÃ¡i láº¥y há»“ sÆ¡"), ("gender_code", "MÃ£ giá»›i tÃ­nh"),
        ("status", "Tráº¡ng thÃ¡i"), ("last_check", "Kiá»ƒm tra láº§n cuá»‘i"),
    ]

    def __init__(self, account, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ThÃ´ng tin tÃ i khoáº£n")
        self.setMinimumWidth(520)
        self.inputs = {}
        layout = QFormLayout(self)
        for key, label in self.FIELDS:
            value = account.get(key)
            field = QLineEdit("" if value is None else str(value))
            field.setReadOnly(key != "first_name_kanji")
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
            if key == "first_name_kanji":
                field.setPlaceholderText("Chá»‰ trÆ°á»ng nÃ y cÃ³ thá»ƒ chá»‰nh sá»­a")
            self.inputs[key] = field
            layout.addRow(label + ":", field)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def updated_first_name(self):
        return self.inputs["first_name_kanji"].text().strip()


class AccountManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NAMCO Account Manager")
        self.setMinimumSize(1400, 800)
        
        # Dá»¯ liá»‡u
        self.accounts = []  # List of dict with all account fields
        self.workers = []
        self.pending_name_changes = {}
        
        self.setup_ui()
        self.load_data()
        self.apply_styles()

    def setup_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Toolbar
        self.create_toolbar()
        main_layout.addWidget(self.toolbar)
        
        # Content Area - Tabbed interface
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        main_layout.addWidget(self.tab_widget)

        self.input_tab = self.create_left_panel()
        input_layout = self.input_tab.layout()
        input_layout.removeWidget(self.log_text)
        self.log_text.hide()
        log_label = input_layout.itemAt(input_layout.count() - 3).widget()
        if isinstance(log_label, QLabel):
            input_layout.removeWidget(log_label)
            log_label.deleteLater()
        self.tab_widget.addTab(self.input_tab, load_svg_icon(AppIcons.PLUS, 16), "Nháº­p tÃ i khoáº£n")

        self.list_tab = QWidget()
        list_layout = QHBoxLayout(self.list_tab)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(12)
        list_layout.addWidget(self.create_right_panel(), 3)
        log_panel = QFrame()
        log_layout = QVBoxLayout(log_panel)
        log_layout.addWidget(QLabel("Nháº­t kÃ½"))
        self.log_text.show()
        self.log_text.setMinimumWidth(260)
        self.log_text.setMaximumHeight(16777215)
        log_layout.addWidget(self.log_text)
        list_layout.addWidget(log_panel, 1)
        self.tab_widget.addTab(self.list_tab, load_svg_icon(AppIcons.FOLDER_OPEN, 16), "Danh sÃ¡ch tÃ i khoáº£n")
        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sáºµn sÃ ng")

    def create_toolbar(self):
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setStyleSheet("QToolBar { border: none; padding: 10px; }")
        
        # Title
        title = QLabel("NAMCO Account Manager")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #d61718;")
        self.toolbar.addWidget(title)
        
        self.toolbar.addSeparator()
        
        # Add Account Button
        add_btn = QPushButton(" ThÃªm tÃ i khoáº£n")
        add_btn.setIcon(load_svg_icon(AppIcons.PLUS, 20, "white"))
        add_btn.clicked.connect(self.add_account)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #d61718;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b51515; }
        """)
        self.toolbar.addWidget(add_btn)
        
        # Import Button
        import_btn = QPushButton(" Import TXT")
        import_btn.setIcon(load_svg_icon(AppIcons.FOLDER_OPEN, 20, "white"))
        import_btn.clicked.connect(self.import_from_txt)
        import_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90d9;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #3a7bc8; }
        """)
        self.toolbar.addWidget(import_btn)
        
        # Check All Button
        check_btn = QPushButton(" Kiá»ƒm tra táº¥t cáº£")
        check_btn.setIcon(load_svg_icon(AppIcons.CHECK, 20, "white"))
        check_btn.clicked.connect(self.check_all_accounts)
        check_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #218838; }
        """)
        self.toolbar.addWidget(check_btn)
        
        # Delete Selected Button
        delete_btn = QPushButton(" XÃ³a Ä‘Ã£ chá»n")
        delete_btn.setIcon(load_svg_icon(AppIcons.TRASH, 20, "white"))
        delete_btn.clicked.connect(self.delete_selected)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #c82333; }
        """)
        self.toolbar.addWidget(delete_btn)
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Stats
        self.stats_label = QLabel("0 tÃ i khoáº£n")
        self.stats_label.setStyleSheet("color: #666; font-size: 14px;")
        self.toolbar.addWidget(self.stats_label)

    def create_left_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border-radius: 8px;
                border: 1px solid #dee2e6;
            }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Nháº­p tÃ i khoáº£n")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # Format hint
        hint = QLabel("Äá»‹nh dáº¡ng: email|má»Ÿi dÃ²ng 1 tÃ i khoáº£n")
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)
        
        # Text Input
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("email1|password1\nemail2|password2\n...")
        self.text_input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 10px;
                font-family: Consolas, monospace;
                font-size: 13px;
            }
        """)
        layout.addWidget(self.text_input)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton(" ThÃªm vÃ o danh sÃ¡ch")
        add_btn.setIcon(load_svg_icon(AppIcons.PLUS, 18))
        add_btn.clicked.connect(self.add_from_text)
        add_btn.setStyleSheet("""
            QPushButton {
                background-color: #d61718;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #b51515; }
        """)
        btn_layout.addWidget(add_btn)
        
        clear_btn = QPushButton(" XÃ³a")
        clear_btn.setIcon(load_svg_icon(AppIcons.X, 18))
        clear_btn.clicked.connect(self.text_input.clear)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #5a6268; }
        """)
        btn_layout.addWidget(clear_btn)
        
        layout.addLayout(btn_layout)
        
        # Quick Actions
        actions_group = QGroupBox("Thao tÃ¡c nhanh")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        actions_layout = QVBoxLayout(actions_group)
        
        # Check single account
        check_single_btn = QPushButton(" Kiá»ƒm tra tÃ i khoáº£n Ä‘áº§u tiÃªn")
        check_single_btn.setIcon(load_svg_icon(AppIcons.CHECK, 18))
        check_single_btn.clicked.connect(self.check_first_account)
        actions_layout.addWidget(check_single_btn)
        
        # Export
        export_btn = QPushButton(" Export danh sÃ¡ch")
        export_btn.setIcon(load_svg_icon(AppIcons.DOWNLOAD, 18))
        export_btn.clicked.connect(self.export_accounts)
        actions_layout.addWidget(export_btn)
        
        layout.addWidget(actions_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Log
        log_label = QLabel("Nháº­t kÃ½:")
        log_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border-radius: 4px;
                padding: 5px;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.log_text)
        
        layout.addStretch()
        
        return panel

    def create_right_panel(self):
        panel = QFrame()
        panel.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #dee2e6;
            }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Danh sÃ¡ch tÃ i khoáº£n")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "STT", "Email", "Máº­t kháº©u", "Tráº¡ng thÃ¡i", "Kiá»ƒm tra láº§n cuá»‘i"
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellDoubleClicked.connect(self.show_account_details)
        self.table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                gridline-color: #e9ecef;
                selection-background-color: #d61718;
                selection-color: white;
                alternate-background-color: #f8f9fa;
                outline: none;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #dee2e6;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #e9ecef;
            }
            QTableWidget::item:selected {
                background-color: #d61718;
                color: white;
                font-weight: bold;
                border: 2px solid #d61718;
            }
            QTableWidget::item:selected:active {
                background-color: #b51515;
                color: white;
                font-weight: bold;
                border: 2px solid #d61718;
            }
            QTableWidget::item:selected:!active {
                background-color: #d61718;
                color: white;
                font-weight: bold;
                border: 2px solid #d61718;
            }
            QTableWidget::item:hover {
                background-color: #fff3cd;
            }
        """)
        layout.addWidget(self.table)
        
        # Filter
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Lá»c:")
        filter_layout.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Táº¥t cáº£", "Hoáº¡t Ä‘á»™ng", "KhÃ´ng hoáº¡t Ä‘á»™ng", "ChÆ°a kiá»ƒm tra"])
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_combo)
        
        filter_layout.addStretch()
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("TÃ¬m kiáº¿m email...")
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input)
        
        layout.addLayout(filter_layout)
        
        return panel

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QPushButton {
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QLineEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px;
            }
            QComboBox {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px;
            }
            QTableWidget {
                selection-background-color: #d61718;
                selection-color: white;
            }
            QTableWidget::item:selected {
                background-color: #d61718;
                color: white;
                font-weight: bold;
            }
        """)

    # ============================================================
    # DATA MANAGEMENT
    # ============================================================
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
                self.log(f"ÄÃ£ táº£i {len(self.accounts)} tÃ i khoáº£n tá»« file")
                self.update_table()
            except Exception as e:
                self.log(f"Lá»—i táº£i dá»¯ liá»‡u: {e}")

    def save_data(self):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, ensure_ascii=False, indent=2)
            self.log(f"ÄÃ£ lÆ°u {len(self.accounts)} tÃ i khoáº£n")
        except Exception as e:
            self.log(f"Lá»—i lÆ°u dá»¯ liá»‡u: {e}")

    # ============================================================
    # ACCOUNT OPERATIONS
    # ============================================================
    def add_account(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.Accepted:
            email, password = dialog.get_data()
            if email and password:
                if self.add_single_account(email, password):
                    self.log(f"ÄÃ£ thÃªm: {email}")
                    self.update_table()
                    self.save_data()

    def add_from_text(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Cáº£nh bÃ¡o", "Vui lÃ²ng nháº­p dá»¯ liá»‡u!")
            return
        
        lines = text.split('\n')
        added = 0
        skipped = 0
        
        for line in lines:
            line = line.strip()
            if not line or '|' not in line:
                continue
            
            parts = line.split('|', 1)
            if len(parts) != 2:
                continue
            
            email, password = parts[0].strip(), parts[1].strip()
            
            if self.add_single_account(email, password):
                added += 1
            else:
                skipped += 1
        
        self.log(f"ThÃªm: {added} | Bá» qua (trÃ¹ng): {skipped}")
        self.update_table()
        self.save_data()
        
        QMessageBox.information(
            self, "HoÃ n táº¥t",
            f"ÄÃ£ thÃªm: {added} tÃ i khoáº£n\nBá» qua (trÃ¹ng): {skipped} tÃ i khoáº£n"
        )

    def add_single_account(self, email, password):
        # Kiá»ƒm tra trÃ¹ng láº·p
        for acc in self.accounts:
            if acc['email'] == email:
                return False
        
        self.accounts.append({
            'email': email,
            'password': password,
            'status': 'ChÆ°a kiá»ƒm tra',
            'last_check': None
        })
        return True

    def import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chá»n file TXT", "", "Text Files (*.txt);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            added = 0
            skipped = 0
            
            for line in lines:
                line = line.strip()
                if not line or '|' not in line:
                    continue
                
                parts = line.split('|', 1)
                if len(parts) != 2:
                    continue
                
                email, password = parts[0].strip(), parts[1].strip()
                
                if self.add_single_account(email, password):
                    added += 1
                else:
                    skipped += 1
            
            self.log(f"Import: +{added} | Bá» qua: {skipped}")
            self.update_table()
            self.save_data()
            
            QMessageBox.information(
                self, "Import hoÃ n táº¥t",
                f"ÄÃ£ thÃªm: {added} tÃ i khoáº£n\nBá» qua (trÃ¹ng): {skipped} tÃ i khoáº£n"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Lá»—i", f"KhÃ´ng thá»ƒ Ä‘á»c file: {e}")

    def delete_selected(self):
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.warning(self, "Cáº£nh bÃ¡o", "Vui lÃ²ng chá»n tÃ i khoáº£n cáº§n xÃ³a!")
            return
        
        reply = QMessageBox.question(
            self, "XÃ¡c nháº­n",
            f"Báº¡n cÃ³ cháº¯c muá»‘n xÃ³a {len(selected_rows)} tÃ i khoáº£n Ä‘Ã£ chá»n?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # XÃ³a tá»« cuá»‘i lÃªn Ä‘á»ƒ khÃ´ng lá»—i index
            for row in sorted(selected_rows, reverse=True):
                if row < len(self.accounts):
                    del self.accounts[row]
            
            self.update_table()
            self.save_data()
            self.log(f"ÄÃ£ xÃ³a {len(selected_rows)} tÃ i khoáº£n")

    # ============================================================
    # CHECK ACCOUNTS
    # ============================================================
    def check_all_accounts(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cáº£nh bÃ¡o", "KhÃ´ng cÃ³ tÃ i khoáº£n nÃ o!")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.accounts))
        self.progress_bar.setValue(0)
        
        # Chuáº©n bá»‹ danh sÃ¡ch
        accounts_to_check = [(acc['email'], acc['password']) for acc in self.accounts]
        
        # Táº¡o worker
        self.worker = BatchCheckWorker(accounts_to_check)
        self.worker.result_ready.connect(self.on_check_result)
        self.worker.progress.connect(self.on_check_progress)
        self.worker.finished_checking.connect(self.on_check_finished)
        self.worker.start()
        
        self.log(f"Báº¯t Ä‘áº§u kiá»ƒm tra {len(accounts_to_check)} tÃ i khoáº£n...")

    def check_first_account(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cáº£nh bÃ¡o", "KhÃ´ng cÃ³ tÃ i khoáº£n nÃ o!")
            return
        
        acc = self.accounts[0]
        self.check_single_account(0)

    def check_single_account(self, index):
        if index >= len(self.accounts):
            return
        
        acc = self.accounts[index]
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        
        self.worker = LoginWorker(acc['email'], acc['password'])
        self.worker.result_ready.connect(lambda email, success, msg: self.on_single_result(index, email, success, msg))
        self.worker.profile_ready.connect(self.on_profile_ready)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.start()
        
        self.log(f"Äang kiá»ƒm tra: {acc['email']}")

    def on_single_result(self, index, email, success, message):
        self.accounts[index]['status'] = "Hoáº¡t Ä‘á»™ng" if success else "KhÃ´ng hoáº¡t Ä‘á»™ng"
        self.accounts[index]['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.update_table()
        self.save_data()
        self.log(f"{email}: {message}")
        self.progress_bar.setVisible(False)
        if success and index < len(self.accounts):
            self.show_account_details(index)

    def on_profile_ready(self, email, profile):
        for account in self.accounts:
            if account.get("email") == email:
                account.update(profile)
                self.save_data()
                self.update_table()
                return

    def show_account_details(self, row, column=0):
        if row < 0 or row >= len(self.accounts):
            return
        account = self.accounts[row]
        dialog = AccountDetailsDialog(account, self)
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.updated_first_name()
            if new_name != account.get("first_name_kanji", ""):
                self.execute_change_name(row, account, {"first_name": new_name})

    def on_check_result(self, email, success, message):
        # TÃ¬m account theo email
        for acc in self.accounts:
            if acc['email'] == email:
                acc['status'] = "Hoáº¡t Ä‘á»™ng" if success else "KhÃ´ng hoáº¡t Ä‘á»™ng"
                acc['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        
        self.update_table()
        self.log(f"{email}: {message}")

    def on_check_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f"Äang kiá»ƒm tra: {current}/{total}")

    def on_check_finished(self):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("HoÃ n táº¥t kiá»ƒm tra")
        self.save_data()
        self.log("HoÃ n táº¥t kiá»ƒm tra táº¥t cáº£ tÃ i khoáº£n")

    # ============================================================
    # UI UPDATES
    # ============================================================
    def update_table(self):
        columns = [
            ("#", None), ("Email", "email"), ("Password", "__password__"),
            ("Status", "status"), ("Last check", "last_check"),
            ("Last name (Kanji)", "last_name_kanji"), ("First name (Kanji)", "first_name_kanji"),
            ("Last name (Kana)", "last_name_kana"), ("First name (Kana)", "first_name_kana"),
            ("Nickname", "nickname"), ("Date of birth", "dob"), ("Gender", "gender"),
            ("Postal code", "postal_code"), ("Prefecture", "prefecture"), ("City", "city"),
            ("Address", "address_number"), ("Building", "building"), ("Phone", "phone"),
            ("Points", "current_points"), ("Bandai Namco ID", "bandai_namco_id_status"),
            ("Points terms", "points_terms_status"), ("Profile access", "profile_fetch_status"),
            ("Gender code", "gender_code"),
        ]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([column[0] for column in columns])
        self.table.setRowCount(len(self.accounts))
        for row, account in enumerate(self.accounts):
            for column, (label, key) in enumerate(columns):
                if key is None:
                    value = str(row + 1)
                elif key == "__password__":
                    value = "********"
                else:
                    value = account.get(key)
                    value = "" if value is None else str(value)
                item = QTableWidgetItem(value)
                if key == "status" and "Hoat" in value:
                    item.setForeground(QColor("#28a745"))
                elif key == "status" and "Khong" in value:
                    item.setForeground(QColor("#dc3545"))
                self.table.setItem(row, column, item)
        self.stats_label.setText(f"{len(self.accounts)} accounts")
    def apply_filter(self):
        filter_text = self.filter_combo.currentText()
        search_text = self.search_input.text().lower()
        
        for i in range(self.table.rowCount()):
            email_item = self.table.item(i, 1)
            status_item = self.table.item(i, 3)
            
            if not email_item or not status_item:
                continue
            
            email = email_item.text().lower()
            status = status_item.text()
            
            # Filter by status
            show = True
            if filter_text == "Hoáº¡t Ä‘á»™ng" and status != "Hoáº¡t Ä‘á»™ng":
                show = False
            elif filter_text == "KhÃ´ng hoáº¡t Ä‘á»™ng" and status != "KhÃ´ng hoáº¡t Ä‘á»™ng":
                show = False
            elif filter_text == "ChÆ°a kiá»ƒm tra" and status != "ChÆ°a kiá»ƒm tra":
                show = False
            
            # Filter by search
            if search_text and search_text not in email:
                show = False
            
            self.table.setRowHidden(i, not show)

    def export_accounts(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export danh sÃ¡ch", "accounts_export.txt", "Text Files (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for acc in self.accounts:
                    f.write(f"{acc['email']}|{acc['password']}\n")
            
            self.log(f"ÄÃ£ export {len(self.accounts)} tÃ i khoáº£n")
            QMessageBox.information(self, "HoÃ n táº¥t", f"ÄÃ£ export Ä‘áº¿n:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Lá»—i", f"KhÃ´ng thá»ƒ export: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    # ============================================================
    # CONTEXT MENU
    # ============================================================
    def show_context_menu(self, position):
        """Hiá»ƒn thá»‹ context menu khi chuá»™t pháº£i vÃ o báº£ng"""
        menu = QMenu(self)
        
        # Láº¥y dÃ²ng Ä‘Æ°á»£c chá»n
        row = self.table.rowAt(position.y())
        if row < 0 or row >= len(self.accounts):
            return
        
        # CÃ¡c hÃ nh Ä‘á»™ng
        change_name_action = QAction(load_svg_icon(AppIcons.EDIT), " Äá»•i tÃªn", self)
        change_name_action.triggered.connect(lambda: self.change_account_name(row))
        menu.addAction(change_name_action)

        details_action = QAction("Xem thÃ´ng tin tÃ i khoáº£n", self)
        details_action.triggered.connect(lambda: self.show_account_details(row))
        menu.addAction(details_action)
        
        menu.addSeparator()
        
        check_action = QAction(load_svg_icon(AppIcons.CHECK), " Kiá»ƒm tra tÃ i khoáº£n", self)
        check_action.triggered.connect(lambda: self.check_single_account(row))
        menu.addAction(check_action)
        
        copy_email_action = QAction(load_svg_icon(AppIcons.COPY), " Copy email", self)
        copy_email_action.triggered.connect(lambda: self.copy_email(row))
        menu.addAction(copy_email_action)
        
        menu.addSeparator()
        
        delete_action = QAction(load_svg_icon(AppIcons.TRASH), " XÃ³a tÃ i khoáº£n", self)
        delete_action.triggered.connect(lambda: self.delete_single_account(row))
        menu.addAction(delete_action)
        
        menu.exec(self.table.viewport().mapToGlobal(position))

    def copy_email(self, row):
        """Copy email vÃ o clipboard"""
        if row < len(self.accounts):
            email = self.accounts[row]['email']
            QApplication.clipboard().setText(email)
            self.log(f"ÄÃ£ copy email: {email}")

    def delete_single_account(self, row):
        """XÃ³a má»™t tÃ i khoáº£n"""
        if row >= len(self.accounts):
            return
        
        email = self.accounts[row]['email']
        reply = QMessageBox.question(
            self, "XÃ¡c nháº­n",
            f"Báº¡n cÃ³ cháº¯c muá»‘n xÃ³a tÃ i khoáº£n {email}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.accounts[row]
            self.update_table()
            self.save_data()
            self.log(f"ÄÃ£ xÃ³a: {email}")

    # ============================================================
    # CHANGE NAME
    # ============================================================
    def change_account_name(self, row):
        """Má»Ÿ dialog Ä‘á»•i tÃªn cho tÃ i khoáº£n"""
        if row >= len(self.accounts):
            return
        
        acc = self.accounts[row]
        
        # Láº¥y thÃ´ng tin tÃªn hiá»‡n táº¡i (cáº§n Ä‘Äƒng nháº­p Ä‘á»ƒ láº¥y)
        # Hiá»‡n táº¡i dÃ¹ng giÃ¡ trá»‹ máº·c Ä‘á»‹nh
        dialog = ChangeNameDialog(self, current_first_name=acc.get("first_name_kanji", ""))
        
        if dialog.exec() == QDialog.Accepted:
            name_data = dialog.get_data()
            
            # Kiá»ƒm tra Ã­t nháº¥t 1 trÆ°á»ng cÃ³ giÃ¡ trá»‹
            if not any(name_data.values()):
                QMessageBox.warning(self, "Cáº£nh bÃ¡o", "Vui lÃ²ng nháº­p Ã­t nháº¥t 1 trÆ°á»ng!")
                return
            
            # XÃ¡c nháº­n
            reply = QMessageBox.question(
                self, "XÃ¡c nháº­n Ä‘á»•i tÃªn",
                f"Báº¡n cÃ³ cháº¯c muá»‘n Ä‘á»•i tÃªn tÃ i khoáº£n {acc['email']}?\n\n"
                f"Há» má»›i: {name_data.get('last_name', '(giá»¯ nguyÃªn)')}\n"
                f"TÃªn má»›i: {name_data.get('first_name', '(giá»¯ nguyÃªn)')}\n"
                f"Nickname: {name_data.get('nickname', '(giá»¯ nguyÃªn)')}",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.execute_change_name(row, acc, name_data)

    def execute_change_name(self, row, acc, name_data):
        """Thá»±c hiá»‡n Ä‘á»•i tÃªn"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        
        self.pending_name_changes[acc['email']] = name_data.get("first_name", "")
        self.worker = ChangeNameWorker(acc['email'], acc['password'], name_data)
        self.worker.result_ready.connect(lambda email, success, msg: self.on_change_name_result(row, email, success, msg))
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.start()
        
        self.log(f"Äang Ä‘á»•i tÃªn: {acc['email']}")

    def on_change_name_result(self, row, email, success, message):
        if success and email in self.pending_name_changes and row < len(self.accounts):
            self.accounts[row]["first_name_kanji"] = self.pending_name_changes.pop(email)
            self.save_data()
        elif not success:
            self.pending_name_changes.pop(email, None)
        """Xá»­ lÃ½ káº¿t quáº£ Ä‘á»•i tÃªn"""
        self.progress_bar.setVisible(False)
        
        if success:
            self.log(f"âœ“ {email}: {message}")
            QMessageBox.information(self, "ThÃ nh cÃ´ng", f"Äá»•i tÃªn thÃ nh cÃ´ng!\n{email}")
        else:
            self.log(f"âœ— {email}: {message}")
            QMessageBox.warning(self, "Tháº¥t báº¡i", f"Äá»•i tÃªn tháº¥t báº¡i!\n{message}")

    def closeEvent(self, event):
        # Dá»«ng táº¥t cáº£ workers
        for worker in self.workers:
            worker.stop()
        
        self.save_data()
        event.accept()

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = AccountManager()
    window.show()
    
    sys.exit(app.exec())

