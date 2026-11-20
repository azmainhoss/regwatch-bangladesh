"""Notes on which free Gemini keys are used up for today, kept between runs.

Free daily quotas are per key and per model and come back at the same moment for all of them. The notes
live in quota_state.json so a re-run does not knock on keys that are already used up. The page reader
runs in another process and has its own notes; a key it used up shows up here as a refused call.
"""
from datetime import datetime, timedelta, timezone
from typing import Iterable

import common

STATE = common.SCORING_ROOT / "quota_state.json"


def _tag(key: str) -> str:
    return common.sha(key)[:10]


def load(models: Iterable[str]) -> None:
    from backend.app.modules.extraction import vision

    try:
        data = common.read_json(STATE)
    except (OSError, ValueError):
        return
    now = datetime.now(timezone.utc)
    for key in vision.gemini_keys():
        for model in set(models):
            until = data.get(f"{_tag(key)}|{model}")
            if not until:
                continue
            try:
                when = datetime.fromisoformat(until)
            except ValueError:
                continue
            if when > now:
                vision._exhausted_until[(key, model)] = when


def save() -> None:
    from backend.app.modules.extraction import vision

    now = datetime.now(timezone.utc)
    out = {f"{_tag(k)}|{m}": w.isoformat() for (k, m), w in vision._exhausted_until.items() if w > now}
    common.write_json(STATE, out)


def reset_time_text() -> str:
    from backend.app.modules.extraction import vision

    reset = vision._next_quota_reset()
    dhaka = reset.astimezone(timezone(timedelta(hours=6)))
    return f"{dhaka.strftime('%H:%M')} Bangladesh time ({reset.strftime('%H:%M')} UTC)"
