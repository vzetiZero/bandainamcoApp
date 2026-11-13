# NAMCO Account Manager

Windows desktop app for organizing BANDAI NAMCO ID / NAMCO Parks accounts.

## Features

- Add accounts manually or import `email|password|token` lines from a text file — the **Import TXT** button lives inside the account input dialog (the trailing token is kept separately and is not part of the password).
- Track limited-time campaign windows with dates parsed for real, a derived status column, a countdown, filters, and a warning when a campaign opens within 24 hours.

- Show profile fields, points, and membership flags in the account table after the Parks2 login handoff completes.
- Open the account input panel from the toolbar button **Nhập tài khoản**; the account list tab comes first and the activity log starts closed beside the account table — use the **Nhật ký** toolbar button to show or hide it, and **Xóa log** inside the panel to clear it.
- A dashboard strip at the top of the account list tab shows total, active, inactive and unchecked account counts, refreshed together with the table.
- Account table extras: hide/show columns (remembered between runs), click a header to sort, status drawn as colored badges, an empty-state message when no row matches the filter, and shortcuts Ctrl+N / Ctrl+I / Ctrl+F / Del.
- The input dialog has an **Import TXT** button and accepts a dragged .txt file; both load the file into the text box, which previews how many lines will be added, skipped as duplicates, or rejected before you press Thêm.
- Right-click actions follow the selection: pick several rows (drag, Ctrl+click, Shift+click) and **Kiểm tra**, **Copy email** and **Xóa** apply to every selected account — the menu labels show the count. Deleting always asks for confirmation and lists the emails it is about to remove.
- While accounts are being checked, each row shows its own progress: the Email cell fills with the accent colour up to that account's percentage and prints the number in the corner, so with several accounts running at once you can see which one is at which stage. The bar clears as soon as the result is written.
- Batch checks run concurrently. The Settings tab has a **Kiểm tra đồng thời** spinner for the number of parallel threads (1–10, default **5**, remembered between runs).
- Edit the two Kanji name fields (`last_name_kanji`, `first_name_kanji`) in the profile dialog; the rest of the profile is read-only.
- Send every request (login, check, name change) through proxies read from `proxy.txt`, configured in the Settings tab.
- Run campaign sign-ups in a real browser: every account gets **its own Chrome window** (own profile, own proxy, own debug port), the app replays a JSON *recipe* of clicks/fills, and it can press the final submit button itself. `chrome-devtools-mcp` is attached to the same window to dump the accessibility snapshot and page elements when a site changes.

## Setup

Two processes: the Python API (all logic) and the Next.js UI.

```powershell
python -m pip install -r requirements.txt          # requests, PySide6, playwright, fastapi, uvicorn
cmd /c "npm.cmd i -g chrome-devtools-mcp"          # MCP server for page discovery

python server.py --no-browser                       # API  → http://127.0.0.1:8787  (docs: /docs)
cd web
npm install
npm run dev                                         # UI   → http://localhost:3000
```

Or double-click `start_api.bat` and `start_web.bat`. Requires Python 3.10+, Node.js LTS and
Google Chrome.

`npm.ps1` is blocked by the default PowerShell execution policy, so call `npm.cmd` (or run
`Set-ExecutionPolicy -Scope Process Bypass` first). The legacy PySide6 desktop app still runs
with `python account_manager.py` / `start.bat`.

Set `NEXT_PUBLIC_API` if the API is not on `http://127.0.0.1:8787`.

## Architecture

```
Browser ──HTTP/JSON──> api/ (FastAPI)  ──> app/services ──> app/domain
                          │                     └─> adapters: requests (Bandai auth/name),
                          │                        Playwright + chrome-devtools-mcp,
                          │                        AccountRepository, CheckoutStore
                          └─ JobRegistry (background threads) + LogBuffer
```

Long tasks (checking accounts, running a campaign in Chrome, probing proxies, page discovery)
are jobs: `POST` returns a job id and the UI polls `/api/jobs/{id}`. Logs stream through
`/api/logs?after=<seq>`.

Pages: `/` overview, `/accounts`, `/campaigns`, `/settings` (proxy, recipe editor, Chrome
options, order/payment profile). The API never returns passwords, card numbers or CVVs;
`GET /api/checkout` shows `**** **** **** 1234`, and leaving the card fields blank on save keeps
the stored values.

## Project structure

The code is layered MVC-style, and every collaborator is injected from one composition root:

