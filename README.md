# NAMCO Account Manager

Windows desktop app for organizing BANDAI NAMCO ID / NAMCO Parks accounts.

## Features

- Add accounts manually or import `email|password` lines from a text file.
- Check account credentials and save the latest check time.
- Show profile fields, points, and membership flags in the account table after the Parks2 login handoff completes.
- Keep account input and account list in separate tabs; the activity log appears beside the account table.
- Edit only `first_name_kanji` through the profile dialog.

## Setup

Requires Python 3.10 or later on Windows.

```powershell
python -m pip install -r requirements.txt
python account_manager.py
```

You can also run `install.bat` and `start.bat`.

## Authentication notes

The app first calls the BANDAI NAMCO ID `v3/login/idpw` endpoint. The response may send the session through `v3/passkey/info` and request an approval in the browser before Parks2 grants access to `member_mypage.html`. The app reports this state and does not accept account approvals or create passkeys automatically. Profile fields are shown only when the authenticated Parks2 page is available.

## Local account data

The app writes credentials and profile data to `accounts_data.json` in plaintext. Keep this file private. It is excluded from Git by `.gitignore`; never commit it or session cookie files.
