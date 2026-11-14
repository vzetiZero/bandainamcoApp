# PROJECT_CONTEXT — NAMCO Account Manager

Quản lý nhiều tài khoản NAMCO Parks trên Windows: kiểm tra đăng nhập, đọc hồ sơ, đổi tên,
theo dõi chiến dịch 抽選 và chạy đăng ký bằng Chrome thật (mỗi tài khoản một cửa sổ).

## 1. Kiến trúc

```
Electron window (web/out) ──HTTP/JSON──> api/ (FastAPI) ──> app/services ──> app/domain
                                            │                    └─> app/infrastructure (adapters)
                                            └─ JobRegistry (thread nền) + LogBuffer
```

| Thư mục / file | Vai trò |
|---|---|
| `api/` | `app.py` (route REST + CORS), `state.py` (wiring, LogBuffer, JobRegistry, các job) |
| `app/domain/` | quy tắc thuần, không I/O: `accounts`, `campaigns`, `checkout`, `browser_recipe`, `ip_rules`, `login_rules`, `names` |
| `app/services/` | use case: `account_service`, `campaign_service`, `browser_campaign_service` |
| `app/infrastructure/` | adapter: `bandai_auth` (login + handoff + hồ sơ), `bandai_name`, `bandai_profile`, `account_repository`, `file_settings`, `checkout_store`, `web`, `browser/` |
| `app/infrastructure/browser/` | `browser_session` (Chrome riêng mỗi tài khoản), `campaign_runner` (replay recipe), `mcp_client` (chrome-devtools-mcp), `discovery` (dò trang) |
| `web/` | UI Next.js 14 (App Router) + theme-ui; build tĩnh ra `web/out` |
| `desktop/` | vỏ Electron: nạp `web/out` qua protocol `app://`, truyền `API_BASE` |
| `recipes/*.json` | công thức thao tác trình duyệt (dữ liệu, không phải code) |
| `server.py` | chạy API (`--kill-port` mặc định: cổng bận thì kill tiến trình cũ) |
| `start.py` / `start.bat` | khởi động tất cả: cài thiếu → build UI → giải phóng cổng → API → Electron |
| `tools/port_tools.py` | kiểm tra/giải phóng cổng TCP (`netstat`+`taskkill`, POSIX `lsof`) |
| `browser_campaign.py`, `change_name.py` | CLI dò/chạy chiến dịch và đổi tên |
| `proxy_manager.py` | proxy cho mọi request HTTP (`new_session()`, `proxy.txt`) |

## 2. Đăng nhập & hồ sơ

1. **BNID** (`account.bandainamcoid.com`): `v3/login/init` → `v3/login/idpw` (kèm `env_info`)
   → handoff `btn-next` (**không tạo passkey**) → Parks2 `member_mypage.html`.
2. **Form Parks2** (`parks2.../login.html?request=redirect_logon`): `#LOGINID` / `#PASSWORD`
   → `input[type=submit][value="ログイン"]`. Đây là đường **duy nhất** chạy được với tài khoản
   chỉ có Parks2; BNID trả 「メールアドレス…が間違っている」 cho nhóm này.
3. Hồ sơ đọc từ `member_mypage.html`: 16 trường (tên kanji/kana, postal_code, prefecture,
   city, address_number, phone, points…). Lỗi `UnexpectedRemoteAddress` ⇒ IP bị chặn.
4. Mọi request HTTP đi qua `new_session()` để dùng proxy; proxy bị chặn nghỉ 300s.

## 3. Chiến dịch

- Mỗi chiến dịch: `name`, `url`, `opens_at`, `closes_at` (`YYYY-MM-DD HH:MM`), `notes`.
  Trạng thái (`Đang mở` / `Chưa mở` / `Đã đóng` / `Chưa rõ`) **tính từ thời gian**, không nhập tay.
- Ghi nhận đăng ký theo khoá `"tên|link"` → `{campaign_key: [{email, at}]}`.
- Trạng thái chạy: `registered`, `already`, `closed`, `paused`, `dry_run`, `unverified`,
  `login_failed`, `ip_blocked`, `error`, `skipped`; chỉ `registered`/`already` được ghi nhận.

## 4. Recipe (dữ liệu, không phải code)

`recipes/parks2_campaign.json` — 4 khối: `name`, `login`, `entry`, `verification`.

Bước (`entry.steps` / `login.steps`) là object: `action` ∈ `goto, fill, select, check, click,
press, wait_text, wait_selector, sleep, screenshot, dismiss, clear_cart, pause, submit`, kèm
`selector`, `value`, và các cờ:

