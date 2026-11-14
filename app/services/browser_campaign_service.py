"""Use case: chạy đăng ký chiến dịch bằng trình duyệt cho nhiều tài khoản.

Service này là cầu nối duy nhất giữa UI/worker và hạ tầng trình duyệt:
- đọc recipe và báo trước (không mở Chrome) khi recipe còn nháp;
- chạy lần lượt/từng nhóm tài khoản, mỗi tài khoản một Chrome riêng;
- ghi nhận tài khoản đã đăng ký qua `CampaignService.mark()` như luồng thủ công.
"""
import json
import os
import threading

from app.config import (
    BROWSER_RECIPE_FILE, DEFAULT_BROWSER_PARALLEL, MAX_BROWSER_PARALLEL,
)
from app.domain import checkout as checkout_domain
from app.domain.browser_recipe import RecipeNotReady, load_recipe, validate_recipe
from app.infrastructure.browser.browser_session import find_chrome, profile_slug
from app.infrastructure.browser.campaign_runner import (
    SUCCESS_STATUSES, BrowserRunResult, CampaignBrowserRunner,
)
from app.infrastructure.checkout_store import CheckoutStore
from proxy_manager import proxy_manager as default_proxy_manager


class BrowserCampaignService:
    """Chạy recipe trên nhiều tài khoản và ghi nhận kết quả."""

    def __init__(self, campaign_service=None, recipe_path=BROWSER_RECIPE_FILE,
                 submit=True, headless=False, parallel=DEFAULT_BROWSER_PARALLEL,
                 proxy_manager=None, chrome_path=None, checkout_store=None):
        self.campaign_service = campaign_service
        self.recipe_path = recipe_path
        self.submit = bool(submit)
        self.headless = bool(headless)
        self.parallel = max(1, min(MAX_BROWSER_PARALLEL, int(parallel or 1)))
        self.proxy_manager = proxy_manager if proxy_manager is not None else default_proxy_manager
        self.chrome_path = chrome_path or find_chrome()
        # Hồ sơ đặt hàng/thẻ do người dùng nhập trong UI (không hard-code).
        self.checkout_store = checkout_store or CheckoutStore()
        self._log = lambda message: None
        # Cửa sổ Chrome đang để mở cho người dùng làm tiếp (bước thanh toán).
        self.open_sessions = {}
        # Chặn mở quá nhiều cửa sổ cùng lúc (mỗi Chrome ~300-500MB RAM).
        self.max_paused = 3

    # ---------------- kiểm tra trước khi chạy ----------------
    def preflight(self):
        """Trả (ok, message): thiếu Chrome / thiếu recipe thì báo ngay, không mở Chrome."""
        if not self.chrome_path or not os.path.isfile(self.chrome_path):
            return False, ("Không tìm thấy chrome.exe. Cài Google Chrome rồi thử lại "
                           "(hoặc đặt biến CHROME_PATH).")
        if not os.path.isfile(self.recipe_path):
            return False, ("Chưa có recipe: %s\nDò trang bằng:\n"
                           "python browser_campaign.py --discover --email <email> "
                           "--password <pass> --url <link chiến dịch>" % self.recipe_path)
        try:
            load_recipe(self.recipe_path)
        except RecipeNotReady as exc:
            return False, str(exc)
        return True, "Recipe và Chrome sẵn sàng"

    def load_recipe(self):
        """Recipe đã validate; raise RecipeNotReady khi chưa dùng được."""
        return load_recipe(self.recipe_path)

    @staticmethod
    def validate_file(path):
        """Kiểm tra cấu trúc một file recipe mà không cần Chrome."""
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                return validate_recipe(json.load(handle))
        except OSError as exc:
            return ["Không đọc được %s: %s" % (path, exc)]
        except ValueError as exc:
            return ["JSON không hợp lệ: %s" % exc]

    # ---------------- chạy ----------------
    def run(self, campaign, accounts, on_log=None, on_progress=None, on_result=None,
            should_stop=None, submit=None, keep_open_seconds=0,
            on_account_progress=None, recipe=None, recipe_for=None, profile_for=None,
            clear_cart=False, use_proxy=None):
        """Chạy cho `accounts` = [(email, password)].

        `submit=None` dùng giá trị của service; `on_result(BrowserRunResult)` được
        gọi ngay khi từng tài khoản xong để UI cập nhật dòng của nó;
        `on_account_progress(email, percent)` báo tiến trình của *từng* tài khoản;
        `recipe` để nơi gọi truyền recipe đã sửa (vd: đổi slot ngày/giờ);
        `recipe_for(email)` trả recipe riêng của tài khoản đó — dùng khi mỗi tài khoản
        có một slot ngày/giờ khác nhau (rỗng thì dùng `recipe` chung);
        `profile_for(email)` trả biến hồ sơ riêng của tài khoản (địa chỉ khác nhau) —
        giá trị khác rỗng sẽ đè lên hồ sơ dùng chung.
        """
        log = on_log or self._log
        progress = on_progress or (lambda done, total: None)
        submit = self.submit if submit is None else bool(submit)
        recipe = recipe or self.load_recipe()   # RecipeNotReady -> worker báo lỗi
        # Hồ sơ đặt hàng/thẻ: đọc một lần cho cả lượt chạy, chỉ log bản tóm tắt an toàn.
        profile = self.checkout_store.load()
        card = checkout_domain.profile_vars(profile)
        if card:
            log("Hồ sơ đặt hàng: %s" % checkout_domain.summary(profile))
        gaps = checkout_domain.missing_required(profile)
        if gaps:
            log("Thiếu thông tin bắt buộc (sẽ để trống cho bạn điền): %s" % ", ".join(gaps))
        targets = []
        for account in accounts:
            # `(email, password)` như cũ, hoặc `(email, password, token)` khi tài khoản
            # có serial code riêng (token) cho chiến dịch 景品ミニゲーム.
            email = account[0]
            password = account[1] if len(account) > 1 else ""
            token = account[2] if len(account) > 2 else ""
            if (email or "").strip():
                targets.append((email, password, token or ""))
        total = len(targets)
        results = []
        log("Chiến dịch '%s': %d tài khoản, %s, %d Chrome song song"
            % (campaign.get("name") or "(chưa đặt tên)", total,
               "tự bấm gửi" if submit else "chỉ điền, không gửi", self.parallel))
        if not total:
            return results

        def task(email, password, token=""):
            if len(self.open_sessions) >= self.max_paused:
                return BrowserRunResult(
                    email=email, status="skipped",
                    message="Bỏ qua: đã có %d cửa sổ Chrome đang chờ bạn thanh toán"
                            % self.max_paused)
            # Hồ sơ riêng của tài khoản (nếu có) đè lên hồ sơ dùng chung.
            account_card = dict(card)
            # Token của tài khoản = serial code 景品ミニゲーム; recipe dùng `{token}`.
            account_card["token"] = token
            if profile_for:
                try:
                    extra = profile_for(email) or {}
                    account_card.update({key: value for key, value in extra.items() if value})
                except Exception as exc:  # noqa: BLE001 - thiếu hồ sơ riêng không chặn chạy
                    log("Không lấy được hồ sơ riêng của %s: %s" % (email, exc))
            runner = CampaignBrowserRunner(
                # Slot ngày/giờ có thể khác nhau từng tài khoản -> recipe riêng.
                recipe=(recipe_for(email) if recipe_for else recipe),
                submit=submit, headless=self.headless,
                # use_proxy=False: chạy bằng IP máy dù proxy đang bật trong cấu hình.
                proxy_manager=self.proxy_manager if use_proxy is not False else None,
                chrome_path=self.chrome_path, on_log=log,
                keep_open_seconds=keep_open_seconds, on_keep_open=self._keep_open,
                card=account_card, clear_cart=clear_cart)
            report = (lambda percent: on_account_progress(email, percent)
                      if on_account_progress else None)
            return runner.run(email, password, campaign.get("url", ""),
                              on_progress=report)

        # Mỗi tài khoản chạy trong MỘT THREAD RIÊNG: Playwright sync API gắn chặt với
        # thread đã tạo nó, nên nếu tài khoản trước bị giữ cửa sổ (bước `pause`) mà
        # tài khoản sau chạy lại trong cùng thread thì Playwright thứ hai treo.
        # Semaphore giữ đúng số Chrome song song; parallel=1 thì join từng cái.
        semaphore = threading.Semaphore(self.parallel)
        lock = threading.Lock()
        state = {"done": 0}

        def worker(email, password, token=""):
            if should_stop and should_stop():
                return
            with semaphore:
                try:
                    result = task(email, password, token)
                except Exception as exc:  # noqa: BLE001 - một tài khoản chết không giết mẻ
                    result = BrowserRunResult(email=email, status="error",
                                              message="Lỗi không mong đợi: %s" % exc)
            with lock:
                results.append(result)
                self._record(campaign, result, log)
                if on_result:
                    on_result(result)
                state["done"] += 1
                progress(state["done"], total)

        threads = []
        for email, password, token in targets:
            thread = threading.Thread(target=worker, args=(email, password, token),
                                      name="browser-%s" % profile_slug(email), daemon=True)
            thread.start()
            threads.append(thread)
            if self.parallel == 1:
                thread.join()
        for thread in threads:
            thread.join()
        return results

    def _record(self, campaign, result, log):
        """Ghi nhận tài khoản đã đăng ký — chỉ khi trang xác nhận thành công."""
        if result.status not in SUCCESS_STATUSES or self.campaign_service is None:
            return
        if self.campaign_service.mark(campaign, result.email):
            log("Ghi nhận %s đã đăng ký '%s'"
                % (result.email, campaign.get("name") or "(chưa đặt tên)"))

    # ---------------- cửa sổ để mở cho người dùng ----------------
    def _keep_open(self, email, session):
        """Giữ phiên Chrome ở đúng trang đang làm để người dùng tự hoàn tất.

        Không close() phiên này: Playwright giữ tiến trình Chrome sống theo app, nên
        cửa sổ còn nguyên chừng nào app còn chạy.
        """
        self.open_sessions[email] = session
        self._log("[%s] giữ cửa sổ Chrome ở cổng %s để bạn làm tiếp"
                  % (email, session.port))

    def close_open_sessions(self):
        """Đóng các cửa sổ đang giữ (gọi khi người dùng bấm đóng hoặc thoát app)."""
        count = len(self.open_sessions)
        for email, session in list(self.open_sessions.items()):
            try:
                session.close()
            except Exception:  # noqa: BLE001 - đóng cửa sổ không được thì bỏ qua
                pass
            self.open_sessions.pop(email, None)
        return count

