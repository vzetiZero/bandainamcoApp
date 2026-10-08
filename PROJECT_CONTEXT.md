# NAMCO Account Manager — Tài liệu dự án cho AI Agent

Tài liệu này mô tả **logic đã có**, **trạng thái triển khai** và **kế hoạch** của dự án.
Đọc file này trước khi sửa bất kỳ dòng code nào.

> Nguyên tắc bất di bất dịch của dự án: **không tự động hoá trình duyệt** (không
> Selenium/Playwright). Toàn bộ luồng đăng nhập đi bằng `requests` thuần.

---

## 1. Tổng quan

Ứng dụng desktop Windows (PySide6) để quản lý danh sách tài khoản BANDAI NAMCO ID /
NAMCO Parks: thêm, kiểm tra đăng nhập, đọc hồ sơ thành viên, đổi tên Kanji.

| File | Vai trò |
|---|---|
| `account_manager.py` (~2000 dòng) | Toàn bộ UI + logic chính. Điểm khởi chạy app. |
| `proxy_manager.py` | Quản lý proxy cho mọi HTTP request. Đọc `proxy.txt`. |
| `change_name.py` | Module đổi tên, chạy độc lập (CLI) hoặc được gọi từ GUI. |
| `icon_helper.py` | Nạp SVG icon từ thư mục `icons/`, có cache. |
| `accounts_data.json` | Dữ liệu tài khoản + hồ sơ. **Git-ignored, chứa mật khẩu.** |
| `proxy.txt` | Danh sách proxy. **Git-ignored, chứa user/pass.** |

### Hằng số mạng (trong cả 2 file)

```python
API_URL       = "https://account-api.bandainamcoid.com/"
LOGIN_URL     = "https://account.bandainamcoid.com/login.html"
CLIENT_ID     = "namcoparks_onlinestore"          # OAuth client đã đăng ký — KHÔNG ĐỔI
REDIRECT_URI  = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
USER_AGENT    = "Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36"   # dùng chung 2 nơi
```

> `CLIENT_ID` là client OAuth đã đăng ký của app NAMCO Parks, khớp `REDIRECT_URI`.
> **Không bao giờ random hóa** — server sẽ từ chối (`invalid_client`) và mọi tài khoản
> thật đều dùng chung giá trị này. Không phải fingerprint thiết bị.

---

## 2. Cấu trúc UI — 4 tab

`AccountManager.setup_ui()` dựng `QTabWidget` theo thứ tự:

| # | Tab | Hàm dựng | Nội dung |
|---|---|---|---|
| 1 | Nhập tài khoản | `create_left_panel()` | Ô nhập `email\|password`, 4 nút compact |
| 2 | Danh sách tài khoản | `create_right_panel()` | Bảng 22 cột + nhật ký bên phải |
| 3 | Chiến dịch | `create_campaign_tab()` | Bảng CRUD chiến dịch |
| 4 | Cấu hình | `create_settings_tab()` | Bật/tắt proxy, file, chế độ, kiểm tra proxy |

### 2.1 Tab 1 — Nhập tài khoản

4 nút gọn trên một hàng, tất cả dùng `objectName` để style trong `apply_styles()`:

| objectName | Nhãn | Icon | Handler | Tooltip |
|---|---|---|---|---|
| `actionAdd` | Thêm | `plus` | `add_from_text` | Thêm các tài khoản trong ô nhập vào danh sách |
| `actionClear` | Xóa | `x` | `text_input.clear` | Xóa toàn bộ nội dung ô nhập |
| `actionCheck` | Kiểm tra đầu tiên | `check` | `check_first_account` | Kiểm tra tài khoản đầu tiên trong danh sách |
| `actionExport` | Export | `download` | `export_accounts` | Export danh sách tài khoản ra file |

**Quy ước bắt buộc:** muốn thêm nút mới vào tab này thì đặt `objectName` và khai báo
màu trong `apply_styles()`. **Không** dùng `setStyleSheet()` trực tiếp trên widget —
`apply_styles()` xoá sạch stylesheet của mọi widget con mỗi lần đổi giao diện.