```
account_manager.py            entry point only (QApplication + main window)
app/config.py                 URLs, CLIENT_ID, USER_AGENT, ENV_INFO, paths
app/domain/                   pure rules, no Qt and no network
    accounts.py               email|password|token lines, statuses, filters, counts
    campaigns.py              campaign status + countdown from dates
    login_rules.py            describe_login_error() — the only login success test
    names.py                  NameForm, kanji_overrides()
app/infrastructure/           adapters: the only place that touches network/disk/QSettings
    bandai_auth.py            login → Parks2 handoff → member profile
    bandai_profile.py         handoff + mypage/edit-page parsing
    bandai_name.py            profile edit form (confirm + execute)
    account_repository.py     accounts_data.json, with the legacy-password migration
    settings_store.py         QSettings wrapper
    checkout_store.py         order/payment profile, DPAPI-encrypted on disk
    web.py                    shared headers + cookie handling
    browser/                  per-account Chrome + DevTools MCP
        browser_session.py    launch Chrome (profile, debug port, proxy), goto/screenshot
        campaign_runner.py    replay a recipe: login → campaign page → submit → classify
        mcp_client.py         stdio JSON-RPC client for chrome-devtools-mcp
        discovery.py          dump html/text/elements/a11y snapshot for recipe authoring
app/services/                 use cases the view calls
    account_service.py        add/delete/status/profile/export
    campaign_service.py       campaign CRUD + registration records
    browser_campaign_service.py  preflight + run the recipe for many accounts
app/ui/                       view, dialogs, QThread workers, delegate, table spec, stylesheet
app/container.py              build_container() — wires the real collaborators
recipes/                      JSON recipes of browser steps (data, not code)
browser_campaign.py           CLI: --discover / --check / --run / --all
```

`AccountManager(container=...)` is how you hand the app a fake: pass a
`session_factory` that returns a stub session and a temp `data_file`, and the whole
login, profile and name-change flow runs offline.

## Renaming from the command line

```powershell
python change_name.py --email user@example.com --password secret --last-name 山田 --first-name 太郎
```

Blank fields keep their current values; kana and nickname are only overwritten when you
pass their flags. The client posts the site's `request=confirm` page, then the
`request=execute` confirmation, and re-reads the profile page to prove the new names stuck.

## Campaigns

The **Chiến dịch** tab is a manual tracker: one row per campaign, no sign-up automation. Enter `Mở đăng ký` and `Đóng đăng ký` as `YYYY-MM-DD HH:MM` and the app derives everything else:

- **Trạng thái** – Chưa mở / Đang mở / Đã đóng / Chưa rõ, recomputed on a 60-second timer so no manual refresh is needed.
- **Còn lại** – countdown to the next deadline, or how long it has been overdue.
- Filters for Đang mở, Sắp mở trong 24h, Chưa mở, Đã đóng, plus a name/link search box and a running count per status.
- A warning in the status bar and log when a campaign is about to open, once per campaign.
- **Export danh sách** writes the table to a pipe-separated file.
- **Đăng ký thủ công theo chiến dịch** — pick a campaign row and an account, then *Mở trang chiến dịch* opens the official link in your browser and copies the account details to the clipboard. Paste with Ctrl+V and press submit yourself. *Ghi nhận đã đăng ký* then stores which account was registered for which campaign, shown in the *Đã đăng ký* column.

The app never fills or submits the sign-up form itself in this manual panel — that step stays manual.

Dates are validated when saving, and closing must come after opening. Leave both blank if the schedule is unknown. Campaigns already stored with free-form dates keep working and simply show as Chưa rõ until edited.

## Campaign automation with Chrome

The **Chạy tự động bằng Chrome** group in the campaign tab drives the sign-up page with a real browser:

- **One Chrome per account** — `browser_profiles/<email>` (cookies and sessions never mix), a free
  `--remote-debugging-port`, and the proxy from `proxy.txt` handed out by the same proxy manager the
  request flow uses. Accounts run sequentially by default; you can raise the parallel count to 3.
- **Recipe driven** — `recipes/parks2_campaign.json` lists the steps (`goto`, `fill`, `select`,
  `check`, `click`, `press`, `wait_text`, `wait_selector`, `sleep`, `screenshot`, `submit`) and the
  phrases that mean *registered / already registered / closed / error*. When the site changes you edit
  JSON, not Python.
- **Submit gating** — every step can be marked `requires_submit`, and the final `submit` step only
  runs when *Tự bấm gửi* is on. The run always asks for confirmation first and lists how many
  accounts it will submit for.
- **Evidence** — a screenshot per account plus console/a11y dumps land in `browser_artifacts/`
  (git-ignored). Successful runs are recorded in the campaign's *Đã đăng ký* column.
- **MCP discovery** — **Soi trang (MCP)** opens the selected account's Chrome, walks to the campaign
  link and saves `page.html`, `text.txt`, `elements.json` (with suggested selectors) and
  `a11y_snapshot.txt` from `chrome-devtools-mcp`, which is what you need to fill in the recipe.

