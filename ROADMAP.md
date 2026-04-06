# deploymedaddy — Product Roadmap

> Last updated: April 6, 2026
> Current version: v0.36.2 | 440 tests
> Previous name: Hermes Web UI

---

## What this is

A browser-based interface for running AI agents against your own server, files, and tools.
Today it runs Hermes. The roadmap below adds pi and eventually OpenHands as additional
agents you can run from the same UI, with the same sessions, same workspace, same history.

The goal is not "support every agent". The goal is: if you are already using Hermes
day-to-day, this is the best possible front-end for it — and it can also run pi when
you want pi's strengths (OAuth auth, branching, minimal footprint), and OpenHands when
you want a full sandboxed coding run.

---

## Competitive landscape

| Tool | What it is | Their strength | Our angle |
|------|-----------|----------------|-----------|
| OpenHands | Browser UI, multi-agent, Docker sandbox | Most mature multi-agent UI, 35k stars | We have persistent memory, crons, skills, profiles — they don't |
| Cursor/Windsurf | IDE + agent | Tight editor integration | We're server-side, browser-only, no editor required |
| Claude.ai | Polished cloud chat | UX quality bar | We run locally, your files, your models, your keys |
| pi (coding agent) | Minimal CLI + RPC protocol | Extensible, subscription auth, branching | We surface pi's output in a proper UI with history |

Our real differentiator: Hermes is a platform (memory, crons, skills, profiles, cross-platform
messaging). deploymedaddy is the browser face of that platform. OpenHands can run an agent
on your files. It can't remember what you told it last week or run scheduled tasks overnight.

---

## Current state (v0.36.2)

- Hermes chat, streaming, tool cards, approval flow — all working
- File browser, workspace management, git badge
- Cron / skills / memory panels — full CRUD
- Session management: projects, archive, pin, search, tags
- Multi-profile support, model switching, multi-provider
- Password auth, 6 themes, mobile layout, Docker, voice input
- LLM-generated session titles (opt-in setting, v0.36.2)
- Topbar stats row: tokens in/out, estimated cost, workspace path, session date
- Sidebar header: logo above icons, full-width nav spread, 86px column layout
- 440 automated tests

Known architectural problems (from April 2026 review):
- Session storage is flat JSON files with O(n) index rebuild on every save
- Routes are one 1365-line if-chain
- os.environ used for thread isolation (blocks true concurrency)
- Password hashing is SHA-256 with static salt (weak)
- No CSRF protection
- Hand-rolled markdown renderer (fragile)
- No static asset caching

---

## Priority tiers

### Tier 0 — Fix the foundation (before adding anything new)

These are architectural problems that will get worse every sprint we ignore them.
None are user-visible individually, but together they're what separates a prototype
from a real product.

**A. SQLite session storage**
Replace flat JSON files + _index.json with a proper SQLite database.
- sessions table: id, title, agent, model, workspace, profile, created_at, updated_at, pinned, archived, project_id
- messages table: id, session_id, role, content, timestamp
- tool_calls table: id, session_id, message_id, name, args_json, result_json
- Atomic writes. O(1) lookups. No more index rebuilds on every save.
- The `agent` column is included now so pi/OpenHands sessions slot in later with no schema change.
- The existing CLI bridge (state.db reads) becomes a simple JOIN instead of a separate code path.

**B. Proper router**
Replace the 1365-line if-chain in routes.py with a dispatch table.
- Dict mapping (method, path) -> handler function
- Each domain (sessions, files, workspace, crons, skills, memory, auth) gets its own handler module
- routes.py becomes a registration file, ~50 lines

**C. Password hashing**
Replace SHA-256 + static salt with PBKDF2 (stdlib, no new deps) or bcrypt (one pip dep).
Current implementation is a dictionary attack waiting to happen if settings.json leaks.

**D. CSRF protection**
One token in a cookie, checked on every POST. One filter function, ~10 lines.
Currently any page can POST to /api/memory/write or /api/session/delete from a user's browser.

**E. Static asset caching**
Add ETags and Cache-Control: max-age to JS/CSS responses.
Currently every page load re-downloads all 7 JS files and the CSS. No cache at all.

---

### Tier 1 — Quality and daily driver polish

Things that make the existing Hermes experience meaningfully better.

