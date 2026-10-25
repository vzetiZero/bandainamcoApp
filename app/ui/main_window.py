import os
from datetime import datetime
import webbrowser
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QProgressBar,
    QMenu, QFrame, QComboBox, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QTabWidget, QGroupBox, QSizePolicy, QAbstractItemView, QMainWindow, QStatusBar,
    QToolBar, QApplication, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent
from PySide6.QtGui import QAction, QIcon, QFont, QColor, QPixmap, QShortcut, QKeySequence

from icon_helper import load_svg_icon, AppIcons
from proxy_manager import MODE_PER_REQUEST, MODE_PER_SESSION, PROXY_FILE, proxy_manager

from app.config import DEFAULT_CONCURRENCY, ICONS_DIR, MAX_CONCURRENCY, PROXY_FORMAT_HINT
from app.container import build_container
from app.services.campaign_service import CampaignService
from app.domain.campaigns import (
    CAMPAIGN_SOON_WINDOW, CAMPAIGN_STATUS_CLOSED, CAMPAIGN_STATUS_COLORS,
    CAMPAIGN_STATUS_NOT_STARTED, CAMPAIGN_STATUS_OPEN, CAMPAIGN_STATUS_UNDETERMINED,
    campaign_status, format_campaign_remaining, parse_campaign_time,
)
from app.ui.delegates import EmailProgressDelegate, StatusDelegate
from app.ui.dialogs import AccountDetailsDialog, AddAccountDialog, CampaignDialog, ChangeNameDialog
from app.ui.styles import build_stylesheet, read_appearance
from app.ui.table_spec import ACCOUNT_COLUMNS, EMAIL_COLUMN, PROGRESS_ROLE
from app.ui.workers import BatchCheckWorker, ChangeNameWorker, LoginWorker, ProxyCheckWorker


