"""Hộp thoại nhập liệu: chỉ lo widget, không tự gọi mạng."""
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QTextEdit,
)

from app.domain.campaigns import parse_campaign_time

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
        ("profile_loaded_at", "Hồ sơ đọc lúc"), ("status", "Trạng thái"),
        ("last_check", "Kiểm tra lần cuối"),
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
        for field in (self.open_input, self.close_input):
            field.setPlaceholderText("YYYY-MM-DD HH:MM")
        layout.addRow("Tên chiến dịch:", self.name_input)
        layout.addRow("Link chính thức:", self.url_input)
        layout.addRow("Mở đăng ký:", self.open_input)
        layout.addRow("Đóng đăng ký:", self.close_input)
        layout.addRow("Ghi chú thể lệ:", self.notes_input)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def validate_and_accept(self):
        """Reject bad dates here so bad data never reaches storage."""
        for label, field in (("Mở đăng ký", self.open_input), ("Đóng đăng ký", self.close_input)):
            if field.text().strip() and parse_campaign_time(field.text()) is None:
                QMessageBox.warning(
                    self, "Thông tin chưa hợp lệ",
                    "%s sai định dạng. Dùng YYYY-MM-DD HH:MM, ví dụ 2026-10-20 10:00." % label,
                )
                return
        opens_at = parse_campaign_time(self.open_input.text())
        closes_at = parse_campaign_time(self.close_input.text())
        if opens_at and closes_at and closes_at <= opens_at:
            QMessageBox.warning(
                self, "Thông tin chưa hợp lệ",
                "Thời gian đóng đăng ký phải sau thời gian mở đăng ký.",
            )
            return
        self.accept()

    def get_campaign(self):
        return {
            "name": self.name_input.text().strip(),
            "url": self.url_input.text().strip(),
            "opens_at": self.open_input.text().strip(),
            "closes_at": self.close_input.text().strip(),
            "notes": self.notes_input.toPlainText().strip(),
        }
