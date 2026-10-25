# NAMCO Account Manager — Tài liệu dự án cho AI Agent

Tài liệu này mô tả **logic đã có**, **trạng thái triển khai** và **kế hoạch** của dự án.
Đọc file này trước khi sửa bất kỳ dòng code nào.

> Nguyên tắc bất di bất dịch của dự án: **không tự động hoá trình duyệt** (không
> Selenium/Playwright). Toàn bộ luồng đăng nhập đi bằng `requests` thuần.

---

## 1. Tổng quan

Ứng dụng desktop Windows (PySide6) để quản lý danh sách tài khoản BANDAI NAMCO ID /
NAMCO Parks: thêm, kiểm tra đăng nhập, đọc hồ sơ thành viên, đổi tên Kanji.

### 1.1 Cấu trúc MVC + DI

Project tách theo lớp; **mọi phụ thuộc đi qua `app/container.py`**, UI không tự
`import` client mạng hay mở file dữ liệu.

| Path | Vai trò | Chứa gì |
|---|---|---|
| `account_manager.py` (24 dòng) | Điểm khởi chạy | `QApplication` + `AccountManager()`. Không còn logic. |
| `app/config.py` | Hằng số duy nhất | URL, `CLIENT_ID`, `USER_AGENT`, `ENV_INFO`, `ACCOUNT_COOKIE_DOMAIN`, `DATA_FILE`, `ICONS_DIR` |
| `app/domain/` | **Model** — quy tắc thuần, không import PySide6/requests | `accounts.py` (dòng nhập liệu, trạng thái, lọc, đếm), `names.py` (`NameForm`, `kanji_overrides`), `campaigns.py` (trạng thái theo ngày), `login_rules.py` (`describe_login_error`) |
| `app/infrastructure/` | **Adapter** — chạm mạng/dĩa/QSettings | `bandai_auth.py` (login + handoff + hồ sơ), `bandai_profile.py`, `bandai_name.py` (form đổi tên), `account_repository.py` (`accounts_data.json`), `settings_store.py` (QSettings), `web.py` (header + cookie) |
| `app/services/` | **Use case** — nghiệp vụ trên model + repo | `account_service.py` (add/delete/status/profile/export), `campaign_service.py` (CRUD + đăng ký) |
| `app/ui/` | **View/Controller** | `main_window.py` (view + handler), `dialogs.py`, `workers.py` (`QThread`), `delegates.py` (badge), `table_spec.py` (cột), `styles.py` (QSS) |
| `app/container.py` | **Composition root** | `build_container(...)` trả `Container(settings, auth_client, name_client, account_repository, account_service, campaign_service)` |
| `proxy_manager.py` | Proxy cho mọi HTTP request | `new_session()`, đọc `proxy.txt` |
| `change_name.py` | CLI đổi tên | chỉ tham số dòng lệnh + gọi `BandaiNameClient.change_profile()` |
| `icon_helper.py` | Nạp SVG icon | cache theo tên icon |
| `accounts_data.json` | Dữ liệu tài khoản + hồ sơ | **Git-ignored, chứa mật khẩu.** |
| `proxy.txt` | Danh sách proxy | **Git-ignored, chứa user/pass.** |

**Chiều phụ thuộc:** `ui → services → domain` và `ui → infrastructure` (qua container);
`domain` không biết `infrastructure`; `infrastructure` không biết `ui`. Muốn test mà
không cần mạng: `build_container(session_factory=lambda: FakeSession(), settings=store,
data_file=temp)` rồi truyền chai đó vào `AccountManager(container=...)`.

### Hằng số mạng

Toàn bộ nằm trong `app/config.py` — **đừng** khai báo lại ở nơi khác:

```python
API_URL       = "https://account-api.bandainamcoid.com/"
LOGIN_URL     = "https://account.bandainamcoid.com/login.html"
CLIENT_ID     = "namcoparks_onlinestore"          # OAuth client đã đăng ký — KHÔNG ĐỔI
REDIRECT_URI  = "https://parks2.bandainamco-am.co.jp/member_regist_new.html?backto=top"
USER_AGENT    = "Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36"
```

> `CLIENT_ID` là client OAuth đã đăng ký của app NAMCO Parks, khớp `REDIRECT_URI`.
> **Không bao giờ random hóa** — server sẽ từ chối (`invalid_client`) và mọi tài khoản
> thật đều dùng chung giá trị này. Không phải fingerprint thiết bị.

---

