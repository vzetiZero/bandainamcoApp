"""FastAPI app: mở toàn bộ nghiệp vụ của `app/` ra HTTP/JSON cho UI Next.js.

Nguyên tắc:
- Không có logic nghiệp vụ ở đây; chỉ đọc/ghi qua `ApiState` (services + domain).
- Không trả mật khẩu, không trả số thẻ đầy đủ/CVV ra client.
- Tác vụ dài (kiểm tra hàng loạt, chạy Chrome) trả `job_id` để UI poll.

Chạy: `python server.py` (hoặc `uvicorn api.app:app --port 8787`).
"""
import os
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.config import API_CORS_ORIGINS, MAX_BROWSER_PARALLEL, MAX_CONCURRENCY
from app.domain import checkout as checkout_domain
from app.domain.browser_recipe import RecipeNotReady, load_recipe, validate_recipe
from app.domain.campaigns import CAMPAIGN_STATUS_CLOSED, CAMPAIGN_STATUS_OPEN
from api.state import ApiState, default_state


def create_app(state: Optional[ApiState] = None) -> FastAPI:
    api = FastAPI(title="NAMCO Account Manager API", version="1.0",
                  description="Backend Python cho UI Next.js")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in API_CORS_ORIGINS if origin.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app_state = state or default_state()
    api.state.api = app_state

    def st() -> ApiState:
        return api.state.api

    # ========================================================
    # HEALTH
    # ========================================================
    @api.get("/api/health")
    def health():
        current = st()
        try:
            load_recipe(current.browser.recipe_path)
            recipe_ok, recipe_message = True, "Recipe hợp lệ"
        except RecipeNotReady as exc:
            recipe_ok, recipe_message = False, str(exc).splitlines()[0]
        return {
            "ok": True,
            "accounts": len(current.accounts.accounts),
            "campaigns": len(current.campaigns.campaigns),
            "recipe_ok": recipe_ok,
            "recipe_message": recipe_message,
            "chrome": current.browser.chrome_path or "",
            "checkout_filled": current.checkout_public()["filled"],
            "mode": "web",
        }

    @api.get("/api/logs")
    def logs(after: int = Query(0, ge=0)):
        return st().logs.since(after)

    # ========================================================
    # JOBS
    # ========================================================
    @api.get("/api/jobs")
    def jobs_recent(limit: int = Query(10, ge=1, le=50)):
        return {"items": st().jobs.recent(limit)}

    @api.get("/api/jobs/{job_id}")
    def job_detail(job_id: str):
        job = st().jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Không có job %s" % job_id)
        return job.as_dict()

    @api.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str):
        if not st().jobs.cancel(job_id):
            raise HTTPException(409, "Job không chạy hoặc đã kết thúc")
        return {"ok": True}

    # ========================================================
    # TÀI KHOẢN
    # ========================================================
    @api.get("/api/accounts")
    def accounts_list(query: str = "", status: str = ""):
        current = st()
        items = [current.account_public(account)
                 for account in current.accounts.visible(query, status)]
        return {"items": items, "counts": current.accounts.counts(),
                "total": len(current.accounts.accounts)}

    @api.post("/api/accounts")
    def accounts_add(payload: dict = Body(...)):
        current = st()
        email = (payload.get("email") or "").strip()
        password = payload.get("password") or ""
        if not email or not password:
            raise HTTPException(400, "Cần email và password")
        if not current.accounts.add(email, password, payload.get("token")):
            raise HTTPException(409, "Tài khoản %s đã có trong danh sách" % email)
        current.save_accounts()
        return current.account_public(current.accounts.find(email))

    @api.post("/api/accounts/preview")
    def accounts_preview(payload: dict = Body(...)):
        lines = (payload.get("text") or "").splitlines()
        return st().accounts.preview(lines)

    @api.post("/api/accounts/import")
    def accounts_import(payload: dict = Body(...)):
        current = st()
        lines = (payload.get("text") or "").splitlines()
        result = current.accounts.add_lines(lines)
        current.save_accounts()
        return result

    @api.delete("/api/accounts")
    def accounts_delete(payload: dict = Body(...)):
        current = st()
        emails = payload.get("emails") or []
        rows = [index for index, account in enumerate(current.accounts.accounts)
                if account.get("email") in emails]
        deleted = current.accounts.delete_rows(rows)
        current.save_accounts()
        return {"deleted": deleted}

    @api.get("/api/accounts/export", response_class=PlainTextResponse)
    def accounts_export():
        return "\n".join(st().accounts.export_lines())

    @api.get("/api/accounts/{email}")
    def account_detail(email: str):
        current = st()
        account = current.accounts.find(email)
        if account is None:
            raise HTTPException(404, "Không có tài khoản %s" % email)
        return current.account_public(account)

    @api.post("/api/accounts/{email}/check")
    def account_check(email: str):
        current = st()
        if current.accounts.find(email) is None:
            raise HTTPException(404, "Không có tài khoản %s" % email)
        return current.start_account_check([email]).as_dict()

    @api.post("/api/accounts/check")
    def accounts_check(payload: dict = Body(default={})):
        """Kiểm tra nhiều tài khoản: `emails` hoặc `all: true` (bỏ qua tài khoản đang hoạt động)."""
        current = st()
        if payload.get("all"):
            emails = [account["email"] for account in current.accounts.accounts
                      if not payload.get("only_inactive")
                      or account.get("status") != "Hoạt động"]
        else:
            emails = payload.get("emails") or []
        if not emails:
            raise HTTPException(400, "Chọn ít nhất một tài khoản")
        return current.start_account_check(emails).as_dict()

    @api.post("/api/accounts/{email}/name")
    def account_change_name(email: str, payload: dict = Body(...)):
        try:
            job = st().start_name_change(email, payload.get("last_name", ""),
                                         payload.get("first_name", ""))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return job.as_dict()

    # ========================================================
    # CHIẾN DỊCH
    # ========================================================
    @api.get("/api/campaigns")
    def campaigns_list(status: str = "", query: str = ""):
        current = st()
        items = current.campaigns_view()
        if status in (CAMPAIGN_STATUS_OPEN, CAMPAIGN_STATUS_CLOSED, "soon", "Chưa mở", "Chưa rõ"):
            if status == "soon":
                items = [item for item in items
                         if item["status"] == "Chưa mở" and item["remaining"]]
            else:
                items = [item for item in items if item["status"] == status]
        if query.strip():
            needle = query.strip().lower()
            items = [item for item in items
                     if needle in (item.get("name") or "").lower()
                     or needle in (item.get("url") or "").lower()]
        return {"items": items}

    @api.post("/api/campaigns")
    def campaign_add(payload: dict = Body(...)):
        current = st()
        campaign = {
            "name": (payload.get("name") or "").strip(),
            "url": (payload.get("url") or "").strip(),
            "opens_at": (payload.get("opens_at") or "").strip(),
            "closes_at": (payload.get("closes_at") or "").strip(),
            "notes": (payload.get("notes") or "").strip(),
        }
        if not current.campaigns.is_valid(campaign):
            raise HTTPException(400, "Tên/link không hợp lệ (link phải http/https, "
                                     "ngày dạng YYYY-MM-DD HH:MM)")
        current.campaigns.add(campaign)
        return current.campaigns_view()[-1]

    @api.put("/api/campaigns/{row}")
    def campaign_update(row: int, payload: dict = Body(...)):
        current = st()
        campaign = {
            "name": (payload.get("name") or "").strip(),
            "url": (payload.get("url") or "").strip(),
            "opens_at": (payload.get("opens_at") or "").strip(),
            "closes_at": (payload.get("closes_at") or "").strip(),
            "notes": (payload.get("notes") or "").strip(),
        }
        if not current.campaigns.is_valid(campaign):
            raise HTTPException(400, "Tên/link không hợp lệ (link phải http/https, "
                                     "ngày dạng YYYY-MM-DD HH:MM)")
        if not current.campaigns.update(row, campaign):
            raise HTTPException(404, "Không có dòng %d" % row)
        return current.campaign_view(current.campaigns.campaigns[row], row)

    @api.delete("/api/campaigns/{row}")
    def campaign_delete(row: int):
        removed = st().campaigns.remove(row)
        if removed is None:
            raise HTTPException(404, "Không có dòng %d" % row)
        return {"removed": removed.get("name", "")}

    @api.get("/api/campaigns/{row}/signups")
    def campaign_signups(row: int):
        current = st()
        if not 0 <= row < len(current.campaigns.campaigns):
            raise HTTPException(404, "Không có dòng %d" % row)
        campaign = current.campaigns.campaigns[row]
        return {"campaign": current.campaign_view(campaign, row),
                "signups": current.campaigns.signups_for(campaign)}

    @api.post("/api/campaigns/{row}/signups")
    def campaign_mark(row: int, payload: dict = Body(...)):
        current = st()
        if not 0 <= row < len(current.campaigns.campaigns):
            raise HTTPException(404, "Không có dòng %d" % row)
        campaign = current.campaigns.campaigns[row]
        email = (payload.get("email") or "").strip()
        if not current.campaigns.mark(campaign, email):
            raise HTTPException(409, "%s đã được ghi nhận cho chiến dịch này" % email)
        return {"signups": current.campaigns.signups_for(campaign)}

    @api.delete("/api/campaigns/{row}/signups/{email}")
    def campaign_unmark(row: int, email: str):
        current = st()
        if not 0 <= row < len(current.campaigns.campaigns):
            raise HTTPException(404, "Không có dòng %d" % row)
        campaign = current.campaigns.campaigns[row]
        if not current.campaigns.unmark(campaign, email):
            raise HTTPException(404, "%s không có trong danh sách đã đăng ký" % email)
        return {"signups": current.campaigns.signups_for(campaign)}

    @api.get("/api/campaigns/export", response_class=PlainTextResponse)
    def campaigns_export():
        lines = []
        for view in st().campaigns_view():
            lines.append("%s | %s | %s | %s" % (view.get("name", ""), view.get("url", ""),
                                                view.get("opens_at", ""),
                                                view.get("closes_at", "")))
        return "\n".join(lines)

    # ========================================================
    # CẤU HÌNH CHUNG / PROXY
    # ========================================================
    @api.get("/api/settings")
    def settings_get():
        current = st()
        return {
            "max_workers": current.max_workers,
            "max_workers_limit": MAX_CONCURRENCY,
            "proxy": current.proxy_settings(),
            "browser": current.browser_settings(),
        }

    @api.put("/api/settings/general")
    def settings_general(payload: dict = Body(...)):
        current = st()
        try:
            value = int(payload.get("max_workers", current.max_workers))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "max_workers phải là số") from exc
        current.max_workers = max(1, min(MAX_CONCURRENCY, value))
        current.settings.set(max_workers=current.max_workers)
        return {"max_workers": current.max_workers}

    @api.put("/api/settings/proxy")
    def settings_proxy(payload: dict = Body(...)):
        current = st()
        current.settings.set(
            proxy_enabled=bool(payload.get("enabled", False)),
            proxy_mode=payload.get("mode") or "per_request",
            proxy_file=payload.get("file") or "",
        )
        current.apply_proxy_settings()
        return current.proxy_settings()

    @api.get("/api/proxy")
    def proxy_list():
        """Danh sách proxy + số giây còn tạm nghỉ (không trả mật khẩu)."""
        from proxy_manager import proxy_manager

        items = []
        for index, entry in enumerate(proxy_manager.proxies):
            items.append({
                "index": index + 1,
                "host": entry.get("host", ""),
                "port": entry.get("port", ""),
                "username": entry.get("username", ""),
                "blocked_seconds": proxy_manager.blocked_remaining(entry),
            })
        return {"items": items, "settings": st().proxy_settings()}

    @api.post("/api/proxy/reload")
    def proxy_reload():
        current = st()
        current.apply_proxy_settings()
        return current.proxy_settings()

    @api.post("/api/proxy/check")
    def proxy_check():
        return st().start_proxy_check().as_dict()

    @api.post("/api/proxy/reset-blocks")
    def proxy_reset():
        from proxy_manager import proxy_manager

        proxy_manager.reset_blocks()
        return {"blocked": proxy_manager.blocked_count()}

    @api.get("/api/proxy/blocked")
    def proxy_blocked():
        from proxy_manager import proxy_manager

        return {"items": proxy_manager.blocked_entries()}

    # ========================================================
    # CẤU HÌNH TRÌNH DUYỆT + RECIPE
    # ========================================================
    @api.put("/api/settings/browser")
    def settings_browser(payload: dict = Body(...)):
        current = st()
        parallel = payload.get("parallel", current.browser_settings()["parallel"])
        try:
            parallel = max(1, min(MAX_BROWSER_PARALLEL, int(parallel)))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "parallel phải là số") from exc
        current.settings.set(
            browser_recipe=payload.get("recipe_path") or "",
            browser_headless=bool(payload.get("headless", False)),
            browser_parallel=parallel,
            browser_submit=bool(payload.get("submit", True)),
        )
        current.apply_browser_settings()
        return current.browser_settings()

    @api.get("/api/settings/recipe")
    def recipe_check(path: str = ""):
        current = st()
        target = path or current.browser_settings()["recipe_path"]
        errors = current.browser.validate_file(target)
        return {"path": target, "ok": not errors, "errors": errors}

    @api.get("/api/browser/recipe", response_class=PlainTextResponse)
    def recipe_raw():
        current = st()
        path = current.browser_settings()["recipe_path"]
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            raise HTTPException(404, "Không đọc được recipe %s: %s" % (path, exc)) from exc

    @api.put("/api/browser/recipe")
    def recipe_save(payload: dict = Body(...)):
        """Lưu recipe (JSON text) sau khi validate — sửa selector không cần sửa code."""
        import json

        current = st()
        path = current.browser_settings()["recipe_path"]
        raw = payload.get("json") or ""
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(400, "JSON không hợp lệ: %s" % exc) from exc
        errors = validate_recipe(parsed)
        if errors:
            raise HTTPException(400, "Recipe chưa dùng được: " + "; ".join(errors[:5]))
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(parsed, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            raise HTTPException(500, "Không ghi được %s: %s" % (path, exc)) from exc
        current.log("Đã lưu recipe %s" % os.path.basename(path), "ok")
        return {"ok": True, "path": path}

    # ========================================================
    # CHẠY CHIẾN DỊCH BẰNG CHROME
    # ========================================================
    @api.post("/api/browser/run")
    def browser_run(payload: dict = Body(...)):
        current = st()
        row = payload.get("campaign_row")
        campaign = None
        if isinstance(row, int) and 0 <= row < len(current.campaigns.campaigns):
            campaign = current.campaigns.campaigns[row]
        elif payload.get("url"):
            campaign = {"name": payload.get("name") or payload["url"],
                        "url": payload["url"]}
        if not campaign:
            raise HTTPException(400, "Chọn chiến dịch (campaign_row) hoặc gửi url")
        emails = payload.get("emails") or []
        if not emails:
            raise HTTPException(400, "Chọn ít nhất một tài khoản")
        ok, message = current.browser.preflight()
        if not ok:
            raise HTTPException(409, message)
        job = current.start_browser_run(campaign, emails,
                                        submit=payload.get("submit"),
                                        slot=payload.get("slot") or "",
                                        use_account_address=bool(
                                            payload.get("use_account_address")))
        return job.as_dict()

    @api.get("/api/browser/sessions")
    def browser_sessions():
        return {"items": st().sessions_view()}

    @api.post("/api/browser/sessions/close")
    def browser_close_sessions():
        count = st().browser.close_open_sessions()
        return {"closed": count}

    @api.post("/api/browser/discover")
    def browser_discover(payload: dict = Body(...)):
        current = st()
        email = payload.get("email") or ""
        url = payload.get("url") or ""
        if not email or not url:
            raise HTTPException(400, "Cần email và url")
        if current.accounts.find(email) is None:
            raise HTTPException(404, "Không có tài khoản %s" % email)
        return current.start_discovery(email, url).as_dict()

    # ========================================================
    # HỒ SƠ ĐẶT HÀNG / THẺ
    # ========================================================
    @api.get("/api/checkout")
    def checkout_get():
        current = st()
        return {"profile": current.checkout_public(),
                "fields": [{"name": name, "label": label, "group": group}
                           for name, label, group in checkout_domain.FIELDS],
                "card_fields": [{"name": name, "label": label}
                                for name, label in checkout_domain.CARD_FIELDS],
                "prefectures": list(checkout_domain.PREFECTURES)}

    @api.put("/api/checkout")
    def checkout_save(payload: dict = Body(...)):
        """Lưu hồ sơ. Số thẻ/CVV để trống nghĩa là GIỮ giá trị cũ (không gửi lại từ UI)."""
        current = st()
        existing = current.checkout.load()
        merged = dict(existing)
        for name, _label, _group in checkout_domain.FIELDS:
            if name in payload:
                merged[name] = payload.get(name) or ""
        merged["building_none"] = bool(payload.get("building_none",
                                                   existing.get("building_none")))
        for name, _label in checkout_domain.CARD_FIELDS:
            value = (payload.get(name) or "").strip()
            if value:
                merged[name] = value
        if payload.get("clear_card"):
            merged["card_number"] = ""
            merged["card_exp"] = ""
            merged["card_cvv"] = ""
            merged["card_holder"] = ""
        ok, message = current.checkout.save(merged)
        if not ok:
            raise HTTPException(400, message)
        current.log("Đã lưu hồ sơ đặt hàng", "ok")
        return {"ok": True, "message": message, "profile": current.checkout_public()}

    @api.delete("/api/checkout")
    def checkout_clear():
        current = st()
        if not current.checkout.clear():
            raise HTTPException(404, "Chưa có hồ sơ để xoá")
        return {"ok": True, "profile": current.checkout_public()}

    # ========================================================
    # LỖI CHUNG
    # ========================================================
    @api.exception_handler(RecipeNotReady)
    def recipe_error(_request, exc):  # pragma: no cover - hiếm
        return JSONResponse({"detail": str(exc)}, status_code=409)

    return api


app = create_app()