| Cờ | Ý nghĩa |
|---|---|
| `when` | chỉ chạy khi biến có giá trị (rỗng/0/false ⇒ bỏ bước) |
| `only_if_empty` | `true` = không ghi đè ô của chính nó; **selector** = chỉ chạy khi ô đó đang trống (dùng cho `check`) |
| `optional` | lỗi thì bỏ qua bước, không dừng lượt chạy |
| `requires_submit` | chỉ chạy khi bật **Tự bấm gửi** |
| `unless_submit` | chỉ chạy khi **TẮT** tự bấm gửi (dùng cho `pause`) |

`clear_cart` xoá các dòng đang có trong giỏ (`value` = URL giỏ, `selector` = nút xoá) rồi quay
lại trang chiến dịch — cần khi đổi 種類 để đơn không thành 2 dòng.

Biến dùng trong `selector`/`value`: `{email}`, `{password}`, `{l_name}`, `{f_name}`, `{l_kana}`,
`{f_kana}`, `{zip}`, `{pref}`, `{city}`, `{street}`, `{building}`, `{building_none}`, `{tel}`,
`{card_holder}`, `{card_number}`, `{card_exp}`, `{card_exp_month}`, `{card_exp_year}`, `{card_cvv}`.

`validate_recipe()` chặn action sai, thiếu trường và placeholder (`TODO`, `<` trong selector).
Sửa file qua panel Settings → Recipe JSON (API validate trước khi ghi) hoặc bằng tay.

Luồng hiện tại của 熊本店 OP-18 (đã chạy thật tới ご注文完了):

```
login Parks2 → trang item
→ clear_cart (nếu bật — xoá dòng giỏ cũ khi đổi 種類)
→ dismiss popup 本人確認 (#confirmCheck + #closePopupButton)
→ select #PRIORITY_ITEMPROPERTY_CD_MATRIX_0 (mặc định 159016_1121_1100_1 = 11/21 11:00)
→ #CART_AMOUNT_0 → #addCart → 購入手続きに進む → a[onclick*="cart_seisan.html"]
→ ご注文情報入力: điền họ tên/zip/pref/city/street/tel (chỉ ô trống, theo hồ sơ tài khoản);
   tick 「ビル・マンション名・部屋番号なし」 khi ô ビル名 trống
→ pause  (chỉ khi TẮT tự bấm gửi)
→ click 入力内容を確認する → wait ご注文情報確認
→ submit #order_now_btn (注文する) → wait ご注文完了
```

Lưu ý selector: id có dấu chấm của Interfactory (`ORDER_H.FREE_ITEM12`) **không dùng được** làm
CSS id (`.` = class) — dùng `input[name="ORDER_H.FREE_ITEM12"]`. Checkbox 「なし」 là
`input[name="ORDER_H.FREE_ITEM22"]`, ô ビル名 là `input[name="ADDR3"]`.
Kết quả thật 2026-11-14 (qua proxy): trinha5 → ご注文完了, 注文番号 EC-2108582488.

## 5. Trình duyệt (Playwright + chrome-devtools-mcp)

- Mỗi tài khoản: profile riêng `browser_profiles/<slug email>`, `--remote-debugging-port` riêng,
  proxy riêng. Chrome thật (`channel="chrome"`), cờ chống occlusion để screenshot không trắng.
- **Mỗi tài khoản chạy trong thread riêng**: Playwright sync gắn với thread tạo nó; tài khoản
  bị `pause` (giữ cửa sổ) sẽ treo tài khoản sau nếu dùng lại thread.
- `pause` ⇒ không `close()` phiên, `status=paused`, cửa sổ ở lại cho người dùng làm tiếp;
  tối đa 3 cửa sổ chờ (`max_paused`).
- `chrome-devtools-mcp` gắn vào cùng cổng (`--browser-url`) chỉ để **dò trang/snapshot/chẩn đoán**;
  flow chạy hàng loạt dùng selector CSS ổn định.
- **Proxy**: `ApiState.__init__` gọi `apply_proxy_settings()` nên cấu hình proxy có hiệu lực ngay
  sau restart (trước đây phải PUT lại mới ăn). Mỗi lượt chạy lấy proxy qua
  `ProxyManager.next_proxy_entry()`; `use_proxy=false` để chạy bằng IP máy. Gặp chặn IP
  (`UnexpectedRemoteAddress`) hoặc trang không tải được ⇒ `mark_blocked` + **thử proxy kế tiếp**
  (tối đa 2 lần), hết lượt thì `status=ip_blocked`. Proxy đã dùng được ghi vào job item.