## 2. Cấu trúc UI — toolbar + 3 tab

`AccountManager.setup_ui()` (app/ui/main_window.py) dựng `QToolBar` rồi `QTabWidget` theo thứ tự:

| # | Tab | Hàm dựng | Nội dung |
|---|---|---|---|
| 1 | Danh sách tài khoản | `create_right_panel()` | Bảng 21 cột + progress + nhật ký bên phải |
| 2 | Chiến dịch | `create_campaign_tab()` | Bảng CRUD chiến dịch |
| 3 | Cấu hình | `create_settings_tab()` | Bật/tắt proxy, file, chế độ, kiểm tra proxy |

### 2.0 Toolbar — nút hành động

4 nút hành động cùng cấp trên toolbar, style qua `objectName` trong `apply_styles()`:

| objectName | Nhãn | Handler |
|---|---|---|
| `toolInput` | Nhập tài khoản | `open_input_dialog()` — mở `self.input_dialog` |
| `toolImport` | Import TXT | `import_from_txt` |
| `toolCheckAll` | Kiểm tra tất cả tài khoản | `check_all_accounts` |
| `toolDelete` | Xóa đã chọn | `delete_selected` |

### 2.1 Dialog Nhập tài khoản

Panel nhập (`create_left_panel()`) không còn là tab — nó nằm trong `self.input_dialog`
(`QDialog` không modal, giữ nguyên widget giữa các lần mở). Ô nhập `email|password`,
4 nút compact trên một hàng, tất cả dùng `objectName` để style trong `apply_styles()`:

| objectName | Nhãn | Icon | Handler | Tooltip |
|---|---|---|---|---|
| `actionAdd` | Thêm | `plus` | `add_from_text` | Thêm các tài khoản trong ô nhập vào danh sách |
| `actionClear` | Xóa | `x` | `text_input.clear` | Xóa toàn bộ nội dung ô nhập |
| `actionCheck` | Kiểm tra đầu tiên | `check` | `check_first_account` | Kiểm tra tài khoản đầu tiên trong danh sách |
| `actionExport` | Export | `download` | `export_accounts` | Export danh sách tài khoản ra file |

**Quy ước bắt buộc:** muốn thêm nút mới thì đặt `objectName` và khai báo
màu trong bảng QSS của `app/ui/styles.py::build_stylesheet()`. `apply_styles()` chỉ còn
hai việc: xoá stylesheet của từng widget con rồi `setStyleSheet(build_stylesheet(**read_appearance(self.ui_settings)))`.
**Không** dùng `setStyleSheet()` trực tiếp trên widget —`apply_styles()` xoá sạch stylesheet
của mọi widget con mỗi lần đổi giao diện.

`progress_bar` nằm ở tab danh sách (trên bảng); `log_text` được tạo trong `setup_ui()`
và đặt ở khung nhật ký bên phải bảng.

### 2.2 Tab 1 — Danh sách tài khoản

- Dashboard 4 thẻ thống kê trên bảng: Tổng / Hoạt động / Không hoạt động / Chưa kiểm tra.
  `update_dashboard()` được gọi cuối `update_table()` nên số liệu luôn khớp bảng.
  objectName: `statCard`, `statValueTotal`, `statValueActive`, `statValueInactive`,
  `statValueUnchecked`, `statCaption` — màu khai báo trong `apply_styles()`.
- Bảng **không còn cột `#`**: số thứ tự do vertical header đảm nhiệm. Cột 0 là Email,
  cột 1 Password, cột 2 Status — `apply_filter()` đọc đúng các index này.
- Cột `Password` luôn hiển thị `********`.
- Danh sách cột là hằng số module `ACCOUNT_COLUMNS`. Nút **Cột hiển thị** (`column_button`)
  mở menu checkable; cột ẩn lưu QSettings key `hidden_account_columns` (JSON) qua
  `set_column_hidden()`. Email luôn hiển thị, không nằm trong menu.
- Sắp xếp: `on_header_clicked()` **sắp lại tại chỗ danh sách của `AccountService`**
  (property `self.accounts` trỏ đúng list đó) rồi `update_table()` + `save_data()` — index
  bảng luôn khớp list. Không dùng `setSortingEnabled()` vì sẽ phá invariant index
  (context menu, xóa, double-click đều đọc `self.accounts[row]`).
- Cột Status vẽ badge bo tròn bởi `StatusDelegate` (màu từ `STATUS_BADGE_COLORS`, nền tint
  alpha 40 nên đúng cả theme sáng/tối); giá trị lạ fallback về vẽ mặc định.