Ô nhật ký (`log_text`) và nhãn `log_label` được **di chuyển** sang tab 2
(xem `setup_ui()`); tab 1 chỉ còn `text_input`.

### 2.2 Tab 2 — Danh sách tài khoản

- Cột `Password` luôn hiển thị `********`.
- Cột `Status` tô màu: `Hoạt động` → `#28a745`, `Không hoạt động` → `#dc3545`,
  `Chưa kiểm tra` → `#8a94a6`. Phải so sánh **chuỗi có dấu chính xác**
  (lỗi cũ từng so `"Hoat"` với `"Hoạt động"` nên không bao giờ tô màu).
- Lọc: `apply_filter()` theo status + tìm kiếm email (dùng `setRowHidden`).
- Context menu chuột phải: Đổi tên / Xem thông tin / Kiểm tra / Copy email / Xóa.

### 2.3 Tab 3 — Chiến dịch (chi tiết ở mục 3)

### 2.4 Tab 4 — Cấu hình (chi tiết ở mục 4)

---

## 3. Logic tab Chiến dịch

**Mục đích:** lưu danh sách link chiến dịch (link đăng ký 抽選 thời gian giới hạn) để
nhìn nhanh chiến dịch nào đang hiệu lực. Đây là **sổ tay**, app **không** tự động
đăng ký hộ (xem mục 10.9).

**Mô hình dữ liệu: mỗi chiến dịch là một dòng riêng.** Không cần cập nhật liên tục.
Thêm một dòng khi có chiến dịch mới, giữ dòng cũ để tra cứu, chỉ sửa khi link hoặc ngày
của chính chiến dịch đó thay đổi. Trạng thái được **tính từ ngày**, không phải nhập tay.

### Cấu trúc dữ liệu — 5 trường lưu trữ

| Key | Cột hiển thị | Quy tắc |
|---|---|---|
| `name` | Tên | Bắt buộc, không rỗng |
| `url` | Link | Bắt buộc, scheme phải là `http` hoặc `https` |
| `opens_at` | Mở đăng ký | `YYYY-MM-DD HH:MM`, để trống nếu chưa công bố |
| `closes_at` | Đóng đăng ký | `YYYY-MM-DD HH:MM`, để trống nếu chưa công bố |
| `notes` | Ghi chú | Tự do, `QTextEdit` giới hạn 120px |

Hai cột **Trạng thái** và **Còn lại** không lưu — chúng tính lại mỗi lần vẽ bảng.

### Hàm module-level (logic thuần, không đụng UI)

```python
CAMPAIGN_STATUS_OPEN          = "Đang mở"
CAMPAIGN_STATUS_NOT_STARTED   = "Chưa mở"
CAMPAIGN_STATUS_CLOSED        = "Đã đóng"
CAMPAIGN_STATUS_UNDETERMINED  = "Chưa rõ"
CAMPAIGN_SOON_WINDOW          = timedelta(hours=24)
CAMPAIGN_STATUS_COLORS        = {...}

parse_campaign_time(text)                 # -> datetime | None
campaign_status(campaign, now=None)       # -> 1 trong 4 trạng thái
format_campaign_remaining(campaign, now)  # -> "còn 3h" / "quá hạn 4d"
```

`parse_campaign_time` nhận `%Y-%m-%d %H:%M`, `%Y-%m-%d %H:%M:%S`, `%Y-%m-%d`; trả
`None` cho chuỗi rác hoặc rỗng. `campaign_status` xử lý đúng 4 ca: không có ngày nào →
Chưa rõ; quá `closes_at` → Đã đóng; chưa tới `opens_at` → Chưa mở; còn lại → Đang mở.

### Bảng — 8 cột

`Tên | Link | Mở đăng ký | Đóng đăng ký | Trạng thái | Còn lại | Đã đăng ký | Ghi chú`

