"""Chạy recipe của chiến dịch trên Chrome riêng của từng tài khoản.

Trách nhiệm: mở phiên, đăng nhập nếu cần, chạy các bước trên trang 抽選, bấm gửi
(chỉ khi bật submit), phân loại kết quả và chụp ảnh làm bằng chứng. Không biết gì
về Qt/UI; mọi thứ báo ra qua callback `on_log` / `on_progress`.
"""
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.config import (
    BROWSER_ACTION_TIMEOUT, BROWSER_ARTIFACTS_DIR, BROWSER_PROFILE_DIR,
)
from app.domain.browser_recipe import (
    RecipeNotReady, classify_outcome, phase_steps, render_value, truthy,
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
STATUS_PAUSED = "paused"             # dừng ở bước người dùng tự làm (thanh toán), cửa sổ để mở
STATUS_ERROR = "error"

SUCCESS_STATUSES = (STATUS_REGISTERED, STATUS_ALREADY)
# Nghỉ ngắn sau cú bấm gửi/nút cuối để trang kịp trả lời trước khi đọc kết quả.
SETTLE_AFTER_SUBMIT_MS = 2500
# Popup lỗi site hiện ngay sau một cú bấm — thường là do chưa chọn được 種類 (mã slot
# không có trong trang: 景品ミニゲームの商品コードが指定されていません) hoặc hết hàng.
# Gặp là dừng ngay kèm câu thông báo, thay vì chờ 20s cho bước sau rồi báo timeout khó hiểu.
SITE_ERROR_HINTS = (
    "商品コードが指定されていません",
    "シリアルコードが正しくありません",
    "既に使用されています",
    "使用済みのシリアルコード",
    "在庫がありません",
    "販売期間外",
    "受付を終了しました",
    "アクセスが集中しております",
)
# Ô chứa câu lỗi cụ thể của site (vd serial code sai/đã dùng): đọc trước khi dò chữ.
SITE_ERROR_SELECTORS = ("#ITEM_SERIAL_CHECK_MODAL_ERROR_MESSAGE",)


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
    # True khi recipe dừng ở bước `pause`: cửa sổ Chrome được giữ lại cho người dùng.
    keep_open: bool = False
    details: dict = field(default_factory=dict)


class _PauseFlow(Exception):
    """Điều khiển luồng: recipe yêu cầu dừng và để cửa sổ lại cho người dùng."""


class _ProxyRetry(Exception):
    """Proxy lỗi hoặc IP bị chặn: thử lại bằng proxy kế tiếp (nếu còn)."""


class _SiteError(Exception):
    """Site hiện thông báo lỗi ngay sau thao tác: dừng lượt chạy của tài khoản đó."""


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
                 on_log=None, keep_open_seconds=0, on_keep_open=None, card=None,
                 clear_cart=False):
        self.recipe = recipe
        self.submit = bool(submit)
        self.headless = bool(headless)
        self.proxy_manager = proxy_manager
        self.chrome_path = chrome_path
        self.profile_root = profile_root
        self.on_log = on_log or (lambda message: None)
        self.keep_open_seconds = max(0, int(keep_open_seconds or 0))
        # Nhận phiên đang mở khi recipe dừng ở bước `pause` (người dùng làm tiếp).
        self.on_keep_open = on_keep_open or (lambda email, session: None)
        # Biến thẻ thanh toán ({card_number}, {card_exp}...) do UI/Cấu hình cung cấp.
        self.card = card or {}
        # Xoá dòng giỏ cũ trước khi thêm slot mới (đổi khung giờ mà không bị 2 dòng).
        self.clear_cart = bool(clear_cart)
        self.campaign_url = ""

    # ---------------- API chính ----------------
    def run(self, email, password, campaign_url, on_progress=None):
        report = on_progress or (lambda percent: None)
        self.campaign_url = campaign_url or ""
        result = BrowserRunResult(email=email, status=STATUS_ERROR,
                                  message="Chưa chạy bước nào")
        # Proxy lỗi/chặn IP thì thử proxy kế tiếp (tối đa 2 lần) trước khi bỏ cuộc.
        attempts = 2 if self.proxy_manager is not None else 1
        for attempt in range(1, attempts + 1):
            finished = self._run_once(email, password, campaign_url, result, report,
                                     attempt, attempts)
            if finished:
                return result
            self._mark_proxy_blocked()
            self.on_log("[%s] proxy lỗi/bị chặn — thử proxy khác (%d/%d)"
                        % (email, attempt, attempts))
        result.status = STATUS_IP_BLOCKED
        result.message = (
            "Proxy lỗi hoặc IP bị chặn ở mọi lần thử — thêm proxy khác vào proxy.txt rồi chạy lại"
            if self._current_proxy else
            "IP bị site chặn (UnexpectedRemoteAddress) — bật proxy rồi chạy lại")
        result.screenshot = ""
        report(100)
        return result

    def _run_once(self, email, password, campaign_url, result, report, attempt, attempts):
        """Một lần thử với một proxy. Trả True khi đã có kết luận (không retry)."""
        proxy = self.proxy_manager.next_proxy_entry() if self.proxy_manager else None
        self._current_proxy = proxy
        result.details["proxy"] = ("%s:%s" % (proxy["host"], proxy["port"])) if proxy else ""
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
            if proxy and attempt < attempts:
                session.close()
                return False          # thử lại với proxy khác
            report(100)
            return True
        retry = False
        try:
            self._run_flow(session, email, password, campaign_url, result, report)
        except _ProxyRetry:
            retry = proxy is not None and attempt < attempts
            if retry:
                result.message = "Proxy lỗi — đang thử proxy khác"
        except _PauseFlow:
            result.status = STATUS_PAUSED
            result.ok = True
            result.keep_open = True
            result.final_url = session.page.url if session.page else ""
            result.message = ("Đã dừng trước bước thanh toán — cửa sổ Chrome giữ nguyên "
                              "để bạn tự hoàn tất")
            result.screenshot = session.screenshot(_screenshot_path(email, "paused"))
            self.on_log("[%s] %s" % (email, result.message))
        except RecipeNotReady as exc:
            result.status, result.message = STATUS_ERROR, str(exc)
            result.screenshot = session.screenshot(_screenshot_path(email, "recipe-error"))
            self.on_log("[%s] %s" % (email, result.message))
        except _SiteError as exc:
            result.status, result.message = STATUS_ERROR, str(exc)
            result.screenshot = session.screenshot(_screenshot_path(email, "site-error"))
            self.on_log("[%s] %s" % (email, result.message))
        except Exception as exc:  # noqa: BLE001 - một tài khoản lỗi không được giết cả mẻ
            result.status = STATUS_ERROR
            result.message = "Lỗi khi chạy: %s" % exc
            self.on_log("[%s] lỗi: %s" % (email, exc))
            result.screenshot = result.screenshot or session.screenshot(
                _screenshot_path(email, "error"))
        finally:
            if result.keep_open:
                # Chuyển phiên ra ngoài: KHÔNG close(), Chrome ở lại đúng trang đang làm.
                self.on_keep_open(email, session)
            else:
                if self.keep_open_seconds and not self.headless:
                    session.page.wait_for_timeout(self.keep_open_seconds * 1000)
                session.close()
        if retry:
            return False
        report(100)
        return True

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
            raise _ProxyRetry("trang chiến dịch chặn IP (UnexpectedRemoteAddress)")
        if response is None:
            # Không có response = mạng/proxy hỏng, thử proxy khác.
            raise _ProxyRetry("không tải được trang chiến dịch")
        if response.status >= 400:
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
        logged_out_selector = (login.get("logged_out_selector") or "").strip()
        if not login:
            return True

        def looks_logged_in():
            if logged_in_selector and self._has(session, logged_in_selector):
                return True
            if logged_out_selector and self._has(session, logged_out_selector):
                return False
            # Không có selector nào: recipe dựa vào việc form đã submit xong.
            return True

        report(15)
        if campaign_url:
            session.goto(campaign_url)
            session.page.wait_for_timeout(900)
            if looks_logged_in():
                self.on_log("[%s] phiên còn đăng nhập, bỏ qua bước login" % email)
                return True
        self.on_log("[%s] đăng nhập" % email)
        response = session.goto(login["url"])
        if response is None:
            raise _ProxyRetry("không tải được trang đăng nhập")
        session.page.wait_for_timeout(600)
        self._run_steps(session, phase_steps(recipe, "login"), email, password, result, report)
        if not campaign_url:
            return True
        session.goto(campaign_url)
        session.page.wait_for_timeout(900)
        if is_ip_lockout(session.page_text()):
            raise _ProxyRetry("trang chiến dịch chặn IP sau khi đăng nhập")
        if logged_in_selector or logged_out_selector:
            return looks_logged_in()
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
            if step.get("unless_submit") and self.submit:
                # Bước chỉ dành cho chế độ "chỉ điền" (vd: pause giữ cửa sổ lại).
                self.on_log("[%s] bỏ bước '%s' (đang bật submit)"
                            % (email, step.get("name") or action))
                continue
            if action == "submit" and not self.submit:
                result.last_step = "submit (bỏ vì chưa bật submit)"
                return True
            label = step.get("name") or action
            result.last_step = label
            missing = self._missing_card_tokens(step)
            if missing:
                raise RecipeNotReady(
                    "Bước '%s' cần thông tin thẻ (%s) nhưng chưa cấu hình. "
                    "Vào tab Cấu hình → nhóm 'Thông tin đặt hàng & thanh toán' để nhập."
                    % (label, ", ".join(missing)))
            when = step.get("when")
            if when and not truthy(render_value(when, email, password, self.card)):
                self.on_log("[%s] bỏ bước '%s' (chưa có %s)" % (email, label, when))
                continue
            try:
                self._run_step(session, step, email, password, result)
            except _PauseFlow:
                raise
            except Exception as exc:  # noqa: BLE001
                if step.get("optional"):
                    self.on_log("[%s] bỏ qua bước '%s': %s" % (email, label, exc))
                    continue
                raise RecipeNotReady("Bước '%s' thất bại: %s" % (label, exc)) from exc
            result.steps_done = index + 1
            report(min(84, 45 + int(35 * (index + 1) / total)))
        return False

    def _clear_cart(self, session, email, url, selector, campaign_url):
        """Xoá các dòng đang có trong giỏ rồi quay lại trang chiến dịch.

        Cần trước khi chọn slot khác: Parks2 giữ giỏ theo tài khoản, nên nếu không xoá
        thì đơn sẽ gồm cả dòng cũ (sai khung giờ, và có thể vượt giới hạn 1 vé/người).
        """
        page = session.page
        if not url:
            self.on_log("[%s] bỏ clear_cart: recipe thiếu URL giỏ hàng" % email)
            return
        session.goto(url)
        page.wait_for_timeout(1200)
        selector = selector or 'a[onclick*="\'delete\'"]'
        removed = 0

        def visible_delete():
            locator = page.locator(selector)
            for index in range(locator.count()):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:  # noqa: BLE001
                    continue
            return None

        # Đếm số dòng cần xoá trước, để không bấm lặp vô ích nếu nút vẫn còn trên trang.
        pending = 0
        locator = page.locator(selector)
        for index in range(locator.count()):
            try:
                if locator.nth(index).is_visible():
                    pending += 1
            except Exception:  # noqa: BLE001
                continue
        for _ in range(max(0, pending)):
            target = visible_delete()
            if target is None:
                break
            try:
                target.click(timeout=8000)
                removed += 1
                page.wait_for_timeout(1500)
            except Exception as exc:  # noqa: BLE001
                self.on_log("[%s] không xoá được dòng giỏ: %s" % (email, exc))
                break
        self.on_log("[%s] xoá %d dòng giỏ cũ" % (email, removed))
        if campaign_url:
            session.goto(campaign_url)
            page.wait_for_timeout(1200)

    def _click(self, page, selector, timeout):
        """Bấm phần tử ĐANG HIỆN đầu tiên khớp selector.

        Trang Parks2 lặp phần tử cho desktop và thanh dính đáy (cùng `#addCart`), nên
        `page.click()` có thể trúng bản bị che và treo tới hết timeout.
        """
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            raise RecipeNotReady("Không thấy phần tử %s" % selector)
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible():
                    continue
            except Exception:  # noqa: BLE001
                continue
            candidate.click(timeout=timeout)
            return True
        # Không thấy bản hiện: để Playwright báo lỗi rõ ràng như cũ.
        locator.first.click(timeout=timeout)
        return True

    def _fill(self, page, selector, value, timeout):
        """Điền cả khi ô nhập bị ẩn (Parks2 có bản mobile ẩn cùng id)."""
        locator = page.locator(selector)
        if locator.count() == 0:
            raise RecipeNotReady("Không thấy ô nhập %s" % selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            try:
                if item.is_visible():
                    item.fill(value, timeout=timeout)
                    return True
            except Exception:  # noqa: BLE001
                continue
        # Mọi bản đều ẩn: đặt giá trị bằng JS và phát event như người dùng gõ.
        locator.first.evaluate(
            "(el, v) => { el.value = v;"
            " el.dispatchEvent(new Event('input', {bubbles: true}));"
            " el.dispatchEvent(new Event('change', {bubbles: true})); }", value)
        return True

    def _select(self, page, selector, value, timeout):
        locator = page.locator(selector)
        if locator.count() == 0:
            raise RecipeNotReady("Không thấy ô chọn %s" % selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            try:
                if item.is_visible():
                    item.select_option(value=value, timeout=timeout)
                    return True
            except Exception:  # noqa: BLE001
                continue
        locator.first.evaluate(
            "(el, v) => { el.value = v;"
            " el.dispatchEvent(new Event('change', {bubbles: true})); }", value)
        return True

    def _current_value(self, page, selector):
        """Giá trị hiện tại của ô/select ('' nếu không đọc được)."""
        try:
            locator = page.locator(selector)
            if not locator.count():
                return ""
            return (locator.first.input_value(timeout=1500) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def _option_values(self, page, selector, limit=12):
        """Các `value` mà ô chọn đang có (để báo lỗi kèm lựa chọn thật của trang)."""
        try:
            values = page.locator(selector).first.evaluate(
                "(el) => Array.from(el.options || []).map(o => o.value).filter(Boolean)")
        except Exception:  # noqa: BLE001
            return []
        return list(values or [])[:limit]

    def _require_selected(self, session, email, selector, value):
        """Select xong mà ô vẫn trống -> dừng với danh sách mã trang đang có."""
        if self._current_value(session.page, selector):
            return
        options = self._option_values(session.page, selector)
        available = ", ".join(options) if options else "(không đọc được danh sách mã)"
        raise RecipeNotReady(
            "Không chọn được '%s' cho %s: ô %s vẫn trống. Mã trang đang có: %s"
            % (value, email, selector, available))

    def _raise_site_error(self, session):
        """Popup lỗi của site sau một cú bấm -> dừng ngay, không chờ timeout."""
        page = session.page
        for selector in SITE_ERROR_SELECTORS:
            message = self._element_text(page, selector)
            if message:
                raise _SiteError("Site báo: 「%s」" % message)
        text = session.page_text()
        for hint in SITE_ERROR_HINTS:
            if hint in text:
                raise _SiteError("Site báo: 「%s」" % hint)

    def _element_text(self, page, selector):
        """Chữ đang hiện trong một ô ('' nếu không có/không đọc được)."""
        try:
            locator = page.locator(selector)
            if not locator.count():
                return ""
            return locator.first.inner_text(timeout=1000).strip()
        except Exception:  # noqa: BLE001
            return ""

    def _missing_card_tokens(self, step):
        """Biến `{card_*}` mà recipe dùng nhưng hồ sơ thanh toán chưa có."""
        if (self.card or {}).get("card_number"):
            return []
        texts = [step.get("selector") or "", step.get("value") or "",
                 step.get("when") or ""]
        texts.extend(step.get("selectors") or [])
        used = set()
        for text in texts:
            if not isinstance(text, str):
                continue
            for token in re.findall(r"\{(card_[a-z_]+)\}", text):
                used.add(token)
        return sorted(used)

    def _run_step(self, session, step, email, password, result):
        page = session.page
        action = step.get("action")
        timeout = int(step.get("timeout") or BROWSER_ACTION_TIMEOUT)
        context = self.card
        selector = render_value(step.get("selector") or "", email, password, context)
        value = render_value(step.get("value") or "", email, password, context)

        if action == "goto":
            session.goto(render_value(value, email, password, context))
            page.wait_for_timeout(int(step.get("settle") or 500))
        elif action == "clear_cart":
            if not self.clear_cart:
                self.on_log("[%s] bỏ clear_cart (chưa bật xoá giỏ cũ)" % email)
                return
            self._clear_cart(session, email, value, selector, self.campaign_url)
        elif action == "fill":
            if step.get("only_if_empty") and self._current_value(page, selector):
                self.on_log("[%s] giữ nguyên %s (site đã có dữ liệu)" % (email, selector))
                return
            self._fill(page, selector, value, timeout)
        elif action == "select":
            if step.get("only_if_empty") and self._current_value(page, selector):
                self.on_log("[%s] giữ nguyên %s (đã chọn sẵn)" % (email, selector))
                return
            self._select(page, selector, value, timeout)
            if value:
                # Mã không có trong trang (vd 種類 của chiến dịch khác) thì ô chọn vẫn
                # trống -> báo ngay kèm mã trang đang có, khỏi phải đoán.
                self._require_selected(session, email, selector, value)
        elif action == "check":
            guard = step.get("only_if_empty")
            if isinstance(guard, str) and self._current_value(page, guard):
                self.on_log("[%s] giữ nguyên %s (đã có dữ liệu)" % (email, guard))
                return
            self._tick(session, selector, email)
        elif action == "click":
            self._click(page, selector, timeout)
            page.wait_for_timeout(int(step.get("settle") or 400))
            self._raise_site_error(session)
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
        elif action == "dismiss":
            self._dismiss(session, step, email, selector)
        elif action == "pause":
            # Recipe chỉ định điểm dừng an toàn (vd: trước bước thanh toán).
            self.on_log("[%s] dừng theo recipe: %s" % (email, step.get("name") or "pause"))
            raise _PauseFlow()
        elif action == "submit":
            result.submit_done = True
            self.on_log("[%s] bấm gửi đăng ký" % email)
            if selector:
                self._click(page, selector, timeout)
            else:
                page.keyboard.press("Enter")
        else:  # validate_recipe đã chặn, phòng khi recipe bị sửa tay lúc đang chạy
            raise RecipeNotReady("Bước không hỗ trợ: %s" % action)

    def _dismiss(self, session, step, email, fallback_selector):
        """Đóng popup: tick checkbox (nếu recipe khai báo) rồi bấm nút đang hiện.

        Popup của Parks2 là `#kessai-method-modal` chặn toàn trang: nút 閉じる chỉ bật
        sau khi tick 「内容確認しました。」. Checkbox đó bị ẩn trong `<label class="check-area">`
        (ô vuông là `span.custom-checkbox`), nên `check()` của Playwright không bấm được;
        phải bấm label bọc ngoài hoặc bật bằng JS + phát event change.
        """
        page = session.page
        check_selector = render_value(step.get("check") or "", email)
        if check_selector:
            self._tick(session, check_selector, email)
        selectors = step.get("selectors") or [fallback_selector]
        for candidate in selectors:
            if not candidate:
                continue
            try:
                locator = page.locator(candidate)
                if not locator.count():
                    continue
                for index in range(locator.count()):
                    item = locator.nth(index)
                    if not item.is_visible():
                        continue
                    item.click(timeout=3000)
                    page.wait_for_timeout(500)
                    self.on_log("[%s] đã đóng popup: %s" % (email, candidate))
                    break
            except Exception as exc:  # noqa: BLE001 - popup không đóng được cũng không chặn
                self.on_log("[%s] không đóng được popup %s: %s" % (email, candidate, exc))

    def _tick(self, session, selector, email):
        """Tick checkbox kể cả khi input bị ẩn trong label custom."""
        page = session.page
        try:
            if not page.locator(selector).count():
                return
            box = page.locator(selector).first
            try:
                if box.is_checked():
                    self.on_log("[%s] %s đã tick sẵn" % (email, selector))
                    return
            except Exception:  # noqa: BLE001 - không phải checkbox thì bỏ qua kiểm tra
                pass
            try:
                box.check(timeout=2000)
            except Exception:
                try:
                    page.locator("%s >> xpath=ancestor::label[1]" % selector).first.click(
                        timeout=3000)
                except Exception:
                    box.evaluate(
                        "el => { el.checked = true;"
                        " el.dispatchEvent(new Event('change', {bubbles: true})); }")
            page.wait_for_timeout(400)
            self.on_log("[%s] đã tick %s" % (email, selector))
        except Exception as exc:  # noqa: BLE001
            self.on_log("[%s] không tick được %s: %s" % (email, selector, exc))

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