- **Tiến trình theo từng tài khoản**: cột Email (index 0) có `EmailProgressDelegate`.
  `set_row_progress(email, percent)` ghi percent vào `self.row_progress` rồi đặt
  `PROGRESS_ROLE` (khai báo ở `table_spec.py`) lên item Email và vẽ lại đúng ô đó bằng
  `viewport().update(visualRect(index))` — không gọi `update_table()` (sẽ mất fill).
  Delegate vẽ nền màu accent alpha 90 chiếm `percent` chiều rộng ô, text email elided bên
  trái và `NN%` góc phải; `percent = 0` → trả về vẽ mặc định. Vì vậy khi kiểm tra song song
  nhiều tài khoản, mỗi dòng tự cho biết tài khoản đó đang tới đâu.
  `on_check_result`/`on_single_result` xoá fill (`set_row_progress(email, 0)`) trước khi ghi kết quả.
- `refresh_account_row(email)` chỉ dựng lại một dòng (theo `account_row()`), dùng cho kết quả
  kiểm tra/đổi tên đơn lẻ; `update_dashboard()` + `apply_filter()` vẫn chạy sau đó.
  Chỉ `setItem()` khi ô chưa có item: Qt 6 cảnh báo
  "cannot insert an item that is already owned by another QTableWidget" và **bỏ qua** lần
  insert đó kể cả khi item thuộc cùng bảng, nên code cũ `item or QTableWidgetItem()` rồi
  `setItem()` lại sinh 21 dòng log mỗi lần refresh một dòng. Sửa: lấy item sẵn có →
  `setText()` trực tiếp, chỉ tạo + insert khi `item is None`.
- Trạng thái rỗng: `empty_label` phủ giữa bảng khi chưa có tài khoản hoặc không dòng nào
  khớp bộ lọc; geometry đồng bộ qua `eventFilter` bắt Resize của viewport.
- Phím tắt: Ctrl+N mở dialog nhập, Ctrl+I import, Ctrl+F focus ô tìm kiếm,
  Del xóa dòng chọn (context `WidgetShortcut` gắn trên bảng để không bắt phím khi gõ ô khác).
- Toolbar: `stats_chip` rich-text "x hoạt động · y lỗi · z chưa kiểm tra" cạnh nhãn tổng số.
- Bảng nhật ký (`self.log_panel`, QFrame bên phải bảng) **mặc định đóng** để bảng tài khoản
  rộng tối đa; nút **Nhật ký** trên toolbar (checkable, `log_btn`) gọi
  `set_log_panel_visible()` để mở/đóng, nhãn đổi thành "Ẩn nhật ký" khi đang mở. Log vẫn được
  ghi vào `log_text` khi panel đóng nên mở lại là thấy đủ. Trong panel có nút **Xóa log**
  (`clear_log()`), chỉ xóa nội dung hiển thị, không đụng dữ liệu.
- Dialog nhập: kéo thả file `.txt` vào ô nhập (eventFilter DragEnter/Drop, chỉ nhận `.txt`),
  `update_input_preview()` đếm sẵn "Sẽ thêm / Trùng / Sai định dạng" theo `textChanged`.
- Cột `Status` tô màu: `Hoạt động` → `#28a745`, `Không hoạt động` → `#dc3545`,
  `Chưa kiểm tra` → `#8a94a6`. Phải so sánh **chuỗi có dấu chính xác**
  (lỗi cũ từng so `"Hoat"` với `"Hoạt động"` nên không bao giờ tô màu).
- Lọc: `apply_filter()` theo status + tìm kiếm email (dùng `setRowHidden`).
- Context menu chuột phải: `context_rows()` quyết định menu tác động lên đâu — bấm vào
  **trong vùng đang chọn** thì giữ nguyên cả vùng (Kiểm tra / Copy / Xóa chạy cho **tất cả**
  tài khoản đã chọn, nhãn menu ghi rõ số dòng), bấm ra ngoài vùng thì chỉ dòng vừa bấm.
  "Đổi tên" và "Xem thông tin" về bản chất chỉ làm được với 1 tài khoản (một worker, một hộp
  thoại) nên nhãn của chúng ghi kèm email mục tiêu để không nhầm là đã áp dụng cho cả vùng.
- Xóa (menu chuột phải, nút toolbar và Del) luôn qua `confirm_and_delete()`: hộp thoại xác nhận
  liệt kê tối đa 10 email ("… và N tài khoản nữa"), bấm No không xóa gì, bấm Yes xóa trọn
  vùng và ghi xuống file.