Cột **Trạng thái** tô màu theo `CAMPAIGN_STATUS_COLORS`. Cột **Còn lại** đếm ngược tới
mốc kế tiếp (`opens_at` nếu chưa tới giờ, ngược lại `closes_at`). Cột **Đã đăng ký** hiện
số tài khoản đã ghi nhận cho chiến dịch đó, tô xanh dương; rỗng thì hiện `—`.

### Vòng đời

```
add_campaign()    → CampaignDialog → validate_and_accept() → validate name/url → append → save
edit_campaign()   → selected_campaign_row() → CampaignDialog(campaign) → validate → gán đè → save
delete_campaign() → selected_campaign_row() → QMessageBox hỏi → del → save
open_campaign()   → selected_campaign_row() → webbrowser.open(url)
export_campaigns()→ QFileDialog → ghi file "|" ngăn cách
```

`CampaignDialog.validate_and_accept()` chặn **trước khi** dữ liệu vào bộ nhớ: sai
định dạng ngày thì báo, và `closes_at <= opens_at` thì báo. Bỏ trống cả hai ngày thì hợp lệ
(trạng thái Chưa rõ).

### Hàm cốt lõi trong `AccountManager`

| Hàm | Trách nhiệm |
|---|---|
| `create_campaign_tab()` | Dựng hàng lọc + hàng nút + bảng 7 cột + `campaign_timer` |
| `refresh_campaign_table()` | Vẽ lại bảng, tạo `self.campaign_states` (row → trạng thái) |
| `update_campaign_summary()` | Dòng tổng kết + **cảnh báo sắp mở trong 24h, mỗi chiến dịch đúng 1 lần** |
| `apply_campaign_filter()` | `setRowHidden` theo combo lọc + ô tìm kiếm tên/link |
| `export_campaigns()` | Ghi file txt phân cách bằng `\|`, có dòng header |
| `selected_campaign_row()` | Index dòng đang chọn, hoặc `None` + hộp thoại nhắc |
| `save_campaigns()` | Ghi QSettings → `sync()` → refresh |
| `add_campaign()` / `edit_campaign()` | Validate `name` khác rỗng và `urlparse(url).scheme in {"http","https"}` |

### Lọc và tìm kiếm

| Giá trị combo | Ý nghĩa |
|---|---|
| `all` | Tất cả |
| `Đang mở` | Chỉ trạng thái Đang mở |
| `soon` | Chưa mở **và** cách `opens_at` ≤ 24h |
| `Chưa mở` / `Đã đóng` / `Chưa rõ` | Lọc theo trạng thái |

`apply_campaign_filter` dùng `setRowHidden` nên chỉ ẩn dòng, **không** xoá khỏi
`self.campaigns` — index bảng luôn khớp index list.

### Làm mới theo thời gian

`QTimer` 60 giây gọi `refresh_campaign_table()`. Nhờ vậy sang nửa đêm hoặc tới giờ mở
thì trạng thái tự đổi, không cần bấm tay. `campaign_states` giữ trạng thái của lần vẽ
trước để cảnh báo chỉ bắn một lần cho mỗi chiến dịch.

### Lưu trữ và tương thích dữ liệu cũ

- Biến trong RAM: `self.campaigns` (list[dict]).
- Lưu: `QSettings("NAMCO", "AccountManager")` key `campaigns`, **chuỗi JSON**
  (`ensure_ascii=False`).
- Nạp trong `load_data()`, chống lỗi JSON hỏng (reset `[]`).
- Dữ liệu cũ ghi ngày dạng text tự do vẫn đọc được: `parse_campaign_time` trả `None`
  → hiển thị "Chưa rõ". Sửa lại qua nút **Sửa** là chuyển sang trạng thái thật.

### Giới hạn còn lại

- Không có sắp xếp cột, không chọn nhiều dòng để xoá.
- Không có import từ file (chỉ export).
- Cảnh báo hiện status bar + nhật ký, không có popup.

### Đăng ký thủ công theo chiến dịch (Phần 2 & 3)

