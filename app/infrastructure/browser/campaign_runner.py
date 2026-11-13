"""Chạy recipe của chiến dịch trên Chrome riêng của từng tài khoản.

Trách nhiệm: mở phiên, đăng nhập nếu cần, chạy các bước trên trang 抽選, bấm gửi
(chỉ khi bật submit), phân loại kết quả và chụp ảnh làm bằng chứng. Không biết gì
về Qt/UI; mọi thứ báo ra qua callback `on_log` / `on_progress`.
"""
import os
from dataclasses import dataclass, field
from datetime import datetime

from app.config import (
    BROWSER_ACTION_TIMEOUT, BROWSER_ARTIFACTS_DIR, BROWSER_PROFILE_DIR,
)
from app.domain.browser_recipe import (
    RecipeNotReady, classify_outcome, phase_steps, render_value,
)
from app.domain.ip_rules import is_ip_lockout
from app.infrastructure.browser.browser_session import (
    BrowserSession, BrowserStartError, profile_slug,
)

# Trạng thái một lần chạy cho một tài khoản.
STATUS_REGISTERED = "registered"     # gửi xong và trang xác nhận đã nhận
STATUS_ALREADY = "already"           # đã đăng ký trước đó
STATUS_CLOSED = "closed"             # ngoài thời gian nhận đăng ký
STATUS_DRY_RUN = "dry_run"           # điền xong nhưng CHƯA bấm gửi
STATUS_UNVERIFIED = "unverified"     # đã bấm gửi nhưng không thấy câu xác nhận
STATUS_LOGIN_FAILED = "login_failed"
STATUS_IP_BLOCKED = "ip_blocked"
STATUS_ERROR = "error"

SUCCESS_STATUSES = (STATUS_REGISTERED, STATUS_ALREADY)
# Nghỉ ngắn sau cú bấm gửi/nút cuối để trang kịp trả lời trước khi đọc kết quả.
SETTLE_AFTER_SUBMIT_MS = 2500


@dataclass
class BrowserRunResult:
    """Kết quả một tài khoản; `message` là câu tiếng Việt hiển thị thẳng lên UI."""
    email: str
    status: str
    message: str
    ok: bool = False
    screenshot: str = ""
    final_url: str = ""
    last_step: str = ""
    submit_done: bool = False
    steps_done: int = 0
    details: dict = field(default_factory=dict)


def _artifacts_dir(email):
    stamp = datetime.now().strftime("%Y%m%d")
    return os.path.join(BROWSER_ARTIFACTS_DIR, stamp)


def _screenshot_path(email, role):
    stamp = datetime.now().strftime("%H%M%S")
    return os.path.join(_artifacts_dir(email), "%s_%s_%s.png"
                        % (profile_slug(email), stamp, role))


