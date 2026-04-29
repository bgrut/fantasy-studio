"""Pipeline status + analytics endpoints."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter

from ..db import get_conn

router = APIRouter(prefix="/api", tags=["pipeline"])


def _row_to_dict(row):
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _duration_s(created: str | None, updated: str | None) -> float | None:
    t0 = _parse_ts(created)
    t1 = _parse_ts(updated)
    if t0 and t1:
        return max(0, (t1 - t0).total_seconds())
    return None


def _extract_subject(topic: str) -> str:
    """Best-effort subject extraction from a prompt string."""
    topic = topic.strip().lower()
    # remove common leading articles / filler
    topic = re.sub(r"^(a |an |the |my )", "", topic)
    # take first 1-3 words before a preposition
    m = re.match(r"([\w'-]+(?:\s[\w'-]+){0,2}?)(?:\s+(?:in|at|on|over|through|from|racing|soaring|walking|running|jumping|galloping|swimming|flying|cooking|dancing|standing|sitting))", topic)
    if m:
        return m.group(1).strip().title()
    # fallback: first two words
    words = topic.split()[:2]
    return " ".join(words).title()


# ────────────────────────────────────────────────────────────
# GET /api/pipeline/status
# ────────────────────────────────────────────────────────────

@router.get("/pipeline/status")
def pipeline_status():
    with get_conn() as conn:
        # Active (rendering or planning)
        active_row = conn.execute(
            "SELECT * FROM render_jobs WHERE status IN ('rendering','planning') ORDER BY id DESC LIMIT 1"
        ).fetchone()

        # Queued
        queued_rows = conn.execute(
            "SELECT id, topic, template_name, created_at FROM render_jobs WHERE status='queued' ORDER BY id ASC"
        ).fetchall()

        # Recent completed/failed (last 10)
        recent_rows = conn.execute(
            "SELECT * FROM render_jobs WHERE status IN ('complete','failed') ORDER BY id DESC LIMIT 10"
        ).fetchall()

        # Counts
        counts = {}
        for s in ("queued", "planning", "rendering", "complete", "failed"):
            counts[s] = conn.execute(
                "SELECT COUNT(*) c FROM render_jobs WHERE status=?", (s,)
            ).fetchone()["c"]

        total = sum(counts.values())
        completed = counts["complete"]
        failed = counts["failed"]

        # Avg render time (complete jobs only)
        complete_rows = conn.execute(
            "SELECT created_at, updated_at FROM render_jobs WHERE status='complete'"
        ).fetchall()

    durations = []
    for row in complete_rows:
        d = _duration_s(row["created_at"], row["updated_at"])
        if d is not None and d > 0:
            durations.append(d)

    avg_render_time = round(sum(durations) / len(durations), 1) if durations else 0

    # Build active job dict
    active = None
    if active_row:
        d = _row_to_dict(active_row)
        active = {
            "id": d["id"],
            "topic": d["topic"],
            "status": d["status"],
            "template_name": d["template_name"],
            "progress": 0.5 if d["status"] == "rendering" else 0.2,
            "stage": d["status"],
        }

    # Build queued list
    queued = [
        {"id": r["id"], "topic": r["topic"], "created_at": r["created_at"]}
        for r in queued_rows
    ]

    # Build recent list
    recent = []
    for r in recent_rows:
        d = _row_to_dict(r)
        dur = _duration_s(d["created_at"], d["updated_at"])
        recent.append({
            "id": d["id"],
            "topic": d["topic"],
            "status": d["status"],
            "output_url": d.get("output_url"),
            "error": d.get("error_text"),
            "duration_s": round(dur, 1) if dur else None,
            "completed_at": d["updated_at"],
        })

    return {
        "ok": True,
        "active": active,
        "queued": queued,
        "recent": recent,
        "stats": {
            "total_renders": total,
            "completed": completed,
            "failed": failed,
            "queued": counts["queued"],
            "in_progress": counts["rendering"] + counts["planning"],
            "avg_render_time_s": avg_render_time,
            "total_render_time_s": round(sum(durations), 1),
        },
    }


# ────────────────────────────────────────────────────────────
# GET /api/analytics
# ────────────────────────────────────────────────────────────

@router.get("/analytics")
def analytics():
    with get_conn() as conn:
        all_jobs = conn.execute(
            "SELECT * FROM render_jobs ORDER BY id DESC"
        ).fetchall()

    total = len(all_jobs)
    completed = sum(1 for j in all_jobs if j["status"] == "complete")
    failed = sum(1 for j in all_jobs if j["status"] == "failed")
    success_rate = round(completed / max(total, 1), 2)

    # Duration stats
    durations_all = []
    durations_preview = []
    for j in all_jobs:
        if j["status"] != "complete":
            continue
        d = _duration_s(j["created_at"], j["updated_at"])
        if d is not None and d > 0:
            durations_all.append(d)
            tn = j["template_name"] or ""
            pn = j["provider_name"] or ""
            if tn.startswith("preview") or "preview" in pn.lower():
                durations_preview.append(d)

    avg_time = round(sum(durations_all) / len(durations_all), 1) if durations_all else 0
    avg_preview = round(sum(durations_preview) / len(durations_preview), 1) if durations_preview else avg_time

    # Tier breakdown — derive from provider_name or template info
    tier_counter = Counter()
    for j in all_jobs:
        provider = (j["provider_name"] or "") if j["provider_name"] else ""
        pl = provider.lower()
        if "preview" in pl or "eevee" in pl:
            tier_counter["preview"] += 1
        elif "fast" in pl:
            tier_counter["fast"] += 1
        elif "cinematic" in pl:
            tier_counter["cinematic"] += 1
        elif "standard" in pl:
            tier_counter["standard"] += 1
        else:
            tier_counter["preview"] += 1  # default

    # Top subjects
    subject_counter = Counter()
    for j in all_jobs:
        topic = j["topic"] or ""
        if topic:
            subject_counter[_extract_subject(topic)] += 1

    top_subjects = [
        {"subject": s, "count": c}
        for s, c in subject_counter.most_common(10)
    ]

    # Template usage
    template_counter = Counter()
    for j in all_jobs:
        tn = j["template_name"] if j["template_name"] else "auto"
        template_counter[tn] += 1

    # Timeline — renders per hour
    hour_counter: Counter = Counter()
    for j in all_jobs:
        ts = _parse_ts(j["created_at"])
        if ts:
            hour_counter[ts.strftime("%H:00")] += 1

    timeline = sorted(
        [{"hour": h, "count": c} for h, c in hour_counter.items()],
        key=lambda x: x["hour"],
    )

    # Recent activity (last 20)
    recent = []
    for j in all_jobs[:20]:
        d = _row_to_dict(j)
        dur = _duration_s(d["created_at"], d["updated_at"])
        recent.append({
            "id": d["id"],
            "topic": d["topic"],
            "status": d["status"],
            "tier": "preview",
            "template_name": d["template_name"],
            "duration_s": round(dur, 1) if dur else None,
            "timestamp": d["created_at"],
            "output_url": d["output_url"],
            "error": d["error_text"],
        })

    return {
        "ok": True,
        "summary": {
            "total_renders": total,
            "completed": completed,
            "failed": failed,
            "avg_render_time_s": avg_time,
            "avg_preview_time_s": avg_preview,
            "success_rate": success_rate,
        },
        "tier_breakdown": dict(tier_counter),
        "top_subjects": top_subjects,
        "template_usage": dict(template_counter),
        "timeline": timeline,
        "recent": recent,
    }