Group box **Đăng ký thủ công theo chiến dịch** nằm dưới bảng. Ràng buộc quan trọng:
app **không** điền form và **không** submit — đăng ký là thao tác thủ công của người
dùng trên trang 抽選. App chỉ mở link và chép sẵn thông tin để giảm việc gõ.

| Thành phần | Trách nhiệm |
|---|---|
| `signup_campaign_label` | Tên + trạng thái chiến dịch đang chọn, cập nhật theo `itemSelectionChanged` |
| `signup_account_combo` | Danh sách email lấy từ `self.accounts`, chỉ dựng lại khi danh sách thay đổi |
| `signup_copy_password` | Mặc định **tắt** → chép email. Bật → chép `email\npassword` (dán vào 2 ô) |
| `signup_summary_label` | Số tài khoản đã đăng ký của chiến dịch đang chọn |

| Hàm | Việc làm |
|---|---|
| `open_campaign_with_account()` | `webbrowser.open(url)` + `setText` clipboard, báo status bar và nhật ký |
| `mark_account_registered()` | Thêm `{email, at}` vào danh sách của chiến dịch, bỏ qua nếu đã có |
| `unmark_account_registered()` | Bỏ email khỏi danh sách của chiến dịch |
| `show_campaign_signups()` | Hộp thoại liệt kê email + thời điểm, sắp theo thời gian |

### Lưu ghi nhận đăng ký

```python
campaign_key(campaign)  # -> "tên|link", ổn định qua đổi thứ tự dòng
self.campaign_signups    # {campaign_key: [{"email": ..., "at": "YYYY-MM-DD HH:MM:SS"}]}
QSettings key: "campaign_signups"   # chuỗi JSON
```

- `load_signups()` gọi trong `load_data()`, chống lỗi JSON hỏng → `{}`.
- `save_signups()` ghi rồi refresh bảng.
- `prune_orphan_signups()` chạy trong `save_campaigns()`: xoá ghi nhận của chiến dịch
  đã bị xoá để dữ liệu không phình vô hạn.
- `refresh_signup_accounts()` được gọi từ `update_table()` nên combo tài khoản luôn khớp
  danh sách; có so chữ ký `signup_account_emails` để không dựng lại combo vô ích.

---

## 4. Logic tab Cấu hình — Proxy

### File `proxy.txt`

Mỗi dòng 1 proxy. Định dạng chính: `ip:port:username:pass`.

`parse_proxy(line)` chấp nhận thêm: `ip:port`, `user:pass@ip:port`,
`http(s)://ip:port:username:pass`. Dòng `#` hoặc `//` = comment. Mật khẩu được
`quote()` khi dựng URL nên chứa được `:` và `@`.

```python
"1.2.3.4:8080:usr:p@ss:w:rd"  →  http://usr:p%40ss%3Aw%3Ard@1.2.3.4:8080
```

### `proxy_manager.py`

```python
proxy_manager = ProxyManager()      # singleton dùng chung
new_session()                       # -> ProxySession, dùng thay requests.Session()
```

| Thành phần | Trách nhiệm |
|---|---|
| `parse_proxy` | Dòng → dict `{host, port, username, password, scheme, raw}` hoặc lý do lỗi |
| `proxy_url` / `as_requests_proxies` | Dict `{"http": url, "https": url}` |
| `check_proxy` | GET một URL qua proxy, trả `(ok, message)` |
| `check_all_proxies` | ThreadPoolExecutor 10 luồng, `emit(index, ok, msg)` |
| `ProxyManager` | Giữ `path`, `enabled`, `mode`, `proxies`, `errors`; cursor luân phiên + `threading.Lock` |
| `ProxySession(requests.Session)` | Override `request()` để gắn proxy |

### Hai chế độ

| Mode | Hành vi |
|---|---|
| `MODE_PER_REQUEST` | Mỗi HTTP request lấy proxy kế tiếp (vòng tròn) |
| `MODE_PER_SESSION` | Proxy chọn một lần khi tạo session, giữ suốt phiên |