### 2.3 Tab 3 — Chiến dịch (chi tiết ở mục 3)

### 2.4 Tab 4 — Cấu hình (chi tiết ở mục 4)

Tab Cấu hình có nhóm **Kiểm tra đồng thời** (`_create_concurrency_group()`, `QSpinBox`
`max_workers_input`, suffix " luồng", range `1..MAX_CONCURRENCY` ở `app/config.py`).
`on_concurrency_changed()` gán ngay `self.max_workers` và ghi QSettings `max_workers`, nên
lần chạy batch kế tiếp dùng đúng số luồng vừa chọn. Mặc định `DEFAULT_CONCURRENCY = 5`.

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

### Hằng số module-level (logic thuần, không đụng UI) — `app/domain/campaigns.py`

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
add_campaign()    → CampaignDialog → validate_and_accept() → campaign_service.add() → refresh
edit_campaign()   → selected_campaign_row() → CampaignDialog(campaign) → campaign_service.update(row, …)
delete_campaign() → selected_campaign_row() → QMessageBox hỏi → campaign_service.remove(row)
open_campaign()   → selected_campaign_row() → webbrowser.open(url)
export_campaigns()→ QFileDialog → ghi file "|" ngăn cách
```

`CampaignDialog.validate_and_accept()` chặn **trước khi** dữ liệu vào bộ nhớ: sai
định dạng ngày thì báo, và `closes_at <= opens_at` thì báo. Bỏ trống cả hai ngày thì hợp lệ
(trạng thái Chưa rõ).

### Chia trách nhiệm — view vs `CampaignService`

| Thuộc tính / hàm | Việc làm |
|---|---|
| `campaign_service.add/update/remove/save` | Sửa list chiến dịch rồi ghi QSettings (qua `SettingsStore`), tự `prune_orphan_signups()` khi save |
| `campaign_service.mark/unmark/signups_for/is_registered` | Ghi nhận tài khoản đã đăng ký theo khoá chiến dịch |
| `campaign_service.key/is_valid` (staticmethod) | Khoá `"tên\|link"` và chuẩn kiểm tên + scheme http(s) |
| `create_campaign_tab()` | Dựng hàng lọc + hàng nút + bảng 8 cột + `campaign_timer` |
| `refresh_campaign_table()` | Vẽ lại bảng từ `self.campaigns`, tạo `self.campaign_states` (row → trạng thái) |
| `update_campaign_summary()` | Dòng tổng kết + **cảnh báo sắp mở trong 24h, mỗi chiến dịch đúng 1 lần** |
| `apply_campaign_filter()` | `setRowHidden` theo combo lọc + ô tìm kiếm tên/link |
| `export_campaigns()` | Ghi file txt phân cách bằng `\|`, có dòng header |
| `selected_campaign_row()` | Index dòng đang chọn, hoặc `None` + hộp thoại nhắc |

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

- Biến trong RAM: `CampaignService.campaigns` (list[dict]); view đọc qua property
  `self.campaigns` / `self.campaign_signups` — **không có setter**, muốn sửa phải đi qua service.
- Lưu: `QSettings("NAMCO", "AccountManager")` key `campaigns`, **chuỗi JSON**
  (`ensure_ascii=False`), ghi bởi `SettingsStore.set_json`.
- Nạp trong `load_data()` → `campaign_service.load()`, chống lỗi JSON hỏng (reset `[]`).
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
CampaignService.key(campaign)  # -> "tên|link", ổn định qua đổi thứ tự dòng
campaign_service.signups       # {campaign_key: [{"email": ..., "at": "YYYY-MM-DD HH:MM:SS"}]}
QSettings key: "campaign_signups"   # chuỗi JSON
```

- `campaign_service.load()` đọc cả hai key trong `load_data()`, chống lỗi JSON hỏng → `[]`/`{}`.
- `save_signups()` ghi rồi refresh bảng.
- `prune_orphan_signups()` chạy trong `campaign_service.save()`: xoá ghi nhận của chiến dịch
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

- `build_container()` mặc định đặt `session_factory = proxy_manager.new_session`, nên
  `BandaiAuthClient` và `BandaiNameClient` đều đi qua proxy. Không client nào tự
  `requests.Session()`.
- `ProxyCheckWorker` gọi `check_all_proxies()` trực tiếp.
- Tắt proxy → `next_proxies()` trả `None` → request đi thẳng như bản gốc.

