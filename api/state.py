"""Trạng thái dùng chung của API: wiring, log buffer, hàng đợi job.

Một tiến trình API giữ đúng một `ApiState`; mọi router lấy từ đây. Nghiệp vụ vẫn
gọi service/domain trong `app/` — không có logic mới ở tầng này.
"""
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from app.config import (
    BROWSER_ARTIFACTS_DIR, BROWSER_RECIPE_FILE, CHECKOUT_FILE, DATA_FILE,
    DEFAULT_BROWSER_PARALLEL, DEFAULT_CONCURRENCY, MAX_BROWSER_PARALLEL,
    MAX_CONCURRENCY, SETTINGS_FILE, WEB_SETTINGS_FILE,
)
from app.domain import checkout as checkout_domain
from app.infrastructure.account_repository import AccountRepository
from app.infrastructure.bandai_auth import BandaiAuthClient
from app.infrastructure.bandai_name import BandaiNameClient
from app.infrastructure.browser.browser_session import find_chrome
from app.infrastructure.browser.campaign_runner import navigate_only
from app.infrastructure.browser.discovery import discover_page
from app.infrastructure.checkout_store import CheckoutStore
from app.infrastructure.file_settings import FileSettingsStore
from app.services.account_service import AccountService
from app.services.browser_campaign_service import BrowserCampaignService
from app.services.campaign_service import CampaignService
from app.domain.names import kanji_overrides
from proxy_manager import PROXY_FILE, proxy_manager, set_event_sink

MAX_LOG_LINES = 500
LOG_LEVELS = ("info", "warn", "error", "ok")


# ============================================================
# LOG
# ============================================================
class LogBuffer:
    """Nhật ký trong bộ nhớ: UI web lấy phần mới bằng con trỏ `seq`."""

    def __init__(self, size=MAX_LOG_LINES):
        self._lines = deque(maxlen=size)
        self._seq = 0
        self._lock = threading.Lock()

    def add(self, message: str, level: str = "info"):
        text = str(message or "").strip()
        if not text:
            return
        with self._lock:
            self._seq += 1
            self._lines.append({
                "seq": self._seq,
                "at": datetime.now().strftime("%H:%M:%S"),
                "level": level if level in LOG_LEVELS else "info",
                "message": text,
            })
        # In ra stdout để chạy CLI/docker vẫn xem được log (console Windows có thể
        # không phải UTF-8 nên phải chịu lỗi encoding, không được làm chết API).
        try:
            print("[%s] %s" % (level, text), flush=True)
        except (UnicodeEncodeError, OSError):
            try:
                print(("[%s] %s" % (level, text)).encode("ascii", "replace").decode("ascii"),
                      flush=True)
            except OSError:
                pass

    def since(self, seq: int = 0):
        with self._lock:
            items = [line for line in self._lines if line["seq"] > seq]
            return {"cursor": self._seq, "lines": items}


# ============================================================
# JOB
# ============================================================
@dataclass
class Job:
    id: str
    kind: str
    title: str
    total: int = 0
    done: int = 0
    status: str = "running"           # running | done | error | cancelled
    message: str = ""
    items: list = field(default_factory=list)
    result: dict = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    finished_at: str = ""
    _stop: bool = False

    def as_dict(self):
        return {
            "id": self.id, "kind": self.kind, "title": self.title,
            "total": self.total, "done": self.done, "status": self.status,
            "message": self.message, "items": self.items, "result": self.result,
            "started_at": self.started_at, "finished_at": self.finished_at,
        }