### Điểm nối vào luồng chính

- `LoginWorker.run()` → `session = new_session()`
- `change_name.change_name()` → `session = new_session()`
- Tắt proxy → `next_proxies()` trả `None` → request đi thẳng như bản gốc.

### Vòng đời trong UI

```
load_proxy_settings()   # đọc QSettings, blockSignals, apply_proxy_settings(reload_file=True)
apply_proxy_settings()  # gán path/mode/enabled → proxy_manager.load() → refresh bảng → status
```

`refresh_campaign_table` tương tự pattern này cho chiến dịch.

Keys QSettings: `proxy_file`, `proxy_enabled`, `proxy_mode`.

---

## 5. Luồng đăng nhập — chi tiết nhất

Đây là phần dễ vỡ nhất của dự án. `LoginWorker.run()`:

```
1. progress 10  → session = new_session()
2. progress 30  → GET LOGIN_URL?client_id&redirect_uri   (lấy cookie `language`)
3. progress 50  → POST {API_URL}v3/login/idpw           (form: login_id, password, env_info…)
                  → result == "OK" ?
                    ├─ cookie từ response → session.cookies
                    ├─ inspect_login_handoff()  (mục 5.1)
                    └─ fetch_member_profile()   (mục 5.2)
4. progress 100
```

### 5.1 Parks2 handoff — `inspect_login_handoff()`

Mục tiêu: hoàn tất đăng nhập Parks2 **không tạo passkey**.

```
redirect URL từ server → parse code
  → GET v3/passkey/info?client_id&code&...    (X-Requested-With: XMLHttpRequest)
  → result != "OK"              → profile_fetch_status = "Could not complete..."
  → đặt cookie từ response (có `value` = set, thiếu = xoá)
  → data.btn.btn-next.url      → GET url (Accept HTML) → phải về parks2.bandainamco-am.co.jp
```

**Bẻ nhánh quan trọng:** handoff fail **không** đồng nghĩa Parks2 không dùng được.
`LoginWorker` luôn thử thêm `fetch_member_profile()` và chỉ ghi đè
`profile_fetch_status` khi lấy được hồ sơ.

### 5.2 Đọc hồ sơ — `fetch_member_profile()`

```
GET parks2.bandainamco-am.co.jp/member_mypage.html
  ├─ status != 200 hoặc URL không chứa "member_mypage"  → fallback sang edit form
  └─ parse_member_mypage_html()   (HTMLParser, mảng nhãn tiếng Nhật)
        + điền thêm trường còn thiếu bằng fetch_edit_profile()
```

Nhãn Nhật được map sang key tiếng Anh trong `field_map`. Điểm hiểm: `points` phải
trích bằng regex trên text đã bỏ tag vì nó nằm ngoài cặp `dt/dd`.

### 5.3 Đổi tên — `change_name.py`

`change_name()` làm lại đúng 3 bước đầu của login flow, rồi:

```
GET  member_regist.html?request=edit    → đọc hidden input + form action
POST form_action                        → kèm trường trim của framework
```

Kết quả được đo thành công khi status 200 và HTML **không chứa** `error`/エラー.

**Rủi ro đã biết:** cả hai bước đều dựa vào regex trên HTML, nên site đổi layout là
gãy. Nếu cần sửa, hãy kiểm tra lại form action và tên hidden input trước.

### 5.4 env_info phải khớp User-Agent

```python
env_info = json.dumps({"ua": USER_AGENT, "lang": language, "plat": "Win32",
                       "sw": 1920, "sh": 1080}, separators=(',', ':'))
```

`USER_AGENT` là hằng số duy nhất, dùng cho cả header lẫn `env_info.ua`.
Trước đây hai chỗ gõ lệch nhau (`env_info.ua` thiếu `Chrome/120.0.0.0 Safari/537.36`)
— client tự mâu thuẫn về thiết bị của mình là dấu hiệu dễ bị chặn.

---

## 6. Quản lý luồng (threading)

