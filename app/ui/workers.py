"""Các QThread của UI: mỗi worker chỉ gọi một client hạ tầng đã được inject."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import Qt, QThread, Signal

from app.config import DEFAULT_CONCURRENCY, MAX_CONCURRENCY
from app.domain.names import kanji_overrides
from app.infrastructure.bandai_auth import BandaiAuthClient
from app.infrastructure.bandai_name import BandaiNameClient
from proxy_manager import TEST_TIMEOUT, check_all_proxies, proxy_manager

# ============================================================
# WORKER THREAD CHO ĐĂNG NHẬP
# ============================================================
class LoginWorker(QThread):
    """Thread đăng nhập: logic nằm trong BandaiAuthClient, lớp này chỉ đổi tín hiệu."""
    result_ready = Signal(str, bool, str)  # email, success, message
    profile_ready = Signal(str, dict)
    progress = Signal(int)

    def __init__(self, email, password, auth_client=None):
        super().__init__()
        self.email = email
        self.password = password
        self.auth_client = auth_client or BandaiAuthClient()
        self._is_running = True

    def run(self):
        try:
            outcome = self.auth_client.authenticate(
                self.email, self.password, on_progress=self.progress.emit)
        except Exception as exc:
            self.result_ready.emit(self.email, False, f"Lỗi: {exc}")
            return
        if not outcome.success:
            self.result_ready.emit(self.email, False, f"Đăng nhập thất bại: {outcome.reason}")
            self.progress.emit(100)
            return
        profile = dict(outcome.profile)
        profile.setdefault("status", "Chưa kiểm tra")
        profile.setdefault("last_check", None)
        self.profile_ready.emit(self.email, profile)
        if outcome.profile_fields:
            message = (f"Đăng nhập thành công - đọc được "
                       f"{outcome.profile_fields} trường hồ sơ")
        else:
            message = "Đăng nhập thành công nhưng chưa đọc được hồ sơ"
        if outcome.note:
            message += f" ({outcome.note})"
        self.result_ready.emit(self.email, True, message)
        self.progress.emit(100)

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD CHO KIỂM TRA NHIỀU TÀI KHOẢN
# ============================================================
class BatchCheckWorker(QThread):
    """
    Thread kiểm tra nhiều tài khoản **đồng thời**.

    Mỗi tài khoản là một phiên đăng nhập độc lập (session + proxy riêng từ
    `new_session()`), nên chạy song song được; số luồng do người dùng chọn ở tab
    Cấu hình. `account_progress` mang % của *từng* tài khoản để UI tô trên đúng dòng
    của nó, `progress` là đếm overall cho thanh progress chung.
    """
    result_ready = Signal(str, bool, str)  # email, success, message
    profile_ready = Signal(str, dict)
    account_progress = Signal(str, int)    # email, percent của riêng tài khoản đó
    progress = Signal(int, int)  # completed, total
    finished_checking = Signal()

    def __init__(self, accounts, auth_client=None, max_workers=DEFAULT_CONCURRENCY):
        super().__init__()
        self.accounts = accounts  # list of (email, password)
        self.auth_client = auth_client or BandaiAuthClient()
        self.max_workers = max(1, min(MAX_CONCURRENCY, int(max_workers or 1)))
        self._is_running = True

    def run(self):
        total = len(self.accounts)
        completed = 0
        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            futures = [pool.submit(self._check_one, email, password)
                       for email, password in self.accounts]
            for future in as_completed(futures):
                completed += 1
                self.progress.emit(completed, total)
        finally:
            # stop() giữa chừng: bỏ hết việc còn xếp hàng và không chờ thêm tài khoản nào.
            pool.shutdown(wait=self._is_running, cancel_futures=not self._is_running)
        self.finished_checking.emit()

    def _check_one(self, email, password):
        """Chạy một LoginWorker ngay trong thread của pool; signal đi thẳng tới UI."""
        if not self._is_running:
            return
        account_worker = LoginWorker(email, password, self.auth_client)
        account_worker.progress.connect(
            lambda percent, target=email: self.account_progress.emit(target, percent),
            Qt.ConnectionType.DirectConnection,
        )
        account_worker.profile_ready.connect(
            self.profile_ready, Qt.ConnectionType.DirectConnection)
        account_worker.result_ready.connect(
            self.result_ready, Qt.ConnectionType.DirectConnection)
        account_worker.run()

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD CHẠY CHIẾN DỊCH BẰNG TRÌNH DUYỆT
# ============================================================
class BrowserCampaignWorker(QThread):
    """Chạy recipe chiến dịch trên Chrome riêng của từng tài khoản.

    Logic nằm trong `BrowserCampaignService` (mỗi tài khoản một Chrome); lớp này
    chỉ đổi callback thành tín hiệu. Mặc định 1 Chrome/lần nên không đè RAM, và
    tín hiệu vẫn phát theo *từng tài khoản* để UI biết dòng nào đang tới đâu.
    """
    message = Signal(str)                  # dòng nhật ký
    account_progress = Signal(str, int)    # email, % của riêng tài khoản đó
    result_ready = Signal(str, bool, str, str)  # email, ok, message, screenshot
    progress = Signal(int, int)            # done, total
    finished_run = Signal()

    def __init__(self, browser_service, campaign, accounts, submit=None,
                 keep_open_seconds=0):
        super().__init__()
        self.browser_service = browser_service
        self.campaign = campaign
        self.accounts = list(accounts)
        self.submit = submit
        self.keep_open_seconds = keep_open_seconds
        self._is_running = True

    def run(self):
        try:
            self.browser_service.run(
                self.campaign,
                self.accounts,
                on_log=self.message.emit,
                on_progress=lambda done, total: self.progress.emit(done, total),
                on_account_progress=lambda email, percent: self.account_progress.emit(
                    email, percent),
                on_result=lambda result: self.result_ready.emit(
                    result.email, result.ok, result.message, result.screenshot),
                should_stop=lambda: not self._is_running,
                submit=self.submit,
                keep_open_seconds=self.keep_open_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - recipe hỏng/Chrome thiếu đều báo ở đây
            self.message.emit("Không chạy được chiến dịch: %s" % exc)
        self.finished_run.emit()

    def stop(self):
        # Giống các worker khác: chờ tài khoản đang chạy xong rồi mới kết thúc, để
        # không destroy một QThread còn chạy giữa lúc tắt app.
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD DÒ TRANG (soạn recipe bằng chrome-devtools-mcp)
# ============================================================
class DiscoveryWorker(QThread):
    """Mở Chrome của một tài khoản, vào URL và đổ HTML/elements/snapshot ra artifacts.

    Dùng khi trang chiến dịch đổi layout: chạy dò, đọc `elements.json` +
    `a11y_snapshot.txt` rồi sửa `recipes/*.json`.
    """
    message = Signal(str)
    finished_discovery = Signal(str)  # thư mục artifacts đã ghi

    def __init__(self, email, password, url, headless=False, with_mcp=True):
        super().__init__()
        self.email = email
        self.password = password
        self.url = url
        self.headless = headless
        self.with_mcp = with_mcp
        self._is_running = True

    def run(self):
        out_dir = ""
        session = None
        try:
            from app.infrastructure.browser.campaign_runner import navigate_only
            from app.infrastructure.browser.discovery import discover_page
            session = navigate_only(self.email, self.url, proxy_manager=proxy_manager,
                                    headless=self.headless, on_log=self.message.emit)
            paths = discover_page(self.email, self.url, session,
                                  on_log=self.message.emit, with_mcp=self.with_mcp)
            out_dir = paths.get("dir", "")
        except Exception as exc:  # noqa: BLE001 - báo ra nhật ký, không làm sập app
            self.message.emit("Dò trang thất bại: %s" % exc)
        finally:
            if session is not None:
                session.close()
        self.finished_discovery.emit(out_dir)

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD KIỂM TRA PROXY
# ============================================================
class ProxyCheckWorker(QThread):
    """Thread kiểm tra song song danh sách proxy để không block UI"""
    row_ready = Signal(int, bool, str)  # index, ok, message
    finished_check = Signal()

    def __init__(self, proxies):
        super().__init__()
        self.proxies = list(proxies)
        self._is_running = True

    def run(self):
        try:
            check_all_proxies(
                self.proxies,
                emit=lambda index, ok, message: self.row_ready.emit(index, ok, message),
                is_running=lambda: self._is_running,
                timeout=TEST_TIMEOUT,
            )
        except Exception as exc:
            self.row_ready.emit(0, False, f"Lỗi: {str(exc)}")
        self.finished_check.emit()

    def stop(self):
        self._is_running = False
        self.wait()

# ============================================================
# WORKER THREAD CHO ĐỔI TÊN
# ============================================================
class ChangeNameWorker(QThread):
    """Thread đổi tên: logic nằm trong BandaiNameClient, lớp này chỉ đổi tín hiệu."""
    result_ready = Signal(str, bool, str)  # email, success, message
    progress = Signal(int)

    def __init__(self, email, password, name_data, name_client=None):
        super().__init__()
        self.email = email
        self.password = password
        self.name_data = name_data
        self.name_client = name_client or BandaiNameClient()
        self._is_running = True

    def run(self):
        try:
            outcome = self.name_client.change_profile(
                self.email,
                self.password,
                # Bỏ trống nghĩa là giữ giá trị hiện tại trên trang, không phải xoá.
                kanji_overrides(self.name_data.get("last_name", ""),
                                self.name_data.get("first_name", "")),
                on_progress=self.progress.emit,
            )
        except Exception as exc:
            self.result_ready.emit(self.email, False, f"Lỗi: {exc}")
            return
        self.progress.emit(100)
        message = "Đổi tên thành công!" if outcome.success else outcome.message
        self.result_ready.emit(self.email, outcome.success, message)

    def stop(self):
        self._is_running = False
        self.wait()
