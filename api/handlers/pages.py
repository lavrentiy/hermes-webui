"""Page-serving handlers: index, login, favicon, static files, health."""
import time
from pathlib import Path

from api.config import (
    _INDEX_HTML_PATH, SESSIONS, STREAMS, STREAMS_LOCK, SERVER_START_TIME,
)
from api.helpers import j, t


# ── Login page (self-contained, no external deps) ────────────────────────────
_LOGIN_PAGE_HTML = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hermes — Sign in</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1a1a2e;color:#e8e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#16213e;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:36px 32px;
  width:320px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,.3)}
.logo{width:48px;height:48px;border-radius:12px;background:linear-gradient(145deg,#e8a030,#e94560);
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;color:#fff;
  margin:0 auto 12px;box-shadow:0 2px 12px rgba(233,69,96,.3)}
h1{font-size:18px;font-weight:600;margin-bottom:4px}
.sub{font-size:12px;color:#8888aa;margin-bottom:24px}
input{width:100%;padding:10px 14px;border-radius:10px;border:1px solid rgba(255,255,255,.1);
  background:rgba(255,255,255,.04);color:#e8e8f0;font-size:14px;outline:none;margin-bottom:14px;
  transition:border-color .15s}
input:focus{border-color:rgba(124,185,255,.5);box-shadow:0 0 0 3px rgba(124,185,255,.1)}
button{width:100%;padding:10px;border-radius:10px;border:none;background:rgba(124,185,255,.15);
  border:1px solid rgba(124,185,255,.3);color:#7cb9ff;font-size:14px;font-weight:600;cursor:pointer;
  transition:all .15s}
button:hover{background:rgba(124,185,255,.25)}
.err{color:#e94560;font-size:12px;margin-top:10px;display:none}
</style></head><body>
<div class="card">
  <div class="logo">H</div>
  <h1>Hermes</h1>
  <p class="sub">Enter your password to continue</p>
  <form onsubmit="doLogin(event);return false">
    <input type="password" id="pw" placeholder="Password" autofocus
           onkeydown="if(event.key==='Enter'){doLogin(event);event.preventDefault();}">
    <button type="submit">Sign in</button>
  </form>
  <div class="err" id="err"></div>
</div>
<script>
async function doLogin(e){
  e.preventDefault();
  const pw=document.getElementById('pw').value;
  const err=document.getElementById('err');
  err.style.display='none';
  try{
    const res=await fetch('/api/auth/login',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({password:pw}),credentials:'include'});
    const data=await res.json();
    if(res.ok&&data.ok){window.location.href='/';}
    else{err.textContent=data.error||'Invalid password';err.style.display='block';}
  }catch(ex){err.textContent='Connection failed';err.style.display='block';}
}
</script></body></html>'''


def serve_index(handler, parsed):
    return t(handler, _INDEX_HTML_PATH.read_text(encoding='utf-8'),
             content_type='text/html; charset=utf-8')


def serve_login(handler, parsed):
    return t(handler, _LOGIN_PAGE_HTML, content_type='text/html; charset=utf-8')


def serve_favicon(handler, parsed):
    handler.send_response(204); handler.end_headers(); return True


def serve_static(handler, parsed):
    static_root = (Path(__file__).parent.parent.parent / 'static').resolve()
    # Strip the leading '/static/' prefix, then resolve and sandbox
    rel = parsed.path[len('/static/'):]
    static_file = (static_root / rel).resolve()
    try:
        static_file.relative_to(static_root)
    except ValueError:
        return j(handler, {'error': 'not found'}, status=404)
    if not static_file.exists() or not static_file.is_file():
        return j(handler, {'error': 'not found'}, status=404)
    ext = static_file.suffix.lower()
    ct = {'css': 'text/css', 'js': 'application/javascript',
          'html': 'text/html'}.get(ext.lstrip('.'), 'text/plain')
    handler.send_response(200)
    handler.send_header('Content-Type', f'{ct}; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    raw = static_file.read_bytes()
    handler.send_header('Content-Length', str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)
    return True


def serve_health(handler, parsed):
    with STREAMS_LOCK: n_streams = len(STREAMS)
    return j(handler, {
        'status': 'ok', 'sessions': len(SESSIONS),
        'active_streams': n_streams,
        'uptime_seconds': round(time.time() - SERVER_START_TIME, 1),
    })
