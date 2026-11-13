"""Use case: chạy đăng ký chiến dịch bằng trình duyệt cho nhiều tài khoản.

Service này là cầu nối duy nhất giữa UI/worker và hạ tầng trình duyệt:
- đọc recipe và báo trước (không mở Chrome) khi recipe còn nháp;
- chạy lần lượt/từng nhóm tài khoản, mỗi tài khoản một Chrome riêng;
- ghi nhận tài khoản đã đăng ký qua `CampaignService.mark()` như luồng thủ công.
"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import (
    BROWSER_RECIPE_FILE, DEFAULT_BROWSER_PARALLEL, MAX_BROWSER_PARALLEL,
)
from app.domain.browser_recipe import RecipeNotReady, load_recipe, validate_recipe
from app.infrastructure.browser.browser_session import find_chrome
from app.infrastructure.browser.campaign_runner import (
    SUCCESS_STATUSES, BrowserRunResult, CampaignBrowserRunner,
)
from proxy_manager import proxy_manager as default_proxy_manager


class BrowserCampaignService:
    """Chạy recipe trên nhiều tài khoản và ghi nhận kết quả."""

    def __init__(self, campaign_service=None, recipe_path=BROWSER_RECIPE_FILE,
                 submit=True, headless=False, parallel=DEFAULT_BROWSER_PARALLEL,
                 proxy_manager=None, chrome_path=None):
        self.campaign_service = campaign_service
        self.recipe_path = recipe_path
        self.submit = bool(submit)
        self.headless = bool(headless)
        self.parallel = max(1, min(MAX_BROWSER_PARALLEL, int(parallel or 1)))
        self.proxy_manager = proxy_manager if proxy_manager is not None else default_proxy_manager
        self.chrome_path = chrome_path or find_chrome()
        self._log = lambda message: None

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
            on_account_progress=None):
        """Chạy cho `accounts` = [(email, password)].

        `submit=None` dùng giá trị của service; `on_result(BrowserRunResult)` được
        gọi ngay khi từng tài khoản xong để UI cập nhật dòng của nó;
        `on_account_progress(email, percent)` báo tiến trình của *từng* tài khoản.
        """
        log = on_log or self._log
        progress = on_progress or (lambda done, total: None)
        submit = self.submit if submit is None else bool(submit)
        recipe = self.load_recipe()          # RecipeNotReady -> worker báo lỗi
        targets = [(email, password) for email, password in accounts
                   if (email or "").strip()]
        total = len(targets)
        results = []
        log("Chiến dịch '%s': %d tài khoản, %s, %d Chrome song song"
            % (campaign.get("name") or "(chưa đặt tên)", total,
               "tự bấm gửi" if submit else "chỉ điền, không gửi", self.parallel))
        if not total:
            return results

        def task(email, password):
            runner = CampaignBrowserRunner(
                recipe=recipe, submit=submit, headless=self.headless,
                proxy_manager=self.proxy_manager, chrome_path=self.chrome_path,
                on_log=log, keep_open_seconds=keep_open_seconds)
            report = (lambda percent: on_account_progress(email, percent)
                      if on_account_progress else None)
            return runner.run(email, password, campaign.get("url", ""),
                              on_progress=report)

        pool = ThreadPoolExecutor(max_workers=self.parallel)
        try:
            futures = {}
            for email, password in targets:
                if should_stop and should_stop():
                    break
                futures[pool.submit(task, email, password)] = email
            done = 0
            for future in as_completed(futures):
                email = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - một tài khoản chết không giết mẻ
                    result = BrowserRunResult(email=email, status="error",
                                              message="Lỗi không mong đợi: %s" % exc)
                results.append(result)
                self._record(campaign, result, log)
                if on_result:
                    on_result(result)
                done += 1
                progress(done, total)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        return results

    def _record(self, campaign, result, log):
        """Ghi nhận tài khoản đã đăng ký — chỉ khi trang xác nhận thành công."""
        if result.status not in SUCCESS_STATUSES or self.campaign_service is None:
            return
        if self.campaign_service.mark(campaign, result.email):
            log("Ghi nhận %s đã đăng ký '%s'"
                % (result.email, campaign.get("name") or "(chưa đặt tên)"))
