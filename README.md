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

## Authentication flow

The app calls BANDAI NAMCO ID `v3/login/idpw`, then `v3/passkey/info`. When that response includes the `btn-next` continuation URL (the site's "later" option), the app follows it to finish the Parks2 callback without creating a passkey. It then reads `member_mypage.html`, with the member edit page used only to fill fields absent from the profile summary. No browser automation is needed for this flow.

## Local account data

The app writes credentials and profile data to `accounts_data.json` in plaintext. Keep this file private. It is excluded from Git by `.gitignore`; never commit it or session cookie files.

## GitHub update workflow

After every project update or modification, validate the changed files, commit the intended project files, and push the update to the configured GitHub remote. Keep `accounts_data.json`, session cookies, and other secrets out of commits. Report the commit and push result after each update.
