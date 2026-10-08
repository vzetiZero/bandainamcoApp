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

**Mục đích:** lưu danh sách link chiến dịch (link đăng ký thời gian giới hạn) để
nhắc nhở và tra cứu. Đây là **sổ tay thủ công**, app **không** tự động đăng ký hộ.

### Cấu trúc dữ liệu — 5 trường

| Key | Cột hiển thị | Quy tắc |
|---|---|---|
| `name` | Tên | Bắt buộc, không rỗng |
| `url` | Link | Bắt buộc, scheme phải là `http` hoặc `https` |
| `opens_at` | Mở đăng ký | Chuỗi tự do, gợi ý `YYYY-MM-DD HH:MM` |
| `closes_at` | Đóng đăng ký | Chuỗi tự do, gợi ý `YYYY-MM-DD HH:MM` |
| `notes` | Ghi chú | Tự do, `QTextEdit` giới hạn 120px |

### Vòng đời

```
add_campaign()   → CampaignDialog → get_campaign() → validate → append → save_campaigns()
edit_campaign()  → selected_campaign_row() → CampaignDialog(campaign) → validate → gán đè → save
delete_campaign()→ selected_campaign_row() → del campaigns[row] → save
open_campaign()  → selected_campaign_row() → webbrowser.open(url)   # không validate lại
```

### Hàm cốt lõi

| Hàm | Dòng | Trách nhiệm |
|---|---|---|
| `create_campaign_tab()` | 785 | Dựng group nút + `campaign_table` 5 cột, chỉ đọc (NoEditTriggers), chọn 1 dòng |
| `refresh_campaign_table()` | 1039 | Vẽ lại bảng từ `self.campaigns`, cố định thứ tự key `("name","url","opens_at","closes_at","notes")` |
| `selected_campaign_row()` | 1046 | Trả index dòng đang chọn, hoặc `None` + hộp thoại nhắc |
| `save_campaigns()` | 1053 | `QSettings.setValue("campaigns", json.dumps(...))` → `sync()` → refresh bảng |
| `add_campaign()` / `edit_campaign()` | 1058 / 1069 | Validate `name` khác rỗng **và** `urlparse(url).scheme in {"http","https"}` |
| `open_campaign()` | 1083 | `webbrowser.open()` — mở trình duyệt mặc định |
| `delete_campaign()` | 1088 | Xóa không hỏi lại (khác `delete_single_account` vốn có confirm) |

### Lưu trữ

- Biến trong RAM: `self.campaigns` (list[dict]).
- Lưu: `QSettings("NAMCO", "AccountManager")` key `campaigns`, giá trị là **chuỗi
  JSON** (`ensure_ascii=False`).
- Nạp: trong `load_data()`, `json.loads()`, có chống lỗi: nếu không phải list thì
  reset `[]` và vẽ lại bảng.
- Không nằm trong `accounts_data.json`.

### Đặc điểm cần biết (giới hạn hiện tại)

- `opens_at` / `closes_at` **chỉ là text tự do**, không validate ngày, không so sánh,
  không cảnh báo chiến dịch sắp mở/đóng.
- Không có sắp xếp, không có import/export từ file.
- `open_campaign()` không kiểm tra chiến dịch đã đóng.
- Bảng không có cột trạng thái (chưa/khá mở/đã đóng).

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
| Tự động hoá chiến dịch | Theo dõi `opens_at`/`closes_at`, cảnh báo sắp mở/đóng, lọc "còn hiệu lực" | Cao |
| Import/export chiến dịch | Nạp/ghi CSV, JSON từ file | Trung bình |
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