### Vòng đời trong UI

```
load_proxy_settings()   # đọc SettingsStore, blockSignals, apply_proxy_settings(reload_file=True)
apply_proxy_settings()  # gán path/mode/enabled → proxy_manager.load() → refresh bảng → status
```

`refresh_campaign_table` tương tự pattern này cho chiến dịch.

Keys: `proxy_file`, `proxy_enabled`, `proxy_mode` (đọc/ghi qua `SettingsStore`, không
chạm `QSettings` trực tiếp ở services/UI).

---

## 5. Luồng đăng nhập — chi tiết nhất

Đây là phần dễ vỡ nhất của dự án. Logic nằm trong `BandaiAuthClient`
(app/infrastructure/bandai_auth.py), UI chỉ nhận kết quả qua `LoginWorker`
(app/ui/workers.py):

```
1. progress 10  → session = session_factory()  (mặc định = proxy_manager.new_session)
2. progress 25  → GET LOGIN_URL?client_id&redirect_uri
                  + tự set cookie `language` ở miền ACCOUNT_COOKIE_DOMAIN
                  (getLanguage() của site luôn ghi cookie này)
3. progress 40  → GET {API_URL}v3/login/init   → apply_response_cookies()
                  (cấp cookie `challengeProd`; BỎ BƯỚC NÀY thì Parks2 không trả
                   btn-next và không bao giờ đọc được hồ sơ)
4. progress 55  → POST {API_URL}v3/login/idpw  (login_id, password, env_info, cookie…)
5. progress 70  → describe_login_error(payload)  (mục 5.0, app/domain/login_rules.py)
                    ├─ có lỗi  → LoginOutcome(success=False, reason) và DỪNG ở đây
                    └─ không lỗi → complete_parks2_handoff()  (mục 5.1)
                                    → fetch_member_profile() (mục 5.2)
6. progress 100
```

`login()` trả `(AuthenticatedSession|None, reason)`; `authenticate()` chạy trọn
login → handoff → hồ sơ và trả `LoginOutcome(success, reason, profile, profile_fields,
handoff)` — luôn thử đọc hồ sơ kể cả khi handoff báo lỗi.

### 5.0 `result == "OK"` KHÔNG có nghĩa là đăng nhập được

Đây là bug đã gây ra hiện tượng "đăng nhập thành công nhưng không đọc được hồ sơ".
Server trả `result: "OK"` cho mọi request được xử lý, kể cả khi sai mật khẩu:

| Tình huống | `result` | `input_error` | `redirect` |
|---|---|---|---|
| Sai email/mật khẩu | `OK` | có `error_msg.other` (tiếng Nhật) | **không có** |
| Đúng credentials, env_info sai | `NG` | null | `…/error.html` |
| Đúng credentials, đúng env_info | `OK` | null | `passkeyInfo.html?...&code=…` |

`describe_login_error(payload)` là hàm duy nhất quyết định thành/bại: kiểm tra
`result`, rồi `input_error.error_msg`, rồi redirect phải tồn tại và không phải
`error.html`. `LOGIN_ERROR_TRANSLATIONS` dịch hai câu tiếng Nhật hay gặp nhất sang
tiếng Việt để log dễ đọc. **Đừng** quay lại so `result == "OK"`.

### 5.0.1 Định dạng dữ liệu tài khoản

List tài khoản là `email|password|token` (3 trường). `parse_account_line()`
(app/domain/accounts.py) tách theo **từng dấu `|`**: email = trường 1, password = trường 2,
token = phần còn lại.
Bản cũ dùng `split('|', 1)` nên mật khẩu bị dính luôn token (`Letuemy…|k1gx82rp`) →
mọi tài khoản đều sai credentials. `migrate_split_passwords()` chạy trong
`AccountRepository.load()` sửa một lần cho dữ liệu đã lưu và chuyển phần thừa sang key
`token`; `AccountService.export_lines()` ghi lại đủ 3 trường để round-trip không mất dữ liệu.

### 5.1 Parks2 handoff — `complete_parks2_handoff()`

(app/infrastructure/bandai_profile.py)

Mục tiêu: hoàn tất đăng nhập Parks2 **không tạo passkey**.

```
redirect URL từ server → parse code
  → GET v3/passkey/info?client_id&code&...    (X-Requested-With: XMLHttpRequest)
  → result != "OK"              → HandoffResult(ok=False, status="Could not complete...")
  → apply_response_cookies()    (có `value` = set, thiếu = xoá)
  → data.btn.btn-next.url      → GET url (Accept HTML) → phải về parks2.bandainamco-am.co.jp
```