Tất cả network call chạy trong `QThread` để không block UI.

| Worker | Signal | Dùng cho |
|---|---|---|
| `LoginWorker` | `result_ready(str,bool,str)`, `profile_ready(str,dict)`, `progress(int)` | 1 tài khoản |
| `BatchCheckWorker` | `progress(int,int)`, `finished_check` | Cả danh sách, gọi `LoginWorker.run()` tuần tự, `time.sleep(0.5)` giữa các tài khoản |
| `ChangeNameWorker` | `result_ready`, `progress` | Đổi tên |
| `ProxyCheckWorker` | `row_ready(int,bool,str)`, `finished_check` | Kiểm tra proxy song song |

**Bẫy đã gặp:** `BatchCheckWorker` nối signal của `LoginWorker` con bằng
`Qt.ConnectionType.DirectConnection` rồi gọi `run()` trực tiếp (không `start()`).
Đừng đổi sang cách khác nếu chưa hiểu vì sao.

`closeEvent()` gọi `stop()` cho worker đang chạy rồi `save_data()`.

---

## 7. Bảng settings QSettings

| Key | Kiểu | Mặc định |
|---|---|---|
| `campaigns` | chuỗi JSON | `"[]"` |
| `proxy_file` | str | `PROXY_FILE` (cạnh app) |
| `proxy_enabled` | bool | `False` |
| `proxy_mode` | str | `"per_request"` |
| `theme` | str | `"light"` |
| `accent` | str | `"#d61718"` |
| `font_size` | int | `9` |
| `compact` | bool | `False` |
| `campaign_signups` | chuỗi JSON | `"{}"` — map `"tên\|link"` → danh sách `{email, at}` |

`apply_styles()` **xoá stylesheet của toàn bộ widget con** rồi áp lại bảng stylesheet
theo theme, nên mọi style tĩnh phải nằm trong chính bảng đó (dùng `objectName`).

---

## 8. Quy trình làm việc cho AI Agent

### Chạy app

```powershell
python -m pip install -r requirements.txt
python account_manager.py          # hoặc start.bat / install.bat
```

### Kiểm thử thay đổi

Không có test suite trong repo (`.gitignore` chặn `test_*.py`). Cách kiểm chứng đã
dùng và hiệu quả: script tạm với `QT_QPA_PLATFORM=offscreen`, chèn dữ liệu giả vào
widget, khẳng định trạng thái, rồi **xoá file tạm**. Với network thì monkey-patch
`requests.Session.get/post` để chặn và kiểm tra header/payload thật.

### Trước khi commit

1. `python -m py_compile account_manager.py change_name.py proxy_manager.py`
2. Xoá file tạm (`test_*_tmp.py`, ảnh chụp màn hình).
3. `git status` phải sạch trừ các file chủ ý sửa.
4. **Không** commit `accounts_data.json`, `proxy.txt`, `__pycache__/`.

### Commit + push (bắt buộc)

Sau mỗi thay đổi: commit rồi push lên `origin/main`, báo lại kết quả. Git identity
chưa có sẵn trong máy, dùng:

```powershell
git -c user.name="vzetiZero" -c user.email="106722218+vzetiZero@users.noreply.github.com" commit -m "..."
git push origin HEAD
```

Remote: `https://github.com/vzetiZero/bandainamcoApp.git`.

---

## 9. Trạng thái triển khai

### 9.1 Đã xong và đang chạy

