"""Route registration — maps paths to handler functions."""
from api.router import Router
from api.handlers import (
    pages, auth_handlers, sessions, chat, files,
    workspaces, crons, skills, memory, profiles,
    projects, approval, settings, models, updates,
    upload,
)

router = Router()

# ── Pages ─────────────────────────────────────────────────────────────────────
router.get('/', pages.serve_index)
router.get('/index.html', pages.serve_index)
router.get('/login', pages.serve_login)
router.get('/favicon.ico', pages.serve_favicon)
router.get('/health', pages.serve_health)
router.get_prefix('/static/', pages.serve_static)

# ── Auth ──────────────────────────────────────────────────────────────────────
router.get('/api/auth/status', auth_handlers.get_auth_status)
router.post('/api/auth/login', auth_handlers.post_login)
router.post('/api/auth/logout', auth_handlers.post_logout)

# ── Sessions ──────────────────────────────────────────────────────────────────
router.get('/api/session', sessions.get_session_detail)
router.get('/api/sessions', sessions.get_sessions_list)
router.get('/api/session/export', sessions.get_session_export)
router.get('/api/sessions/search', sessions.get_sessions_search)
router.post('/api/session/new', sessions.post_session_new)
router.post('/api/session/rename', sessions.post_session_rename)
router.post('/api/session/update', sessions.post_session_update)
router.post('/api/session/delete', sessions.post_session_delete)
router.post('/api/session/clear', sessions.post_session_clear)
router.post('/api/session/truncate', sessions.post_session_truncate)
router.post('/api/session/pin', sessions.post_session_pin)
router.post('/api/session/archive', sessions.post_session_archive)
router.post('/api/session/move', sessions.post_session_move)
router.post('/api/sessions/cleanup', sessions.post_sessions_cleanup)
router.post('/api/sessions/cleanup_zero_message', sessions.post_sessions_cleanup_zero)
router.post('/api/session/import', sessions.post_session_import)
router.post('/api/session/import_cli', sessions.post_session_import_cli)

# ── Chat ──────────────────────────────────────────────────────────────────────
router.post('/api/chat/start', chat.post_chat_start)
router.get('/api/chat/stream', chat.get_chat_stream)
router.get('/api/chat/stream/status', chat.get_chat_stream_status)
router.get('/api/chat/cancel', chat.get_chat_cancel)
router.post('/api/chat', chat.post_chat_sync)

# ── Files ─────────────────────────────────────────────────────────────────────
router.get('/api/file', files.get_file)
router.get('/api/file/raw', files.get_file_raw)
router.get('/api/list', files.get_list_dir)
router.get('/api/git-info', files.get_git_info)
router.post('/api/file/delete', files.post_file_delete)
router.post('/api/file/save', files.post_file_save)
router.post('/api/file/create', files.post_file_create)
router.post('/api/file/rename', files.post_file_rename)
router.post('/api/file/create-dir', files.post_create_dir)

# ── Upload ────────────────────────────────────────────────────────────────────
router.post('/api/upload', upload.post_upload)

# ── Workspaces ────────────────────────────────────────────────────────────────
router.get('/api/workspaces', workspaces.get_workspaces)
router.post('/api/workspaces/add', workspaces.post_workspace_add)
router.post('/api/workspaces/remove', workspaces.post_workspace_remove)
router.post('/api/workspaces/rename', workspaces.post_workspace_rename)

# ── Cron jobs ─────────────────────────────────────────────────────────────────
router.get('/api/crons', crons.get_crons)
router.get('/api/crons/output', crons.get_crons_output)
router.get('/api/crons/recent', crons.get_crons_recent)
router.post('/api/crons/create', crons.post_cron_create)
router.post('/api/crons/update', crons.post_cron_update)
router.post('/api/crons/delete', crons.post_cron_delete)
router.post('/api/crons/run', crons.post_cron_run)
router.post('/api/crons/pause', crons.post_cron_pause)
router.post('/api/crons/resume', crons.post_cron_resume)

# ── Skills ────────────────────────────────────────────────────────────────────
router.get('/api/skills', skills.get_skills)
router.get('/api/skills/content', skills.get_skills_content)
router.post('/api/skills/save', skills.post_skill_save)
router.post('/api/skills/delete', skills.post_skill_delete)

# ── Memory ────────────────────────────────────────────────────────────────────
router.get('/api/memory', memory.get_memory)
router.post('/api/memory/write', memory.post_memory_write)

# ── Profiles ──────────────────────────────────────────────────────────────────
router.get('/api/profiles', profiles.get_profiles)
router.get('/api/profile/active', profiles.get_profile_active)
router.post('/api/profile/switch', profiles.post_profile_switch)
router.post('/api/profile/create', profiles.post_profile_create)
router.post('/api/profile/delete', profiles.post_profile_delete)

# ── Projects ──────────────────────────────────────────────────────────────────
router.get('/api/projects', projects.get_projects)
router.post('/api/projects/create', projects.post_project_create)
router.post('/api/projects/rename', projects.post_project_rename)
router.post('/api/projects/delete', projects.post_project_delete)

# ── Approval ──────────────────────────────────────────────────────────────────
router.get('/api/approval/pending', approval.get_approval_pending)
router.get('/api/approval/inject_test', approval.get_approval_inject_test)
router.post('/api/approval/respond', approval.post_approval_respond)

# ── Settings ──────────────────────────────────────────────────────────────────
router.get('/api/settings', settings.get_settings)
router.post('/api/settings', settings.post_settings)

# ── Models ────────────────────────────────────────────────────────────────────
router.get('/api/models', models.get_models)

# ── Updates ───────────────────────────────────────────────────────────────────
router.get('/api/updates/check', updates.get_updates_check)
router.post('/api/updates/apply', updates.post_updates_apply)


# ── Backward-compat shims for server.py ───────────────────────────────────────
def handle_get(handler, parsed) -> bool:
    """Legacy entry point — delegates to router.dispatch('GET', ...)."""
    return router.dispatch('GET', parsed, handler)


def handle_post(handler, parsed) -> bool:
    """Legacy entry point — delegates to router.dispatch('POST', ...)."""
    return router.dispatch('POST', parsed, handler)
