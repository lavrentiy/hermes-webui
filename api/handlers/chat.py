"""Chat handlers: start, stream, stream status, cancel, sync."""
import os
import queue
import threading
import uuid
from pathlib import Path
from urllib.parse import parse_qs

from api.config import (
    STREAMS, STREAMS_LOCK, CANCEL_FLAGS, CLI_TOOLSETS, CHAT_LOCK,
    load_settings,
)
from api.helpers import require, bad, j, read_body
from api.models import (
    get_session, title_from, _is_auto_title, generate_title_async,
)
from api.workspace import set_last_workspace
from api.streaming import _sse, _run_agent_streaming, cancel_stream


def post_chat_start(handler, parsed):
    body = read_body(handler)
    try: require(body, 'session_id')
    except ValueError as e: return bad(handler, str(e))
    try: s = get_session(body['session_id'])
    except KeyError: return bad(handler, 'Session not found', 404)
    msg = str(body.get('message', '')).strip()
    if not msg: return bad(handler, 'message is required')
    attachments = [str(a) for a in (body.get('attachments') or [])][:20]
    workspace = str(Path(body.get('workspace') or s.workspace).expanduser().resolve())
    model = body.get('model') or s.model
    s.workspace = workspace; s.model = model; s.save()
    set_last_workspace(workspace)
    stream_id = uuid.uuid4().hex
    q = queue.Queue()
    with STREAMS_LOCK: STREAMS[stream_id] = q
    thr = threading.Thread(
        target=_run_agent_streaming,
        args=(s.session_id, msg, model, workspace, stream_id, attachments),
        daemon=True,
    )
    thr.start()
    return j(handler, {'stream_id': stream_id, 'session_id': s.session_id})


def get_chat_stream(handler, parsed):
    stream_id = parse_qs(parsed.query).get('stream_id', [''])[0]
    q = STREAMS.get(stream_id)
    if q is None: return j(handler, {'error': 'stream not found'}, status=404)
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('X-Accel-Buffering', 'no')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()
    try:
        while True:
            try:
                event, data = q.get(timeout=30)
            except queue.Empty:
                handler.wfile.write(b': heartbeat\n\n')
                handler.wfile.flush()
                continue
            _sse(handler, event, data)
            if event in ('done', 'error', 'cancel'):
                break
    except (BrokenPipeError, ConnectionResetError):
        pass
    return True


def get_chat_stream_status(handler, parsed):
    stream_id = parse_qs(parsed.query).get('stream_id', [''])[0]
    return j(handler, {'active': stream_id in STREAMS, 'stream_id': stream_id})


def get_chat_cancel(handler, parsed):
    stream_id = parse_qs(parsed.query).get('stream_id', [''])[0]
    if not stream_id:
        return bad(handler, 'stream_id required')
    cancelled = cancel_stream(stream_id)
    return j(handler, {'ok': True, 'cancelled': cancelled, 'stream_id': stream_id})


def post_chat_sync(handler, parsed):
    """Fallback synchronous chat endpoint (POST /api/chat). Not used by frontend."""
    body = read_body(handler)
    from api.config import _get_session_agent_lock
    s = get_session(body['session_id'])
    msg = str(body.get('message', '')).strip()
    if not msg: return j(handler, {'error': 'empty message'}, status=400)
    workspace = Path(body.get('workspace') or s.workspace).expanduser().resolve()
    s.workspace = str(workspace); s.model = body.get('model') or s.model
    old_cwd = os.environ.get('TERMINAL_CWD')
    os.environ['TERMINAL_CWD'] = str(workspace)
    old_exec_ask = os.environ.get('HERMES_EXEC_ASK')
    old_session_key = os.environ.get('HERMES_SESSION_KEY')
    os.environ['HERMES_EXEC_ASK'] = '1'
    os.environ['HERMES_SESSION_KEY'] = s.session_id
    try:
        from run_agent import AIAgent
        with CHAT_LOCK:
            from api.config import resolve_model_provider
            _model, _provider, _base_url = resolve_model_provider(s.model)
            # Resolve API key via Hermes runtime provider (matches gateway behaviour)
            _api_key = None
            try:
                from hermes_cli.runtime_provider import resolve_runtime_provider
                _rt = resolve_runtime_provider()
                _api_key = _rt.get("api_key")
                # Also use runtime provider/base_url if the webui config didn't resolve them
                if not _provider:
                    _provider = _rt.get("provider")
                if not _base_url:
                    _base_url = _rt.get("base_url")
            except Exception as _e:
                print(f"[webui] WARNING: resolve_runtime_provider failed: {_e}", flush=True)
            agent = AIAgent(model=_model, provider=_provider, base_url=_base_url,
                           api_key=_api_key, platform='cli', quiet_mode=True,
                           enabled_toolsets=CLI_TOOLSETS, session_id=s.session_id)
            workspace_ctx = f"[Workspace: {s.workspace}]\n"
            workspace_system_msg = (
                f"Active workspace at session start: {s.workspace}\n"
                "Every user message is prefixed with [Workspace: /absolute/path] indicating the "
                "workspace the user has selected in the web UI at the time they sent that message. "
                "This tag is the single authoritative source of the active workspace and updates "
                "with every message. It overrides any prior workspace mentioned in this system "
                "prompt, memory, or conversation history. Always use the value from the most recent "
                "[Workspace: ...] tag as your default working directory for ALL file operations: "
                "write_file, read_file, search_files, terminal workdir, and patch. "
                "Never fall back to a hardcoded path when this tag is present."
            )
            from api.streaming import _sanitize_messages_for_api
            result = agent.run_conversation(
                user_message=workspace_ctx + msg,
                system_message=workspace_system_msg,
                conversation_history=_sanitize_messages_for_api(s.messages),
                task_id=s.session_id,
                persist_user_message=msg,
            )
    finally:
        if old_cwd is None: os.environ.pop('TERMINAL_CWD', None)
        else: os.environ['TERMINAL_CWD'] = old_cwd
        if old_exec_ask is None: os.environ.pop('HERMES_EXEC_ASK', None)
        else: os.environ['HERMES_EXEC_ASK'] = old_exec_ask
        if old_session_key is None: os.environ.pop('HERMES_SESSION_KEY', None)
        else: os.environ['HERMES_SESSION_KEY'] = old_session_key
    s.messages = result.get('messages') or s.messages
    _sync_title_is_auto = _is_auto_title(s.title, s.messages)
    s.title = title_from(s.messages, s.title); s.save()
    if _sync_title_is_auto:
        generate_title_async(s)
    # Sync to state.db for /insights (opt-in setting)
    try:
        if load_settings().get('sync_to_insights'):
            from api.state_sync import sync_session_usage
            sync_session_usage(
                session_id=s.session_id,
                input_tokens=s.input_tokens or 0,
                output_tokens=s.output_tokens or 0,
                estimated_cost=s.estimated_cost,
                model=s.model,
                title=s.title,
            )
    except Exception:
        pass
    return j(handler, {
        'answer': result.get('final_response') or '',
        'status': 'done' if result.get('completed', True) else 'partial',
        'session': s.compact() | {'messages': s.messages},
        'result': {k: v for k, v in result.items() if k != 'messages'},
    })