**Bẻ nhánh quan trọng:** handoff fail **không** đồng nghĩa Parks2 không dùng được.
`BandaiAuthClient.authenticate()` luôn gọi thêm `fetch_member_profile()` và chỉ ghi đè
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
Tài khoản thật đã kiểm chứng trả về 16 trường (kanji/kana, nickname, giới tính, địa
chỉ, điện thoại, điểm, trạng thái BNID…).

### 5.3 Đổi tên / sửa hồ sơ — `BandaiNameClient.change_profile()`

Site là flow Interfactory **hai bước**; POST một lần duy nhất không sửa được gì:

```
login + handoff + GET member_regist.html?request=edit   → parse_name_form(html, url, "memberFrm")
POST action (request=confirm, đủ 5 field tên + trim)     → HTML có <form name="confirmForm">
POST member_regist_confirm.html (request=execute,
     token + CONFIRM_TOKEN)                               → lưu thật
GET lại trang edit                                        → so từng field đã override
```

Ba điểm phải giữ:

- **Chọn đúng form.** Trang edit chứa cả form tìm kiếm ở header/mobile
  (`action="item_list.html"`); `form_block_html(html, form_name)` lấy theo
  `name="memberFrm"` / `name="confirmForm"`. Chọn form đầu tiên là gửi sai chỗ.
- **Gửi đủ mọi field.** `NameForm.form_data()` nạp giá trị hiện tại rồi mới đè override;
  thiếu `L_KANA`/`F_KANA`/`NICKNAME` là xoá dữ liệu thật của tài khoản, thiếu
  `jp.co.interfactory.framework.trim.<FIELD>` thì framework bỏ qua submit.
- **Xác minh bằng đọc lại.** `change_profile` so từng field đã gửi với trang đọc lại;
  khác nhau trả thất bại kèm "Trang vẫn hiển thị: ...".

GUI (`ChangeNameWorker`) chỉ gửi hai trường Kanji qua `kanji_overrides()`; CLI
`change_name.py` cho phép thêm kana/nickname. Kết quả được đo thành công khi status 200
và HTML **không chứa** `error`/エラー.

**Rủi ro đã biết:** cả hai bước đều dựa vào regex trên HTML, nên site đổi layout là
gãy. Nếu cần sửa, hãy kiểm tra lại form action và tên hidden input trước.

### 5.4 env_info phải đúng dạng của site

`getEnvInfo()` trong `js/webauthn-client.js` chỉ trả về **hai** trường, lấy từ
`navigator.userAgentData`:

```python
ENV_INFO = json.dumps({"mobile": False, "platform": "Windows"}, separators=(",", ":"))
```

Dạng cũ `{ua, lang, plat, sw, sh}` là tự bịa; server không nhận và trả
`result: NG` kèm `data.msg = "bnidv3 auth_sns_user get {'title': 'BadRequest', 'status': 400…}"`
rồi redirect về `error.html`. `USER_AGENT` vẫn là hằng số duy nhất cho **header**.

---

## 6. Quản lý luồng (threading)

Tất cả network call chạy trong `QThread` để không block UI. Worker nằm trong
`app/ui/workers.py` và **nhận client từ ngoài** (`auth_client`, `name_client`) thay vì
tự tạo — truyền client giả là test được worker mà không cần mạng.

| Worker | Signal | Dùng cho |
|---|---|---|
| `LoginWorker` | `result_ready(str,bool,str)`, `profile_ready(str,dict)`, `progress(int)` | 1 tài khoản; gọi `auth_client.authenticate()` rồi dịch `LoginOutcome` sang thông báo tiếng Việt |
| `BatchCheckWorker` | `result_ready`, `profile_ready`, `account_progress(str,int)`, `progress(int,int)`, `finished_checking` | Nhiều tài khoản **song song**: `ThreadPoolExecutor(max_workers=self.max_workers)` submit `_check_one` cho từng cặp email/password; `as_completed` tăng bộ đếm và emit `progress(completed, total)`. `max_workers` clamp `1..MAX_CONCURRENCY` ngay trong `__init__`. |
| `ChangeNameWorker` | `result_ready`, `progress` | Đổi tên; gọi `name_client.change_profile(..., kanji_overrides(last, first), on_progress=self.progress.emit)` |
| `ProxyCheckWorker` | `row_ready(int,bool,str)`, `finished_check` | Kiểm tra proxy song song |