class JobRegistry:
    """Chạy tác vụ dài trong thread nền; UI poll `GET /api/jobs/{id}`."""

    def __init__(self, logs: LogBuffer, keep=40):
        self._jobs = {}
        self._order = deque(maxlen=keep)
        self._logs = logs
        self._lock = threading.Lock()

    def start(self, kind, title, worker: Callable[[Job], Any], total=0) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title, total=total)
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)

        def runner():
            self._logs.add(title)
            try:
                result = worker(job)
                job.result = result if isinstance(result, dict) else {}
                if job.status == "running":
                    job.status = "done"
                if job.message:
                    self._logs.add("%s: %s" % (title, job.message), "ok")
            except Exception as exc:  # noqa: BLE001 - job lỗi không được làm chết server
                job.status = "error"
                job.message = str(exc)
                self._logs.add("%s: lỗi - %s" % (title, exc), "error")
            finally:
                job.finished_at = datetime.now().strftime("%H:%M:%S")

        threading.Thread(target=runner, name="job-%s" % kind, daemon=True).start()
        return job

    def get(self, job_id) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id) -> bool:
        job = self.get(job_id)
        if job is None or job.status != "running":
            return False
        job._stop = True
        job.status = "cancelled"
        self._logs.add("%s: đã yêu cầu dừng" % job.title, "warn")
        return True

    def recent(self, limit=10):
        with self._lock:
            ids = list(self._order)[-limit:]
            return [self._jobs[job_id].as_dict() for job_id in reversed(ids)
                    if job_id in self._jobs]


