"""Cron job handlers."""
import threading
from urllib.parse import parse_qs

from api.helpers import require, bad, j, read_body


def get_crons(handler, parsed):
    from cron.jobs import list_jobs
    return j(handler, {'jobs': list_jobs(include_disabled=True)})


def get_crons_output(handler, parsed):
    from cron.jobs import OUTPUT_DIR as CRON_OUT
    qs = parse_qs(parsed.query)
    job_id = qs.get('job_id', [''])[0]
    limit = int(qs.get('limit', ['5'])[0])
    if not job_id: return j(handler, {'error': 'job_id required'}, status=400)
    out_dir = CRON_OUT / job_id
    outputs = []
    if out_dir.exists():
        files = sorted(out_dir.glob('*.md'), reverse=True)[:limit]
        for f in files:
            try:
                txt = f.read_text(encoding='utf-8', errors='replace')
                outputs.append({'filename': f.name, 'content': txt[:8000]})
            except Exception:
                pass
    return j(handler, {'job_id': job_id, 'outputs': outputs})


def get_crons_recent(handler, parsed):
    """Return cron jobs that have completed since a given timestamp."""
    import datetime
    qs = parse_qs(parsed.query)
    since = float(qs.get('since', ['0'])[0])
    try:
        from cron.jobs import list_jobs
        jobs = list_jobs(include_disabled=True)
        completions = []
        for job in jobs:
            last_run = job.get('last_run_at')
            if not last_run:
                continue
            if isinstance(last_run, str):
                try:
                    ts = datetime.datetime.fromisoformat(last_run.replace('Z', '+00:00')).timestamp()
                except (ValueError, TypeError):
                    continue
            else:
                ts = float(last_run)
            if ts > since:
                completions.append({
                    'job_id': job.get('id', ''),
                    'name': job.get('name', 'Unknown'),
                    'status': job.get('last_status', 'unknown'),
                    'completed_at': ts,
                })
        return j(handler, {'completions': completions, 'since': since})
    except ImportError:
        return j(handler, {'completions': [], 'since': since})


def post_cron_create(handler, parsed):
    body = read_body(handler)
    try: require(body, 'prompt', 'schedule')
    except ValueError as e: return bad(handler, str(e))
    try:
        from cron.jobs import create_job
        job = create_job(
            prompt=body['prompt'], schedule=body['schedule'],
            name=body.get('name') or None, deliver=body.get('deliver') or 'local',
            skills=body.get('skills') or [], model=body.get('model') or None,
        )
        return j(handler, {'ok': True, 'job': job})
    except Exception as e:
        return j(handler, {'error': str(e)}, status=400)


def post_cron_update(handler, parsed):
    body = read_body(handler)
    try: require(body, 'job_id')
    except ValueError as e: return bad(handler, str(e))
    from cron.jobs import update_job, parse_schedule
    updates = {k: v for k, v in body.items() if k != 'job_id' and v is not None}
    # The frontend sends schedule as a raw string, but update_job expects the
    # parsed dict format (matching how create_job stores it).  Parse it here.
    if 'schedule' in updates and isinstance(updates['schedule'], str):
        try:
            updates['schedule'] = parse_schedule(updates['schedule'])
        except Exception as e:
            return bad(handler, f'Invalid schedule: {e}')
    try:
        job = update_job(body['job_id'], updates)
    except Exception as e:
        return bad(handler, f'Update failed: {e}')
    if not job: return bad(handler, 'Job not found', 404)
    return j(handler, {'ok': True, 'job': job})


def post_cron_delete(handler, parsed):
    body = read_body(handler)
    try: require(body, 'job_id')
    except ValueError as e: return bad(handler, str(e))
    from cron.jobs import remove_job
    ok = remove_job(body['job_id'])
    if not ok: return bad(handler, 'Job not found', 404)
    return j(handler, {'ok': True, 'job_id': body['job_id']})


def post_cron_run(handler, parsed):
    body = read_body(handler)
    job_id = body.get('job_id', '')
    if not job_id: return bad(handler, 'job_id required')
    from cron.jobs import get_job
    from cron.scheduler import run_job
    job = get_job(job_id)
    if not job: return bad(handler, 'Job not found', 404)
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return j(handler, {'ok': True, 'job_id': job_id, 'status': 'triggered'})


def post_cron_pause(handler, parsed):
    body = read_body(handler)
    job_id = body.get('job_id', '')
    if not job_id: return bad(handler, 'job_id required')
    from cron.jobs import pause_job
    result = pause_job(job_id, reason=body.get('reason'))
    if result: return j(handler, {'ok': True, 'job': result})
    return bad(handler, 'Job not found', 404)


def post_cron_resume(handler, parsed):
    body = read_body(handler)
    job_id = body.get('job_id', '')
    if not job_id: return bad(handler, 'job_id required')
    from cron.jobs import resume_job
    result = resume_job(job_id)
    if result: return j(handler, {'ok': True, 'job': result})
    return bad(handler, 'Job not found', 404)
