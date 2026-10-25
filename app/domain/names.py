"""Model form sửa hồ sơ Parks2: những trường nào thực sự đổi khi người dùng nhập."""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

NAME_FIELDS = ("L_NAME", "F_NAME", "L_KANA", "F_KANA", "NICKNAME")
# Framework của site cần field "trim" rỗng cho từng trường nhập, nếu thiếu nó bỏ qua submit.
TRIM_PREFIX = "jp.co.interfactory.framework.trim."
FIELD_TO_ATTR = {
    "L_NAME": "last_name",
    "F_NAME": "first_name",
    "L_KANA": "last_kana",
    "F_KANA": "first_kana",
    "NICKNAME": "nickname",
}

# GUI chỉ được phép sửa hai trường tên Kanji; các trường khác luôn gửi lại giá trị cũ.
KANJI_FIELDS = {"last_name": "L_NAME", "first_name": "F_NAME"}


def kanji_overrides(last_name: str = "", first_name: str = "") -> Dict[str, str]:
    """Tên Kanji người dùng nhập, quy về field của site; trường bỏ trống được loại ra."""
    pairs = {"last_name": last_name, "first_name": first_name}
    return {KANJI_FIELDS[key]: value for key, value in pairs.items() if value}


@dataclass
class NameForm:
    """Giá trị đang hiển thị trên trang member_regist.html?request=edit."""
    last_name: str = ""
    first_name: str = ""
    last_kana: str = ""
    first_kana: str = ""
    nickname: str = ""
    page: str = ""
    action: str = ""
    hidden: Dict[str, str] = field(default_factory=dict)
    submit: Optional[Tuple[str, str]] = None

    def current(self, field_name: str) -> str:
        return getattr(self, FIELD_TO_ATTR[field_name], "")

    def form_data(self, overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Dữ liệu POST: gửi lại mọi hidden input, chỉ thay field có trong overrides.

        Site yêu cầu gửi đủ trường (kana, nickname, token...); thiếu field nào là mất
        dữ liệu đó trên tài khoản. Giá trị ưu tiên: override -> giá trị đọc được
        từ input hiển thị -> hidden input cùng tên.
        """
        given = overrides or {}
        data = dict(self.hidden)
        for site_name in NAME_FIELDS:
            current = getattr(self, FIELD_TO_ATTR[site_name], "")
            data[site_name] = given.get(site_name) or current or self.hidden.get(site_name, "")
        for site_name in NAME_FIELDS:
            # Framework cần field "trim" rỗng cho từng trường nhập.
            data[TRIM_PREFIX + site_name] = ""
        if self.submit:
            data[self.submit[0]] = self.submit[1]
        return data

