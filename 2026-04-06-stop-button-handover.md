# Stop/Cancel Button + Topbar Layout Fix — Handover for Implementation Agent

**Date:** 2026-04-06
**Repo:** `/home/laurent/deploymedaddy/hermes-webui`
**Goals:**
1. Make the existing Cancel button actually stop a looping agent, not just mute the SSE output.
2. Fix the topbar layout: move token/cost stats from under the title to under the buttons.

---

## Problem Statement

When a Hermes agent gets caught in a loop (e.g. repeatedly calling tools, stuck in retry logic, or burning tokens in circles), the user needs a way to **hard-stop** it from the web UI.

We already have partial cancel infrastructure (Sprint 10), but it has a critical gap: **the agent thread keeps running after cancel**. The cancel flag only suppresses SSE events — the underlying `agent.run_conversation()` call continues executing tool calls and burning tokens until it finishes naturally.

---

## Current Architecture (What Exists)

### Backend: `api/streaming.py`

1. **Cancel flag** (`threading.Event`) created per stream in `CANCEL_FLAGS[stream_id]`
2. **`cancel_stream(stream_id)`** function (line 383) — sets the flag and pushes a `cancel` sentinel to the SSE queue
3. **Pre-flight cancel check** (line 92) — if flag is set before `run_conversation()`, it exits early
4. **Event suppression** (line 77) — the `put()` helper drops events when cancelled, so no new SSE events reach the client

**The gap:** Once `agent.run_conversation()` is called (line 208), the cancel flag is never checked again. The agent thread runs to completion regardless. There's no mechanism to interrupt the agent's tool-calling loop.

### Backend: `api/handlers/chat.py`

- `GET /api/chat/cancel?stream_id=X` — calls `cancel_stream()` (line 77-82)
- `POST /api/chat/start` — spawns daemon thread for `_run_agent_streaming` (line 37-42)

### Frontend: `static/boot.js` + `static/messages.js`

- `cancelStream()` function in `boot.js` (line 1) — hits `/api/chat/cancel`
- Cancel button (`#btnCancel`) in `index.html` (line 274) — red ■ Cancel button in the activity bar
- Button shown when streaming starts (messages.js line 71-72)
- Button hidden on done/error/cancel events (messages.js lines 156, 214)

### Frontend Cancel Button Location (index.html line 274)

```html
<button id="btnCancel" onclick="cancelStream()" style="display:none;..."
  title="Cancel this task">&#9632; Cancel</button>
```

It lives inside `#activityBarInner`, next to the activity status text and dots.

---

## What Needs to Change

### Priority 1: Kill the Agent Thread (Backend)

The agent runs inside `_run_agent_streaming()` in `api/streaming.py`. The call to `agent.run_conversation()` (line 208) is a blocking call that runs the full agent loop — LLM calls, tool execution, repeat.

**Options to interrupt it (pick the best approach):**

#### Option A: Thread interrupt via cancel_event polling (Recommended)

The AIAgent from `run_agent.py` (hermes-agent) likely has a callback mechanism or a way to check for cancellation between tool calls. Investigate:

1. Check if `AIAgent` accepts a `cancel_check` callback or `should_stop` callable
2. If so, pass `cancel_event.is_set` as the check function
3. If not, check if `AIAgent.run_conversation()` can be modified to accept one (this is our own codebase at hermes-agent)

Search the hermes-agent codebase for: `should_stop`, `cancel`, `abort`, `interrupt`, `max_iterations`

#### Option B: Force-kill the thread

Python threads can't be cleanly killed, but we can:
1. Store a reference to the agent object: `agents[stream_id] = agent`
2. On cancel, set a flag on the agent that its tool dispatcher checks
3. Or use `ctypes.pythonapi.PyThreadState_SetAsyncExc` to raise an exception in the thread (nuclear option, use only as last resort)

#### Option C: Run agent in a subprocess instead of a thread

