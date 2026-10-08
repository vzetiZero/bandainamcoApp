# NAMCO Account Manager

Windows desktop app for organizing BANDAI NAMCO ID / NAMCO Parks accounts.

## Features

- Add accounts manually or import `email|password` lines from a text file.
- Track limited-time campaign windows with dates parsed for real, a derived status column, a countdown, filters, and a warning when a campaign opens within 24 hours.
- Check account credentials and save the latest check time.
- Show profile fields, points, and membership flags in the account table after the Parks2 login handoff completes.
- Keep account input and account list in separate tabs; the activity log appears beside the account table.
- Edit only `first_name_kanji` through the profile dialog.
- Send every request (login, check, name change) through proxies read from `proxy.txt`, configured in the Settings tab.

## Setup

Requires Python 3.10 or later on Windows.

```powershell
python -m pip install -r requirements.txt
python account_manager.py
```

You can also run `install.bat` and `start.bat`.

## Campaigns

The **Chiến dịch** tab is a manual tracker: one row per campaign, no sign-up automation. Enter `Mở đăng ký` and `Đóng đăng ký` as `YYYY-MM-DD HH:MM` and the app derives everything else:

- **Trạng thái** – Chưa mở / Đang mở / Đã đóng / Chưa rõ, recomputed on a 60-second timer so no manual refresh is needed.
- **Còn lại** – countdown to the next deadline, or how long it has been overdue.
- Filters for Đang mở, Sắp mở trong 24h, Chưa mở, Đã đóng, plus a name/link search box and a running count per status.
- A warning in the status bar and log when a campaign is about to open, once per campaign.
- **Export danh sách** writes the table to a pipe-separated file.

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
