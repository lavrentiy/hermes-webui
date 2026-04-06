# Hermes Web UI: Fork Roadmap

> Forked from nesquena/hermes-webui at v0.36.2
> Goal: cleaner, less vibecoded UI without breaking functionality.
> Running on: luna-vps port 8787

---

## Fork Changes (Completed)

### UI Cleanup — Session 1 (Apr 6, 2026)

| Change | Files |
|--------|-------|
| Replace orange gradient "H" logo + h1 with box-drawing ASCII art HERMES | index.html, style.css |
| Replace all emoji nav icons (💬📅🧩🧠📁✅) with consistent thin-stroke SVGs | index.html, style.css |
| Replace 🦉 empty-state mascot with clean SVG chat bubble | index.html |
| Strip emoji prefixes from suggestion pills (📁📋🗺) | index.html |
| Strip emoji from sidebar bottom buttons (↓ Transcript, ❬/❭ JSON, ↑ Import) | index.html |
| Replace workspace folder emoji with SVG | index.html |
| Replace topbar gear/clear/files emoji with SVGs | index.html |
| Change chip border-radius from pill (999px) to rectangular (6px) | style.css |
| Clean up sm-btn: no background, uppercase text, 6px radius | style.css |
| Clean up suggestion pills: no background, 7px radius | style.css |
| Remove Mac-only ⌘K hint from New conversation button | index.html |
| Fix double border between sidebar header and nav strip | style.css |
| Merge header + nav into one unified zone, align border with topbar | index.html, style.css |
| Lock topbar and sidebar-header to same height (86px) | style.css |
| Expand header to 86px with breathing room between logo and nav icons | style.css |
| Topbar stats row: tokens in/out, estimated cost, workspace path, session date | index.html, style.css, ui.js, sessions.js |
| Mobile fixes: topbar 54px, hide stats row, shrink sidebar header on mobile | style.css |
| Fix new conversation button broken by ws variable name conflict | ui.js |

---

## Up Next

### UI Cleanup — Round 2
- [ ] Session list items — the action icons (pin/archive/delete) feel clunky
- [ ] Settings panel — needs the same SVG/pill cleanup treatment
- [ ] Approval card — button styles inconsistent with the rest
- [ ] Right panel (file browser) header — still has some rough edges
- [ ] Consider darker/more neutral color palette option (less blue-purple)

### Features
- [ ] Keep in sync with upstream (pull upstream commits regularly)
- [ ] Token cost display accuracy — verify rates per model are up to date
- [ ] Topbar stats: add context window usage % (already tracked in activity bar)

---

## Upstream Sync

Last synced: v0.36.2 (Apr 5, 2026)

To pull upstream changes:
```
cd /home/laurent/lavrentiy-hermes-webui
git remote add upstream https://github.com/nesquena/hermes-webui.git
git fetch upstream
git merge upstream/master
```

To update running instance after push:
```
cd /home/laurent/hermes-webui && git pull
```
