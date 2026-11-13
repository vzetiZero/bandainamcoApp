"""CLI chạy đăng ký chiến dịch bằng Chrome thật (Playwright + chrome-devtools-mcp).

Ba việc, cùng một file:

```powershell
# 1. Dò trang để viết recipe (mở Chrome của tài khoản, đổ HTML/elements/snapshot)
python browser_campaign.py --discover --email a@b.c --password secret --url <link>

# 2. Kiểm tra recipe trước khi chạy
python browser_campaign.py --check

# 3. Chạy thật: một tài khoản, hoặc tất cả tài khoản trong accounts_data.json
python browser_campaign.py --run --campaign "Tên chiến dịch" --email a@b.c --password secret
python browser_campaign.py --all --campaign "Tên chiến dịch" --submit
```

Mặc định **không** bấm gửi; thêm `--submit` mới bấm nút gửi cuối cùng. Mọi thứ
khác (đăng nhập, điền form, phân loại kết quả, ảnh chụp) nằm trong
`app/infrastructure/browser/` và `app/services/browser_campaign_service.py`.
"""
import argparse
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from app.config import BROWSER_RECIPE_FILE, SETTINGS_FILE
from app.infrastructure.account_repository import AccountRepository
from app.infrastructure.browser.browser_session import find_chrome
from app.infrastructure.browser.campaign_runner import navigate_only
from app.infrastructure.browser.discovery import discover_page
from app.infrastructure.settings_store import SettingsStore
from app.services.browser_campaign_service import BrowserCampaignService
from app.services.campaign_service import CampaignService


def log(message):
    print(message, flush=True)


def load_campaigns():
    store = SettingsStore(path=SETTINGS_FILE)
    service = CampaignService(store)
    service.load()
    return service, service.campaigns


def pick_campaign(campaigns, name=None, url=None):
    """Chọn chiến dịch theo tên (khớp một phần) hoặc theo link."""
    if url:
        for campaign in campaigns:
            if (campaign.get("url") or "").strip() == url.strip():
                return campaign
        return {"name": url, "url": url}
    if not name:
        return None
    lowered = name.strip().lower()
    exact = [c for c in campaigns if (c.get("name") or "").lower() == lowered]
    if exact:
        return exact[0]
    partial = [c for c in campaigns if lowered in (c.get("name") or "").lower()]
    return partial[0] if partial else None


def load_accounts(path="accounts_data.json"):
    repository = AccountRepository(path=path, on_change=None)
    return repository.load()


def find_account(accounts, email):
    for account in accounts:
        if (account.get("email") or "").lower() == email.lower():
            return account
    return None


def command_discover(args):
    session = navigate_only(args.email, args.url, headless=args.headless,
                            on_log=log, hold_seconds=args.hold)
    try:
        paths = discover_page(args.email, args.url, session, on_log=log,
                              with_mcp=not args.no_mcp)
    finally:
        session.close()
    print("\nDò trang xong. Đọc các file sau để điền selector vào recipe:")
    for key in ("html", "text", "elements", "snapshot", "screenshot"):
        if paths.get(key):
            print("  %-10s %s" % (key, paths[key]))
    print("  %-10s %s" % ("dir", paths.get("dir", "")))
    return 0


def command_check(args):
    errors = BrowserCampaignService.validate_file(args.recipe)
    if errors:
        print("Recipe CHƯA dùng được:", args.recipe)
        for error in errors:
            print("  - %s" % error)
        return 1
    print("Recipe hợp lệ:", args.recipe)
    print("Chrome:", find_chrome() or "(không tìm thấy)")
    return 0


