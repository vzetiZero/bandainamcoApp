"""Điểm khởi động NAMCO Account Manager.

Toàn bộ mã nguồn nằm trong gói app/ theo lớp MVC:
domain (luật thuần) - infrastructure (mạng, file, QSettings) - services - ui.
File này chỉ dựng QApplication và mở cửa sổ chính.
"""
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.ui.main_window import AccountManager


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = AccountManager()
    window.show()
    return sys.exit(app.exec())


if __name__ == "__main__":
    main()