| Hạng mục | Commit | Ghi chú |
|---|---|---|
| Thêm/nhập/xuất tài khoản | `329f7e1` | Nhập dán `email\|password` hoặc file TXT |
| Đăng nhập + Parks2 handoff | `4079c14`, `4579c2c` | Không tạo passkey |
| Parse hồ sơ từ mypage | `7f173c5`, `7c7d171` | Fallback sang edit form |
| Sửa 2 trường tên Kanji | `c0d1bdc` | Không sửa ngày sinh (đã gỡ) |
| Đổi tên qua form | `e65bc6f` | Regex trên HTML |
| Lọc/tìm kiếm, context menu, export | `329f7e1` | |
| Tab Chiến dịch | `86dcac5` | CRUD thủ công |
| Trạng thái + lọc + cảnh báo chiến dịch | xem git log | Tính từ ngày, không nhập tay |
| Đăng ký thủ công + ghi nhận tài khoản | xem git log | Mở link + clipboard, người dùng tự submit |
| Proxy cho mọi request | `6ccd2d3` | + tab Cấu hình, kiểm tra proxy |
| env_info khớp User-Agent | `10d8598` | |
| Màu cột Status | `10d8598` | Sửa bug so chuỗi không dấu |
| Nút compact tab Nhập | `20d5914` | 4 nút một hàng |
| Chủ đề sáng/tối, cỡ chữ | `717533c` | QSettings |

### 9.2 Đã thử rồi bỏ

| Hạng mục | Lý do |
|---|---|
| Sửa ngày sinh | Site không hỗ trợ qua form này (commit `8b96a95`) |
| Random `client_id` | Phá vỡ OAuth — xem mục 1 |
| Bot tự đăng ký chiến dịch | Rủi ro cao, app giữ mô hình thủ công |

### 9.3 Chưa làm

| Hạng mục | Mô tả | Mức độ ưu tiên |
|---|---|---|
| Import chiến dịch từ file | Nạp CSV/JSON (đã có export) | Trung bình |
| Lọc "chưa đăng ký" trong danh sách tài khoản | Lọc account theo chiến dịch đang chọn để biết còn tài khoản nào chưa đăng ký | Trung bình |
| Xuất danh sách tài khoản đã đăng ký | Ghi riêng file kèm thời điểm | Thấp |
| Sắp xếp bảng chiến dịch | Sort theo tên / thời gian | Thấp |
| Xoá nhiều chiến dịch | Chọn nhiều dòng | Thấp |
| Lọc proxy đã chết | Tự loại proxy báo lỗi khỏi danh sách dùng | Cao |
| Số liệu proxy | Đếm số lần dùng / lỗi theo từng proxy | Trung bình |
| Hỗ trợ SOCKS | Cần `pip install requests[socks]` | Thấp |
| Đổi mật khẩu tài khoản | Chưa có luồng nào | Trung bình |
| Sửa thêm trường hồ sơ | Kana, nickname, địa chỉ, sđt — `AccountDetailsDialog` đang read-only | Trung bình |
| Kiểm tra hàng loạt song song | `BatchCheckWorker` vẫn chạy tuần tự | Trung bình |
| Test suite | Chưa có file test được commit | Trung bình |
| Log ra file | Nhật ký chỉ hiện trong RAM, mất khi đóng app | Thấp |

---

## 10. Ràng buộc không được phá vỡ

1. Không thêm Selenium/Playwright — luồng hiện tại bằng `requests` là cố ý.
2. Không random `CLIENT_ID`, không bỏ qua `redirect_uri`.
3. Không commit secret (`accounts_data.json`, `proxy.txt`).
4. Mọi network call phải qua `new_session()` để còn dùng được proxy.
5. Mọi network call trên UI phải bọc trong `QThread`.
6. Style widget tĩnh phải khai báo trong `apply_styles()` qua `objectName`.
7. `USER_AGENT` là nguồn duy nhất cho cả header lẫn `env_info.ua`.
8. Chỉ sửa `last_name_kanji` / `first_name_kanji` qua `AccountDetailsDialog`.
9. Không viết automation tự điền form và submit đăng ký hàng loạt vào trang 抽選.
   Đã trình bày với người dùng và được xác nhận giữ nguyên quan điểm này. Phần được
   phép là trợ lý *mở link + chép thông tin cho một tài khoản*, người dùng tự dán và
   tự bấm submit. Đừng mở rộng `open_campaign_with_account()` thành vòng lặp nhiều tài khoản.
10. `signup_copy_password` mặc định **tắt**. Chỉ bật khi người dùng chủ động tick.
