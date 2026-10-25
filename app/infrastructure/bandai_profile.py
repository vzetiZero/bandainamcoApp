"""Đọc hồ sơ thành viên Parks2 bằng requests thuần - không Selenium, không Playwright."""
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import requests

from app.config import API_URL, CLIENT_ID, REDIRECT_URI
from app.infrastructure.http_cookies import apply_response_cookies, cookie_payload


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
    params.update({"code": code, "language": language, "cookie": cookie_payload(session)})
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
    apply_response_cookies(session, data)
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
