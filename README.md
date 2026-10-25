# NAMCO Account Manager

Windows desktop app for organizing BANDAI NAMCO ID / NAMCO Parks accounts.

## Features

- Add accounts manually or import `email|password|token` lines from a text file (the trailing token is kept separately and is not part of the password).
- Track limited-time campaign windows with dates parsed for real, a derived status column, a countdown, filters, and a warning when a campaign opens within 24 hours.
- Check account credentials against the live login flow and report the server's real reason when a login is rejected.
- Show profile fields, points, and membership flags in the account table after the Parks2 login handoff completes.
- Open the account input panel from the toolbar button **Nhập tài khoản** (same row as Import TXT); the account list tab comes first and the activity log appears beside the account table.
- A dashboard strip at the top of the account list tab shows total, active, inactive and unchecked account counts, refreshed together with the table.
- Account table extras: hide/show columns (remembered between runs), click a header to sort, status drawn as colored badges, an empty-state message when no row matches the filter, and shortcuts Ctrl+N / Ctrl+I / Ctrl+F / Del.
- The input dialog accepts a dragged .txt file and previews how many lines will be added, skipped as duplicates, or rejected before you press Thêm.
- Edit the two Kanji name fields (`last_name_kanji`, `first_name_kanji`) in the profile dialog; the rest of the profile is read-only.
- Send every request (login, check, name change) through proxies read from `proxy.txt`, configured in the Settings tab.

## Setup

Requires Python 3.10 or later on Windows.

```powershell
python -m pip install -r requirements.txt
python account_manager.py
```

You can also run `install.bat` and `start.bat`.

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
    web.py                    shared headers + cookie handling
app/services/                 use cases the view calls
    account_service.py        add/delete/status/profile/export
    campaign_service.py       campaign CRUD + registration records
app/ui/                       view, dialogs, QThread workers, delegate, table spec, stylesheet
app/container.py              build_container() — wires the real collaborators
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

The app never fills or submits the sign-up form itself — that step stays manual.

Dates are validated when saving, and closing must come after opening. Leave both blank if the schedule is unknown. Campaigns already stored with free-form dates keep working and simply show as Chưa rõ until edited.

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