**Bẫy đã gặp:** `BatchCheckWorker` nối signal của `LoginWorker` con bằng
`Qt.ConnectionType.DirectConnection` rồi gọi `run()` trực tiếp trong thread của pool (không
`start()`). Tín hiệu vì vậy phát trên thread pool, nên handler phía UI chỉ được làm việc nhẹ
(ghi dict + `viewport().update`) — muốn đổi sang `QueuedConnection` phải kiểm tra lại thứ tự
`profile_ready`/`result_ready`.

`_check_one` chuyển `LoginWorker.progress(int)` sang `account_progress(email, percent)` để
fill của đúng dòng tài khoản (view nối vào `set_row_progress`).

Hủy: `stop()` đặt `_is_running = False`; `run()` kết thúc bằng
`pool.shutdown(wait=self._is_running, cancel_futures=not self._is_running)` — đang chạy thì
chờ task hiện tại xong, bị stop thì hủy task còn xếp hàng. `_check_one` cũng kiểm tra
`_is_running` nên tài khoản bị hủy không phát signal, không để lại fill trên dòng.
`finished_checking` luôn emit sau khi pool đóng (view dùng nó để ẩn progress bar).

**Worker phải được giữ tham chiếu:** mọi `worker.start()` đi qua `start_worker()` của view,
thêm worker vào `self.workers` và tự gỡ khi thread phát `finished`. Trước đây worker chỉ nằm
ở `self.worker` nên lần kiểm tra kế tiếp làm GC một `QThread` còn đang chạy — Qt abort
("QThread: Destroyed while thread is still running"), và `closeEvent()` không dừng được gì
vì `self.workers` luôn rỗng.

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
| `hidden_account_columns` | chuỗi JSON | `"[]"` — tập key cột đang ẩn, `set_column_hidden()` ghi |
| `max_workers` | int | `DEFAULT_CONCURRENCY` = **5**, clamp `1..MAX_CONCURRENCY` (10) khi đọc và khi ghi |

UI/services không tự chạm `QSettings`; mọi reading/ghi đi qua `SettingsStore`
(`get/get_bool/get_int/set`, `get_json/set_json`) và `Container.settings`.

`apply_styles()` **xoá stylesheet của toàn bộ widget con** rồi áp `build_stylesheet()`
(app/ui/styles.py) theo theme, nên mọi style tĩnh phải nằm trong bảng QSS của module đó
(dùng `objectName`).

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
widget, khẳng định trạng thái, rồi **xoá file tạm**. Sau khi tách MVC/DI thì không cần
patch mạng nữa:

```python
container = build_container(data_file=duong_dan_temp, session_factory=lambda: FakeSession(),
                            settings=SettingsStore(), on_log=print)
window = AccountManager(container=container)      # service + client đều là đồ giả
```

- `FakeSession` (chỉ có `get`/`post` trả HTML dựng sẵn) chứng minh được flow đổi tên
  chạy **đủ hai bước** `request=confirm` → `request=execute`.
- `AccountRepository(path=temp)` cho test migrate/add/save mà không đụng
  `accounts_data.json` thật.
- Với network thật thì monkey-patch `requests.Session.get/post` để chặn và kiểm tra
  header/payload thật.
- Chạy `python -m pyflakes app/ account_manager.py change_name.py` để bắt tên chưa import.

### Trước khi commit

