import sys
import json
import os
import requests
import time
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import webbrowser
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
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QPoint, QSettings
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPalette, QLinearGradient, QBrush, QPainter, QPixmap

from icon_helper import load_svg_icon, AppIcons

# ============================================================
# CẤU HÌNH
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
        "SEX": "gender", "GENDER": "gender",
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


class MypageMemberInfoParser(HTMLParser):
    """Extract labeled fields from the member-info dl blocks, including bare text values."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.mode = None

    def handle_starttag(self, tag, attrs):
        if tag == "dl" and self.current is None:
            self.current = {"label": [], "value": [], "bare": []}
            self.mode = None
        elif self.current is not None and tag == "dt":
            self.mode = "label"
        elif self.current is not None and tag == "dd":
            self.mode = "value"
        elif self.current is not None and tag == "br" and self.mode == "label":
            self.current["label"].append(" ")

    def handle_data(self, data):
        if self.current is None:
            return
        if self.mode == "label":
            self.current["label"].append(data)
        elif self.mode == "value":
            self.current["value"].append(data)
        else:
            self.current["bare"].append(data)

    def handle_endtag(self, tag):
        if self.current is None:
            return
        if tag in ("dt", "dd"):
            self.mode = None
        elif tag == "dl":
            label = re.sub(r"[\s:：*]+", "", "".join(self.current["label"]))
            value = "".join(self.current["value"]).strip()
            if not value:
                value = "".join(self.current["bare"]).strip()
            if label:
                self.items.append((label, value))
            self.current = None
            self.mode = None


def parse_member_mypage_html(html):
    parser = MypageMemberInfoParser()
    parser.feed(html)
    field_map = {
        "\u6c0f\u540d\uff08\u6f22\u5b57\uff09": ("last_name_kanji", "first_name_kanji"),
        "\u6c0f\u540d\uff08\u30ab\u30ca\uff09": ("last_name_kana", "first_name_kana"),
        "\u30cb\u30c3\u30af\u30cd\u30fc\u30e0": "nickname", "\u6027\u5225": "gender",
        "\u30e1\u30fc\u30eb\u30a2\u30c9\u30ec\u30b9": "email",
        "\u30d0\u30f3\u30c0\u30a4\u30ca\u30e0\u30b3ID": "bandai_namco_id_status",
        "\u30dd\u30a4\u30f3\u30c8\u898f\u7d04": "points_terms_status",
        "\u90f5\u4fbf\u756a\u53f7": "postal_code", "\u90fd\u9053\u5e9c\u770c": "prefecture",
        "\u5e02\u533a\u753a\u6751": "city", "\u4e01\u76ee\u30fb\u756a\u5730": "address_number",
        "\u30d3\u30eb\u30fb\u30de\u30f3\u30b7\u30e7\u30f3\u540d\u30fb\u90e8\u5c4b\u756a\u53f7": "building",
        "\u96fb\u8a71\u756a\u53f7": "phone",
    }
    profile = {}
    for label, value in parser.items:
        key = field_map.get(label)
        if not value or not key:
            continue
        if isinstance(key, tuple):
            parts = value.split()
            if parts:
                profile[key[0]] = parts[0]
            if len(parts) > 1:
                profile[key[1]] = " ".join(parts[1:])
        else:
            profile[key] = value

    plain_text = unescape(re.sub(r"<[^>]+>", " ", html))
    points = re.search(r"\u73fe\u5728\u306e\u30dd\u30a4\u30f3\u30c8\s*[:：]?\s*([0-9]+\s*\u30dd\u30a4\u30f3\u30c8)", plain_text)
    if points:
        profile["current_points"] = re.sub(r"\s+", " ", points.group(1)).strip()
    return profile


def fetch_member_profile(session, headers):
    """Fetch and parse the authenticated member page, then fill missing fields from edit form."""
    url = "https://parks2.bandainamco-am.co.jp/member_mypage.html"
    profile_headers = dict(headers)
    profile_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    profile_headers["Origin"] = "https://parks2.bandainamco-am.co.jp"
    profile_headers["Referer"] = "https://parks2.bandainamco-am.co.jp/"
    try:
        response = session.get(url, headers=profile_headers, timeout=30)
    except requests.RequestException:
        return fetch_edit_profile(session, profile_headers)
    if response.status_code != 200 or "member_mypage" not in response.url:
        return fetch_edit_profile(session, profile_headers)

    profile = parse_member_mypage_html(response.text)
    if profile:
        for key, value in fetch_edit_profile(session, profile_headers).items():
            profile.setdefault(key, value)
        return profile
    return fetch_edit_profile(session, profile_headers)

def inspect_login_handoff(session, headers, redirect_url, language):
    """Follow the offered 'later' button to finish the Parks2 login without creating a passkey."""
    query = parse_qs(urlparse(redirect_url or "").query)
    code = query.get("code", [""])[0]
    if not code:
        return {}
    params = {
        "client_id": query.get("client_id", [""])[0] or CLIENT_ID,
        "backto": query.get("backto", [""])[0],
        "redirect_uri": query.get("redirect_uri", [""])[0] or REDIRECT_URI,
        "customize_id": query.get("customize_id", [""])[0],
    }
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
                    try:
                        session.cookies.clear(domain=existing.domain, path=existing.path, name=name)
                    except requests.cookies.CookieConflictError:
                        pass
    result = {}
    details = data.get("data", {})
    gadata = details.get("gadata", {}) if isinstance(details, dict) else {}
    if gadata.get("gender") is not None:
        result["gender_code"] = str(gadata["gender"])
    next_url = details.get("btn", {}).get("btn-next", {}).get("url") if isinstance(details, dict) else None
    if not next_url:
        result["profile_fetch_status"] = "The account site did not provide a Parks2 continuation URL"
        return result
    page_headers = dict(headers)
    page_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    page_headers["Referer"] = redirect_url
    try:
        callback = session.get(next_url, headers=page_headers, timeout=30, allow_redirects=True)
    except requests.RequestException:
        result["profile_fetch_status"] = "Could not finish the Parks2 login callback"
        return result
    if callback.status_code >= 400 or "parks2.bandainamco-am.co.jp" not in urlparse(callback.url).netloc:
        result["profile_fetch_status"] = "Could not finish the Parks2 login callback"
    return result

# ============================================================
# WORKER THREAD CHO ĐĂNG NHẬP
# ============================================================
class LoginWorker(QThread):
    """Thread thực hiện đăng nhập để không block UI"""
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
            
            # Lấy cookies
            login_params = {
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
            }
            session.get(LOGIN_URL, params=login_params, headers=headers, timeout=30)
            language = session.cookies.get("language", "ja")

            self.progress.emit(50)
            
            # Đăng nhập
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
                handoff_status = handoff.get("profile_fetch_status")
                profile.update({key: value for key, value in handoff.items() if key != "profile_fetch_status"})

                # A failed passkey handoff does not necessarily mean the Parks2
                # profile page is unavailable, so always try the direct page fetch.
                member_profile = fetch_member_profile(session, headers)
                if member_profile:
                    profile.update(member_profile)
                    profile["profile_fetch_status"] = "Profile loaded from Parks2"
                    if handoff_status:
                        profile["parks2_handoff_status"] = handoff_status
                else:
                    profile["profile_fetch_status"] = handoff_status or "Parks2 login complete; no profile fields were parsed"
                profile.setdefault("status", "Chua kiem tra")
                profile.setdefault("last_check", None)
                self.profile_ready.emit(self.email, profile)
                profile.setdefault("status", "Chưa kiểm tra")
                profile.setdefault("last_check", None)
                self.result_ready.emit(self.email, True, "Đăng nhập thành công")
            else:
                error_msg = response_data.get("msg", "Lỗi không xác định")
                self.result_ready.emit(self.email, False, f"Đăng nhập thất bại: {error_msg}")
            
            self.progress.emit(100)
            
        except Exception as e:
            self.result_ready.emit(self.email, False, f"Lỗi: {str(e)}")

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD CHO KIỂM TRA NHIỀU TÀI KHOẢN
# ============================================================
class BatchCheckWorker(QThread):
    """Thread kiểm tra nhiều tài khoản cùng lúc"""
    result_ready = Signal(str, bool, str)  # email, success, message
    profile_ready = Signal(str, dict)
    progress = Signal(int, int)  # current, total
    finished_checking = Signal()

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts  # list of (email, password)
        self._is_running = True

    def run(self):
        total = len(self.accounts)
        for index, (email, password) in enumerate(self.accounts):
            if not self._is_running:
                break
            self.progress.emit(index + 1, total)
            account_worker = LoginWorker(email, password)
            profiles, results = [], []
            account_worker.profile_ready.connect(
                lambda account_email, profile: profiles.append((account_email, profile)),
                Qt.ConnectionType.DirectConnection,
            )
            account_worker.result_ready.connect(
                lambda account_email, success, message: results.append((account_email, success, message)),
                Qt.ConnectionType.DirectConnection,
            )
            account_worker.run()
            for account_email, profile in profiles:
                self.profile_ready.emit(account_email, profile)
            for account_email, success, message in results:
                self.result_ready.emit(account_email, success, message)
            time.sleep(0.5)
        self.finished_checking.emit()

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# DIALOG THÊM TÀI KHOẢN
# ============================================================
class AddAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm tài khoản")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        layout.setVerticalSpacing(12)
        
        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("email@example.com")
        layout.addRow("Email:", self.email_input)
        
        # Mật khẩu
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("••••••••")
        layout.addRow("Mật khẩu:", self.password_input)
        
        self.show_password = QCheckBox("Hiện mật khẩu")
        self.show_password.toggled.connect(self.toggle_password_visibility)
        layout.addRow("", self.show_password)
        
        # Họ (Kanji)
        self.last_name_input = QLineEdit()
        self.last_name_input.setPlaceholderText("Họ (Kanji) - bắt buộc")
        layout.addRow("Họ (Kanji) *:", self.last_name_input)
        
        # Tên (Kanji) - First name in Kanji
        self.first_name_input = QLineEdit()
        self.first_name_input.setPlaceholderText("Tên (Kanji)")
        layout.addRow("Tên (Kanji):", self.first_name_input)
        
        # Họ (Katakana)
        self.last_kana_input = QLineEdit()
        self.last_kana_input.setPlaceholderText("Họ (Katakana)")
        layout.addRow("Họ (Katakana):", self.last_kana_input)
        
        # Tên (Katakana)
        self.first_kana_input = QLineEdit()
        self.first_kana_input.setPlaceholderText("Tên (Katakana)")
        layout.addRow("Tên (Katakana):", self.first_kana_input)
        
        # Biệt danh
        self.nickname_input = QLineEdit()
        self.nickname_input.setPlaceholderText("Biệt danh")
        layout.addRow("Biệt danh:", self.nickname_input)
        
        
        # Giới tính
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["", "Nam", "Nữ", "Khác"])
        layout.addRow("Giới tính:", self.gender_combo)
        
        # Mã bưu điện
        self.postal_code_input = QLineEdit()
        self.postal_code_input.setPlaceholderText("8618006")
        layout.addRow("Mã bưu điện:", self.postal_code_input)
        
        # Tỉnh
        self.prefecture_input = QLineEdit()
        self.prefecture_input.setPlaceholderText("Tỉnh Kumamoto")
        layout.addRow("Tỉnh:", self.prefecture_input)
        
        # Đô thị/Quận/Huyện
        self.city_input = QLineEdit()
        self.city_input.setPlaceholderText("熊本市北区龍田")
        layout.addRow("Đô thị/Quận:", self.city_input)
        
        # Số nhà/Địa chỉ chi tiết
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("8丁目 3-303号")
        layout.addRow("Số nhà/Địa chỉ:", self.address_input)
        
        # Số điện thoại
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09012345678")
        layout.addRow("Số điện thoại:", self.phone_input)
        
        # Nút
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
            "gender": self.gender_combo.currentText(),
            "postal_code": self.postal_code_input.text().strip(),
            "prefecture": self.prefecture_input.text().strip(),
            "city": self.city_input.text().strip(),
            "address": self.address_input.text().strip(),
            "phone": self.phone_input.text().strip(),
        }


# ============================================================
# DIALOG ĐỔI TÊN - Chỉ đổi Tên (Kanji)
# ============================================================
class ChangeNameDialog(QDialog):
    def __init__(self, parent=None, current_last_name="", current_first_name=""):
        super().__init__(parent)
        self.setWindowTitle("Edit Kanji name")
        self.setMinimumWidth(420)
        self.current_last_name = current_last_name
        self.current_first_name = current_first_name
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        layout.setVerticalSpacing(12)
        info_label = QLabel("Only the two ?????? fields (? and ?) will change. Kana and all other profile fields stay the same.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #555; padding: 8px; background-color: #f8f9fa; border-radius: 4px;")
        layout.addRow(info_label)
        self.last_name_input = QLineEdit(self.current_last_name)
        self.last_name_input.setPlaceholderText("New family name (?)")
        layout.addRow("Family name (Kanji / ?):", self.last_name_input)
        self.first_name_input = QLineEdit(self.current_first_name)
        self.first_name_input.setPlaceholderText("New given name (?)")
        layout.addRow("Given name (Kanji / ?):", self.first_name_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return {
            "last_name": self.last_name_input.text().strip(),
            "first_name": self.first_name_input.text().strip(),
        }


# ============================================================
# WORKER THREAD CHO ĐỔI TÊN
# ============================================================
class ChangeNameWorker(QThread):
    """Thread thực hiện đổi tên để không block UI"""
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
                new_last_name=self.name_data.get("last_name", ""),  # Preserve when blank
                new_first_name=self.name_data.get("first_name", ""),
                new_last_kana="",  # Không đổi họ kana
                new_first_kana="",  # Không đổi tên kana
                new_nickname="",
            )
            
            self.progress.emit(100)
            self.result_ready.emit(self.email, result["success"], result["message"])
            
        except Exception as e:
            self.result_ready.emit(self.email, False, f"Lỗi: {str(e)}")

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# MAIN WINDOW
# ============================================================
class AccountDetailsDialog(QDialog):
    """Display saved profile data; only the two Kanji name fields are editable."""
    FIELDS = [
        ("email", "Email"), ("password", "Password"),
        ("last_name_kanji", "Họ (Kanji)"), ("first_name_kanji", "Tên (Kanji)"),
        ("last_name_kana", "Họ (Kana)"), ("first_name_kana", "Tên (Kana)"),
        ("nickname", "Nickname"), ("gender", "Giới tính"),
        ("postal_code", "Mã bưu điện"), ("prefecture", "Tỉnh"), ("city", "Thành phố"),
        ("address_number", "Địa chỉ"), ("building", "Tòa nhà"), ("phone", "Điện thoại"),
        ("current_points", "Điểm hiện tại"), ("bandai_namco_id_status", "Bandai Namco ID"),
        ("points_terms_status", "Điều khoản điểm"),
        ("profile_fetch_status", "Trạng thái lấy hồ sơ"), ("gender_code", "Mã giới tính"),
        ("status", "Trạng thái"), ("last_check", "Kiểm tra lần cuối"),
    ]

    def __init__(self, account, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thông tin tài khoản")
        self.setMinimumWidth(520)
        self.inputs = {}
        layout = QFormLayout(self)
        for key, label in self.FIELDS:
            value = account.get(key)
            field = QLineEdit("" if value is None else str(value))
            field.setReadOnly(key not in ("last_name_kanji", "first_name_kanji"))
            if key == "password":
                field.setEchoMode(QLineEdit.EchoMode.Password)
            if key == "first_name_kanji":
                field.setPlaceholderText("Chỉ trường này có thể chỉnh sửa")
            self.inputs[key] = field
            layout.addRow(label + ":", field)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def updated_name(self):
        return {
            "last_name": self.inputs["last_name_kanji"].text().strip(),
            "first_name": self.inputs["first_name_kanji"].text().strip(),
        }


class CampaignDialog(QDialog):
    def __init__(self, campaign=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chiến dịch")
        self.setMinimumWidth(460)
        campaign = campaign or {}
        layout = QFormLayout(self)
        self.name_input = QLineEdit(campaign.get("name", ""))
        self.url_input = QLineEdit(campaign.get("url", ""))
        self.open_input = QLineEdit(campaign.get("opens_at", ""))
        self.close_input = QLineEdit(campaign.get("closes_at", ""))
        self.notes_input = QTextEdit()
        self.notes_input.setPlainText(campaign.get("notes", ""))
        self.notes_input.setMaximumHeight(120)
        self.open_input.setPlaceholderText("YYYY-MM-DD HH:MM")
        self.close_input.setPlaceholderText("YYYY-MM-DD HH:MM")
        layout.addRow("Tên chiến dịch:", self.name_input)
        layout.addRow("Link chính thức:", self.url_input)
        layout.addRow("Mở đăng ký:", self.open_input)
        layout.addRow("Đóng đăng ký:", self.close_input)
        layout.addRow("Ghi chú thể lệ:", self.notes_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_campaign(self):
        return {
            "name": self.name_input.text().strip(),
            "url": self.url_input.text().strip(),
            "opens_at": self.open_input.text().strip(),
            "closes_at": self.close_input.text().strip(),
            "notes": self.notes_input.toPlainText().strip(),
        }


class AccountManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NAMCO Account Manager")
        logo_path = os.path.join(os.path.dirname(__file__), "icons", "logo.png")
        self.setWindowIcon(QIcon(logo_path))
        self.setMinimumSize(1400, 800)
        
        # Dữ liệu
        self.accounts = []  # List of dict with all account fields
        self.workers = []
        self.pending_name_changes = {}
        self.ui_settings = QSettings("NAMCO", "AccountManager")
        
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
        self.tab_widget.addTab(self.input_tab, load_svg_icon(AppIcons.PLUS, 16), "Nhập tài khoản")

        self.list_tab = QWidget()
        list_layout = QHBoxLayout(self.list_tab)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(12)
        list_layout.addWidget(self.create_right_panel(), 5)
        log_panel = QFrame()
        log_layout = QVBoxLayout(log_panel)
        log_layout.addWidget(QLabel("Nhật ký"))
        self.log_text.show()
        self.log_text.setMinimumWidth(0)
        self.log_text.setObjectName("activityLog")
        self.log_text.setFont(QFont("Consolas", 8))
        self.log_text.setMaximumHeight(16777215)
        log_layout.addWidget(self.log_text)
        log_panel.setMinimumWidth(180)
        list_layout.addWidget(log_panel, 1)
        self.tab_widget.addTab(self.list_tab, load_svg_icon(AppIcons.FOLDER_OPEN, 16), "Danh sách tài khoản")
        self.campaigns = []
        self.campaign_tab = self.create_campaign_tab()
        self.tab_widget.addTab(self.campaign_tab, load_svg_icon(AppIcons.CHECK, 16), "Chi\u1ebfn d\u1ecbch")

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng")

    def create_campaign_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        heading = QLabel("Qu\u1ea3n l\u00fd chi\u1ebfn d\u1ecbch")
        heading.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(heading)
        explanation = QLabel("L\u01b0u link v\u00e0 th\u1eddi gian t\u1eebng\u00a0\u0111\u1ee3t. M\u1edf trang ch\u00ednh th\u1ee9c \u0111\u1ec3 t\u1ef1 xem th\u1ec3 l\u1ec7 v\u00e0 \u0111\u0103ng k\u00fd.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        actions = QHBoxLayout()
        for label, handler in (("Th\u00eam chi\u1ebfn d\u1ecbch", self.add_campaign), ("S\u1eeda", self.edit_campaign),
                               ("M\u1edf trang ch\u00ednh th\u1ee9c", self.open_campaign), ("X\u00f3a", self.delete_campaign)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.campaign_table = QTableWidget(0, 5)
        self.campaign_table.setHorizontalHeaderLabels(["T\u00ean", "Link", "M\u1edf \u0111\u0103ng k\u00fd", "\u0110\u00f3ng \u0111\u0103ng k\u00fd", "Ghi ch\u00fa"])
        self.campaign_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.campaign_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.campaign_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.campaign_table.setAlternatingRowColors(True)
        for col, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.Stretch)):
            self.campaign_table.horizontalHeader().setSectionResizeMode(col, mode)
        layout.addWidget(self.campaign_table, 1)
        return tab

    def refresh_campaign_table(self):
        self.campaign_table.setRowCount(len(self.campaigns))
        keys = ("name", "url", "opens_at", "closes_at", "notes")
        for row, campaign in enumerate(self.campaigns):
            for col, key in enumerate(keys):
                self.campaign_table.setItem(row, col, QTableWidgetItem(campaign.get(key, "")))

    def selected_campaign_row(self):
        row = self.campaign_table.currentRow()
        if row < 0 or row >= len(self.campaigns):
            QMessageBox.information(self, "Chi\u1ebfn d\u1ecbch", "H\u00e3y ch\u1ecdn m\u1ed9t chi\u1ebfn d\u1ecbch tr\u01b0\u1edbc.")
            return None
        return row

    def save_campaigns(self):
        self.ui_settings.setValue("campaigns", json.dumps(self.campaigns, ensure_ascii=False))
        self.ui_settings.sync()
        self.refresh_campaign_table()

    def add_campaign(self):
        dialog = CampaignDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        campaign = dialog.get_campaign()
        if not campaign["name"] or urlparse(campaign["url"]).scheme not in {"http", "https"}:
            QMessageBox.warning(self, "Th\u00f4ng tin ch\u01b0a h\u1ee3p l\u1ec7", "Nh\u1eadp t\u00ean chi\u1ebfn d\u1ecbch v\u00e0 link http:// ho\u1eb7c https://.")
            return
        self.campaigns.append(campaign)
        self.save_campaigns()

    def edit_campaign(self):
        row = self.selected_campaign_row()
        if row is None:
            return
        dialog = CampaignDialog(self.campaigns[row], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        campaign = dialog.get_campaign()
        if not campaign["name"] or urlparse(campaign["url"]).scheme not in {"http", "https"}:
            QMessageBox.warning(self, "Th\u00f4ng tin ch\u01b0a h\u1ee3p l\u1ec7", "Nh\u1eadp t\u00ean chi\u1ebfn d\u1ecbch v\u00e0 link http:// ho\u1eb7c https://.")
            return
        self.campaigns[row] = campaign
        self.save_campaigns()

    def open_campaign(self):
        row = self.selected_campaign_row()
        if row is not None:
            webbrowser.open(self.campaigns[row]["url"])

    def delete_campaign(self):
        row = self.selected_campaign_row()
        if row is None:
            return
        del self.campaigns[row]
        self.save_campaigns()

    def create_toolbar(self):
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setStyleSheet("QToolBar { border: none; padding: 10px; }")
        
        # Title
        title = QLabel()
        logo = QPixmap(os.path.join(os.path.dirname(__file__), "icons", "logo.png"))
        title.setPixmap(logo.scaled(190, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title.setToolTip("NAMCO Account Manager")
        self.toolbar.addWidget(title)
        
        self.toolbar.addSeparator()
        
        # Import Button
        import_btn = QPushButton(" Import TXT")
        import_btn.setIcon(load_svg_icon(AppIcons.FOLDER_OPEN, 20, "#087f75"))
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
        check_btn = QPushButton(" Ki\u1ec3m tra t\u1ea5t c\u1ea3 t\u00e0i kho\u1ea3n")
        check_btn.setIcon(load_svg_icon(AppIcons.CHECK, 20, "#087f75"))
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
        delete_btn = QPushButton(" Xóa đã chọn")
        delete_btn.setIcon(load_svg_icon(AppIcons.TRASH, 20, "#087f75"))
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
        self.stats_label = QLabel("0 tài khoản")
        self.stats_label.setStyleSheet("color: #666; font-size: 14px;")
        self.toolbar.addWidget(self.stats_label)

        appearance_btn = QPushButton("Giao diện")
        appearance_btn.setToolTip("Tùy chỉnh màu sắc, cỡ chữ và mật độ bảng")
        appearance_btn.clicked.connect(self.open_appearance_settings)
        self.toolbar.addWidget(appearance_btn)

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
        title = QLabel("Nhập tài khoản")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # Format hint
        hint = QLabel("Định dạng: email|mởi dòng 1 tài khoản")
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
        
        add_btn = QPushButton(" Thêm vào danh sách")
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
        
        clear_btn = QPushButton(" Xóa")
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
        actions_group = QGroupBox("Thao tác nhanh")
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
        check_single_btn = QPushButton(" Kiểm tra tài khoản đầu tiên")
        check_single_btn.setIcon(load_svg_icon(AppIcons.CHECK, 18))
        check_single_btn.clicked.connect(self.check_first_account)
        actions_layout.addWidget(check_single_btn)
        
        # Export
        export_btn = QPushButton(" Export danh sách")
        export_btn.setIcon(load_svg_icon(AppIcons.DOWNLOAD, 18))
        export_btn.clicked.connect(self.export_accounts)
        actions_layout.addWidget(export_btn)
        
        layout.addWidget(actions_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Log
        log_label = QLabel("Nhật ký:")
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
        title = QLabel("Danh sách tài khoản")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "STT", "Email", "Mật khẩu", "Trạng thái", "Kiểm tra lần cuối"
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
        filter_label = QLabel("Lọc:")
        filter_layout.addWidget(filter_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tất cả", "Hoạt động", "Không hoạt động", "Chưa kiểm tra"])
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_combo)
        
        filter_layout.addStretch()
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm kiếm email...")
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input)
        
        layout.addLayout(filter_layout)
        
        return panel

    def apply_styles(self):
        theme = self.ui_settings.value("theme", "light")
        accent = self.ui_settings.value("accent", "#d61718")
        font_size = int(self.ui_settings.value("font_size", 9))
        compact = self.ui_settings.value("compact", False, type=bool)
        if theme not in ("light", "dark"):
            theme = "light"
        if accent not in ("#d61718", "#2864c5", "#168578"):
            accent = "#d61718"

        if theme == "dark":
            bg, surface, text, muted, border, alternate = "#171a21", "#222733", "#edf0f6", "#aab3c2", "#394252", "#1d222c"
            selected_row, hover_row = "#39414d", "#2b313c"
        else:
            bg, surface, text, muted, border, alternate = "#f3f5f8", "#ffffff", "#202633", "#687386", "#dce2ea", "#f5f7fa"
            selected_row, hover_row = "#e2e6eb", "#f0f2f4"

        # Clear the old per-widget colors so every screen follows the selected theme.
        for widget in self.findChildren(QWidget):
            widget.setStyleSheet("")
        row_padding = 4 if compact else 9
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {bg}; color: {text}; font-size: {font_size}pt; }}
            QToolBar {{ background: {surface}; border: 0; padding: 10px; spacing: 8px; }}
            QTabWidget::pane {{ background: {bg}; border: 0; }}
            QTabBar::tab {{ background: {surface}; color: {muted}; padding: 10px 18px; margin-right: 4px; border: 1px solid {border}; border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px; }}
            QTabBar::tab:selected {{ color: {accent}; font-weight: 700; background: {bg}; }}
            QFrame {{ background: {surface}; border: 1px solid {border}; border-radius: 8px; }}
            QPushButton {{ background: #b8fff5; color: #102322; border: 1px solid #3ff2d7; padding: 8px 13px; border-radius: 6px; font-weight: 600; }}
            QPushButton:hover {{ background: #93f7e9; border-color: #20ccb7; color: #102322; }}
            QPushButton:pressed {{ background: #72ead8; }}
            QLineEdit, QTextEdit, QComboBox {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 6px; padding: 7px; selection-background-color: {accent}; }}
            QTextEdit#activityLog {{ font-size: 8pt; }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 2px solid {accent}; }}
            QTableWidget {{ background: {surface}; alternate-background-color: {alternate}; color: {text}; gridline-color: {border}; border: 1px solid {border}; outline: none; selection-background-color: {selected_row}; selection-color: {text}; }}
            QHeaderView::section {{ background: {alternate}; color: {text}; padding: {row_padding}px; border: 0; border-bottom: 2px solid {border}; font-weight: 700; }}
            QTableWidget::item {{ padding: {row_padding}px; border-bottom: 1px solid {border}; }}
            QTableWidget::item:selected, QTableWidget::item:selected:hover {{ background: {selected_row}; color: {text}; border: 0; }}
            QTableWidget::item:hover {{ background: {hover_row}; color: {text}; }}
            QTableWidget::item:focus {{ outline: none; border: 0; }}
            QGroupBox {{ border: 1px solid {border}; border-radius: 7px; margin-top: 12px; padding: 12px 8px 8px; font-weight: 600; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
            QStatusBar {{ background: {surface}; color: {muted}; border-top: 1px solid {border}; }}
            QProgressBar {{ background: {alternate}; border: 0; border-radius: 5px; text-align: center; }}
            QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
            QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; }}
            QMenu::item:selected {{ background: {accent}; color: white; }}
        """)

    def open_appearance_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Tùy chỉnh giao diện")
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        title = QLabel("Cá nhân hóa không gian làm việc")
        title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        layout.addWidget(title)
        description = QLabel("Lưu trên máy tính này để dùng lại ở lần mở ứng dụng tiếp theo.")
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        theme = QComboBox()
        theme.addItem("Sáng", "light")
        theme.addItem("Tối", "dark")
        theme.setCurrentIndex(max(0, theme.findData(self.ui_settings.value("theme", "light"))))
        form.addRow("Chế độ màu", theme)
        accent = QComboBox()
        for label, color in (("Đỏ NAMCO", "#d61718"), ("Xanh dương", "#2864c5"), ("Xanh ngọc", "#168578")):
            accent.addItem(label, color)
        accent.setCurrentIndex(max(0, accent.findData(self.ui_settings.value("accent", "#d61718"))))
        form.addRow("Màu nhấn", accent)
        font_size = QComboBox()
        for size, label in ((8, "Nhỏ"), (9, "Tiêu chuẩn"), (10, "Lớn")):
            font_size.addItem(label, size)
        font_size.setCurrentIndex(max(0, font_size.findData(int(self.ui_settings.value("font_size", 9)))))
        form.addRow("Cỡ chữ", font_size)
        density = QComboBox()
        density.addItem("Thoáng", False)
        density.addItem("Gọn", True)
        density.setCurrentIndex(max(0, density.findData(self.ui_settings.value("compact", False, type=bool))))
        form.addRow("Mật độ bảng", density)
        layout.addLayout(form)

        preview = QLabel("Xem trước  ·  Email tài khoản  ·  Đang hoạt động")
        preview.setMinimumHeight(52)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet(f"border: 1px solid {accent.currentData()}; border-radius: 8px; padding: 8px; color: {accent.currentData()}; font-weight: 600;")
        accent.currentIndexChanged.connect(lambda: preview.setStyleSheet(f"border: 1px solid {accent.currentData()}; border-radius: 8px; padding: 8px; color: {accent.currentData()}; font-weight: 600;"))
        layout.addWidget(preview)

        buttons = QDialogButtonBox()
        save_button = buttons.addButton("Lưu tùy chọn", QDialogButtonBox.ButtonRole.AcceptRole)
        reset_button = buttons.addButton("Mặc định", QDialogButtonBox.ButtonRole.ResetRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        reset_button.clicked.connect(lambda: (theme.setCurrentIndex(0), accent.setCurrentIndex(0), font_size.setCurrentIndex(1), density.setCurrentIndex(0)))
        save_button.clicked.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.ui_settings.setValue("theme", theme.currentData())
            self.ui_settings.setValue("accent", accent.currentData())
            self.ui_settings.setValue("font_size", font_size.currentData())
            self.ui_settings.setValue("compact", density.currentData())
            self.ui_settings.sync()
            QApplication.setFont(QFont("Segoe UI", int(font_size.currentData())))
            self.apply_styles()
            self.status_bar.showMessage("Đã áp dụng giao diện", 3000)

    # ============================================================
    # DATA MANAGEMENT
    # ============================================================
    def load_data(self):
        try:
            stored_campaigns = self.ui_settings.value("campaigns", "[]")
            self.campaigns = json.loads(stored_campaigns) if isinstance(stored_campaigns, str) else stored_campaigns
            if not isinstance(self.campaigns, list):
                self.campaigns = []
            self.refresh_campaign_table()
        except (TypeError, ValueError):
            self.campaigns = []
            self.refresh_campaign_table()
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.accounts = json.load(f)
                self.log(f"Đã tải {len(self.accounts)} tài khoản từ file")
                self.update_table()
            except Exception as e:
                self.log(f"Lỗi tải dữ liệu: {e}")

    def save_data(self):
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.accounts, f, ensure_ascii=False, indent=2)
            self.log(f"Đã lưu {len(self.accounts)} tài khoản")
        except Exception as e:
            self.log(f"Lỗi lưu dữ liệu: {e}")

    # ============================================================
    # ACCOUNT OPERATIONS
    # ============================================================
    def add_account(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.Accepted:
            email, password = dialog.get_data()
            if email and password:
                if self.add_single_account(email, password):
                    self.log(f"Đã thêm: {email}")
                    self.update_table()
                    self.save_data()

    def add_from_text(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập dữ liệu!")
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
        
        self.log(f"Thêm: {added} | Bỏ qua (trùng): {skipped}")
        self.update_table()
        self.save_data()
        
        QMessageBox.information(
            self, "Hoàn tất",
            f"Đã thêm: {added} tài khoản\nBỏ qua (trùng): {skipped} tài khoản"
        )

    def add_single_account(self, email, password):
        # Kiểm tra trùng lặp
        for acc in self.accounts:
            if acc['email'] == email:
                return False
        
        self.accounts.append({
            'email': email,
            'password': password,
            'status': 'Chưa kiểm tra',
            'last_check': None
        })
        return True

    def import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file TXT", "", "Text Files (*.txt);;All Files (*)"
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
            
            self.log(f"Import: +{added} | Bỏ qua: {skipped}")
            self.update_table()
            self.save_data()
            
            QMessageBox.information(
                self, "Import hoàn tất",
                f"Đã thêm: {added} tài khoản\nBỏ qua (trùng): {skipped} tài khoản"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc file: {e}")

    def delete_selected(self):
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn tài khoản cần xóa!")
            return
        
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Bạn có chắc muốn xóa {len(selected_rows)} tài khoản đã chọn?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Xóa từ cuối lên để không lỗi index
            for row in sorted(selected_rows, reverse=True):
                if row < len(self.accounts):
                    del self.accounts[row]
            
            self.update_table()
            self.save_data()
            self.log(f"Đã xóa {len(selected_rows)} tài khoản")

    # ============================================================
    # CHECK ACCOUNTS
    # ============================================================
    def check_all_accounts(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cảnh báo", "Không có tài khoản nào!")
            return
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.accounts))
        self.progress_bar.setValue(0)
        
        # Chuẩn bị danh sách
        accounts_to_check = [(acc['email'], acc['password']) for acc in self.accounts]
        
        # Tạo worker
        self.worker = BatchCheckWorker(accounts_to_check)
        self.worker.result_ready.connect(self.on_check_result)
        self.worker.profile_ready.connect(self.on_profile_ready)
        self.worker.progress.connect(self.on_check_progress)
        self.worker.finished_checking.connect(self.on_check_finished)
        self.worker.start()
        
        self.log(f"Bắt đầu kiểm tra {len(accounts_to_check)} tài khoản...")

    def check_first_account(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cảnh báo", "Không có tài khoản nào!")
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
        
        self.log(f"Đang kiểm tra: {acc['email']}")

    def on_single_result(self, index, email, success, message):
        self.accounts[index]['status'] = "Hoạt động" if success else "Không hoạt động"
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
                profile_fields = {
                    key: value for key, value in profile.items()
                    if key not in {"email", "password", "status", "last_check", "profile_fetch_status", "parks2_handoff_status"}
                    and value not in (None, "")
                }
                if profile_fields:
                    handoff_warning = profile.get("parks2_handoff_status")
                    message = f"{email}: đã đọc được {len(profile_fields)} trường hồ sơ"
                    if handoff_warning:
                        message += f" (cảnh báo handoff: {handoff_warning})"
                    self.log(message)
                else:
                    status = profile.get("profile_fetch_status", "Không có dữ liệu hồ sơ")
                    self.log(f"{email}: đăng nhập thành công nhưng chưa đọc được hồ sơ ({status})")
                return

    def show_account_details(self, row, column=0):
        if row < 0 or row >= len(self.accounts):
            return
        account = self.accounts[row]
        dialog = AccountDetailsDialog(account, self)
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.updated_name()
            changed_name = {
                key: value for key, value in new_name.items()
                if value != account.get("last_name_kanji" if key == "last_name" else "first_name_kanji", "")
            }
            if changed_name:
                self.execute_change_name(row, account, changed_name)

    def on_check_result(self, email, success, message):
        # Tìm account theo email
        for acc in self.accounts:
            if acc['email'] == email:
                acc['status'] = "Hoạt động" if success else "Không hoạt động"
                acc['last_check'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        
        self.update_table()
        self.log(f"{email}: {message}")

    def on_check_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f"Đang kiểm tra: {current}/{total}")

    def on_check_finished(self):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Hoàn tất kiểm tra")
        self.save_data()
        self.log("Hoàn tất kiểm tra tất cả tài khoản")

    # ============================================================
    # UI UPDATES
    # ============================================================
    def update_table(self):
        columns = [
            ("#", None), ("Email", "email"), ("Password", "__password__"),
            ("Status", "status"), ("Last check", "last_check"),
            ("Last name (Kanji)", "last_name_kanji"), ("First name (Kanji)", "first_name_kanji"),
            ("Last name (Kana)", "last_name_kana"), ("First name (Kana)", "first_name_kana"),
            ("Nickname", "nickname"), ("Gender", "gender"),
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
            if filter_text == "Hoạt động" and status != "Hoạt động":
                show = False
            elif filter_text == "Không hoạt động" and status != "Không hoạt động":
                show = False
            elif filter_text == "Chưa kiểm tra" and status != "Chưa kiểm tra":
                show = False
            
            # Filter by search
            if search_text and search_text not in email:
                show = False
            
            self.table.setRowHidden(i, not show)

    def export_accounts(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export danh sách", "accounts_export.txt", "Text Files (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for acc in self.accounts:
                    f.write(f"{acc['email']}|{acc['password']}\n")
            
            self.log(f"Đã export {len(self.accounts)} tài khoản")
            QMessageBox.information(self, "Hoàn tất", f"Đã export đến:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể export: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    # ============================================================
    # CONTEXT MENU
    # ============================================================
    def show_context_menu(self, position):
        """Hiển thị context menu khi chuột phải vào bảng"""
        menu = QMenu(self)
        
        # Lấy dòng được chọn
        row = self.table.rowAt(position.y())
        if row < 0 or row >= len(self.accounts):
            return
        
        # Các hành động
        change_name_action = QAction(load_svg_icon(AppIcons.EDIT), " Đổi tên", self)
        change_name_action.triggered.connect(lambda: self.change_account_name(row))
        menu.addAction(change_name_action)

        details_action = QAction("Xem thông tin tài khoản", self)
        details_action.triggered.connect(lambda: self.show_account_details(row))
        menu.addAction(details_action)
        
        menu.addSeparator()
        
        check_action = QAction(load_svg_icon(AppIcons.CHECK), " Kiểm tra tài khoản", self)
        check_action.triggered.connect(lambda: self.check_single_account(row))
        menu.addAction(check_action)
        
        copy_email_action = QAction(load_svg_icon(AppIcons.COPY), " Copy email", self)
        copy_email_action.triggered.connect(lambda: self.copy_email(row))
        menu.addAction(copy_email_action)
        
        menu.addSeparator()
        
        delete_action = QAction(load_svg_icon(AppIcons.TRASH), " Xóa tài khoản", self)
        delete_action.triggered.connect(lambda: self.delete_single_account(row))
        menu.addAction(delete_action)
        
        menu.exec(self.table.viewport().mapToGlobal(position))

    def copy_email(self, row):
        """Copy email vào clipboard"""
        if row < len(self.accounts):
            email = self.accounts[row]['email']
            QApplication.clipboard().setText(email)
            self.log(f"Đã copy email: {email}")

    def delete_single_account(self, row):
        """Xóa một tài khoản"""
        if row >= len(self.accounts):
            return
        
        email = self.accounts[row]['email']
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Bạn có chắc muốn xóa tài khoản {email}?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            del self.accounts[row]
            self.update_table()
            self.save_data()
            self.log(f"Đã xóa: {email}")

    # ============================================================
    # CHANGE NAME
    # ============================================================
    def change_account_name(self, row):
        """Mở dialog đổi tên cho tài khoản"""
        if row >= len(self.accounts):
            return
        
        acc = self.accounts[row]
        
        # Lấy thông tin tên hiện tại (cần đăng nhập để lấy)
        # Hiện tại dùng giá trị mặc định
        dialog = ChangeNameDialog(
            self, current_last_name=acc.get("last_name_kanji", ""),
            current_first_name=acc.get("first_name_kanji", "")
        )
        
        if dialog.exec() == QDialog.Accepted:
            name_data = dialog.get_data()
            
            # Kiểm tra ít nhất 1 trường có giá trị
            if not any(name_data.values()):
                QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập ít nhất 1 trường!")
                return
            
            # Xác nhận
            reply = QMessageBox.question(
                self, "Xác nhận đổi tên",
                f"Bạn có chắc muốn đổi tên tài khoản {acc['email']}?\n\n"
                f"Họ mới: {name_data.get('last_name', '(giữ nguyên)')}\n"
                f"Tên mới: {name_data.get('first_name', '(giữ nguyên)')}\n"
                f"Nickname: {name_data.get('nickname', '(giữ nguyên)')}",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.execute_change_name(row, acc, name_data)

    def execute_change_name(self, row, acc, name_data):
        """Thực hiện đổi tên"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        
        self.pending_name_changes[acc['email']] = dict(name_data)
        self.worker = ChangeNameWorker(acc['email'], acc['password'], name_data)
        self.worker.result_ready.connect(lambda email, success, msg: self.on_change_name_result(row, email, success, msg))
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.start()
        
        self.log(f'\u0110ang c\u1eadp nh\u1eadt h\u1ed3 s\u01a1: {acc["email"]}')

    def on_change_name_result(self, row, email, success, message):
        if success and email in self.pending_name_changes:
            changed = self.pending_name_changes.pop(email)
            account = next((item for item in self.accounts if item.get("email") == email), None)
            if account:
                if changed.get("last_name"):
                    account["last_name_kanji"] = changed["last_name"]
                if changed.get("first_name"):
                    account["first_name_kanji"] = changed["first_name"]
                self.save_data()
                self.update_table()
        elif not success:
            self.pending_name_changes.pop(email, None)

        self.progress_bar.setVisible(False)
        if success:
            self.log(f"\u2713 {email}: {message}")
            QMessageBox.information(self, "Th\u00e0nh c\u00f4ng", f"C\u1eadp nh\u1eadt h\u1ed3 s\u01a1 th\u00e0nh c\u00f4ng!\n{email}")
        else:
            self.log(f"\u2717 {email}: {message}")
            QMessageBox.warning(self, "Th\u1ea5t b\u1ea1i", f"C\u1eadp nh\u1eadt h\u1ed3 s\u01a1 th\u1ea5t b\u1ea1i!\n{message}")

    def closeEvent(self, event):
        # Dừng tất cả workers
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
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    window = AccountManager()
    window.show()
    
    sys.exit(app.exec())