The shipped recipe is **real** for the 熊本店 OP-18 lottery: it logs in through the Parks2 form,
clears the 本人確認書類 popup, picks the slot, adds the item to the cart and walks to
`ご注文情報入力`, where it **pauses and leaves the Chrome window open** for you.

```powershell
python browser_campaign.py --check
python browser_campaign.py --run --email you@example.com --campaign "<name>" --hold-open
python browser_campaign.py --run --emails a@x.com,b@x.com --url "<item url>" --hold-open
python browser_campaign.py --all --campaign "<name>" --slot 159016_1121_1330_1 --hold-open
```

- `--hold-open` keeps the Python process alive so the paused Chrome windows stay open
  (Ctrl+C closes them); without it the window dies with the process.
- `--slot` overrides the 種類 value (`159016_1121_1100_1` = 11/21 11:00).
- `--submit` only matters if the recipe uses the `submit` action instead of `pause`.
- Logins for these accounts go through the Parks2 form, **not** BNID: the BNID page rejects
  Parks2-only accounts with 「メールアドレス…が間違っている」.

## Order and payment details (entered in the UI, nothing hard-coded)

**Cấu hình → Thông tin đặt hàng & thanh toán** opens a form for what the automation should
type into ご注文情報入力 and the payment step:

| Group | Fields | Recipe variables |
|---|---|---|
| Recipient | 姓 / 名 / セイ / メイ | `{l_name}` `{f_name}` `{l_kana}` `{f_kana}` |
| Address | 郵便番号 / 都道府県 / 市区町村 / 丁目・番地 / ビル名 | `{zip}` `{pref}` `{city}` `{street}` `{building}` |
| Address | 「ビル・マンション名・部屋番号なし」 checkbox | `{building_none}` |
| Contact | 携帯電話番号 | `{tel}` |
| Card | name on card / number / MM/YY / CVV | `{card_holder}` `{card_number}` `{card_exp}` `{card_exp_month}` `{card_exp_year}` `{card_cvv}` |

- **Nothing is hard-coded**: recipes reference the variables above, so changing a value in the
  UI changes every future run. Recipes can also drop a step with `"when": "{zip}"` and protect
  member data with `"only_if_empty": true` (the site warns that editing ご依頼主情報 also edits
  the member profile).
- **Storage**: `checkout_profile.json`, git-ignored, each value encrypted with the Windows DPAPI
  for the current user, file ACL restricted with `icacls`. If DPAPI is unavailable the store
  still saves but flags `encrypted: false` and the UI shows “CHƯA mã hoá”.
- **Logs never contain card data**: only `**** **** **** 1234`, brand and expiry are printed.
- The profile is **shared by all accounts**; leave a field blank to keep whatever the member
  profile already has on the site.
- Card steps only run when a card is configured — the 熊本店 lottery needs none (paid in store).

Automating sign-ups for many accounts may violate NAMCO Parks' terms of service and can get accounts
or IPs blocked. Use it at your own risk; the manual panel above still works exactly as before.

## Authentication flow

The app calls BANDAI NAMCO ID `v3/login/idpw`, then `v3/passkey/info`. When that response includes the `btn-next` continuation URL (the site's "later" option), the app follows it to finish the Parks2 callback without creating a passkey. It then reads `member_mypage.html`, with the member edit page used only to fill fields absent from the profile summary. No browser automation is needed for this flow.

## Proxy

The **Cấu hình** (Settings) tab reads proxies from `proxy.txt`, one per line:

```
ip:port:username:pass
```

`ip:port`, `user:pass@ip:port` and `http://ip:port:username:pass` are accepted too; lines starting with `#` are ignored. The tab lists the parsed proxies, lets you pick another file, reload it, and check each proxy against the login page (results appear in the table's status column).

Choose how proxies are handed out:

- **Luân phiên theo từng request** – every HTTP request rotates to the next proxy.
- **Mỗi phiên dùng 1 proxy** – each session (each account check or name change) keeps one proxy.

Uncheck the box to send requests directly, as before. The choice, file path, and mode are remembered between runs. `proxy.txt` holds credentials, so it is ignored by Git; the app creates it with a format template when you click *Mở file proxy*. SOCKS proxies additionally need `pip install requests[socks]`.

## Local account data

The app writes credentials and profile data to `accounts_data.json` in plaintext. Keep this file private. It is excluded from Git by `.gitignore`; never commit it or session cookie files.

## GitHub update workflow

After every project update or modification, validate the changed files, commit the intended project files, and push the update to the configured GitHub remote. Keep `accounts_data.json`, session cookies, and other secrets out of commits. Report the commit and push result after each update.