1. `python -m pyflakes app/ account_manager.py change_name.py`
2. `python -m py_compile app/*.py app/*/*.py account_manager.py change_name.py proxy_manager.py`
3. Xoá file tạm (`test_*_tmp.py`, `_*.py`, ảnh chụp màn hình, HTML dump chứa hồ sơ thật).
4. `git status` phải sạch trừ các file chủ ý sửa.
5. **Không** commit `accounts_data.json`, `proxy.txt`, `__pycache__/`.

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
| Thêm/nhập/xuất tài khoản | `329f7e1` | Nhập dán `email\|password\|token` hoặc file TXT |
| Đăng nhập + Parks2 handoff | `4079c14`, `4579c2c` | Không tạo passkey |
| Parse hồ sơ từ mypage | `7f173c5`, `7c7d171` | Fallback sang edit form |
| Sửa 2 trường tên Kanji | `c0d1bdc` | Không sửa ngày sinh (đã gỡ) |
| Đổi tên qua form | `e65bc6f` | Regex trên HTML |
| Lọc/tìm kiếm, context menu, export | `329f7e1` | |
| Tab Chiến dịch | `86dcac5` | CRUD thủ công |
| Context menu theo vùng chọn + confirm khi xóa | xem log | Kiểm tra/Copy/Xóa áp dụng cho **mọi** dòng đang chọn |
| Fill tiến trình trong ô Email + kiểm tra đa luồng | xem log | `EmailProgressDelegate` + `PROGRESS_ROLE`; `BatchCheckWorker` dùng `ThreadPoolExecutor`, số luồng cấu hình được (mặc định 5) |
| Panel nhật ký mặc định đóng, nút mở/đóng + Xóa log | xem log | `log_btn` checkable trên toolbar, `set_log_panel_visible()`, `clear_log()` |
| Trạng thái + lọc + cảnh báo chiến dịch | xem git log | Tính từ ngày, không nhập tay |
| Đăng ký thủ công + ghi nhận tài khoản | xem git log | Mở link + clipboard, người dùng tự submit |
| Proxy cho mọi request | `6ccd2d3` | + tab Cấu hình, kiểm tra proxy |
| env_info đúng schema của site | xem git log | `{mobile, platform}` — mục 5.4 |
| Thêm bước `v3/login/init` | xem git log | cấp cookie challenge cho handoff |
| `describe_login_error()` thay cho `result=="OK"` | xem git log | hết báo "thành công" giả |
| Tách đúng `email\|password\|token` + migrate | xem git log | 422 tài khoản từng lưu mật khẩu sai |
| Màu cột Status | `10d8598` | Sửa bug so chuỗi không dấu |
| Nút compact tab Nhập | `20d5914` | 4 nút một hàng |
| Chủ đề sáng/tối, cỡ chữ | `717533c` | QSettings |
| Tách MVC + DI toàn dự án | `662b2a6`…`c08bbd9` | `app/{config,domain,infrastructure,services,ui,container}`; `account_manager.py` còn 24 dòng |
| Stylesheet ra khỏi view | `c08bbd9` | `app/ui/styles.py::build_stylesheet` + `read_appearance` |
| Đổi tên chạy đủ 2 bước confirm/execute | `54369ee` | `BandaiNameClient.change_profile`; CLI cũ chỉ POST bước 1 nên không bao giờ đổi |

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
   Đã kiểm chứng 2026-10-25: lỗi "không đọc được hồ sơ" **không** phải do thiếu
   trình duyệt. Nguyên nhân thật là mật khẩu lưu sai dạng `email|password|token`,
   `env_info` sai schema, và code chỉ tin `result == "OK"`. Sau khi sửa, requests
   thuần lấy đủ 16 trường hồ sơ. Đừng quay lại hướng browser automation.
2. Không random `CLIENT_ID`, không bỏ qua `redirect_uri`.
3. Không commit secret (`accounts_data.json`, `proxy.txt`).
4. Mọi network call phải qua `new_session()` để còn dùng được proxy.
5. Mọi network call trên UI phải bọc trong `QThread`.
6. Style widget tĩnh phải khai báo trong `apply_styles()` qua `objectName`.
7. `USER_AGENT` là nguồn duy nhất cho header HTTP. `ENV_INFO` là nguồn duy nhất cho
   trường `env_info` và phải giữ đúng dạng `{mobile, platform}` (mục 5.4).
8. Chỉ sửa `last_name_kanji` / `first_name_kanji` qua `AccountDetailsDialog`.
9. Không viết automation tự điền form và submit đăng ký hàng loạt vào trang 抽選.
   Đã trình bày với người dùng và được xác nhận giữ nguyên quan điểm này. Phần được
   phép là trợ lý *mở link + chép thông tin cho một tài khoản*, người dùng tự dán và
   tự bấm submit. Đừng mở rộng `open_campaign_with_account()` thành vòng lặp nhiều tài khoản.
10. `signup_copy_password` mặc định **tắt**. Chỉ bật khi người dùng chủ động tick.
11. Giữ nguyên phân lớp MVC + DI: `app/domain` là hàm thuần (không import PySide6,
    `requests`, `QSettings`); network/dĩa/settings chỉ ở `app/infrastructure`; UI chỉ nhận
    object từ `build_container()` — không `import requests`, không `QSettings(...)`, không
    `AccountRepository()` ở trong view. Thêm tính năng mới thì thêm service/adapter rồi
    nối ở container, đừng viết logic vào `main_window.py`.
