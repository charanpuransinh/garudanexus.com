# Garuda Power — Systems Tracker

A single-file, mobile-first HTML app to track build progress across trading system projects — engines/modules, files, and notes — with zero backend required.

Live data is stored via the built-in `window.storage` API (works only when opened through Claude, otherwise falls back gracefully) — no server, no database setup needed to get started.

## What this does

- Tracks build progress for **any number of projects** (not just Garuda Power) — each project gets its own isolated save data
- Each project is organized into **categories → engines/modules → files**
- Per file: mark done/pending, confirm correct target folder, delete
- Per engine/module: set expected file count, add notes, see live completion %
- Overall dashboard: master completion ring, per-category progress bars, files/modules/pending stats

## Key features

| Feature | Details |
|---|---|
| Multi-project | Switch projects from the top bar, or create a new one anytime |
| Custom modules | Any project can have modules/engines added on the fly — not fixed to the 17-engine Garuda Power template |
| File upload | Native file picker per module; selecting a file auto-marks it done |
| ZIP extract | Upload a `.zip` and every file inside is auto-listed and marked done (via JSZip, loaded from CDN) |
| Folder guidance | Each module shows its suggested folder path convention (e.g. `garuda-power/core-trading-pipeline/data-engine/`) and a tap-to-confirm tag per file |
| Autosave | Every change (checkbox, note, file add) saves immediately |

## What this does NOT do

- **Does not store actual file content.** Only file *names* and status are tracked — this is a checklist/progress tool, not a file/code storage system. ZIP extraction reads the *list* of files inside an archive, not their contents.
- **Cannot open your phone's file picker inside a `file://` page.** Android/Chrome blocks file pickers on pages opened directly from local storage for security reasons. Host it over `http://` or `https://` (see below) for uploads to work.
- **Cannot run terminal commands on your device** (e.g. Termux, git push) — browsers cannot execute shell commands for security reasons. Any automation like zipping a folder or pushing to GitHub has to be run manually from your terminal.

## Hosting (required for file upload to work properly)

Pick one:

**Quick local test (DigitalOcean or any server):**
```bash
python3 -m http.server 8080
```
Then open `http://<server-ip>:8080/garuda_power_tracker.html` from your phone browser.

**Permanent (Vercel, same pattern as Trishul Pro):**
Push this single file to a repo and deploy as a static site — no build step needed.

## Tech notes

- Single self-contained `.html` file — HTML, CSS, and JS all in one place
- External dependencies loaded from CDN only: Google Fonts, JSZip (`cdnjs.cloudflare.com`) — no extra files to manage or push
- No `localStorage`/`sessionStorage` used (unreliable in sandboxed previews) — persistence goes through `window.storage`

## Folder convention used by the tracker

```
<project-slug>/<category-slug>/<module-slug>/
```
Example for Garuda Power's Data Engine:
```
garuda-power/core-trading-pipeline/data-engine/
```
This is a **suggested convention shown in the UI**, not something the tracker can enforce or auto-move files into — that would require filesystem access no browser grants to a webpage.

## Zipping a project folder before upload (Termux example)

```bash
zip -r project.zip ./garuda-power/
```
Upload `project.zip` through the tracker's upload button — every file inside gets listed and marked done automatically.
