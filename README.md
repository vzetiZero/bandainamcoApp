# NAMCO Account Manager

Windows desktop app (Electron + Next.js UI, Python backend) to manage many BANDAI NAMCO ID /
NAMCO Parks accounts: check logins, read profiles, rename, track 抽選 campaigns and run sign-ups
in a real Chrome window per account.

## Features

- **Accounts**: import `email|password|token` lines, search/filter, status badges, per-account
  progress, batch login checks (1–10 parallel), profile fields, kanji rename, delete, export.
- **Account groups**: create group labels, filter the list by group, move the selected accounts
  into a group (or out of it), and pick a group in the "add accounts" box so pasted accounts land
  in it right away; the campaign run panel can pick a group in one click. Groups live with the
  accounts of that machine (`accounts_data.json` + `web_settings.json`).
- **Campaigns**: one row per campaign with `open`/`close` dates; status and countdown are derived,
  not typed. Registrations per campaign, plus a run panel.
- **Browser automation**: one Chrome per account (own profile, own proxy, own debug port), driven
  by a JSON *recipe*; it can walk to the payment page and stop (`pause`) or press submit.
  `chrome-devtools-mcp` attaches to the same window for page discovery and snapshots.
- **Order/payment profile**: address, phone and card entered in the UI, DPAPI-encrypted on disk;
  the API only ever returns `**** **** **** 1234`.
- **Proxy**: every HTTP request goes through `proxy.txt` (per-request rotation or one proxy per
  account); IP blocks are detected and the proxy rests for 30 minutes.

## Quick start

```powershell
start.bat                 # = python start.py
```

`start.py` installs missing dependencies, rebuilds the static UI when sources changed,
**frees the API port (kills whatever still listens on it, then rebinds)**, starts the Python API,
waits for `/api/health` and opens the Electron window.

```powershell
python start.py --rebuild          # rebuild web/out first
python start.py --port 8800        # different API port (still kills the stale listener)
python start.py --no-pick-port     # fail instead of moving to the next free port
python start.py --dev-ui           # Next dev on :3000 + Electron (hot reload)
python start.py --web              # API only
```

Requirements: Python 3.10+, Node.js LTS, Google Chrome. `npm.ps1` is blocked by the default
PowerShell policy — call `npm.cmd` (or `Set-ExecutionPolicy -Scope Process Bypass` first).
`install.bat` performs the same setup including the Electron binary and a first UI build.

## Runtime shape

- **Electron** (`desktop/`) renders the exported Next.js build from `web/out` over an internal
  `app://` protocol — the UI needs no HTTP server, so there is no second port to collide with.
  It receives `API_BASE` at runtime, so changing the API port needs no rebuild.
- **Python API** (`server.py` → `api/`) owns all logic on `127.0.0.1:8787`.
- Closing the Electron window stops the API; `Ctrl+C` stops both.

## Where things live

```
start.py / start.bat          launcher: deps → build UI → free port → API → Electron
server.py                     FastAPI entry (port handling, --kill-port/--pick-port)
api/app.py                    REST routes + CORS (no business logic)
api/state.py                  wiring, LogBuffer, JobRegistry, background jobs
app/domain/                   pure rules: accounts, campaigns, checkout, browser_recipe, names, ip/login rules
app/infrastructure/           adapters: bandai_auth, bandai_name, bandai_profile, account_repository,
                              file_settings, checkout_store, web, browser/ (session, runner, mcp, discovery)
app/services/                 account_service, campaign_service, browser_campaign_service
web/                          Next.js 14 + theme-ui UI (static export)
desktop/                      Electron shell (app:// protocol, API_BASE injection)
recipes/*.json                browser step recipes (data, not code)
tools/port_tools.py           check/kill a TCP port before binding
browser_campaign.py           CLI: --discover / --check / --run / --all
change_name.py                CLI: rename a profile
```

## API

`GET /api/health`, `/api/accounts`, `/api/campaigns`, `/api/settings`, `/api/proxy`,
`/api/checkout`, `/api/logs?after=<seq>`, `/api/jobs[/{id}]`, `/api/browser/sessions`.
`POST /api/proxy/text` writes a pasted proxy list straight into the proxy file in use
(`replace: false` appends and skips duplicates; malformed lines are reported with credentials
masked) and reloads the proxy manager.
Account groups: `GET/POST /api/accounts/groups`, `DELETE /api/accounts/groups/{name}`,
`POST /api/accounts/group`, and `GET /api/accounts?group=<name|__none__>`.
Long tasks (`/api/accounts/check`, `/api/browser/run`, `/api/proxy/check`, `/api/browser/discover`)
return a job id; the UI polls `/api/jobs/{id}`. Docs at `/docs`.

## Recipe

`recipes/parks2_campaign.json` holds the steps (`goto`, `fill`, `select`, `check`, `click`,
`press`, `wait_text`, `wait_selector`, `sleep`, `screenshot`, `dismiss`, `pause`, `submit`),
flags (`when`, `only_if_empty`, `optional`, `requires_submit`) and the phrases meaning
*registered / already / closed / error*. Template variables: `{email}`, `{password}`, `{zip}`,
`{pref}`, `{city}`, `{street}`, `{tel}`, `{card_number}`, …

The shipped recipe is real for the 熊本店 OP-18 lottery: Parks2 login → item page → optional
cart clear → dismiss the 本人確認書類 popup → pick the slot → add to cart → cart →
`ご注文情報入力` → fill the address from the account profile → then either **pause** (window stays
open for you) or, with *Tự bấm gửi* on, click 入力内容を確認する → 注文する and wait for `ご注文完了`.
A proxy that gets IP-blocked is marked resting and the next one is tried automatically.

```powershell
python browser_campaign.py --check
python browser_campaign.py --run --email you@example.com --campaign "<name>" --hold-open
python browser_campaign.py --all --campaign "<name>" --slot 159016_1121_1330_1 --submit --clear-cart
python browser_campaign.py --run --email you@example.com --url "<item url>" --no-proxy
```

Edit the recipe from **Settings → Recipe (JSON)** in the app (the API validates before writing) or
by hand; **Soi trang (MCP)** dumps `page.html`, `elements.json` and `a11y_snapshot.txt` when a site
changes.

## Data files

| File | Content | Git |
|---|---|---|
| `accounts_data.json` | accounts (email, password, status, profile) | ignored |
| `web_settings.json` | per-machine UI/API settings (proxy, browser, workers, campaign sign-ups) | ignored |
| `campaigns.json` | campaign list, shared by every device (copy the folder or `git pull`) | tracked |
| `proxy.txt` | `ip:port:username:password` | ignored |
| `checkout_profile.json` | order/payment profile, DPAPI-encrypted | ignored |
| `recipes/*.json` | browser recipes | tracked |
| `browser_profiles/`, `browser_artifacts/` | Chrome profiles, screenshots and dumps | ignored |

Campaigns live in `campaigns.json` on purpose: accounts, proxies and the card profile stay
per-machine, but the campaign list travels with the project. The API re-reads the file when it
changes, so a `git pull` on a running app is picked up on the next poll. Sign-ups (which accounts
registered) stay in `web_settings.json` because they refer to that machine's accounts. Override the
location with `CAMPAIGNS_FILE`.

## Notes

- Accounts that only exist in Parks2 log in through the Parks2 form; the BNID page rejects them
  with 「メールアドレス…が間違っている」.
- Automating sign-ups for many accounts may violate NAMCO Parks' terms of service and can get
  accounts or IPs blocked — use at your own risk.