Replace `threading.Thread` with `subprocess.Popen` or `multiprocessing.Process`. Then cancel = `process.terminate()`. This is the cleanest kill but requires refactoring how the agent communicates results back (IPC instead of shared queue).

### Priority 2: Save Partial Results on Cancel (Backend)

When a cancel happens mid-conversation, the current code discards everything (the `put()` drops events, and `run_conversation` result is never saved). We should:

1. After setting `cancel_event`, wait briefly (1-2s) for the agent thread to notice
2. Save whatever messages the agent has accumulated so far to the session
3. Append a system note: `"[Cancelled by user]"`
4. Send the partial session back in the cancel SSE event

Look at `_run_agent_streaming()` lines 215-344 — the post-run session save logic. A subset of this should run on cancel too.

### Priority 3: Frontend UX Improvements

The cancel button exists but could be better:

1. **Make it more prominent during long runs** — Currently it's a small button in the activity bar. Consider also showing it as a floating button or replacing the Send button (like hermes-workspace does)
2. **Immediate visual feedback** — When clicked, show "Stopping…" state with a spinner, disable the button to prevent double-clicks
3. **Confirm the agent actually stopped** — After cancel, poll `/api/chat/stream/status` to confirm the stream is gone, then show "Cancelled" status
4. **Handle the 'cancel' SSE event properly** — In `messages.js`, the cancel event handler should render a "[Cancelled]" indicator on the last message

---

## Files to Modify

| File | What to change |
|------|---------------|
| `api/streaming.py` | Core: make `run_conversation` interruptible, save partial results on cancel |
| `api/handlers/chat.py` | Maybe: change cancel from GET to POST (mutations should be POST) |
| `static/messages.js` | Handle cancel SSE event, show cancelled state |
| `static/boot.js` | Improve cancelStream() with confirmation polling |
| `static/ui.js` | Better cancel button visibility during long runs |
| `static/style.css` | Cancel button styling (if making it more prominent) |

Also investigate (read-only, for understanding):

| File | Why |
|------|-----|
| hermes-agent `run_agent.py` | Check if AIAgent supports cancellation callbacks |
| hermes-agent `hermes_cli/` | Check for `should_stop` or iteration-limit mechanisms |

---

## Reference: How hermes-workspace Does It

The competing project (github.com/outsourc-e/hermes-workspace) handles this with:

1. **Frontend AbortController** — `abortController.abort()` kills the `fetch()` SSE stream
2. **Server ReadableStream cancel** — When fetch aborts, the stream's `cancel()` callback fires, which aborts the upstream request
3. **No true agent kill** — They also don't kill the agent process. They just close the connection and hope the gateway notices.

Their approach is simpler because they use a different architecture (fetch-based SSE with AbortController vs our EventSource + queue). But they have the same fundamental problem: the backend agent may keep running.

We can do better because our agent runs in-process as a Python thread — we have direct access to the agent object and can build a proper cancellation contract.

---

## Acceptance Criteria

1. Clicking Cancel while agent is running tool calls stops the agent within 5 seconds
2. Partial conversation is saved (messages up to the cancel point)
3. UI shows "[Cancelled]" state clearly
4. No orphaned threads burning tokens after cancel
5. Cancel works for both the streaming path (`/api/chat/start` + SSE) and prevents re-send of the same message
6. Existing tests still pass (`python -m pytest tests/ -v`)

---

## Testing

```bash
# Start the server
cd /home/laurent/deploymedaddy/hermes-webui
nohup venv/bin/python server.py > /tmp/webui-mvp.log 2>&1 &

# Run existing tests
venv/bin/python -m pytest tests/ -v

# Manual test: send a message that triggers many tool calls, hit Cancel mid-stream
# Verify: agent stops, partial messages saved, no thread leak
```

---

---

## Task 2: Topbar Layout Rework

### Current Layout (3 text lines on left, 99px tall)

