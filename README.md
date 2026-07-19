# Projecter — Personal App Suite

A collection of single-file HTML apps, all opened from one `index.html` launcher (Command Deck). No build step, no backend — each app is one self-contained file.

## Folder structure

```
garudanexus.com/
├── projecter/                    ← this folder
│   ├── index.html                 (Command Deck — swipeable launcher)
│   ├── garuda_power_tracker.html
│   ├── vault.html
│   ├── hisab-khata.html
│   └── README.md                  (this file)
└── trading-bot/                  ← sibling folder, separate project
    └── dashboard.html             (Algo Backtesting Scanner)
```

`index.html` links to `dashboard.html` using a relative path one folder up (`../trading-bot/dashboard.html`) — both folders must stay siblings under the same repo root for that link to work.

## The apps

### 1. 🔱 Command Deck (`index.html`)
The launcher. Swipe left/right to move between apps — each one loads and runs fully on its own page inside the swipe. Order: small apps first, the multi-file Backtesting Scanner last.

### 2. 🦅 Garuda Tracker (`garuda_power_tracker.html`)
Build-progress tracker for trading system projects — engines/modules, files, notes. Supports multiple projects, custom modules, file upload (with `.zip` auto-extract), and folder-placement reminders.

### 3. 🔐 Vault (`vault.html`)
Password-locked credential locker + format picker. Works entirely offline via manual export/import of encrypted `.txt` files — no ongoing storage needed.

### 4. 📒 श्री हिसाब बही (`hisab-khata.html`)
Khata/ledger app — party udhaar (who owes whom), daily income/expense wallet, dashboard summary. Has a built-in **Backup** button (top-right) to export/restore all data as a `.json` file, plus an automatic reminder if no backup has been taken in 7+ days.

### 5. 📊 Backtesting Scanner (`../trading-bot/dashboard.html`)
Separate, larger project (~15 files: `api_server.py`, `backtest_core.py`, `broker_adapter.py`, etc.) — an interactive strategy backtesting dashboard. Lives in its own `trading-bot` folder; only `dashboard.html` is opened from the launcher.

## How data storage works (important)

Garuda Tracker and Hisab Khata both use a **storage shim**: they try Claude's `window.storage` API first (only present inside Claude's own runtime), and automatically fall back to the browser's `localStorage` when opened anywhere else — GitHub Pages, your own server, or a downloaded file. This means data saves correctly in both places, but:

- **localStorage is per-browser, per-device.** It does not sync across phones and is not a cloud backup.
- **If the browser data is cleared, or the phone is lost/reset, unsaved data is gone.** For Hisab Khata specifically, always use the in-app **Backup** button regularly (download the `.json` file and email/WhatsApp it to yourself) — this is the only real recovery path if the phone is lost.
- Vault does not need this shim — it works by manual encrypted file export/import, so there is nothing to lose as long as you keep your exported `.txt` file.

## Hosting

Any static file host works — GitHub Pages, a DigitalOcean folder served via `python3 -m http.server`, or Vercel. `file://` (opening the HTML directly from your phone's file manager) will **block the native file-picker** used for uploads in Garuda Tracker — always host over `http://` or `https://` for full functionality.

## Adding a new app to the launcher

1. Drop the new single-file `.html` app into this `projecter` folder (or wherever it lives).
2. In `index.html`, add one more `<div class="page" data-name="...">` block with an `<iframe src="...">` pointing to it, in the `.rail` container.
3. Push — it appears as a new swipeable page automatically.
