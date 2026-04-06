"""
Hermes Web UI -- Session model and in-memory session store.
"""
import collections
import json
import time
import uuid
from pathlib import Path

import api.config as _cfg
from api.config import (
    SESSION_DIR, SESSION_INDEX_FILE, SESSIONS, SESSIONS_MAX,
    LOCK, DEFAULT_WORKSPACE, DEFAULT_MODEL, PROJECTS_FILE, HOME
)
from api.workspace import get_last_workspace


def _write_session_index():
    """Rebuild the session index file for O(1) future reads."""
    entries = []
    for p in SESSION_DIR.glob('*.json'):
        if p.name.startswith('_'): continue
        try:
            s = Session.load(p.stem)
            if s: entries.append(s.compact())
        except Exception:
            pass
    with LOCK:
        for s in SESSIONS.values():
            if not any(e['session_id'] == s.session_id for e in entries):
                entries.append(s.compact())
    entries.sort(key=lambda s: s['updated_at'], reverse=True)
    SESSION_INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding='utf-8')


class Session:
    def __init__(self, session_id: str=None, title: str='Untitled',
                 workspace=str(DEFAULT_WORKSPACE), model=DEFAULT_MODEL,
                 messages=None, created_at=None, updated_at=None,
                 tool_calls=None, pinned: bool=False, archived: bool=False,
                 project_id: str=None, profile=None,
                 input_tokens: int=0, output_tokens: int=0, estimated_cost=None,
                 **kwargs):
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.title = title
        self.workspace = str(Path(workspace).expanduser().resolve())
        self.model = model
        self.messages = messages or []
        self.tool_calls = tool_calls or []
        self.created_at = created_at or time.time()
        self.updated_at = updated_at or time.time()
        self.pinned = bool(pinned)
        self.archived = bool(archived)
        self.project_id = project_id or None
        self.profile = profile
        self.input_tokens = input_tokens or 0
        self.output_tokens = output_tokens or 0
        self.estimated_cost = estimated_cost

    @property
    def path(self):
        return SESSION_DIR / f'{self.session_id}.json'

    def save(self) -> None:
        self.updated_at = time.time()
        self.path.write_text(
            json.dumps(self.__dict__, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        _write_session_index()

    @classmethod
    def load(cls, sid):
        p = SESSION_DIR / f'{sid}.json'
        if not p.exists():
            return None
        return cls(**json.loads(p.read_text(encoding='utf-8')))

    def compact(self) -> dict:
        return {
            'session_id': self.session_id,
            'title': self.title,
            'workspace': self.workspace,
            'model': self.model,
            'message_count': len(self.messages),
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'pinned': self.pinned,
            'archived': self.archived,
            'project_id': self.project_id,
            'profile': self.profile,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'estimated_cost': self.estimated_cost,
        }

def get_session(sid):
    with LOCK:
        if sid in SESSIONS:
            SESSIONS.move_to_end(sid)  # LRU: mark as recently used
            return SESSIONS[sid]
    s = Session.load(sid)
    if s:
        with LOCK:
            SESSIONS[sid] = s
            SESSIONS.move_to_end(sid)
            while len(SESSIONS) > SESSIONS_MAX:
                SESSIONS.popitem(last=False)  # evict least recently used
        return s
    raise KeyError(sid)

def new_session(workspace=None, model=None):
    # Use _cfg.DEFAULT_MODEL (not the import-time snapshot) so save_settings() changes take effect
    try:
        from api.profiles import get_active_profile_name
        _profile = get_active_profile_name()
    except ImportError:
        _profile = None
    s = Session(workspace=workspace or get_last_workspace(), model=model or _cfg.DEFAULT_MODEL, profile=_profile)
    with LOCK:
        SESSIONS[s.session_id] = s
        SESSIONS.move_to_end(s.session_id)
        while len(SESSIONS) > SESSIONS_MAX:
            SESSIONS.popitem(last=False)
    s.save()
    return s

def all_sessions():
    # Phase C: try index first for O(1) read; fall back to full scan
    if SESSION_INDEX_FILE.exists():
        try:
            index = json.loads(SESSION_INDEX_FILE.read_text(encoding='utf-8'))
            # Overlay any in-memory sessions that may be newer than the index
            index_map = {s['session_id']: s for s in index}
            with LOCK:
                for s in SESSIONS.values():
                    index_map[s.session_id] = s.compact()
            result = sorted(index_map.values(), key=lambda s: (s.get('pinned', False), s['updated_at']), reverse=True)
            # Hide empty Untitled sessions from the UI (created by tests, page refreshes, etc.)
            result = [s for s in result if not (s.get('title','Untitled')=='Untitled' and s.get('message_count',0)==0)]
            # Backfill: sessions created before Sprint 22 have no profile tag.
            # Attribute them to 'default' so the client profile filter works correctly.
            for s in result:
                if not s.get('profile'):
                    s['profile'] = 'default'
            return result
        except Exception:
            pass  # fall through to full scan
    # Full scan fallback
    out = []
    for p in SESSION_DIR.glob('*.json'):
        if p.name.startswith('_'): continue
        try:
            s = Session.load(p.stem)
            if s: out.append(s)
        except Exception:
            pass
    for s in SESSIONS.values():
        if all(s.session_id != x.session_id for x in out): out.append(s)
    out.sort(key=lambda s: (getattr(s, 'pinned', False), s.updated_at), reverse=True)
    result = [s.compact() for s in out if not (s.title=='Untitled' and len(s.messages)==0)]
    for s in result:
        if not s.get('profile'):
            s['profile'] = 'default'
    return result


def title_from(messages, fallback: str='Untitled'):
    """Derive a session title from the first user message.

    Only generates a title when the current title looks auto-generated
    (i.e. it's 'Untitled' or matches the first 64 chars of the first user
    message).  If the user manually renamed the session, fallback will be
    their custom name and it won't match — so we leave it untouched.
    """
    first_user_text = ''
    for m in messages:
        if m.get('role') == 'user':
            c = m.get('content', '')
            if isinstance(c, list):
                c = ' '.join(p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text')
            first_user_text = str(c).strip()
            if first_user_text:
                break

    # If the existing title looks hand-crafted, keep it.
    auto_title = first_user_text[:64] if first_user_text else ''
    if fallback not in ('Untitled', '') and fallback != auto_title:
        return fallback  # user renamed it — don't clobber

    return auto_title or fallback


# ── LLM-generated session titles ────────────────────────────────────────────

def _is_auto_title(title: str, messages: list) -> bool:
    """Return True if title looks auto-generated (safe to replace with LLM title)."""
    if not title or title == 'Untitled':
        return True
    # Check if it matches the first-message truncation
    auto = title_from(messages, '')
    return title == auto


def generate_title_llm(session, put_fn=None) -> str | None:
    """Generate a short session title via a cheap LLM call.

    Uses the active provider/model from config.  Falls back silently if
    the API call fails.  Returns the new title string, or None on failure.

    put_fn: optional callable(event, data) to push a 'title' SSE event
    back to the client immediately (for streaming sessions).
    """
    try:
        import json as _json
        import urllib.request as _req
        import urllib.error as _uerr
        from api.config import resolve_model_provider, load_settings

        # Honour the opt-in setting
        if not load_settings().get('llm_titles', False):
            return None

        # Extract first user message text
        first_user = ''
        for m in (session.messages or []):
            if m.get('role') == 'user':
                c = m.get('content', '')
                if isinstance(c, list):
                    c = ' '.join(p.get('text', '') for p in c
                                  if isinstance(p, dict) and p.get('type') == 'text')
                first_user = str(c).strip()
                if first_user:
                    break
        if not first_user:
            return None

        # Resolve model + provider
        model_id = session.model or ''
        model, provider, base_url = resolve_model_provider(model_id)

        api_key = None
        try:
            from hermes_cli.runtime_provider import resolve_runtime_provider
            rt = resolve_runtime_provider()
            api_key = rt.get('api_key')
            if not provider:
                provider = rt.get('provider')
            if not base_url:
                base_url = rt.get('base_url')
        except Exception:
            pass

        if not api_key:
            return None

        # Build a minimal chat-completion request
        prompt = (
            "Generate a short, descriptive title (4-6 words max) for a conversation "
            "that starts with this message. Reply with ONLY the title, no quotes, "
            "no punctuation at the end.\n\nMessage: " + first_user[:400]
        )

        # Pick smallest/cheapest model variant if available
        title_model = model
        if provider == 'anthropic':
            title_model = 'claude-haiku-3-5'
            base_url = base_url or 'https://api.anthropic.com'
        elif provider == 'openai':
            title_model = 'gpt-4.1-mini'
            base_url = base_url or 'https://api.openai.com'
        elif provider == 'openrouter':
            title_model = 'anthropic/claude-haiku-3-5'
            base_url = base_url or 'https://openrouter.ai/api'

        # Normalise base_url
        base_url = (base_url or '').rstrip('/')

        payload = {
            'model': title_model,
            'max_tokens': 20,
            'messages': [{'role': 'user', 'content': prompt}],
        }

        if provider == 'anthropic':
            endpoint = base_url + '/v1/messages'
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
            data = _json.dumps(payload).encode()
            request = _req.Request(endpoint, data=data, headers=headers, method='POST')
            with _req.urlopen(request, timeout=10) as resp:
                body = _json.loads(resp.read())
            title_text = (body.get('content') or [{}])[0].get('text', '').strip()
        else:
            # OpenAI-compatible (openai, openrouter, ollama, etc.)
            endpoint = base_url + '/v1/chat/completions'
            headers = {
                'authorization': f'Bearer {api_key}',
                'content-type': 'application/json',
            }
            data = _json.dumps(payload).encode()
            request = _req.Request(endpoint, data=data, headers=headers, method='POST')
            with _req.urlopen(request, timeout=10) as resp:
                body = _json.loads(resp.read())
            title_text = (
                (body.get('choices') or [{}])[0]
                .get('message', {})
                .get('content', '')
                .strip()
            )

        if not title_text:
            return None

        # Trim quotes/punctuation the model sometimes adds
        title_text = title_text.strip('"\'').rstrip('.').strip()
        title_text = title_text[:80]

        # Persist and optionally push to client
        session.title = title_text
        session.save()
        if put_fn:
            try:
                put_fn('title', {'title': title_text, 'session_id': session.session_id})
            except Exception:
                pass
        return title_text

    except Exception as _e:
        print(f'[webui] generate_title_llm failed (non-fatal): {_e}', flush=True)
        return None


def generate_title_async(session, put_fn=None) -> None:
    """Fire-and-forget wrapper — runs generate_title_llm in a daemon thread."""
    import threading
    t = threading.Thread(
        target=generate_title_llm,
        args=(session, put_fn),
        daemon=True,
        name=f'title-gen-{session.session_id[:8]}',
    )
    t.start()


# ── Project helpers ──────────────────────────────────────────────────────────

def load_projects() -> list:
    """Load project list from disk. Returns list of project dicts."""
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return []

def save_projects(projects) -> None:
    """Write project list to disk."""
    PROJECTS_FILE.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding='utf-8')


def import_cli_session(session_id: str, title: str, messages, model: str='unknown', profile=None):
    """Create a new WebUI session populated with CLI messages.
    Returns the Session object.
    """
    s = Session(
        session_id=session_id,
        title=title,
        workspace=get_last_workspace(),
        model=model,
        messages=messages,
        profile=profile,
    )
    s.save()
    return s


# ── CLI session bridge ──────────────────────────────────────────────────────

def get_cli_sessions() -> list:
    """Read CLI sessions from the agent's SQLite store and return them as
    dicts in a format the WebUI sidebar can render alongside local sessions.

    Returns empty list if the SQLite DB is missing, the sqlite3 module is
    unavailable, or any error occurs -- the bridge is purely additive and never
    crashes the WebUI.
    """
    import os
    cli_sessions = []
    try:
        import sqlite3
    except ImportError:
        return cli_sessions

    # Use the active WebUI profile's HERMES_HOME to find state.db.
    # The active profile is determined by what the user has selected in the UI
    # (stored in the server's runtime config). This means:
    #   - default profile  -> ~/.hermes/state.db
    #   - named profile X  -> ~/.hermes/profiles/X/state.db
    # We resolve the active profile's home directory rather than just using
    # HERMES_HOME (which is the server's launch profile, not necessarily the
    # active one after a profile switch).
    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()

    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return cli_sessions

    # Try to resolve the active CLI profile so imported sessions integrate
    # with the WebUI profile filter (available since Sprint 22).
    try:
        from api.profiles import get_active_profile_name
        _cli_profile = get_active_profile_name()
    except ImportError:
        _cli_profile = None  # older agent -- fall back to no profile

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT s.id, s.title, s.model, s.message_count,
                       s.started_at, s.source,
                       MAX(m.timestamp) AS last_activity
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY COALESCE(MAX(m.timestamp), s.started_at) DESC
                LIMIT 200
            """)
            for row in cur.fetchall():
                sid = row['id']
                raw_ts = row['last_activity'] or row['started_at']
                # Prefer the CLI session's own profile from the DB; fall back to
                # the active CLI profile so sidebar filtering works either way.
                profile = _cli_profile  # CLI DB has no profile column; use active profile

                cli_sessions.append({
                    'session_id': sid,
                    'title': row['title'] or 'CLI Session',
                    'workspace': str(get_last_workspace()),
                    'model': row['model'] or 'unknown',
                    'message_count': row['message_count'] or 0,
                    'created_at': row['started_at'],
                    'updated_at': raw_ts,
                    'pinned': False,
                    'archived': False,
                    'project_id': None,
                    'profile': profile,
                    'source_tag': 'cli',
                    'is_cli_session': True,
                })
    except Exception:
        # DB schema changed, locked, or corrupted -- silently degrade
        return []

    return cli_sessions


def get_cli_session_messages(sid) -> list:
    """Read messages for a single CLI session from the SQLite store.
    Returns a list of {role, content, timestamp} dicts.
    Returns empty list on any error.
    """
    import os
    try:
        import sqlite3
    except ImportError:
        return []

    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()
    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return []

    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT role, content, timestamp
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC
            """, (sid,))
            msgs = []
            for row in cur.fetchall():
                msgs.append({
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp'],
                })
    except Exception:
        return []
    return msgs


def delete_cli_session(sid) -> bool:
    """Delete a CLI session from state.db (messages + session row).
    Returns True if deleted, False if not found or error.
    """
    import os
    try:
        import sqlite3
    except ImportError:
        return False

    try:
        from api.profiles import get_active_hermes_home
        hermes_home = Path(get_active_hermes_home()).expanduser().resolve()
    except Exception:
        hermes_home = Path(os.getenv('HERMES_HOME', str(HOME / '.hermes'))).expanduser().resolve()
    db_path = hermes_home / 'state.db'
    if not db_path.exists():
        return False

    try:
        with sqlite3.connect(str(db_path)) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            cur.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            conn.commit()
            return cur.rowcount > 0
    except Exception:
        return False