**Sprint 27 — Foundation (Tier 0 items A+B)**
- SQLite migration (sessions, messages, tool_calls tables)
- Dict router replacing the if-chain
- Zero user-visible changes, all tests still pass
- Estimated: 1 sprint, mostly mechanical

**Sprint 28 — Security hardening (Tier 0 items C+D+E)**
- PBKDF2 password hashing (replaces SHA-256 + static salt)
- CSRF token on all POST endpoints
- ETag + Cache-Control on static assets
- Estimated: 1 sprint

**Sprint 29 — Markdown and rendering**
- Replace hand-rolled regex markdown with marked.js (CDN, battle-tested)
- This fixes nested lists, strikethrough, task lists, edge cases
- Bundle mermaid.js instead of CDN-pinning (removes fragile SRI hash dependency)
- Estimated: 1 sprint

**Sprint 30 — Thread safety and concurrency**
- Replace ThreadingHTTPServer with fixed-size ThreadPoolExecutor (cap at ~20 threads)
- Remove os.environ for context passing — pass workspace/session/profile as explicit args to agent
- This unblocks true concurrent sessions (two users, two agents, no serialization)
- Estimated: 1-2 sprints (touches streaming.py deeply)

---

### Tier 2 — pi integration

**Why pi**: pi has subscription-based auth (use your Claude Pro/Max account without API keys),
session branching (/tree, /fork), and a clean documented RPC protocol designed for embedding
in other UIs. It's also the base for OpenClaw. Adding pi support also adds OpenClaw support
for free.

**Why not a generic AgentAdapter interface**: Hermes is a deep import (library), pi is a subprocess.
They're structurally different. A fake common interface would hide that and add indirection with
no benefit. The session record's `agent` field is the switchboard — the UI reads it and shows
the right panels.

**Sprint 31 — pi runner**
- PiRunner: spawn `pi --mode rpc` as subprocess, send JSONL commands, receive JSONL events
- Translate pi events to your existing SSE event format:
  - message_update text_delta -> token
  - tool_execution_start -> tool
  - agent_end -> done
  - extension_ui_request (confirm/select) -> approval card
- Agent selector in new-session UI: Hermes | pi
- session.agent field used to show/hide panels (crons/memory/skills = Hermes only)
- pi tool icon map: bash -> terminal icon, read -> read_file icon, write -> write_file icon
- Estimated: 1-2 sprints

**Sprint 32 — pi session features**
- Branching UI: show /tree in a panel when session.agent = 'pi'
  (fetch fork points via get_fork_messages, let user jump to any point)
- Steering message queue: interrupt pi mid-run with a new instruction
- Subscription auth: surface pi's /login flow in the UI for users without API keys
- OpenClaw: works automatically since it uses pi's RPC protocol — just point at openclaw binary
- Estimated: 1 sprint

---

### Tier 3 — OpenHands integration

OpenHands is the most mature open-source multi-agent UI. Rather than compete directly,
integrate it as a third runner option for users who want its Docker sandbox execution model.

**Why OpenHands**: Their sandbox approach (Docker container per task) is genuinely safer
for running untrusted code. They've solved problems we haven't (file permission isolation,
network sandboxing, rollback). For coding tasks where you want isolation, OpenHands is better
than running bare Hermes/pi on your server.

**Integration approach**: OpenHands has a REST API + WebSocket event stream. You'd run OpenHands
as a sidecar service (Docker, port 3000), and add an OpenHandsRunner that proxies its events
into your SSE format. Sessions with agent=openhands open in a sandboxed view with a terminal
panel showing the container output.

**Sprint 33 — OpenHands runner (exploratory)**
- Confirm OpenHands REST+WS API is stable enough to build against
- OpenHandsRunner: proxy events from OpenHands WS to your SSE stream
- Agent selector gains third option: OpenHands
- Sandboxed session view (no crons/memory/skills panels, terminal output panel instead)
- Estimated: 2 sprints (depends on OpenHands API stability)

---

### Tier 4 — Distribution

**Sprint 34 — macOS desktop app** (from original Sprint 25 plan)
Swift thin shell + WKWebView wrapping the existing server.
- Single .app download, no SSH tunnel needed
- ServerManager.swift spawns Python server on random port, health-checks before loading
- Native notifications for cron completion
- NSOpenPanel for workspace selection
- Option A (require system python3) for v1 — keeps download small
- Distribute via GitHub Releases as unsigned .dmg (right-click > Open on first launch)
- No Electron, no Chromium, ~30MB total
- Estimated: 2-3 sprints (new language/toolchain)