# ============================================================
# STATE
# ============================================================
class ApiState:
    """Wiring một lần cho cả tiến trình API."""

    def __init__(self, data_file=DATA_FILE, settings_file=WEB_SETTINGS_FILE,
                 recipe_path=BROWSER_RECIPE_FILE, checkout_file=CHECKOUT_FILE):
        self.logs = LogBuffer()
        self.jobs = JobRegistry(self.logs)
        # `web_settings.json` là nơi lưu của bản web; lần đầu chép từ INI của bản
        # desktop để danh sách chiến dịch/tuỳ chọn không bị mất.
        self.settings = FileSettingsStore(settings_file, legacy_ini=SETTINGS_FILE)
        self.repository = AccountRepository(path=data_file, on_change=self.log)
        self.accounts = AccountService(self.repository)
        self.accounts.load()
        self.campaigns = CampaignService(self.settings)
        self.campaigns.load()
        self.auth = BandaiAuthClient()
        self.names = BandaiNameClient(auth_client=self.auth)
        self.checkout = CheckoutStore(path=checkout_file, on_log=self.log)
        self.browser = BrowserCampaignService(
            campaign_service=self.campaigns,
            recipe_path=recipe_path,
            submit=self.settings.get_bool("browser_submit", True),
            headless=self.settings.get_bool("browser_headless", False),
            parallel=self.settings.get_int("browser_parallel", DEFAULT_BROWSER_PARALLEL),
            checkout_store=self.checkout,
        )
        self.max_workers = max(1, min(MAX_CONCURRENCY,
                                      self.settings.get_int("max_workers", DEFAULT_CONCURRENCY)))
        # Nạp proxy đã lưu vào proxy_manager NGAY khi khởi động: thiếu bước này thì
        # sau mỗi lần restart, proxy trong cấu hình bị bỏ qua (request đi bằng IP máy).
        self.apply_proxy_settings()
        self.apply_browser_settings()
        proxy_state = self.proxy_settings()
        if proxy_state["enabled"]:
            self.log("Proxy: %d proxy, chế độ %s" % (proxy_state["count"],
                                                     proxy_state["mode"]))
        else:
            self.log("Proxy: tắt (request dùng IP máy)")
        # Log của proxy_manager và của lần chạy trình duyệt đều đổ về buffer.
        set_event_sink(lambda message: self.log(message))
        self.log("API sẵn sàng — dữ liệu: %s" % data_file)

    # ---------------- log ----------------
    def log(self, message, level="info"):
        self.logs.add(message, level)

    # ---------------- tài khoản ----------------
    def save_accounts(self):
        self.repository.save(self.accounts.accounts)

    def account_public(self, account: dict) -> dict:
        """Bản gửi ra UI: không bao giờ trả mật khẩu."""
        data = {key: value for key, value in account.items() if key != "password"}
        data["email"] = account.get("email", "")
        data["has_password"] = bool(account.get("password"))
        return data

    # ---------------- chiến dịch ----------------
    def campaign_view(self, campaign: dict, row: int) -> dict:
        from app.domain.campaigns import campaign_status, format_campaign_remaining
        view = dict(campaign)
        view["row"] = row
        view["status"] = campaign_status(campaign)
        view["remaining"] = format_campaign_remaining(campaign)
        view["signup_count"] = len(self.campaigns.signups_for(campaign))
        return view

    def campaigns_view(self):
        return [self.campaign_view(campaign, row)
                for row, campaign in enumerate(self.campaigns.campaigns)]

    # ---------------- trình duyệt ----------------
    def browser_settings(self) -> dict:
        recipe_path = (self.settings.get("browser_recipe", "") or BROWSER_RECIPE_FILE)
        return {
            "recipe_path": recipe_path,
            "headless": self.settings.get_bool("browser_headless", False),
            "parallel": self.settings.get_int("browser_parallel", DEFAULT_BROWSER_PARALLEL),
            "submit": self.settings.get_bool("browser_submit", True),
            "max_parallel": MAX_BROWSER_PARALLEL,
            "chrome": find_chrome() or "",
            "artifacts_dir": BROWSER_ARTIFACTS_DIR,
        }

    def apply_browser_settings(self):
        settings = self.browser_settings()
        self.browser.recipe_path = settings["recipe_path"]
        self.browser.headless = settings["headless"]
        self.browser.parallel = max(1, min(MAX_BROWSER_PARALLEL, settings["parallel"]))
        self.browser.submit = settings["submit"]

    def sessions_view(self):
        return [{"email": email, "port": session.port, "profile": session.profile_dir}
                for email, session in self.browser.open_sessions.items()]

    # ---------------- hồ sơ đặt hàng ----------------
    def account_checkout_vars(self, email):
        """Biến địa chỉ của MỘT tài khoản, lấy từ hồ sơ Parks2 đã đọc.

        Dùng khi chạy nhiều tài khoản có địa chỉ khác nhau: hồ sơ chung chỉ giữ phần
        không phụ thuộc tài khoản (thẻ), còn địa chỉ lấy theo từng người.
        """
        account = self.accounts.find(email) or {}
        data = {
            "l_name": account.get("last_name_kanji", ""),
            "f_name": account.get("first_name_kanji", ""),
            "l_kana": account.get("last_name_kana", ""),
            "f_kana": account.get("first_name_kana", ""),
            "zip": account.get("postal_code", ""),
            "pref": account.get("prefecture", ""),
            "city": account.get("city", ""),
            "street": account.get("address_number", ""),
            "tel": account.get("phone", ""),
        }
        variables = checkout_domain.profile_vars(data)
        return {key: value for key, value in variables.items() if value}

    def checkout_public(self) -> dict:
        """Bản gửi ra UI: chỉ số thẻ đã che, không có CVV, không có số đầy đủ."""
        profile = self.checkout.load()
        masked = dict(profile)
        if checkout_domain.has_card(profile):
            masked["card_number"] = checkout_domain.mask_card(profile.get("card_number"))
        else:
            masked["card_number"] = ""
        masked["card_cvv"] = ""
        masked["has_card"] = checkout_domain.has_card(profile)
        masked["filled"] = any(profile.get(name) for name in checkout_domain.ALL_FIELDS)
        masked["encrypted"] = profile.get("encrypted", True) if profile else False
        masked["summary"] = checkout_domain.short_summary(
            profile, profile.get("encrypted", True) if profile else False)
        masked["gaps"] = checkout_domain.missing_required(profile)
        return masked

    # ---------------- proxy ----------------
    def proxy_settings(self) -> dict:
        return {
            "enabled": self.settings.get_bool("proxy_enabled", False),
            "mode": self.settings.get("proxy_mode", "per_request"),
            "file": self.settings.get("proxy_file", PROXY_FILE) or PROXY_FILE,
            "count": len(proxy_manager.proxies),
            "blocked": proxy_manager.blocked_count(),
        }

    def apply_proxy_settings(self):
        proxy_manager.path = self.settings.get("proxy_file", PROXY_FILE) or PROXY_FILE
        proxy_manager.mode = self.settings.get("proxy_mode", "per_request")
        proxy_manager.enabled = self.settings.get_bool("proxy_enabled", False)
        proxy_manager.load()

    # ============================================================
    # JOB: kiểm tra đăng nhập hàng loạt
    # ============================================================
    def start_account_check(self, emails):
        """Đăng nhập từng tài khoản (song song theo max_workers) và ghi kết quả."""
        selected = [self.accounts.find(email) for email in emails]
        selected = [account for account in selected if account]
        total = len(selected)

        def worker(job: Job):
            def check_one(account):
                if job._stop:
                    return None
                email = account.get("email", "")
                try:
                    outcome = self.auth.authenticate(email, account.get("password", ""))
                except Exception as exc:  # noqa: BLE001 - một tài khoản lỗi không giết job
                    self.accounts.set_status(email, False)
                    return {"email": email, "ok": False, "message": "Lỗi: %s" % exc}
                if not outcome.success:
                    self.accounts.set_status(email, False)
                    return {"email": email, "ok": False,
                            "message": "Đăng nhập thất bại: %s" % outcome.reason}
                profile = dict(outcome.profile or {})
                profile.setdefault("status", "Chưa kiểm tra")
                profile.setdefault("last_check", None)
                self.accounts.apply_profile(email, profile)
                self.accounts.set_status(email, True)
                message = "OK (%d trường hồ sơ)" % outcome.profile_fields
                if outcome.note:
                    message += " — %s" % outcome.note
                return {"email": email, "ok": True, "message": message}

            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                for item in pool.map(check_one, selected):
                    if item is None:
                        continue
                    job.items.append(item)
                    job.done += 1
                    level = "ok" if item["ok"] else "error"
                    self.logs.add("%s: %s" % (item["email"], item["message"]), level)
            self.save_accounts()
            ok_count = sum(1 for item in job.items if item["ok"])
            job.message = "%d/%d thành công" % (ok_count, total)
            return {"ok_count": ok_count, "total": total}

        return self.jobs.start("account_check", "Kiểm tra %d tài khoản" % total,
                               worker, total=total)

    # ============================================================
    # JOB: đổi tên
    # ============================================================
    def start_name_change(self, email, last_name, first_name):
        account = self.accounts.find(email)
        if account is None:
            raise ValueError("Không có tài khoản %s" % email)

        def worker(job: Job):
            outcome = self.names.change_profile(
                email, account.get("password", ""),
                kanji_overrides(last_name, first_name))
            job.items.append({"email": email, "ok": bool(outcome.success),
                              "message": outcome.message})
            job.done = 1
            job.message = outcome.message
            return {"success": bool(outcome.success)}

        return self.jobs.start("name_change", "Đổi tên %s" % email, worker, total=1)

    # ============================================================
    # JOB: kiểm tra proxy
    # ============================================================
    def start_proxy_check(self):
        from proxy_manager import check_all_proxies

        entries = list(proxy_manager.proxies)

        def worker(job: Job):
            def emit(index, ok, message):
                label = "%s:%s" % (entries[index]["host"], entries[index]["port"]) \
                    if index < len(entries) else ""
                job.items.append({"email": label, "ok": bool(ok), "message": message})
                job.done += 1

            check_all_proxies(entries, emit, is_running=lambda: not job._stop,
                              manager=proxy_manager)
            ok_count = sum(1 for item in job.items if item["ok"])
            job.message = "%d/%d proxy sống" % (ok_count, len(entries))
            return {"ok_count": ok_count, "total": len(entries)}

        return self.jobs.start("proxy_check", "Kiểm tra %d proxy" % len(entries),
                               worker, total=len(entries))

    # ============================================================
    # JOB: chạy chiến dịch bằng Chrome
    # ============================================================
    def start_browser_run(self, campaign, emails, submit=None, slot="", url_override="",
                          use_account_address=False, clear_cart=False, use_proxy=None):
        """`campaign` là dict có name/url (dựng từ UI); emails lấy mật khẩu trong kho."""
        targets = []
        for email in emails:
            account = self.accounts.find(email)
            if account:
                targets.append((account.get("email", email), account.get("password", "")))
        campaign = dict(campaign or {})
        if url_override:
            campaign["url"] = url_override
        recipe = None
        if slot:
            try:
                recipe = self.browser.load_recipe()
                for step in recipe.get("entry", {}).get("steps", []):
                    if step.get("selector") == "#PRIORITY_ITEMPROPERTY_CD_MATRIX_0":
                        step["value"] = slot
            except Exception:  # noqa: BLE001 - preflight bên dưới sẽ báo lỗi rõ
                recipe = None
        self.apply_browser_settings()
        total = len(targets)

        # Cửa sổ cũ của chính tài khoản đó (đang pause) phải đóng trước: Chrome chỉ cho
        # một tiến trình giữ mỗi profile, nếu không sẽ báo "Opening in existing session".
        for email, _password in targets:
            session = self.browser.open_sessions.pop(email, None)
            if session is not None:
                try:
                    session.close()
                except Exception:  # noqa: BLE001 - đóng không được thì bỏ qua
                    pass
                self.log("[%s] đóng cửa sổ Chrome cũ (profile đang bị giữ)" % email)

        # Địa chỉ của từng tài khoản lấy từ hồ sơ Parks2 đã đọc (mỗi người một địa chỉ).
        profile_for = self.account_checkout_vars if use_account_address else None

        def worker(job: Job):
            def on_result(result):
                job.items.append({"email": result.email, "ok": bool(result.ok),
                                  "message": result.message, "status": result.status,
                                  "screenshot": result.screenshot,
                                  "url": result.final_url,
                                  "proxy": result.details.get("proxy", "")})
                job.done += 1

            results = self.browser.run(
                campaign, targets, on_log=lambda message: self.logs.add(message),
                on_result=on_result, should_stop=lambda: job._stop,
                submit=submit, recipe=recipe, profile_for=profile_for,
                clear_cart=clear_cart, use_proxy=use_proxy)
            ok_count = sum(1 for result in results if result.ok)
            paused = [result.email for result in results if result.keep_open]
            job.message = "%d/%d xong%s" % (
                ok_count, total,
                (" — %d cửa sổ đang chờ bạn hoàn tất" % len(paused)) if paused else "")
            return {"ok_count": ok_count, "total": total, "paused": paused}

        return self.jobs.start("browser_run", "Chạy chiến dịch cho %d tài khoản" % total,
                               worker, total=total)

    # ============================================================
    # JOB: dò trang (soạn recipe)
    # ============================================================
    def start_discovery(self, email, url):
        def worker(job: Job):
            out_dir = ""
            session = None
            try:
                session = navigate_only(email, url, headless=False, on_log=self.logs.add,
                                        hold_seconds=2500)
                paths = discover_page(email, url, session,
                                      on_log=lambda message: self.logs.add(message))
                out_dir = paths.get("dir", "")
                job.items.append({"email": email, "ok": bool(out_dir),
                                  "message": out_dir or "Không lưu được dữ liệu dò trang"})
            finally:
                if session is not None:
                    session.close()
            job.done = 1
            job.message = out_dir or "Dò trang thất bại"
            return {"dir": out_dir}

        return self.jobs.start("browser_discovery", "Dò trang cho %s" % email, worker, total=1)


def default_state() -> ApiState:
    """State mặc định theo biến môi trường (dùng cho `uvicorn api.app:app`)."""
    import os as _os

    return ApiState(
        data_file=_os.environ.get("ACCOUNTS_FILE", DATA_FILE),
        settings_file=_os.environ.get("SETTINGS_FILE", WEB_SETTINGS_FILE),
        recipe_path=_os.environ.get("RECIPE_FILE", BROWSER_RECIPE_FILE),
    )