class CampaignBrowserRunner:
    """Điều khiển một Chrome cho một tài khoản theo recipe."""

    def __init__(self, recipe, submit=False, headless=False, proxy_manager=None,
                 chrome_path=None, profile_root=BROWSER_PROFILE_DIR,
                 on_log=None, keep_open_seconds=0):
        self.recipe = recipe
        self.submit = bool(submit)
        self.headless = bool(headless)
        self.proxy_manager = proxy_manager
        self.chrome_path = chrome_path
        self.profile_root = profile_root
        self.on_log = on_log or (lambda message: None)
        self.keep_open_seconds = max(0, int(keep_open_seconds or 0))

    # ---------------- API chính ----------------
    def run(self, email, password, campaign_url, on_progress=None):
        report = on_progress or (lambda percent: None)
        result = BrowserRunResult(email=email, status=STATUS_ERROR,
                                  message="Chưa chạy bước nào")
        proxy = self.proxy_manager.next_proxy_entry() if self.proxy_manager else None
        self._current_proxy = proxy
        report(5)
        session = BrowserSession(
            email=email, proxy=proxy, headless=self.headless,
            chrome_path=self.chrome_path, profile_root=self.profile_root,
            on_log=self.on_log,
        )
        try:
            session.start()
        except BrowserStartError as exc:
            result.message = str(exc)
            report(100)
            return result
        try:
            self._run_flow(session, email, password, campaign_url, result, report)
        except RecipeNotReady as exc:
            result.status, result.message = STATUS_ERROR, str(exc)
        except Exception as exc:  # noqa: BLE001 - một tài khoản lỗi không được giết cả mẻ
            result.status = STATUS_ERROR
            result.message = "Lỗi khi chạy: %s" % exc
            self.on_log("[%s] lỗi: %s" % (email, exc))
            result.screenshot = result.screenshot or session.screenshot(
                _screenshot_path(email, "error"))
        finally:
            if self.keep_open_seconds and not self.headless:
                # Giữ cửa sổ để người dùng xem tay khi cần (chế độ gỡ lỗi).
                session.page.wait_for_timeout(self.keep_open_seconds * 1000)
            session.close()
        report(100)
        return result

    # ---------------- các pha ----------------
    def _run_flow(self, session, email, password, campaign_url, result, report):
        logged_in = self._ensure_login(session, email, password, campaign_url, result, report)
        if not logged_in:
            result.status = STATUS_LOGIN_FAILED
            result.message = "Không đăng nhập được (kiểm tra mật khẩu hoặc trang đổi layout)"
            result.screenshot = session.screenshot(_screenshot_path(email, "login-failed"))
            return

        report(45)
        page = session.page
        if not campaign_url:
            raise RecipeNotReady("Chiến dịch chưa có link")
        response = session.goto(campaign_url)
        page.wait_for_timeout(800)
        body = session.page_text()
        if is_ip_lockout(body):
            self._mark_proxy_blocked()
            result.status = STATUS_IP_BLOCKED
            result.message = "IP bị site chặn (UnexpectedRemoteAddress) — đổi proxy rồi chạy lại"
            result.screenshot = session.screenshot(_screenshot_path(email, "ip-blocked"))
            return
        if response is not None and response.status >= 400:
            raise RecipeNotReady("Trang chiến dịch trả HTTP %d" % response.status)

        report(60)
        stopped_before_submit = self._run_steps(session, phase_steps(self.recipe, "entry"),
                                                email, password, result, report)
        result.final_url = page.url
        if stopped_before_submit:
            page.wait_for_timeout(1000)
            result.status = STATUS_DRY_RUN
            result.message = "Đã điền xong, chưa bấm gửi (chế độ chỉ điền)"
            result.screenshot = session.screenshot(_screenshot_path(email, "filled"))
            return

        report(85)
        page.wait_for_timeout(SETTLE_AFTER_SUBMIT_MS)
        result.final_url = page.url
        body = session.page_text()
        outcome = classify_outcome(self.recipe, body)
        result.screenshot = session.screenshot(_screenshot_path(email, outcome or "result"))
        if outcome == STATUS_REGISTERED:
            result.ok, result.status = True, STATUS_REGISTERED
            result.message = "Đã gửi đăng ký và trang xác nhận hoàn tất"
        elif outcome == STATUS_ALREADY:
            result.ok, result.status = True, STATUS_ALREADY
            result.message = "Tài khoản đã đăng ký chiến dịch này trước đó"
        elif outcome == STATUS_CLOSED:
            result.ok, result.status = False, STATUS_CLOSED
            result.message = "Ngoài thời gian nhận đăng ký"
        elif outcome == "error":
            result.ok, result.status = False, STATUS_ERROR
            result.message = "Trang báo lỗi sau khi gửi"
        else:
            result.ok = result.submit_done
            result.status = STATUS_UNVERIFIED
            result.message = ("Đã bấm gửi nhưng không thấy câu xác nhận — xem ảnh chụp"
                              if result.submit_done else "Chưa có bước bấm gửi trong recipe")

    def _ensure_login(self, session, email, password, campaign_url, result, report):
        """True khi đã ở trạng thái đăng nhập (hoặc recipe không cần đăng nhập)."""
        recipe = self.recipe
        login = recipe.get("login") or {}
        logged_in_selector = (login.get("logged_in_selector") or "").strip()
        if not login:
            return True
        report(15)
        if campaign_url:
            session.goto(campaign_url)
            session.page.wait_for_timeout(600)
            if logged_in_selector and self._has(session, logged_in_selector):
                self.on_log("[%s] phiên còn đăng nhập, bỏ qua bước login" % email)
                return True
        self.on_log("[%s] đăng nhập" % email)
        session.goto(login["url"])
        self._run_steps(session, phase_steps(recipe, "login"), email, password, result, report)
        if not campaign_url:
            return True
        session.goto(campaign_url)
        session.page.wait_for_timeout(800)
        if is_ip_lockout(session.page_text()):
            self._mark_proxy_blocked()
            return False
        # Không khai báo logged_in_selector thì tin vào việc form đã submit xong:
        # chỉ chặn khi rõ ràng vẫn còn ô mật khẩu.
        if logged_in_selector:
            return self._has(session, logged_in_selector)
        return not self._has(session, login.get("password_selector") or "input[type=password]")

    # ---------------- thực thi bước ----------------
    def _run_steps(self, session, steps, email, password, result, report):
        """Chạy danh sách bước. Trả True khi phải dừng ngay trước bước bấm gửi."""
        total = max(1, len(steps))
        for index, step in enumerate(steps):
            action = step.get("action")
            if step.get("requires_submit") and not self.submit:
                result.last_step = "%s (bỏ vì chưa bật submit)" % action
                return True
            if action == "submit" and not self.submit:
                result.last_step = "submit (bỏ vì chưa bật submit)"
                return True
            label = step.get("name") or action
            result.last_step = label
            try:
                self._run_step(session, step, email, password, result)
            except Exception as exc:  # noqa: BLE001
                if step.get("optional"):
                    self.on_log("[%s] bỏ qua bước '%s': %s" % (email, label, exc))
                    continue
                raise RecipeNotReady("Bước '%s' thất bại: %s" % (label, exc)) from exc
            result.steps_done = index + 1
            report(min(84, 45 + int(35 * (index + 1) / total)))
        return False

    def _run_step(self, session, step, email, password, result):
        page = session.page
        action = step.get("action")
        timeout = int(step.get("timeout") or BROWSER_ACTION_TIMEOUT)
        selector = render_value(step.get("selector") or "", email, password)
        value = render_value(step.get("value") or "", email, password)

        if action == "goto":
            session.goto(value)
            page.wait_for_timeout(int(step.get("settle") or 500))
        elif action == "fill":
            page.fill(selector, value, timeout=timeout)
        elif action == "select":
            page.select_option(selector, value=value, timeout=timeout)
        elif action == "check":
            page.check(selector, timeout=timeout)
        elif action == "click":
            page.click(selector, timeout=timeout)
            page.wait_for_timeout(int(step.get("settle") or 300))
        elif action == "press":
            key = step.get("key") or "Enter"
            if selector:
                page.press(selector, key, timeout=timeout)
            else:
                page.keyboard.press(key)
        elif action == "wait_text":
            page.wait_for_function(
                "(text) => document.body && document.body.innerText.includes(text)",
                arg=value, timeout=timeout)
        elif action == "wait_selector":
            page.wait_for_selector(selector, timeout=timeout)
        elif action == "sleep":
            page.wait_for_timeout(int(float(value) * 1000))
        elif action == "screenshot":
            session.screenshot(_screenshot_path(email, profile_slug(value) or "step"))
        elif action == "submit":
            result.submit_done = True
            self.on_log("[%s] bấm gửi đăng ký" % email)
            if selector:
                page.click(selector, timeout=timeout)
            else:
                page.keyboard.press("Enter")
        else:  # validate_recipe đã chặn, phòng khi recipe bị sửa tay lúc đang chạy
            raise RecipeNotReady("Bước không hỗ trợ: %s" % action)

    # ---------------- tiện ích ----------------
    @staticmethod
    def _has(session, selector):
        try:
            return session.page.locator(selector).count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _mark_proxy_blocked(self):
        proxy = getattr(self, "_current_proxy", None)
        if self.proxy_manager is None or not proxy:
            return
        label = self.proxy_manager.mark_entry_blocked(proxy)
        if label:
            self.on_log("Đưa proxy %s vào tạm nghỉ (bị chặn IP)" % label)


def navigate_only(email, url, proxy_manager=None, headless=False, hold_seconds=0,
                  on_log=None):
    """Mở Chrome của một tài khoản và vào URL, không thao tác gì (dùng khi dò trang).

    Trả BrowserSession đang mở để nơi gọi tự chụp/dump; caller phải `close()`.
    """
    proxy = proxy_manager.next_proxy_entry() if proxy_manager else None
    session = BrowserSession(email=email, proxy=proxy, headless=headless, on_log=on_log)
    session.start()
    if url:
        session.goto(url)
        session.page.wait_for_timeout(int(hold_seconds or 1500))
    return session