- Cửa sổ Chrome cũ của cùng tài khoản phải đóng trước khi mở lại (Chrome khoá profile):
  `start_browser_run` tự đóng session đang pause của chính tài khoản đó, và `BrowserSession`
  chờ 4s + thử lại một lần nếu gặp "Opening in existing browser session".
- Ảnh chụp + HTML dò được lưu ở `browser_artifacts/` (git-ignored).
- Trang Parks2 lặp phần tử desktop/mobile cùng `id` (một bản ẩn) ⇒ engine bấm/điền **phần tử đang hiện**.

## 6. Hồ sơ đặt hàng & thẻ

`checkout_profile.json`, mỗi giá trị mã hoá **DPAPI** (Windows), `icacls` hạn chế quyền.
UI/API chỉ thấy `**** **** **** 1234`; `PUT` với ô thẻ trống = giữ giá trị cũ.
Trường: người nhận, địa chỉ (`zip/pref/city/street/building` + `building_none`), `tel`, thẻ.
Khi chạy nhiều tài khoản: `use_account_address` lấy địa chỉ từ hồ sơ Parks2 của từng tài khoản.

## 7. API

`GET /api/health`, `/api/accounts`, `/api/campaigns`, `/api/settings`, `/api/proxy`,
`/api/checkout`, `/api/logs?after=<seq>`, `/api/jobs[/{id}]`, `/api/browser/sessions`.
Tác vụ dài (`/api/accounts/check`, `/api/browser/run`, `/api/proxy/check`,
`/api/browser/discover`) trả `{id, status:"running", ...}`; UI poll job tới khi xong.
API **không** trả mật khẩu, số thẻ hay CVV. CORS cho `http://localhost:3000` và `app://local`.

## 8. Dữ liệu & cấu hình

| File | Nội dung | Git |
|---|---|---|
| `accounts_data.json` | danh sách tài khoản (email, password, trạng thái, hồ sơ) | ignored |
| `web_settings.json` | tuỳ chọn UI/API (campaigns, proxy, browser, max_workers) | ignored |
| `ui_settings.ini` | tuỳ chọn bản desktop cũ — chỉ dùng để chép sang lần đầu | ignored |
| `proxy.txt` | `ip:port:username:password` | ignored |
| `checkout_profile.json` | hồ sơ đặt hàng/thẻ (DPAPI) | ignored |
| `recipes/*.json` | công thức thao tác | tracked |
| `browser_profiles/`, `browser_artifacts/` | profile Chrome, ảnh/HTML | ignored |

## 9. Chạy & kiểm thử

```powershell
start.bat                  # = python start.py: cài thiếu, build UI, free port, API + Electron
python start.py --rebuild  # build lại UI tĩnh
python start.py --dev-ui   # Next dev :3000 + Electron (sửa UI nóng)
python start.py --web      # chỉ API
python server.py --help    # --port, --kill-port/--no-kill-port, --pick-port
```

- Cổng API mặc định 8787; `tools.port_tools.pick_port()` kill tiến trình cũ rồi bind lại,
  nếu vẫn bận thì nhảy cổng kế tiếp và truyền `API_BASE` cho Electron (không phải build lại UI).
- Kiểm thử nhanh: `python -m pyflakes api app tools server.py start.py`,
  `python browser_campaign.py --check`, hoặc `TestClient` với `ApiState(data_file=tmp, …)`.

## 10. Quy tắc bắt buộc

1. Không đổi `CLIENT_ID`/`redirect_uri` của BNID; `env_info` phải đúng `{mobile, platform}`.
2. Mọi network call qua `new_session()` (để dùng proxy); `USER_AGENT` là nguồn duy nhất cho header.
3. Không commit secret (`accounts_data.json`, `proxy.txt`, `checkout_profile.json`).
4. Selector nằm trong `recipes/*.json`; đổi site thì sửa dữ liệu, không hard-code.
5. `submit` mặc định phải qua xác nhận của người dùng; recipe hiện dừng ở `pause` trước khi chốt đơn.
6. API không trả mật khẩu/thẻ/CVV; log chỉ in `checkout.summary()` (đã che).
7. UI gọn: giải thích đặt ở tooltip, nhãn trạng thái 1 dòng, kết quả dùng toast/status chứ không popup.