def command_run(args):
    store, campaigns = load_campaigns()
    campaign = pick_campaign(campaigns, args.campaign, args.url)
    if campaign is None:
        print("Không tìm thấy chiến dịch '%s'. Các chiến dịch đang có:" % args.campaign)
        for item in campaigns:
            print("  - %s | %s" % (item.get("name"), item.get("url")))
        return 2

    accounts = load_accounts(args.accounts_file)
    if args.emails:
        wanted = [item.strip() for item in args.emails.split(",") if item.strip()]
        targets = []
        for email in wanted:
            record = find_account(accounts, email)
            if record is None:
                print("Không có %s trong %s" % (email, args.accounts_file))
                return 2
            targets.append((record.get("email", email), record.get("password", "")))
    elif args.email:
        password = args.password
        if password is None:
            record = find_account(accounts, args.email)
            if record is None:
                print("Không có %s trong %s; cần --password." % (args.email, args.accounts_file))
                return 2
            password = record.get("password", "")
        targets = [(args.email, password)]
    else:
        targets = [(account.get("email", ""), account.get("password", ""))
                   for account in accounts if account.get("email")]
    if not targets:
        print("Không có tài khoản nào để chạy.")
        return 2

    service = BrowserCampaignService(store, recipe_path=args.recipe, submit=args.submit,
                                    headless=args.headless, parallel=args.parallel)
    ok, message = service.preflight()
    if not ok:
        print(message)
        return 3

    recipe = service.load_recipe()
    if args.slot:
        # Đổi ngày/giờ nhận hàng mà không phải sửa file JSON.
        for step in recipe.get("entry", {}).get("steps", []):
            if step.get("selector") == "#PRIORITY_ITEMPROPERTY_CD_MATRIX_0":
                step["value"] = args.slot
        print("Slot override:", args.slot)

    def on_result(result):
        print("\n[%s] %s -> %s" % ("OK" if result.ok else "LỖI", result.email,
                                   result.status))
        print("       %s" % result.message)
        if result.final_url:
            print("       URL: %s" % result.final_url)
        if result.screenshot:
            print("       Ảnh: %s" % result.screenshot)

    results = service.run(campaign, targets, on_log=log,
                          on_progress=lambda done, total: print("  ... %d/%d" % (done, total)),
                          on_result=on_result, submit=args.submit,
                          keep_open_seconds=args.keep_open, recipe=recipe)
    ok_count = sum(1 for result in results if result.ok)
    print("\n" + "=" * 60)
    print("Tổng %d tài khoản: %d thành công, %d lỗi" % (len(results), ok_count,
                                                       len(results) - ok_count))
    print("=" * 60)

    if service.open_sessions:
        print("\n%d cửa sổ Chrome đang để mở cho bạn làm tiếp:" % len(service.open_sessions))
        for email, session in service.open_sessions.items():
            print("  %-28s cổng %s  profile %s" % (email, session.port, session.profile_dir))
        if args.hold_open:
            print("\nGiữ tiến trình sống để các cửa sổ này KHÔNG bị đóng. Ctrl+C để kết thúc.")
            try:
                while True:
                    time.sleep(3)
            except KeyboardInterrupt:
                print("\nĐóng cửa sổ...")
                service.close_open_sessions()
    return 0 if ok_count == len(results) else 1


def main():
    parser = argparse.ArgumentParser(
        description="Chạy đăng ký chiến dịch bằng Chrome (Playwright + chrome-devtools-mcp)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--discover", action="store_true", help="Dò trang để viết recipe")
    mode.add_argument("--check", action="store_true", help="Kiểm tra file recipe")
    mode.add_argument("--run", action="store_true", help="Chạy cho tài khoản --email")
    mode.add_argument("--all", action="store_true", help="Chạy cho mọi tài khoản đã lưu")

    parser.add_argument("--recipe", default=BROWSER_RECIPE_FILE, help="File recipe JSON")
    parser.add_argument("--campaign", help="Tên chiến dịch (khớp một phần)")
    parser.add_argument("--url", help="Link chiến dịch (thay cho --campaign)")
    parser.add_argument("--email", help="Email tài khoản cần chạy")
    parser.add_argument("--emails", help="Nhiều tài khoản, cách nhau bằng dấu phẩy "
                                         "(mật khẩu lấy từ accounts_data.json)")
    parser.add_argument("--password", help="Mật khẩu (bỏ trống thì lấy từ accounts_data.json)")
    parser.add_argument("--accounts-file", default="accounts_data.json")
    parser.add_argument("--submit", action="store_true",
                        help="Bấm gửi thật (mặc định chỉ điền, không gửi)")
    parser.add_argument("--headless", action="store_true", help="Chạy Chrome ẩn")
    parser.add_argument("--parallel", type=int, default=1, help="Số Chrome song song (1-3)")
    parser.add_argument("--keep-open", type=int, default=0,
                        help="Giữ cửa sổ Chrome mở thêm N giây sau mỗi tài khoản")
    parser.add_argument("--hold-open", action="store_true",
                        help="Sau khi chạy, giữ tiến trình sống để cửa sổ Chrome ở bước "
                             "thanh toán không bị đóng (Ctrl+C để đóng)")
    parser.add_argument("--slot", help="Mã ngày/giờ nhận hàng, vd 159016_1121_1100_1 "
                                       "(ghi đè bước chọn 種類 trong recipe)")
    parser.add_argument("--hold", type=int, default=3,
                        help="Khi dò: chờ N giây trên trang trước khi chụp")
    parser.add_argument("--no-mcp", action="store_true",
                        help="Khi dò: không lấy snapshot qua chrome-devtools-mcp")
    args = parser.parse_args()

    if args.email is None and args.emails is None and (args.discover or args.run):
        parser.error("--discover/--run cần --email hoặc --emails")
    if args.discover:
        return command_discover(args)
    if args.check:
        return command_check(args)
    return command_run(args)


if __name__ == "__main__":
    sys.exit(main())