---

### Tier 5 — Deferred (unchanged from original roadmap, lower priority than above)

These are still valid but deprioritized behind foundation and multi-agent work.

- Artifacts / HTML+SVG inline preview
- TTS playback of responses
- Code execution cells (Jupyter-style inline Python)
- Subagent session tree (show hierarchy in sidebar)
- Toolset control per session (enable/disable individual tools)
- Virtual scroll for large session/skill lists (100+ items)
- Clarify dialog (agent blocks on user question mid-turn)
- ~~LLM-generated session titles~~ (shipped in v0.36.2, opt-in setting)
- Sharing / public session URLs (requires hosted backend, not planned for self-hosted)
- Prism.js theme switching (minor, current default works on all themes)

---

## What is intentionally not planned

- **Sharing / public URLs**: needs hosted backend with access control. Out of scope for self-hosted.
- **Real-time collaboration**: multiple users in the same session. Single-user assumption throughout.
- **Plugin marketplace**: Hermes skills cover this. pi packages cover it for pi sessions.
- **Full Swift/SwiftUI rewrite of the frontend**: wrong tradeoff. Thin shell + existing web UI is 95% benefit at 5% cost.
- **Windows desktop app**: Mac first, assess demand before investing in a different toolchain.

---

## Sprint history (completed — summary)

| Sprint | Theme | Highlights |
|--------|-------|-----------|
| 1 | Bug fixes + foundations | B1-B11, request logging, LOCK on SESSIONS |
| 2 | Rich file preview | Image preview, rendered markdown, tables |
| 3 | Panel nav + viewers | Sidebar tabs, cron/skills/memory panels |
| 4 | Relocation + power features | Session rename/search, file ops |
| 5 | Phase A + workspace | JS extraction, workspace management, file editor |
| 6 | Polish + cron create | Resizable panels, cron create, session JSON export |
| 7 | Wave 2 core | Cron/skill/memory CRUD, session content search |
| 8 | Daily driver | Edit/regenerate messages, Prism.js, reconnect banner |
| 9 | Codebase health | 6 JS modules, tool call cards, todo panel |
| 10 | Server health | api/ module split, cancel, cron run history |
| 11 | Multi-provider models | Dynamic model dropdown, routes extracted |
| 12 | Settings + reliability | Settings panel, SSE auto-reconnect, pin sessions |
| 13 | Alerts + polish | Cron alerts, background error banner, duplicate session |
| 14 | Visual polish | Mermaid, timestamps, file rename, folder create, archive |
| 15 | Session projects | Project folders, code copy button, tool card toggle |
| 16 | Sidebar polish | SVG icons, hover overlay, pin indicator, project border |
| 17 | Workspace + slash commands | Breadcrumbs, /help /clear /model /workspace /new |
| 18 | Thinking + workspace tree | Collapsible thinking cards, expandable directory tree |
| 19 | Auth + security | Password auth, signed cookies, security headers |
| 20 | Voice + send button | Web Speech API voice input, send button animation |
| 21 | Mobile + Docker | Hamburger sidebar, bottom nav, Docker support |
| 22 | Multi-profile | Profile picker, management panel, seamless switching |
| 23 | Agentic transparency | Token/cost display, subagent cards, context indicator |
| v0.32 | Auto-compaction | Compression detection, /compact command, context indicator |
| v0.33 | Insights sync | Opt-in state.db sync for hermes /insights |
| 26 | Pluggable themes | Dark/Light/Slate/Solarized/Monokai/Nord, /theme command |
| v0.35 | Security hardening | Env race fix, random signing key, PBKDF2 password hash |
| v0.35.1 | Model dropdown fixes | Custom providers visible, configured default model injected |
| v0.36 | Self-update checker | Non-blocking boot check, one-click update, 30min cache, settings toggle |
| v0.36.1 | Login form fix | Enter key reliable across browsers (#124) |
| v0.36.2 | UI polish + LLM titles | Topbar stats row (tokens/cost/workspace/date), sidebar column layout, LLM-generated session titles (opt-in), OpenRouter 404 fix (#116) |

---

*Next sprint: Sprint 27 (Foundation — SQLite + router)*
*Following: Sprint 28 (Security hardening)*
*Horizon: Sprint 31 (pi integration)*