```
LEFT SIDE (flex:1 div)                   RIGHT SIDE (.topbar-chips)
──────────────────────────               ────────────────────────────────────
Line 1: topbarTitle (Session Title)       
Line 2: topbarMeta  (48 messages · ...)   [default▾] [Claude Opus 4.6] [Clear] [⚙]
Line 3: topbarStats (6.4M in · 14.3k...) 
```

The stats line (token counts, cost, workspace path) sits below the meta line on the left.
The chips/buttons float vertically centered on the right. This makes the topbar 99px tall —
3 text rows on the left is excessive.

### Desired Layout (2 rows, more compact)

```
LEFT SIDE                                RIGHT SIDE
──────────────────────────               ────────────────────────────────────
Line 1: topbarTitle (Session Title)       [default▾] [Claude Opus 4.6] [Clear] [⚙]
Line 2: topbarMeta  (48 messages · ...)   6.4M in · 14.3k out · ~$97.70 · ~/dmd
```

The `#topbarStats` element moves from the left-side flex div to below `.topbar-chips` on the
right side, right-aligned. This makes the topbar ~70px tall instead of 99px.

**Note:** There is also a context window usage indicator (`#ctxIndicator`) already in the
composer footer (below the textarea, lines 310-313 in index.html). It shows a progress bar +
label like `32k / 200k (16%) · $0.45` — this is per-request context usage, not cumulative
session totals. The topbar stats show cumulative session tokens (`6.4M in · 14.3k out · ~$97`).
Both are useful — don't remove either. The topbar stats just need to move to the right side.

### Files to Change

#### `static/index.html` (lines 195-222)

Move `#topbarStats` from inside the left div to after/inside `.topbar-chips`:

Current structure:
```html
<div class="topbar">
  <button class="mobile-hamburger" ...>...</button>
  <div style="flex:1;min-width:0;overflow:hidden">
    <div class="topbar-title" id="topbarTitle">deploymedaddy</div>
    <div class="topbar-meta" id="topbarMeta">Start a new conversation</div>
    <div class="topbar-stats" id="topbarStats"></div>       <!-- MOVE THIS -->
  </div>
  <div class="topbar-chips">
    ... profile chip, model chip, clear btn, settings btn ...
  </div>
</div>
```

New structure:
```html
<div class="topbar">
  <button class="mobile-hamburger" ...>...</button>
  <div style="flex:1;min-width:0;overflow:hidden">
    <div class="topbar-title" id="topbarTitle">deploymedaddy</div>
    <div class="topbar-meta" id="topbarMeta">Start a new conversation</div>
  </div>
  <div class="topbar-right">
    <div class="topbar-chips">
      ... profile chip, model chip, clear btn, settings btn ...
    </div>
    <div class="topbar-stats" id="topbarStats"></div>       <!-- NOW HERE -->
  </div>
</div>
```

Wrap the existing `.topbar-chips` and the moved `#topbarStats` in a new `.topbar-right`
container that stacks them vertically (flexbox column, align-items: flex-end).

#### `static/style.css`

1. Add `.topbar-right` style:
```css
.topbar-right{display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0;}
```

2. Update `.topbar` height from `99px` to `auto` (or a smaller fixed value like `72px`)

3. Update `.topbar-stats` to right-align:
```css
.topbar-stats{...; text-align:right;}
```

4. Mobile media query: `.topbar-stats` is already `display:none` on mobile (line 433) — no change needed there.

#### `static/ui.js` — `syncTopbar()` function

No logic changes needed — the function already writes to `$('topbarStats')` by ID, so moving
the element in the DOM doesn't affect the JS. Just verify it still works after the HTML change.

### Acceptance Criteria (Topbar)

1. Stats line (tokens/cost/workspace) renders right-aligned below the chips/buttons
2. Title + meta stay on the left (2 lines only)
3. Topbar is visually more compact (under 75px tall)
4. Mobile layout unchanged (stats hidden on mobile)
5. Empty state (no session) still looks clean

---

## Non-Goals (Out of Scope)

- Terminal panel (separate feature)
- WebSocket migration (SSE is fine for now)
- Agent loop detection / auto-stop (nice to have later, not this task)