class AccountManager(QMainWindow):
    def __init__(self, container=None):
        super().__init__()
        self.setWindowTitle("NAMCO Account Manager")
        logo_path = os.path.join(ICONS_DIR, "logo.png")
        self.setWindowIcon(QIcon(logo_path))
        self.setMinimumSize(1400, 800)
        
        # Dữ liệu
        self.workers = []
        self.pending_name_changes = {}
        # Phụ thuộc đi qua chai: test truyền chai giả (services + client giả) là chạy được.
        self.container = container or build_container(on_log=self.log)
        self.ui_settings = self.container.settings
        self.account_service = self.container.account_service
        self.campaign_service = self.container.campaign_service
        self.auth_client = self.container.auth_client
        self.name_client = self.container.name_client
        self.hidden_columns = set(self.ui_settings.get_json("hidden_account_columns", "[]"))
        self.sort_key = None
        self.sort_asc = True
        # email -> % đang xử lý của riêng tài khoản đó (chỉ sống lúc đang chạy)
        self.row_progress = {}
        self.max_workers = max(1, min(MAX_CONCURRENCY,
                                      self.ui_settings.get_int("max_workers",
                                                               DEFAULT_CONCURRENCY)))
        
        self.setup_ui()
        self.load_data()
        self.apply_styles()

    # View đọc dữ liệu qua services; không tự giữ bản sao danh sách.
    @property
    def accounts(self):
        return self.account_service.accounts

    @property
    def campaigns(self):
        return self.campaign_service.campaigns

    @property
    def campaign_signups(self):
        return self.campaign_service.signups

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

        self.input_panel = self.create_left_panel()
        self.input_dialog = QDialog(self)
        self.input_dialog.setWindowTitle("Nhập tài khoản")
        self.input_dialog.resize(560, 480)
        input_dialog_layout = QVBoxLayout(self.input_dialog)
        input_dialog_layout.setContentsMargins(0, 0, 0, 0)
        input_dialog_layout.setSpacing(0)
        input_dialog_layout.addWidget(self.input_panel)

        self.list_tab = QWidget()
        list_layout = QHBoxLayout(self.list_tab)
        list_layout.setContentsMargins(12, 12, 12, 12)
        list_layout.setSpacing(12)
        list_layout.addWidget(self.create_right_panel(), 5)
        log_panel = QFrame()
        log_layout = QVBoxLayout(log_panel)
        log_layout.addWidget(QLabel("Nhật ký"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumWidth(0)
        self.log_text.setObjectName("activityLog")
        self.log_text.setFont(QFont("Consolas", 8))
        log_layout.addWidget(self.log_text)
        log_panel.setMinimumWidth(180)
        list_layout.addWidget(log_panel, 1)
        self.tab_widget.addTab(self.list_tab, load_svg_icon(AppIcons.FOLDER_OPEN, 16), "Danh sách tài khoản")
        # campaigns và campaign_signups thuộc CampaignService, đã load trong load_data.
        self.campaign_states = {}   # row -> trạng thái, để cảnh báo mở đăng ký đúng 1 lần
        self.signup_account_emails = ()  # chữ ký danh sách tài khoản, để chỉ dựng combo khi đổi
        self.campaign_tab = self.create_campaign_tab()
        self.tab_widget.addTab(self.campaign_tab, load_svg_icon(AppIcons.CHECK, 16), "Chi\u1ebfn d\u1ecbch")

        self.settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(self.settings_tab, load_svg_icon(AppIcons.SETTINGS, 16), "C\u1ea5u h\u00ecnh")

        # Ph\u00edm t\u1eaft to\u00e0n c\u1ee5c
        input_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        input_shortcut.activated.connect(self.open_input_dialog)
        import_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        import_shortcut.activated.connect(self.import_from_txt)
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self.focus_search)
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.delete_selected)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng")

        # Proxy settings (sau khi status bar sẵn sàng để báo trạng thái)
        self.load_proxy_settings()

    def create_campaign_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        heading = QLabel("Qu\u1ea3n l\u00fd chi\u1ebfn d\u1ecbch")
        heading.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(heading)
        explanation = QLabel(
            "Mỗi chiến dịch là một dòng riêng. Trạng thái được tính tự động từ thời gian "
            "mở/đóng đăng ký, nên chỉ cần thêm dòng khi có chiến dịch mới và sửa khi link "
            "hoặc ngày của chính chiến dịch đó thay đổi. Để trống ngày nếu không xác định."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Lọc:"))
        self.campaign_filter_combo = QComboBox()
        for label, key in (("Tất cả", "all"), ("Đang mở", CAMPAIGN_STATUS_OPEN),
                           ("Sắp mở trong 24h", "soon"), ("Chưa mở", CAMPAIGN_STATUS_NOT_STARTED),
                           ("Đã đóng", CAMPAIGN_STATUS_CLOSED),
                           ("Chưa rõ ngày", CAMPAIGN_STATUS_UNDETERMINED)):
            self.campaign_filter_combo.addItem(label, key)
        self.campaign_filter_combo.currentIndexChanged.connect(self.apply_campaign_filter)
        filter_row.addWidget(self.campaign_filter_combo)
        filter_row.addWidget(QLabel("Tìm:"))
        self.campaign_search_input = QLineEdit()
        self.campaign_search_input.setPlaceholderText("Tên hoặc link")
        self.campaign_search_input.textChanged.connect(self.apply_campaign_filter)
        filter_row.addWidget(self.campaign_search_input, 1)
        layout.addLayout(filter_row)

        actions = QHBoxLayout()
        for label, handler in (("Thêm chiến dịch", self.add_campaign), ("Sửa", self.edit_campaign),
                               ("Mở trang chính thức", self.open_campaign),
                               ("Xóa", self.delete_campaign),
                               ("Export danh sách", self.export_campaigns)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch(1)
        self.campaign_summary_label = QLabel("")
        actions.addWidget(self.campaign_summary_label)
        layout.addLayout(actions)

        self.campaign_table = QTableWidget(0, 8)
        self.campaign_table.setHorizontalHeaderLabels(
            ["Tên", "Link", "Mở đăng ký", "Đóng đăng ký", "Trạng thái", "Còn lại",
             "Đã đăng ký", "Ghi chú"])
        self.campaign_table.itemSelectionChanged.connect(self.update_signup_panel)
        self.campaign_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.campaign_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.campaign_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.campaign_table.setAlternatingRowColors(True)
        for col, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            self.campaign_table.horizontalHeader().setSectionResizeMode(col, mode)
        layout.addWidget(self.campaign_table, 1)

        # Đăng ký thủ công: mở link + chép thông tin tài khoản, người dùng tự bấm submit
        signup_group = QGroupBox("Đăng ký thủ công theo chiến dịch")
        signup_layout = QVBoxLayout(signup_group)
        hint = QLabel(
            "Chọn một dòng chiến dịch và một tài khoản, bấm Mở trang chiến dịch để ra trình duyệt. "
            "App chỉ chép sẵn thông tin vào clipboard — bạn tự dán và tự bấm submit. "
            "Xong thì bấm Ghi nhận để lưu tài khoản đã đăng ký cho chiến dịch này."
        )
        hint.setWordWrap(True)
        signup_layout.addWidget(hint)

        signup_row = QHBoxLayout()
        signup_row.addWidget(QLabel("Chiến dịch:"))
        self.signup_campaign_label = QLabel("(chọn dòng trong bảng)")
        signup_row.addWidget(self.signup_campaign_label, 2)
        signup_row.addWidget(QLabel("Tài khoản:"))
        self.signup_account_combo = QComboBox()
        self.signup_account_combo.setMinimumWidth(240)
        self.signup_account_combo.setToolTip("Tài khoản sẽ mở trang chiến dịch và chép vào clipboard")
        signup_row.addWidget(self.signup_account_combo, 2)
        self.signup_copy_password = QCheckBox("Chép cả mật khẩu")
        self.signup_copy_password.setToolTip(
            "Tắt (mặc định) chỉ chép email. Bật để chép cả email và mật khẩu, dán bằng Ctrl+V.")
        signup_row.addWidget(self.signup_copy_password)
        signup_layout.addLayout(signup_row)

        signup_actions = QHBoxLayout()
        for label, handler, tip in (
            ("Mở trang chiến dịch", self.open_campaign_with_account,
             "Mở link chiến dịch trong trình duyệt và chép email (tùy chọn mật khẩu) vào clipboard"),
            ("Ghi nhận đã đăng ký", self.mark_account_registered,
             "Lưu tài khoản đang chọn vào danh sách đã đăng ký của chiến dịch này"),
            ("Xoá ghi nhận", self.unmark_account_registered,
             "Bỏ tài khoản đang chọn khỏi danh sách đã đăng ký của chiến dịch này"),
            ("Xem danh sách đã đăng ký", self.show_campaign_signups,
             "Xem các tài khoản đã đăng ký cho chiến dịch đang chọn"),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            signup_actions.addWidget(button)
        signup_actions.addStretch(1)
        self.signup_summary_label = QLabel("")
        signup_actions.addWidget(self.signup_summary_label)
        signup_layout.addLayout(signup_actions)
        layout.addWidget(signup_group)

        # Làm mới trạng thái định kỳ để không phải bấm tay khi tới giờ mở/đóng
        self.campaign_timer = QTimer(self)
        self.campaign_timer.timeout.connect(self.refresh_campaign_table)
        self.campaign_timer.start(60_000)
        return tab

    # ============================================================
    # TAB CẤU HÌNH - PROXY
    # ============================================================
    def create_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self.proxy_check_worker = None

        heading = QLabel("C\u1ea5u h\u00ecnh")
        heading.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(heading)

        proxy_group = QGroupBox("Proxy cho request")
        proxy_layout = QVBoxLayout(proxy_group)

        explanation = QLabel(
            "M\u1ed7i request (\u0111\u0103ng nh\u1eadp, ki\u1ec3m tra t\u00e0i kho\u1ea3n, \u0111\u1ed5i t\u00ean) s\u1ebd d\u00f9ng proxy l\u1ea5y t\u1eeb file "
            "proxy.txt theo \u0111\u1ecbnh d\u1ea1ng ip:port:username:pass. Khi t\u1ebft proxy, request \u0111i th\u1eb3ng nh\u01b0 tr\u01b0\u1edbc."
        )
        explanation.setWordWrap(True)
        proxy_layout.addWidget(explanation)

        self.proxy_enabled = QCheckBox("B\u1ebft proxy cho t\u1ea5t c\u1ea3 request")
        self.proxy_enabled.setToolTip("T\u1eaft l\u1ebfn b\u1ecdc t\u1ea5t c\u1ea3 request \u0111i qua proxy trong file")
        self.proxy_enabled.toggled.connect(self.on_proxy_settings_changed)
        proxy_layout.addWidget(self.proxy_enabled)

        form = QFormLayout()
        file_row = QHBoxLayout()
        self.proxy_file_input = QLineEdit()
        self.proxy_file_input.setPlaceholderText(PROXY_FILE)
        self.proxy_file_input.setToolTip("\u0110\u01b0\u1eddng d\u1eabn \u0111\u1ebfn file danh s\u00e1ch proxy")
        browse_button = QPushButton("Ch\u1ecdn file...")
        browse_button.clicked.connect(self.browse_proxy_file)
        reload_button = QPushButton("T\u1ea3i l\u1ea1i")
        reload_button.clicked.connect(self.reload_proxy_file)
        file_row.addWidget(self.proxy_file_input, 1)
        file_row.addWidget(browse_button)
        file_row.addWidget(reload_button)
        form.addRow("File proxy:", file_row)

        format_hint = QLabel("%s  (mỗi dòng một proxy, dòng bắt đầu bằng #)" % PROXY_FORMAT_HINT)
        format_hint.setWordWrap(True)
        form.addRow("\u0110\u1ecbnh d\u1ea1ng:", format_hint)

        self.proxy_mode_combo = QComboBox()
        self.proxy_mode_combo.addItem("Luân phiên theo từng request", MODE_PER_REQUEST)
        self.proxy_mode_combo.addItem("Mỗi phiên dùng 1 proxy (mỗi tài khoản 1 proxy)", MODE_PER_SESSION)
        self.proxy_mode_combo.setToolTip("Chọn cách phân bổ proxy cho các request")
        self.proxy_mode_combo.currentIndexChanged.connect(self.on_proxy_settings_changed)
        form.addRow("Chế độ:", self.proxy_mode_combo)
        proxy_layout.addLayout(form)

        actions = QHBoxLayout()
        check_button = QPushButton("Kiểm tra proxy")
        check_button.setIcon(load_svg_icon(AppIcons.CHECK, 16))
        check_button.clicked.connect(self.check_proxies)
        open_button = QPushButton("Mở file proxy")
        open_button.setIcon(load_svg_icon(AppIcons.FOLDER_OPEN, 16))
        open_button.clicked.connect(self.open_proxy_file)
        actions.addWidget(check_button)
        actions.addWidget(open_button)
        actions.addStretch(1)
        proxy_layout.addLayout(actions)

        self.proxy_status_label = QLabel("")
        proxy_layout.addWidget(self.proxy_status_label)

        self.proxy_table = QTableWidget(0, 6)
        self.proxy_table.setHorizontalHeaderLabels(["#", "Host", "Port", "Username", "Password", "Trạng thái"])
        self.proxy_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.proxy_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.proxy_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.proxy_table.setAlternatingRowColors(True)
        self.proxy_table.verticalHeader().setVisible(False)
        for col, mode in enumerate((QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch)):
            self.proxy_table.horizontalHeader().setSectionResizeMode(col, mode)
        proxy_layout.addWidget(self.proxy_table, 1)

        layout.addWidget(self._create_concurrency_group())
        layout.addWidget(proxy_group, 1)
        return tab

    def _create_concurrency_group(self):
        """Nhóm cấu hình số tài khoản xử lý cùng lúc khi kiểm tra hàng loạt."""
        group = QGroupBox("Kiểm tra tài khoản")
        form = QFormLayout(group)
        hint = QLabel(
            "Khi chạy nhiều tài khoản cùng lúc, mỗi tài khoản vẫn là một phiên đăng nhập "
            "riêng (dùng proxy từ new_session()). Tăng số luồng thì nhanh hơn nhưng dồn "
            "request vào site và proxy nhiều hơn."
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        self.max_workers_input = QSpinBox()
        self.max_workers_input.setRange(1, MAX_CONCURRENCY)
        self.max_workers_input.setValue(self.max_workers)
        self.max_workers_input.setSuffix(" luồng")
        self.max_workers_input.setToolTip(f"Mặc định {DEFAULT_CONCURRENCY}, tối đa {MAX_CONCURRENCY}")
        self.max_workers_input.valueChanged.connect(self.on_concurrency_changed)
        form.addRow("Số luồng chạy đồng thời:", self.max_workers_input)
        return group

    def on_concurrency_changed(self, value):
        self.max_workers = max(1, min(MAX_CONCURRENCY, int(value)))
        self.ui_settings.set(max_workers=self.max_workers)
        self.status_bar.showMessage(f"Số luồng đồng thời: {self.max_workers}", 3000)

    def load_proxy_settings(self):
        """Nạp cấu hình proxy đã lưu và đọc file proxy.txt."""
        path = self.ui_settings.get("proxy_file", PROXY_FILE)
        if not isinstance(path, str) or not path.strip():
            path = PROXY_FILE
        mode = self.ui_settings.get("proxy_mode", MODE_PER_REQUEST)
        if mode not in (MODE_PER_REQUEST, MODE_PER_SESSION):
            mode = MODE_PER_REQUEST
        enabled = self.ui_settings.get_bool("proxy_enabled", False)

        widgets = (self.proxy_file_input, self.proxy_mode_combo, self.proxy_enabled)
        for widget in widgets:
            widget.blockSignals(True)
        self.proxy_file_input.setText(path)
        index = self.proxy_mode_combo.findData(mode)
        self.proxy_mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.proxy_enabled.setChecked(enabled)
        for widget in widgets:
            widget.blockSignals(False)

        self.apply_proxy_settings(reload_file=True)

    def on_proxy_settings_changed(self, *args):
        self.apply_proxy_settings()

    def apply_proxy_settings(self, reload_file=False):
        path = self.proxy_file_input.text().strip() or PROXY_FILE
        proxy_manager.path = path
        proxy_manager.mode = self.proxy_mode_combo.currentData() or MODE_PER_REQUEST
        proxy_manager.enabled = self.proxy_enabled.isChecked()
        if reload_file:
            proxy_manager.load()
        self.ui_settings.set(proxy_file=path, proxy_mode=proxy_manager.mode,
                             proxy_enabled=proxy_manager.enabled)
        if reload_file or self.proxy_table.rowCount() != len(proxy_manager.proxies):
            self.refresh_proxy_table()
        self.update_proxy_status()

    def update_proxy_status(self):
        status = proxy_manager.status_text()
        detail = "%s  ·  %s" % (status, proxy_manager.path)
        if proxy_manager.errors:
            detail += "  ·  bỏ qua %d dòng lỗi" % len(proxy_manager.errors)
        self.proxy_status_label.setText(detail)
        if proxy_manager.enabled and proxy_manager.proxies:
            scope = "mỗi request" if proxy_manager.mode == MODE_PER_REQUEST else "mỗi phiên"
            self.status_bar.showMessage("Proxy: %d (%s)" % (len(proxy_manager.proxies), scope), 4000)

    def refresh_proxy_table(self):
        proxies = proxy_manager.proxies
        self.proxy_table.setRowCount(len(proxies))
        for row, proxy in enumerate(proxies):
            password = proxy.get("password", "")
            values = [str(row + 1), proxy.get("host", ""), str(proxy.get("port", "")),
                      proxy.get("username", ""), ("\u2022" * 8) if password else "", "Chưa kiểm tra"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 2):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 4 and password:
                    item.setToolTip(password)
                self.proxy_table.setItem(row, col, item)

    def browse_proxy_file(self):
        start_dir = self.proxy_file_input.text().strip() or PROXY_FILE
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file proxy", os.path.dirname(start_dir),
            "Text files (*.txt);;All files (*)",
        )
        if path:
            self.proxy_file_input.setText(path)
            self.apply_proxy_settings(reload_file=True)

    def reload_proxy_file(self):
        self.apply_proxy_settings(reload_file=True)
        if not os.path.exists(proxy_manager.path):
            QMessageBox.information(self, "Proxy", "Không tìm thấy file:\n%s" % proxy_manager.path)
            return
        if proxy_manager.errors:
            preview = "\n".join("Dòng %d: %s" % (number, reason)
                                for number, _, reason in proxy_manager.errors[:5])
            QMessageBox.warning(self, "Proxy",
                                "%d dòng sai định dạng:\n%s" % (len(proxy_manager.errors), preview))
        self.log("Đã tải %d proxy từ %s" % (len(proxy_manager.proxies),
                                            os.path.basename(proxy_manager.path)))

    def open_proxy_file(self):
        path = self.proxy_file_input.text().strip() or PROXY_FILE
        if not os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("# Mỗi dòng 1 proxy theo định dạng: %s\n" % PROXY_FORMAT_HINT)
                    handle.write("# Ví dụ: 123.45.67.89:8080:myuser:mypassword\n")
            except OSError as exc:
                QMessageBox.warning(self, "Proxy", "Không tạo được file:\n%s" % exc)
                return
            self.apply_proxy_settings(reload_file=True)
        webbrowser.open(os.path.abspath(path))

    def check_proxies(self):
        if self.proxy_check_worker is not None and self.proxy_check_worker.isRunning():
            QMessageBox.information(self, "Kiểm tra proxy", "Đang kiểm tra proxy, vui lòng đợi.")
            return
        if not proxy_manager.proxies:
            QMessageBox.information(self, "Kiểm tra proxy",
                                    "Chưa có proxy để kiểm tra. Hãy tải file proxy.txt trước.")
            return
        for row in range(self.proxy_table.rowCount()):
            self.proxy_table.setItem(row, 5, QTableWidgetItem("Đang kiểm tra..."))
        self.proxy_check_worker = ProxyCheckWorker(proxy_manager.proxies)
        self.proxy_check_worker.row_ready.connect(self.on_proxy_check_result)
        self.proxy_check_worker.finished_check.connect(self.on_proxy_check_finished)
        self.proxy_check_worker.start()
        self.proxy_status_label.setText("Đang kiểm tra %d proxy..." % len(proxy_manager.proxies))
        self.log("Bắt đầu kiểm tra %d proxy..." % len(proxy_manager.proxies))

    def on_proxy_check_result(self, row, ok, message):
        if row < 0 or row >= self.proxy_table.rowCount():
            return
        item = QTableWidgetItem(("\u2713 " if ok else "\u2717 ") + message)
        item.setForeground(QColor("#168578") if ok else QColor("#dc3545"))
        item.setToolTip(message)
        self.proxy_table.setItem(row, 5, item)

    def on_proxy_check_finished(self):
        total = self.proxy_table.rowCount()
        working = sum(1 for row in range(total)
                      if (self.proxy_table.item(row, 5) or QTableWidgetItem("")).text().startswith("\u2713"))
        self.proxy_status_label.setText("Kiểm tra xong: %d/%d proxy hoạt động" % (working, total))
        self.log("Kiểm tra proxy: %d/%d hoạt động" % (working, total))
        self.status_bar.showMessage("Kiểm tra proxy: %d hoạt động" % working, 5000)

    def refresh_campaign_table(self):
        """Redraw the campaign table, deriving status and countdown from the dates."""
        now = datetime.now()
        previous_states = getattr(self, "campaign_states", {})
        states = {}
        self.campaign_table.setRowCount(len(self.campaigns))
        for row, campaign in enumerate(self.campaigns):
            status = campaign_status(campaign, now)
            states[row] = status
            remaining = format_campaign_remaining(campaign, now)
            values = [
                campaign.get("name", ""),
                campaign.get("url", ""),
                campaign.get("opens_at", ""),
                campaign.get("closes_at", ""),
                status,
                remaining,
                self.signup_count_text(campaign),
                campaign.get("notes", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 4:
                    item.setForeground(QColor(CAMPAIGN_STATUS_COLORS.get(status, "#8a94a6")))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                elif col in (5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 6 and value:
                    item.setForeground(QColor("#2864c5"))
                self.campaign_table.setItem(row, col, item)
        self.campaign_states = states
        self.update_campaign_summary(previous_states)
        self.apply_campaign_filter()

    def update_campaign_summary(self, previous_states=None):
        """Show how many campaigns are live, and warn once when one opens within 24h."""
        counts = {}
        for status in self.campaign_states.values():
            counts[status] = counts.get(status, 0) + 1
        summary = "Tổng %d" % len(self.campaigns)
        for status in (CAMPAIGN_STATUS_OPEN, CAMPAIGN_STATUS_NOT_STARTED,
                       CAMPAIGN_STATUS_CLOSED, CAMPAIGN_STATUS_UNDETERMINED):
            if counts.get(status):
                summary += "  ·  %s %d" % (status, counts[status])
        self.campaign_summary_label.setText(summary)

        now = datetime.now()
        for row, status in self.campaign_states.items():
            if status != CAMPAIGN_STATUS_NOT_STARTED:
                continue
            opens_at = parse_campaign_time(self.campaigns[row].get("opens_at"))
            if opens_at is None or opens_at - now > CAMPAIGN_SOON_WINDOW:
                continue
            if previous_states and previous_states.get(row) == status:
                continue
            name = self.campaigns[row].get("name") or "(chưa đặt tên)"
            message = "Chiến dịch %s mở đăng ký lúc %s" % (name, opens_at.strftime("%d/%m %H:%M"))
            self.status_bar.showMessage(message, 15000)
            self.log(message)

    def apply_campaign_filter(self, *args):
        """Hide rows that do not match the status filter and the search text."""
        selected = self.campaign_filter_combo.currentData()
        search_text = self.campaign_search_input.text().strip().lower()
        now = datetime.now()
        for row in range(self.campaign_table.rowCount()):
            campaign = self.campaigns[row] if row < len(self.campaigns) else {}
            status = self.campaign_states.get(row, campaign_status(campaign, now))
            show = True
            if selected == "soon":
                opens_at = parse_campaign_time(campaign.get("opens_at"))
                show = (status == CAMPAIGN_STATUS_NOT_STARTED and opens_at is not None
                        and opens_at - now <= CAMPAIGN_SOON_WINDOW)
            elif selected != "all" and selected != status:
                show = False
            if show and search_text:
                haystack = "%s %s" % (campaign.get("name", ""), campaign.get("url", ""))
                show = search_text in haystack.lower()
            self.campaign_table.setRowHidden(row, not show)

    def export_campaigns(self):
        """Write the campaign list to a pipe-separated text file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export danh sách chiến dịch", "campaigns_export.txt", "Text Files (*.txt)"
        )
        if not file_path:
            return
        now = datetime.now()
        try:
            with open(file_path, "w", encoding="utf-8") as fh:
                fh.write("# Tên | Mở | Đóng | Trạng thái | Còn lại | Link | Ghi chú\n")
                for campaign in self.campaigns:
                    fh.write("|".join([
                        campaign.get("name", ""),
                        campaign.get("opens_at", ""),
                        campaign.get("closes_at", ""),
                        campaign_status(campaign, now),
                        format_campaign_remaining(campaign, now),
                        campaign.get("url", ""),
                        campaign.get("notes", "").replace("\n", " "),
                    ]) + "\n")
            self.log("Đã export %d chiến dịch" % len(self.campaigns))
            QMessageBox.information(self, "Hoàn tất", "Đã export đến:\n%s" % file_path)
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi", "Không thể export: %s" % exc)

    def selected_campaign_row(self):
        row = self.campaign_table.currentRow()
        if row < 0 or row >= len(self.campaigns):
            QMessageBox.information(self, "Chiến dịch", "Hãy chọn một chiến dịch trước.")
            return None
        return row

    def save_campaigns(self):
        self.campaign_service.save()
        self.refresh_campaign_table()

    def add_campaign(self):
        dialog = CampaignDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        campaign = dialog.get_campaign()
        if not CampaignService.is_valid(campaign):
            QMessageBox.warning(self, "Thông tin chưa hợp lệ", "Nhập tên chiến dịch và link http:// hoặc https://.")
            return
        self.campaign_service.add(campaign)
        self.refresh_campaign_table()

    def edit_campaign(self):
        row = self.selected_campaign_row()
        if row is None:
            return
        dialog = CampaignDialog(self.campaigns[row], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        campaign = dialog.get_campaign()
        if not CampaignService.is_valid(campaign):
            QMessageBox.warning(self, "Thông tin chưa hợp lệ", "Nhập tên chiến dịch và link http:// hoặc https://.")
            return
        self.campaign_service.update(row, campaign)
        self.refresh_campaign_table()

    def open_campaign(self):
        row = self.selected_campaign_row()
        if row is not None:
            webbrowser.open(self.campaigns[row]["url"])

    def delete_campaign(self):
        row = self.selected_campaign_row()
        if row is None:
            return
        name = self.campaigns[row].get("name") or "(chưa đặt tên)"
        reply = QMessageBox.question(
            self, "Xác nhận", "Xóa chiến dịch %s?" % name, QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.campaign_service.remove(row)
            self.refresh_campaign_table()


    # ============================================================
    # ĐĂNG KÝ THỦ CÔNG THEO CHIẾN DỊCH
    # ============================================================
    @staticmethod
    def campaign_key(campaign):
        """Khoá ổn định của một chiến dịch, không đổi khi thứ tự dòng thay đổi."""
        return CampaignService.key(campaign)

    def save_signups(self):
        self.campaign_service.save_signups()
        self.refresh_campaign_table()

    def signups_for(self, campaign):
        return self.campaign_service.signups_for(campaign)

    def signup_count_text(self, campaign):
        count = len(self.signups_for(campaign))
        return "%d tài khoản" % count if count else "—"

    def selected_account_email(self):
        email = self.signup_account_combo.currentData()
        return email or None

    def selected_account_record(self):
        """Trả (email, password) của tài khoản đang chọn trong combo."""
        email = self.selected_account_email()
        if not email:
            return None, None
        for account in self.accounts:
            if account.get("email") == email:
                return email, account.get("password", "")
        return email, ""

    def refresh_signup_accounts(self):
        """Dựng lại combo tài khoản, chỉ khi danh sách tài khoản thực sự thay đổi."""
        emails = tuple(account.get("email", "") for account in self.accounts)
        if emails == self.signup_account_emails:
            return
        self.signup_account_emails = emails
        current = self.signup_account_combo.currentData()
        self.signup_account_combo.blockSignals(True)
        self.signup_account_combo.clear()
        for email in emails:
            self.signup_account_combo.addItem(email, email)
        if current:
            index = self.signup_account_combo.findData(current)
            if index >= 0:
                self.signup_account_combo.setCurrentIndex(index)
        self.signup_account_combo.blockSignals(False)
        self.update_signup_panel()

    def update_signup_panel(self, *args):
        """Cập nhật nhãn chiến dịch và tổng kết số tài khoản đã đăng ký."""
        row = self.campaign_table.currentRow()
        if 0 <= row < len(self.campaigns):
            campaign = self.campaigns[row]
            status = self.campaign_states.get(row) or campaign_status(campaign)
            self.signup_campaign_label.setText(
                "%s (%s)" % (campaign.get("name") or "(chưa đặt tên)", status))
            count = len(self.signups_for(campaign))
            self.signup_summary_label.setText(
                "Chiến dịch này: %d tài khoản đã đăng ký" % count)
        else:
            self.signup_campaign_label.setText("(chọn dòng trong bảng)")
            self.signup_summary_label.setText("")

    def open_campaign_with_account(self):
        """
        Mở trang chiến dịch kèm thông tin tài khoản trong clipboard.

        Cố tình KHÔNG điền form và KHÔNG submit: đăng ký là thao tác thủ công của
        người dùng trên trang 抽選, app chỉ chuẩn bị sẵn để giảm việc gõ.
        """
        row = self.selected_campaign_row()
        if row is None:
            return
        email, password = self.selected_account_record()
        if not email:
            QMessageBox.information(self, "Đăng ký thủ công",
                                    "Chưa có tài khoản nào trong danh sách. Hãy thêm tài khoản trước.")
            return
        campaign = self.campaigns[row]
        # Mặc định chỉ chép email; bật checkbox mới chép kèm mật khẩu (dán bằng Ctrl+V vào 2 ô)
        clipboard = "%s\n%s" % (email, password) if self.signup_copy_password.isChecked() else email
        QApplication.clipboard().setText(clipboard)
        webbrowser.open(campaign["url"])
        detail = "email và mật khẩu" if self.signup_copy_password.isChecked() else "email"
        message = "Đã mở %s và chép %s của %s vào clipboard. Dán bằng Ctrl+V rồi tự bấm submit." % (
            campaign.get("name") or "trang chiến dịch", detail, email)
        self.status_bar.showMessage(message, 10000)
        self.log(message)

    def mark_account_registered(self):
        """Ghi nhận tài khoản đã đăng ký cho chiến dịch đang chọn."""
        row = self.selected_campaign_row()
        if row is None:
            return
        email = self.selected_account_email()
        if not email:
            QMessageBox.information(self, "Ghi nhận đăng ký",
                                    "Chọn một tài khoản trong ô Tài khoản trước khi ghi nhận.")
            return
        campaign = self.campaigns[row]
        if not self.campaign_service.mark(campaign, email):
            self.status_bar.showMessage("%s đã có trong danh sách của chiến dịch này" % email, 5000)
            return
        self.refresh_campaign_table()
        message = "Đã ghi nhận %s cho chiến dịch %s" % (
            email, campaign.get("name") or "(chưa đặt tên)")
        self.status_bar.showMessage(message, 6000)
        self.log(message)
        self.update_signup_panel()

    def unmark_account_registered(self):
        """Bỏ tài khoản khỏi danh sách đã đăng ký của chiến dịch đang chọn."""
        row = self.selected_campaign_row()
        if row is None:
            return
        email = self.selected_account_email()
        if not email:
            return
        campaign = self.campaigns[row]
        if not self.campaign_service.unmark(campaign, email):
            self.status_bar.showMessage("%s chưa được ghi nhận cho chiến dịch này" % email, 5000)
            return
        self.refresh_campaign_table()
        message = "Đã bỏ ghi nhận %s khỏi chiến dịch %s" % (
            email, campaign.get("name") or "(chưa đặt tên)")
        self.status_bar.showMessage(message, 6000)
        self.log(message)
        self.update_signup_panel()

    def show_campaign_signups(self):
        """Liệt kê tài khoản đã đăng ký cho chiến dịch đang chọn."""
        row = self.selected_campaign_row()
        if row is None:
            return
        campaign = self.campaigns[row]
        entries = self.signups_for(campaign)
        name = campaign.get("name") or "(chưa đặt tên)"
        if not entries:
            QMessageBox.information(self, "Danh sách đã đăng ký",
                                    "Chiến dịch %s chưa có tài khoản nào được ghi nhận." % name)
            return
        lines = ["Tài khoản đã đăng ký cho: %s" % name, ""]
        for entry in sorted(entries, key=lambda item: item.get("at", "")):
            lines.append("%s    (%s)" % (entry.get("email", ""), entry.get("at", "")))
        QMessageBox.information(self, "Danh sách đã đăng ký", "\n".join(lines))

    def create_toolbar(self):
        self.toolbar = QToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.toolbar.setStyleSheet("QToolBar { border: none; padding: 10px; }")
        
        # Title
        title = QLabel()
        logo = QPixmap(os.path.join(ICONS_DIR, "logo.png"))
        title.setPixmap(logo.scaled(190, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        title.setToolTip("NAMCO Account Manager")
        self.toolbar.addWidget(title)
        
        self.toolbar.addSeparator()
        
        # Input Button
        input_btn = QPushButton(" Nhập tài khoản")
        input_btn.setObjectName("toolInput")
        input_btn.setIcon(load_svg_icon(AppIcons.PLUS, 20, "#ffffff"))
        input_btn.setToolTip("Mở ô nhập tài khoản thủ công")
        input_btn.clicked.connect(self.open_input_dialog)
        self.toolbar.addWidget(input_btn)
        
        # Import Button
        import_btn = QPushButton(" Import TXT")
        import_btn.setObjectName("toolImport")
        import_btn.setIcon(load_svg_icon(AppIcons.FOLDER_OPEN, 20, "#ffffff"))
        import_btn.setToolTip("Nhập tài khoản từ file TXT")
        import_btn.clicked.connect(self.import_from_txt)
        self.toolbar.addWidget(import_btn)
        
        # Check All Button
        check_btn = QPushButton(" Ki\u1ec3m tra t\u1ea5t c\u1ea3 t\u00e0i kho\u1ea3n")
        check_btn.setObjectName("toolCheckAll")
        check_btn.setIcon(load_svg_icon(AppIcons.CHECK, 20, "#ffffff"))
        check_btn.setToolTip("Kiểm tra đăng nhập toàn bộ danh sách")
        check_btn.clicked.connect(self.check_all_accounts)
        self.toolbar.addWidget(check_btn)
        
        # Delete Selected Button
        delete_btn = QPushButton(" Xóa đã chọn")
        delete_btn.setObjectName("toolDelete")
        delete_btn.setIcon(load_svg_icon(AppIcons.TRASH, 20, "#ffffff"))
        delete_btn.setToolTip("Xóa các dòng đang chọn trong bảng")
        delete_btn.clicked.connect(self.delete_selected)
        self.toolbar.addWidget(delete_btn)
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)
        
        # Stats
        self.stats_label = QLabel("0 tài khoản")
        self.stats_label.setStyleSheet("color: #666; font-size: 14px;")
        self.toolbar.addWidget(self.stats_label)

        self.stats_chip = QLabel("")
        self.stats_chip.setObjectName("statsChip")
        self.toolbar.addWidget(self.stats_chip)

        appearance_btn = QPushButton("Giao diện")
        appearance_btn.setToolTip("Tùy chỉnh màu sắc, cỡ chữ và mật độ bảng")
        appearance_btn.clicked.connect(self.open_appearance_settings)
        self.toolbar.addWidget(appearance_btn)

    def open_input_dialog(self):
        self.input_dialog.show()
        self.input_dialog.raise_()
        self.input_dialog.activateWindow()
        self.text_input.setFocus()
        self.update_input_preview()

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
        hint = QLabel("Định dạng: email|password, mỗi dòng 1 tài khoản · có thể kéo thả file .txt vào ô dưới")
        hint.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(hint)
        
        # Text Input
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("email1|password1\nemail2|password2\n...")
        self.text_input.setAcceptDrops(True)
        self.text_input.installEventFilter(self)
        self.text_input.textChanged.connect(self.update_input_preview)
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
        
        self.input_preview = QLabel("")
        self.input_preview.setObjectName("inputPreview")
        self.input_preview.setWordWrap(True)
        layout.addWidget(self.input_preview)
        
        # Buttons - gọn, gom trên một hàng
        def compact_button(text, object_name, icon_name, tip):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setIcon(load_svg_icon(icon_name, 15))
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            return button

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        add_btn = compact_button("Thêm", "actionAdd", AppIcons.PLUS,
                                "Thêm các tài khoản trong ô nhập vào danh sách")
        add_btn.clicked.connect(self.add_from_text)
        btn_layout.addWidget(add_btn)

        clear_btn = compact_button("Xóa", "actionClear", AppIcons.X,
                                  "Xóa toàn bộ nội dung ô nhập")
        clear_btn.clicked.connect(self.text_input.clear)
        btn_layout.addWidget(clear_btn)

        check_single_btn = compact_button("Kiểm tra đầu tiên", "actionCheck", AppIcons.CHECK,
                                         "Kiểm tra tài khoản đầu tiên trong danh sách")
        check_single_btn.clicked.connect(self.check_first_account)
        btn_layout.addWidget(check_single_btn)

        export_btn = compact_button("Export", "actionExport", AppIcons.DOWNLOAD,
                                   "Export danh sách tài khoản ra file")
        export_btn.clicked.connect(self.export_accounts)
        btn_layout.addWidget(export_btn)

        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)
        
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
        
        # Dashboard thống kê nhanh
        self.stat_values = {}
        dashboard = QHBoxLayout()
        dashboard.setSpacing(10)
        for key, caption in (("total", "Tổng tài khoản"), ("active", "Hoạt động"),
                             ("inactive", "Không hoạt động"), ("unchecked", "Chưa kiểm tra")):
            card = QFrame()
            card.setObjectName("statCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(2)
            value = QLabel("0")
            value.setObjectName("statValue" + key.capitalize())
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(value)
            caption_label = QLabel(caption)
            caption_label.setObjectName("statCaption")
            caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(caption_label)
            dashboard.addWidget(card, 1)
            self.stat_values[key] = value
        layout.addLayout(dashboard)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Email", "Mật khẩu", "Trạng thái", "Kiểm tra lần cuối"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellDoubleClicked.connect(self.show_account_details)
        self.table.setItemDelegateForColumn(2, StatusDelegate(self.table))
        self.email_progress_delegate = EmailProgressDelegate(self.table)
        self.table.setItemDelegateForColumn(EMAIL_COLUMN, self.email_progress_delegate)
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.empty_label = QLabel(self.table)
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()
        self.table.viewport().installEventFilter(self)
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
        
        self.column_button = QPushButton("Cột hiển thị")
        self.column_button.setToolTip("Chọn cột hiển thị trong bảng")
        self.column_button.setMenu(self.build_column_menu())
        filter_layout.addWidget(self.column_button)
        
        filter_layout.addStretch()
        
        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm kiếm email...")
        self.search_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.search_input)
        
        layout.addLayout(filter_layout)
        
        return panel

    def apply_styles(self):
        """Nối lại QSS từ app.ui.styles; widget tĩnh vẫn theo objectName."""
        appearance = read_appearance(self.ui_settings)
        for widget in self.findChildren(QWidget):
            widget.setStyleSheet("")
        self.email_progress_delegate.set_accent(appearance["accent"])
        self.setStyleSheet(build_stylesheet(**appearance))

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
        theme.setCurrentIndex(max(0, theme.findData(self.ui_settings.get("theme", "light"))))
        form.addRow("Chế độ màu", theme)
        accent = QComboBox()
        for label, color in (("Đỏ NAMCO", "#d61718"), ("Xanh dương", "#2864c5"), ("Xanh ngọc", "#168578")):
            accent.addItem(label, color)
        accent.setCurrentIndex(max(0, accent.findData(self.ui_settings.get("accent", "#d61718"))))
        form.addRow("Màu nhấn", accent)
        font_size = QComboBox()
        for size, label in ((8, "Nhỏ"), (9, "Tiêu chuẩn"), (10, "Lớn")):
            font_size.addItem(label, size)
        font_size.setCurrentIndex(max(0, font_size.findData(self.ui_settings.get_int("font_size", 9))))
        form.addRow("Cỡ chữ", font_size)
        density = QComboBox()
        density.addItem("Thoáng", False)
        density.addItem("Gọn", True)
        density.setCurrentIndex(max(0, density.findData(self.ui_settings.get_bool("compact", False))))
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
            self.ui_settings.set(theme=theme.currentData(), accent=accent.currentData(),
                                 font_size=font_size.currentData(),
                                 compact=density.currentData())
            QApplication.setFont(QFont("Segoe UI", int(font_size.currentData())))
            self.apply_styles()
            self.status_bar.showMessage("Đã áp dụng giao diện", 3000)

    # ============================================================
    # DATA MANAGEMENT
    # ============================================================
    def load_data(self):
        self.campaign_service.load()
        self.refresh_signup_accounts()
        self.refresh_campaign_table()
        total = self.account_service.load()
        if total:
            self.log(f"Đã tải {total} tài khoản từ file")
            self.update_table()

    def save_data(self):
        self.account_service.save()

    # ============================================================
    # ACCOUNT OPERATIONS
    # ============================================================
    def add_account(self):
        dialog = AddAccountDialog(self)
        if dialog.exec() == QDialog.Accepted:
            email, password = dialog.get_data()
            if email and password:
                if self.account_service.add(email, password):
                    self.log(f"Đã thêm: {email}")
                    self.update_table()
                    self.save_data()

    def add_from_text(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng nhập dữ liệu!")
            return
        
        result = self.account_service.add_lines(text.split("\n"))
        added, skipped = result["added"], result["skipped"]
        self.log(f"Thêm: {added} | Bỏ qua (trùng): {skipped}")
        self.update_table()
        self.save_data()
        
        QMessageBox.information(
            self, "Hoàn tất",
            f"Đã thêm: {added} tài khoản\nBỏ qua (trùng): {skipped} tài khoản"
        )


    def import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file TXT", "", "Text Files (*.txt);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                result = self.account_service.add_lines(f.readlines())
            added, skipped = result["added"], result["skipped"]
            
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
        """Nút Xóa đã chọn + phím Del: xóa trọn vùng đang chọn có hộp thoại xác nhận."""
        rows = sorted({item.row() for item in self.table.selectedItems()})
        self.confirm_and_delete(rows)

    # ============================================================
    # CHECK ACCOUNTS
    # ============================================================
    def check_all_accounts(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cảnh báo", "Không có tài khoản nào!")
            return

        self.run_batch_check([(acc['email'], acc['password']) for acc in self.accounts],
                             "tất cả tài khoản")

    def check_rows(self, rows):
        """Menu chuột phải: kiểm tra mọi tài khoản trong vùng đã chọn, không chỉ dòng đầu."""
        rows = [row for row in rows if 0 <= row < len(self.accounts)]
        if not rows:
            return
        if len(rows) == 1:
            self.check_single_account(rows[0])
            return
        targets = [(self.accounts[row]['email'], self.accounts[row]['password'])
                   for row in rows]
        self.run_batch_check(targets, f"{len(targets)} tài khoản đã chọn")

    def run_batch_check(self, targets, label):
        """Chạy BatchCheckWorker cho một danh sách (email, password) bất kỳ."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(targets))
        self.progress_bar.setValue(0)

        worker = BatchCheckWorker(targets, self.auth_client, max_workers=self.max_workers)
        worker.result_ready.connect(self.on_check_result)
        worker.profile_ready.connect(self.on_profile_ready)
        worker.account_progress.connect(self.set_row_progress)
        worker.progress.connect(self.on_check_progress)
        worker.finished_checking.connect(self.on_check_finished)
        self.start_worker(worker)

        self.log(f"Bắt đầu kiểm tra {label} ({len(targets)}) với {self.max_workers} luồng...")

    def check_first_account(self):
        if not self.accounts:
            QMessageBox.warning(self, "Cảnh báo", "Không có tài khoản nào!")
            return
        
        self.check_single_account(0)

    def check_single_account(self, index):
        if index >= len(self.accounts):
            return
        
        acc = self.accounts[index]
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        
        worker = LoginWorker(acc['email'], acc['password'], self.auth_client)
        worker.result_ready.connect(lambda email, success, msg: self.on_single_result(index, email, success, msg))
        worker.profile_ready.connect(self.on_profile_ready)
        worker.progress.connect(self.progress_bar.setValue)
        worker.progress.connect(lambda percent, email=acc['email']: self.set_row_progress(email, percent))
        self.start_worker(worker)
        
        self.log(f"Đang kiểm tra: {acc['email']}")

    def on_single_result(self, index, email, success, message):
        self.set_row_progress(email, 0)
        self.account_service.set_status(email, success)
        self.refresh_account_row(email)
        self.save_data()
        self.log(f"{email}: {message}")
        self.progress_bar.setVisible(False)
        if success and index < len(self.accounts):
            self.show_account_details(index)

    def on_profile_ready(self, email, profile):
        """Gộp hồ sơ Parks2 vào tài khoản rồi báo số trường đọc được."""
        fields = self.account_service.apply_profile(email, profile)
        if not fields:
            return
        self.save_data()
        self.refresh_account_row(email)
        handoff_warning = profile.get("parks2_handoff_status")
        message = f"{email}: đã đọc được {fields} trường hồ sơ"
        if handoff_warning:
            message += f" (cảnh báo handoff: {handoff_warning})"
        self.log(message)

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
        self.set_row_progress(email, 0)
        self.account_service.set_status(email, success)
        self.refresh_account_row(email)
        self.log(f"{email}: {message}")

    def on_check_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(f"Đang kiểm tra: {current}/{total} "
                                    f"({self.max_workers} luồng)")

    def on_check_finished(self):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Hoàn tất kiểm tra")
        self.save_data()
        self.row_progress.clear()
        self.update_table()
        self.log("Hoàn tất kiểm tra")

    # ============================================================
    # UI UPDATES
    # ============================================================
    def update_table(self):
        columns = ACCOUNT_COLUMNS
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([column[0] for column in columns])
        for column, (label, key) in enumerate(columns):
            self.table.setColumnHidden(column, key in self.hidden_columns)
        self.table.setRowCount(len(self.accounts))
        for row, account in enumerate(self.accounts):
            for column, (label, key) in enumerate(columns):
                if key == "__password__":
                    value = "********"
                else:
                    value = account.get(key)
                    value = "" if value is None else str(value)
                item = QTableWidgetItem(value)
                if column == EMAIL_COLUMN:
                    item.setData(PROGRESS_ROLE, self.row_progress.get(account.get("email"), 0))
                self.table.setItem(row, column, item)
        self.stats_label.setText(f"{len(self.accounts)} accounts")
        self.update_dashboard()
        self.refresh_signup_accounts()
        self.apply_filter()

    def account_row(self, email):
        """Index dòng của email (invariant: index list == index bảng), hoặc None."""
        return next((row for row, account in enumerate(self.accounts)
                     if account.get("email") == email), None)

    def set_row_progress(self, email, percent):
        """
        Gắn % của một tài khoản vào đúng ô Email của nó rồi vẽ lại ô đó.

        Không gọi update_table(): đang có nhiều tài khoản chạy song song nên mỗi lần
        tick mà dựng lại cả bảng thì UI sẽ nghẹn.
        """
        if percent:
            self.row_progress[email] = max(1, min(100, int(percent)))
        else:
            self.row_progress.pop(email, None)
        row = self.account_row(email)
        if row is None:
            return
        item = self.table.item(row, EMAIL_COLUMN)
        if item is None:
            return
        item.setData(PROGRESS_ROLE, self.row_progress.get(email, 0))
        self.table.viewport().update(self.table.visualRect(self.table.model().index(row, EMAIL_COLUMN)))

    def refresh_account_row(self, email):
        """Chỉ vẽ lại dòng của một tài khoản: dữ liệu mới + bar tiến trình của nó."""
        row = self.account_row(email)
        if row is None:
            return
        account = self.accounts[row]
        for column, (label, key) in enumerate(ACCOUNT_COLUMNS):
            if key == "__password__":
                value = "********"
            else:
                value = account.get(key)
                value = "" if value is None else str(value)
            item = self.table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, column, item)
            item.setText(value)
            if column == EMAIL_COLUMN:
                item.setData(PROGRESS_ROLE, self.row_progress.get(email, 0))
        self.update_dashboard()
        self.apply_filter()

    def update_dashboard(self):
        counts = self.account_service.counts()
        active, inactive = counts["active"], counts["inactive"]
        for key, label in self.stat_values.items():
            label.setText(str(counts[key]))
        self.stats_chip.setText(
            f'<span style="color:#28a745;font-weight:700;">{active} hoạt động</span>'
            f'&nbsp;·&nbsp;<span style="color:#dc3545;font-weight:700;">{inactive} lỗi</span>'
            f'&nbsp;·&nbsp;<span style="color:#8a94a6;font-weight:700;">{counts["unchecked"]} chưa kiểm tra</span>'
        )

    def on_header_clicked(self, column):
        if column >= len(ACCOUNT_COLUMNS):
            return
        label, key = ACCOUNT_COLUMNS[column]
        if key == "__password__":
            return
        if self.sort_key == key:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_key = key
            self.sort_asc = True
        self.accounts.sort(key=lambda acc: str(acc.get(key) or "").lower(),
                           reverse=not self.sort_asc)
        order = Qt.SortOrder.AscendingOrder if self.sort_asc else Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(column, order)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.update_table()
        self.save_data()
        self.log(f"Sắp xếp theo {label}: {'tăng dần' if self.sort_asc else 'giảm dần'}")

    def build_column_menu(self):
        menu = QMenu(self)
        for label, key in ACCOUNT_COLUMNS[1:]:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(key not in self.hidden_columns)
            action.toggled.connect(lambda checked, column_key=key: self.set_column_hidden(column_key, not checked))
            menu.addAction(action)
        return menu

    def set_column_hidden(self, key, hidden):
        if hidden:
            self.hidden_columns.add(key)
        else:
            self.hidden_columns.discard(key)
        for column, (_, column_key) in enumerate(ACCOUNT_COLUMNS):
            if column_key == key:
                self.table.setColumnHidden(column, hidden)
                break
        self.ui_settings.set_json("hidden_account_columns", sorted(self.hidden_columns))

    def focus_search(self):
        self.tab_widget.setCurrentWidget(self.list_tab)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def update_input_preview(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            self.input_preview.setText("")
            return
        counts = self.account_service.preview(text.split("\n"))
        self.input_preview.setText(
            f"Sẽ thêm: {counts['added']} · Trùng: {counts['skipped']} "
            f"· Sai định dạng: {counts['bad']}"
        )

    def eventFilter(self, obj, event):
        if obj is self.text_input and event.type() in (QEvent.Type.DragEnter, QEvent.Type.Drop):
            if not event.mimeData().hasUrls():
                return super().eventFilter(obj, event)
            if event.type() == QEvent.Type.DragEnter:
                event.acceptProposedAction()
                return True
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if not path or not path.lower().endswith(".txt"):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    self.log(f"Không đọc được {path}: {e}")
                    continue
                current = self.text_input.toPlainText().strip()
                self.text_input.setPlainText(f"{current}\n{content}" if current else content)
                self.log(f"Đã kéo thả file: {path}")
            event.acceptProposedAction()
            return True
        if hasattr(self, "table") and obj is self.table.viewport() and event.type() == QEvent.Type.Resize:
            self.empty_label.setGeometry(obj.geometry())
        return super().eventFilter(obj, event)

    def apply_filter(self):
        filter_text = self.filter_combo.currentText()
        search_text = self.search_input.text().lower()
        
        visible = 0
        for i in range(self.table.rowCount()):
            email_item = self.table.item(i, 0)
            status_item = self.table.item(i, 2)
            
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
            if show:
                visible += 1
        
        if not self.accounts:
            self.empty_label.setText("Chưa có tài khoản nào.\n"
                                     "Bấm \"Nhập tài khoản\" hoặc \"Import TXT\" để bắt đầu.")
        elif visible == 0:
            self.empty_label.setText("Không có tài khoản khớp bộ lọc.")
        else:
            self.empty_label.hide()
            return
        self.empty_label.setGeometry(self.table.viewport().geometry())
        self.empty_label.show()
        self.empty_label.raise_()

    def export_accounts(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export danh sách", "accounts_export.txt", "Text Files (*.txt)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for line in self.account_service.export_lines():
                    f.write(line + "\n")
            
            self.log(f"Đã export {len(self.accounts)} tài khoản")
            QMessageBox.information(self, "Hoàn tất", f"Đã export đến:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể export: {e}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def start_worker(self, worker):
        """
        Giữ tham chiếu tới worker đang chạy.

        Không có danh sách này thì lần kiểm tra tiếp theo làm GC một `QThread` còn đang
        chạy và Qt abort; `closeEvent()` cũng dựa vào `self.workers` để dừng worker khi
        đóng cửa sổ.
        """
        self.workers.append(worker)
        worker.finished.connect(lambda w=worker: self.forget_worker(w))
        worker.start()

    def forget_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)

    # ============================================================
    # CONTEXT MENU
    # ============================================================
    def context_rows(self, position):
        """
        Những dòng mà menu chuột phải sẽ tác động.

        Bấm chuột phải vào trong vùng đang chọn thì giữ nguyên cả vùng (thao tác
        áp dụng cho mọi tài khoản đã chọn); bấm ra ngoài vùng thì chỉ dòng đó.
        """
        clicked = self.table.rowAt(position.y())
        if clicked < 0 or clicked >= len(self.accounts):
            return []
        selected = sorted({item.row() for item in self.table.selectedItems()
                           if 0 <= item.row() < len(self.accounts)})
        if clicked in selected and len(selected) > 1:
            return selected
        return [clicked]

    def show_context_menu(self, position):
        """Hiển thị context menu khi chuột phải vào bảng"""
        rows = self.context_rows(position)
        if not rows:
            return

        menu = QMenu(self)
        many = len(rows) > 1
        # Hành động chỉ làm được với 1 tài khoản (một worker / một hộp thoại) nói rõ
        # target ngay trên nhãn để không nhầm là đã áp dụng cho cả vùng chọn.
        target_email = self.accounts[rows[0]]['email']

        change_name_action = QAction(load_svg_icon(AppIcons.EDIT),
                                     f" Đổi tên{' ' + target_email if many else ''}", self)
        change_name_action.triggered.connect(lambda: self.change_account_name(rows[0]))
        menu.addAction(change_name_action)

        details_action = QAction(f"Xem thông tin tài khoản{' ' + target_email if many else ''}", self)
        details_action.triggered.connect(lambda: self.show_account_details(rows[0]))
        menu.addAction(details_action)

        menu.addSeparator()

        check_label = f" Kiểm tra {len(rows)} tài khoản đã chọn" if many else " Kiểm tra tài khoản"
        check_action = QAction(load_svg_icon(AppIcons.CHECK), check_label, self)
        check_action.triggered.connect(lambda: self.check_rows(rows))
        menu.addAction(check_action)

        copy_label = f" Copy {len(rows)} email" if many else " Copy email"
        copy_email_action = QAction(load_svg_icon(AppIcons.COPY), copy_label, self)
        copy_email_action.triggered.connect(lambda: self.copy_emails(rows))
        menu.addAction(copy_email_action)

        menu.addSeparator()

        delete_label = f" Xóa {len(rows)} tài khoản đã chọn" if many else " Xóa tài khoản"
        delete_action = QAction(load_svg_icon(AppIcons.TRASH), delete_label, self)
        delete_action.triggered.connect(lambda: self.confirm_and_delete(rows))
        menu.addAction(delete_action)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def copy_emails(self, rows):
        """Copy email của một hoặc nhiều tài khoản đã chọn, mỗi email một dòng."""
        emails = [self.accounts[row]['email'] for row in rows if row < len(self.accounts)]
        if not emails:
            return
        QApplication.clipboard().setText("\n".join(emails))
        if len(emails) == 1:
            self.log(f"Đã copy email: {emails[0]}")
        else:
            self.log(f"Đã copy {len(emails)} email đã chọn")

    def confirm_and_delete(self, rows):
        """Hỏi xác nhận kèm danh sách email rồi xóa trọn vùng đã chọn."""
        rows = sorted({row for row in rows if 0 <= row < len(self.accounts)})
        if not rows:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn tài khoản cần xóa!")
            return

        emails = [self.accounts[row]['email'] for row in rows]
        listing = "\n".join(emails[:10])
        if len(emails) > 10:
            listing += f"\n… và {len(emails) - 10} tài khoản nữa"
        reply = QMessageBox.question(
            self, "Xác nhận xóa",
            f"Bạn có chắc muốn xóa {len(emails)} tài khoản?\n\n{listing}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        removed = self.account_service.delete_rows(rows)
        self.update_table()
        self.save_data()
        self.log(f"Đã xóa {removed} tài khoản")

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
        worker = ChangeNameWorker(acc['email'], acc['password'], name_data, self.name_client)
        worker.result_ready.connect(lambda email, success, msg: self.on_change_name_result(row, email, success, msg))
        worker.progress.connect(self.progress_bar.setValue)
        worker.progress.connect(lambda percent, email=acc['email']: self.set_row_progress(email, percent))
        self.start_worker(worker)
        
        self.log(f'\u0110ang c\u1eadp nh\u1eadt h\u1ed3 s\u01a1: {acc["email"]}')

    def on_change_name_result(self, row, email, success, message):
        self.set_row_progress(email, 0)
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
        if self.proxy_check_worker is not None and self.proxy_check_worker.isRunning():
            self.proxy_check_worker.stop()

        self.save_data()
        event.accept()
