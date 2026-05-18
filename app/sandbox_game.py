"""
Hackathon sandbox compute for immersive tic-tac-toe.

Flow (see https://hackday.videodb.io/sandbox.html):
  1. create_sandbox → wait_for_ready
  2. Per turn: FLUX board art + minimax coach (VideoDB-hosted inference)
  3. Game end: OmniVoice narration + Timeline recap → cloud stream
  4. stop sandbox + record usage credits
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from videodb import SandboxModel, SandboxTier, connect

from app import immersive_games as ig
from app import videodb_game as vdb

VALID_GAMES = frozenset({"tic_tac_toe", "fps", "car"})

ROOT_DIR = Path(__file__).resolve().parent.parent
BAD_SANDBOXES_PATH = ROOT_DIR / "data" / "bad_sandboxes.json"
USAGE_PATH = ROOT_DIR / "data" / "sandbox_usage.json"
SANDBOX_SESSION_DIR = ROOT_DIR / "data" / "sandbox_sessions"

SANDBOX_HOURLY_USD = {"small": 1.0, "medium": 3.5}
TIER_ACTIVE_LIMIT = {"small": 3, "medium": 3}
DEFAULT_TIER = "medium"
DEFAULT_IDLE_TIMEOUT = 600


def _load_env() -> None:
    vdb._load_env()


def _tier() -> str:
    _load_env()
    raw = (os.getenv("VIDEODB_SANDBOX_TIER") or DEFAULT_TIER).strip().lower()
    return raw if raw in SANDBOX_HOURLY_USD else DEFAULT_TIER


def _idle_timeout() -> int:
    _load_env()
    try:
        return max(60, int(os.getenv("VIDEODB_SANDBOX_IDLE_TIMEOUT") or DEFAULT_IDLE_TIMEOUT))
    except ValueError:
        return DEFAULT_IDLE_TIMEOUT


def _flux_config() -> dict[str, Any]:
    _load_env()
    size = (os.getenv("VIDEODB_SANDBOX_FLUX_SIZE") or "1280x720").strip()
    steps = os.getenv("VIDEODB_SANDBOX_FLUX_STEPS")
    cfg: dict[str, Any] = {"size": size}
    if steps:
        try:
            cfg["num_inference_steps"] = int(steps)
        except ValueError:
            pass
    elif os.getenv("RENDER") or (
        (os.getenv("SANDBOX_ASYNC_FLUX") or "").lower() in ("1", "true", "yes")
    ):
        cfg["num_inference_steps"] = 12
    return cfg


def _use_async_flux() -> bool:
    """Render free tier times out HTTP at ~30s; FLUX often needs longer."""
    _load_env()
    raw = (os.getenv("SANDBOX_ASYNC_FLUX") or "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes"):
        return True
    return bool(os.getenv("RENDER"))


def _clean_error(err: str) -> str:
    text = (err or "").replace("\n", " ").strip()
    if text.endswith(": None") or text.endswith(": none"):
        text = text.rsplit(":", 1)[0].strip() or "VideoDB request failed"
    return text[:240]


def _ensure_sandbox_ready(sandbox_id: str) -> None:
    conn = _connect()
    sb = conn.get_sandbox(sandbox_id)
    sb.refresh()
    if not sb.is_active:
        sb.wait_for_ready(timeout=180, interval=5)


def session_path(session_id: str) -> Path:
    SANDBOX_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SANDBOX_SESSION_DIR / f"{session_id}.json"


def save_session(session_id: str, payload: dict[str, Any]) -> Path:
    path = session_path(session_id)
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_session(session_id: str) -> dict[str, Any]:
    path = session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Sandbox session {session_id} not found")
    return json.loads(path.read_text())


def _empty_usage() -> dict[str, Any]:
    return {
        "flux_images": 0,
        "omnivoice_jobs": 0,
        "timelines": 0,
        "sandbox_seconds": 0.0,
        "estimated_usd": 0.0,
        "sessions": 0,
    }


def load_global_usage() -> dict[str, Any]:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not USAGE_PATH.exists():
        return _empty_usage()
    try:
        data = json.loads(USAGE_PATH.read_text())
    except json.JSONDecodeError:
        data = _empty_usage()
    for key, val in _empty_usage().items():
        data.setdefault(key, val)
    return data


def save_global_usage(data: dict[str, Any]) -> None:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_PATH.write_text(json.dumps(data, indent=2))


def _estimate_sandbox_cost(seconds: float, tier: str) -> float:
    rate = SANDBOX_HOURLY_USD.get(tier, SANDBOX_HOURLY_USD["medium"])
    return round((seconds / 3600.0) * rate, 4)


def _session_usage(session: dict[str, Any]) -> dict[str, Any]:
    usage = session.setdefault("usage", _empty_usage())
    for key, val in _empty_usage().items():
        if key not in usage:
            usage[key] = val
    return usage


def _record_sandbox_runtime(session: dict[str, Any]) -> None:
    started = session.get("sandbox_started_at")
    if not started:
        return
    elapsed = max(0.0, time.time() - float(started))
    usage = _session_usage(session)
    usage["sandbox_seconds"] = round(float(usage.get("sandbox_seconds", 0)) + elapsed, 2)
    tier = session.get("sandbox_tier") or _tier()
    usage["estimated_usd"] = round(
        float(usage.get("estimated_usd", 0)) + _estimate_sandbox_cost(elapsed, tier),
        4,
    )
    session["sandbox_started_at"] = time.time()


def _merge_session_usage_to_global(session: dict[str, Any]) -> None:
    global_u = load_global_usage()
    su = _session_usage(session)
    global_u["flux_images"] = int(global_u.get("flux_images", 0)) + int(su.get("flux_images", 0))
    global_u["omnivoice_jobs"] = int(global_u.get("omnivoice_jobs", 0)) + int(
        su.get("omnivoice_jobs", 0)
    )
    global_u["timelines"] = int(global_u.get("timelines", 0)) + int(su.get("timelines", 0))
    global_u["sandbox_seconds"] = round(
        float(global_u.get("sandbox_seconds", 0)) + float(su.get("sandbox_seconds", 0)),
        2,
    )
    global_u["estimated_usd"] = round(
        float(global_u.get("estimated_usd", 0)) + float(su.get("estimated_usd", 0)),
        4,
    )
    global_u["sessions"] = int(global_u.get("sessions", 0)) + 1
    save_global_usage(global_u)


def _connect():
    return connect()


def _collection(conn):
    return vdb._collection(conn)


def _tier_limit(tier: str) -> int:
    return TIER_ACTIVE_LIMIT.get(tier.lower(), 3)


def _tier_matches(sb: Any, tier: str) -> bool:
    st = str(getattr(sb, "tier", "") or "").lower()
    want = tier.lower()
    return st == want or st.endswith(want)


def _load_bad_sandbox_ids() -> set[str]:
    if not BAD_SANDBOXES_PATH.exists():
        return set()
    try:
        data = json.loads(BAD_SANDBOXES_PATH.read_text())
        return {str(x) for x in data if x}
    except (json.JSONDecodeError, TypeError):
        return set()


def _mark_sandbox_bad(sandbox_id: str) -> None:
    if not sandbox_id:
        return
    bad = _load_bad_sandbox_ids()
    bad.add(sandbox_id)
    BAD_SANDBOXES_PATH.parent.mkdir(parents=True, exist_ok=True)
    BAD_SANDBOXES_PATH.write_text(json.dumps(sorted(bad), indent=2))


def _is_sandbox_bad(sandbox_id: str | None) -> bool:
    return bool(sandbox_id and sandbox_id in _load_bad_sandbox_ids())


def _pick_reusable_sandbox(conn: Any, tier: str) -> Any | None:
    active = _list_active_for_tier(conn, tier)
    good = [sb for sb in active if not _is_sandbox_bad(sb.id)]
    return good[-1] if good else None


def _list_active_for_tier(conn: Any, tier: str) -> list[Any]:
    out: list[Any] = []
    for sb in conn.list_sandboxes():
        try:
            sb.refresh()
        except Exception:
            pass
        if _tier_matches(sb, tier) and sb.is_active:
            out.append(sb)
    return out


def _rotate_sandbox(session: dict[str, Any]) -> dict[str, Any]:
    """Mark current sandbox unhealthy and attach a fresh medium pool."""
    old = session.get("sandbox_id")
    if old:
        _mark_sandbox_bad(old)
        try:
            _stop_sandbox_by_id(_connect(), old)
        except Exception:
            pass
    session.pop("sandbox_id", None)
    session["sandbox_status"] = None
    return provision_sandbox(session)


def _attach_sandbox_to_session(session: dict[str, Any], sb: Any, *, reused: bool) -> dict[str, Any]:
    session["sandbox_id"] = sb.id
    session["sandbox_tier"] = _tier()
    session["sandbox_status"] = sb.status
    session["sandbox_stopped"] = False
    if not session.get("sandbox_started_at"):
        session["sandbox_started_at"] = time.time()
    return {
        "ok": True,
        "sandbox_id": sb.id,
        "status": sb.status,
        "tier": _tier(),
        "reused": reused,
    }


def _stop_sandbox_by_id(conn: Any, sandbox_id: str) -> bool:
    try:
        sb = conn.get_sandbox(sandbox_id)
        sb.stop(grace=True)
        try:
            sb.wait_for_stop(timeout=120, interval=5)
        except Exception:
            pass
        return True
    except Exception:
        return False


def cleanup_extra_sandboxes(keep: int = 0, tier: str | None = None) -> dict[str, Any]:
    """Stop active sandboxes on the account until at most `keep` remain (same tier)."""
    if not vdb.is_videodb_configured():
        return {"ok": False, "error": "VIDEO_DB_API_KEY not configured"}
    tier_name = (tier or _tier()).lower()
    keep = max(0, int(keep))
    try:
        conn = _connect()
        active = _list_active_for_tier(conn, tier_name)
        to_stop = active[:-keep] if keep else active
        stopped: list[str] = []
        for sb in to_stop:
            if _stop_sandbox_by_id(conn, sb.id):
                stopped.append(sb.id)
        remaining = _list_active_for_tier(conn, tier_name)
        return {
            "ok": True,
            "tier": tier_name,
            "stopped": stopped,
            "stopped_count": len(stopped),
            "active_remaining": len(remaining),
            "limit": _tier_limit(tier_name),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _sandbox_is_active(session: dict[str, Any]) -> bool:
    sandbox_id = session.get("sandbox_id")
    if not sandbox_id:
        return False
    try:
        sb = _connect().get_sandbox(sandbox_id)
        sb.refresh()
        session["sandbox_status"] = sb.status
        return bool(sb.is_active)
    except Exception:
        return session.get("sandbox_status") == "active"


def _normalize_game_type(game_type: str | None) -> str:
    g = (game_type or "tic_tac_toe").strip().lower()
    return g if g in VALID_GAMES else "tic_tac_toe"


def provision_sandbox(session: dict[str, Any]) -> dict[str, Any]:
    """Reuse an active sandbox when possible; create only if under tier limit."""
    if not vdb.is_videodb_configured():
        return {"ok": False, "error": "VIDEO_DB_API_KEY not configured"}

    tier_name = _tier()
    limit = _tier_limit(tier_name)

    try:
        conn = _connect()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    sandbox_id = session.get("sandbox_id")
    if sandbox_id and _is_sandbox_bad(sandbox_id):
        session.pop("sandbox_id", None)
        sandbox_id = None
    if sandbox_id:
        try:
            sb = conn.get_sandbox(sandbox_id)
            sb.refresh()
            if sb.is_active:
                session["sandbox_status"] = sb.status
                return _attach_sandbox_to_session(session, sb, reused=True)
        except Exception:
            pass

    reusable = _pick_reusable_sandbox(conn, tier_name)
    if reusable:
        return _attach_sandbox_to_session(session, reusable, reused=True)

    active = _list_active_for_tier(conn, tier_name)
    if len(active) >= limit:
        cleanup_extra_sandboxes(keep=max(0, limit - 1), tier=tier_name)
        reusable = _pick_reusable_sandbox(conn, tier_name)
        if reusable:
            return _attach_sandbox_to_session(session, reusable, reused=True)

    try:
        sandbox = conn.create_sandbox(tier=tier_name)
        session["sandbox_id"] = sandbox.id
        session["sandbox_tier"] = tier_name
        session["sandbox_status"] = sandbox.status
        session["sandbox_started_at"] = time.time()
        session["sandbox_stopped"] = False
        sandbox.wait_for_ready(timeout=300, interval=5)
        session["sandbox_status"] = sandbox.status
        return {
            "ok": True,
            "sandbox_id": sandbox.id,
            "status": sandbox.status,
            "tier": tier_name,
            "reused": False,
        }
    except Exception as e:
        err = str(e)
        if "Maximum active sandboxes" in err:
            cleanup = cleanup_extra_sandboxes(keep=1, tier=tier_name)
            reusable = _pick_reusable_sandbox(conn, tier_name)
            if reusable:
                return _attach_sandbox_to_session(session, reusable, reused=True)
            if cleanup.get("stopped_count", 0) > 0:
                try:
                    sandbox = conn.create_sandbox(tier=tier_name)
                    session["sandbox_id"] = sandbox.id
                    session["sandbox_tier"] = tier_name
                    session["sandbox_status"] = sandbox.status
                    session["sandbox_started_at"] = time.time()
                    session["sandbox_stopped"] = False
                    sandbox.wait_for_ready(timeout=300, interval=5)
                    session["sandbox_status"] = sandbox.status
                    return {
                        "ok": True,
                        "sandbox_id": sandbox.id,
                        "status": sandbox.status,
                        "tier": tier_name,
                        "reused": False,
                        "cleaned_up": cleanup.get("stopped"),
                    }
                except Exception as e2:
                    err = str(e2)
            return {
                "ok": False,
                "error": (
                    f"{err[:200]} — stopped {cleanup.get('stopped_count', 0)} sandbox(es) "
                    f"but still at limit. Use Usage → Free sandbox slots."
                ),
                "cleanup": cleanup,
            }
        return {"ok": False, "error": err[:300]}


def generate_flux_turn_art(
    game_type: str,
    state: dict[str, Any],
    move: dict[str, Any],
    coach: ig.CoachResult,
    sandbox_id: str,
    session: dict[str, Any] | None = None,
    *,
    _retried: bool = False,
) -> dict[str, Any]:
    """FLUX image on sandbox compute for the completed turn."""
    empty: dict[str, Any] = {
        "image_url": None,
        "image_id": None,
        "error": None,
        "generation_ok": False,
    }
    if not sandbox_id:
        return {**empty, "error": "No active sandbox"}

    prompt = ig.flux_prompt(game_type, state, move, coach)[:2000]
    cfg = _flux_config()
    try:
        _ensure_sandbox_ready(sandbox_id)
        conn = _connect()
        coll = _collection(conn)
        image = coll.generate_image(
            prompt=prompt,
            aspect_ratio="16:9",
            model_name=SandboxModel.FLUX,
            sandbox_id=sandbox_id,
            config=cfg if cfg else None,
            wait=True,
            timeout=900,
            poll_interval=5,
        )
        if not image or not getattr(image, "id", None):
            raise ValueError("FLUX returned no image")
        url = vdb._resolve_image_url(image)
        if not url:
            raise ValueError("Image URL not ready")
        return {
            **empty,
            "image_url": url,
            "image_id": image.id,
            "generation_ok": True,
        }
    except Exception as e:
        err = _clean_error(str(e))
        stale = (
            "invalid request" in err.lower()
            or "no image" in err.lower()
            or "failed" in err.lower()
        )
        if session is not None and stale and not _retried:
            prov = _rotate_sandbox(session)
            if prov.get("ok") and session.get("sandbox_id"):
                return generate_flux_turn_art(
                    game_type,
                    state,
                    move,
                    coach,
                    session["sandbox_id"],
                    session=session,
                    _retried=True,
                )
        try:
            conn = _connect()
            coll = _collection(conn)
            url, img_id = vdb._fallback_collection_image(coll)
            if url:
                note = (
                    "Sandbox was rotated — showing a collection still."
                    if _retried
                    else f"Using collection image (FLUX: {err})"
                )
                return {
                    **empty,
                    "image_url": url,
                    "image_id": img_id,
                    "error": note,
                    "fallback": "collection_image",
                    "generation_ok": False,
                }
        except Exception:
            pass
        return {**empty, "error": err or "FLUX generation failed"}


def build_sandbox_recap(session: dict[str, Any]) -> dict[str, Any]:
    """OmniVoice + per-move FLUX stills on a VideoDB Timeline (sandbox compute)."""
    empty: dict[str, Any] = {
        "stream_url": None,
        "player_url": None,
        "embed_url": None,
        "error": None,
    }
    moves = session.get("moves", [])
    if not moves:
        return {**empty, "error": "No moves to compile"}
    sandbox_id = session.get("sandbox_id")
    if not sandbox_id:
        return {**empty, "error": "Sandbox not provisioned"}

    try:
        from videodb.editor import AudioAsset, Clip, Fit, ImageAsset, Timeline, Track

        conn = _connect()
        coll = _collection(conn)

        game_type = _normalize_game_type(session.get("game_type"))
        winner = session.get("state", {}).get("winner")
        titles = {g["id"]: g["title"] for g in ig.GAME_CATALOG}
        lines = [f"{titles.get(game_type, game_type)} immersive recap."]
        if winner and winner not in ("draw", None):
            lines.append(f"Outcome: {winner}.")
        elif winner == "draw":
            lines.append("The session ended in a draw.")
        for move in moves:
            lines.append(ig.recap_script_line(game_type, move))
        script = " ".join(lines)

        audio_job = coll.generate_voice(
            text=script[:4000],
            model_name=SandboxModel.OMNIVOICE,
            sandbox_id=sandbox_id,
            config={
                "instructions": "female, young adult, calm sports broadcaster, energetic but clear",
            },
        )
        audio = audio_job.wait(timeout=900, interval=5)
        audio_len = float(getattr(audio, "length", 0) or 0)
        if audio_len <= 0:
            audio_len = max(3.0 * len(moves), 12.0)

        per_move = audio_len / max(len(moves), 1)

        timeline = Timeline(conn)
        timeline.resolution = "1280x720"
        timeline.background = "#000000"

        image_track = Track()
        audio_track = Track()
        cursor = 0.0
        placed = False

        for move in moves:
            img_id = move.get("flux_image_id")
            dur = per_move
            if img_id:
                image_track.add_clip(
                    cursor,
                    Clip(
                        asset=ImageAsset(id=img_id),
                        duration=dur,
                        fit=Fit.crop,
                    ),
                )
                placed = True
            cursor += dur

        if not placed:
            return {**empty, "error": "No FLUX images on moves — play at least one turn first"}

        audio_track.add_clip(0, Clip(asset=AudioAsset(id=audio.id), duration=audio_len))
        timeline.add_track(image_track)
        timeline.add_track(audio_track)

        stream = timeline.generate_stream()
        pl = vdb.player_payload(stream, getattr(timeline, "player_url", None))
        usage = _session_usage(session)
        usage["omnivoice_jobs"] = int(usage.get("omnivoice_jobs", 0)) + 1
        usage["timelines"] = int(usage.get("timelines", 0)) + 1
        return {**pl, "error": None, "audio_id": audio.id, "duration": audio_len}
    except Exception as e:
        return {**empty, "error": str(e)[:300]}


def stop_session_sandbox(session: dict[str, Any]) -> dict[str, Any]:
    _record_sandbox_runtime(session)
    sandbox_id = session.get("sandbox_id")
    if not sandbox_id:
        return {"ok": True, "stopped": False}
    try:
        conn = _connect()
        sb = conn.get_sandbox(sandbox_id)
        sb.stop(grace=True)
        try:
            sb.wait_for_stop(timeout=180, interval=5)
        except Exception:
            pass
        session["sandbox_status"] = getattr(sb, "status", "stopped")
        return {"ok": True, "stopped": True, "status": session["sandbox_status"]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    finally:
        session["sandbox_stopped"] = True


def get_usage_payload(session_id: str | None = None) -> dict[str, Any]:
    global_u = load_global_usage()
    session_u: dict[str, Any] | None = None
    if session_id:
        try:
            session = load_session(session_id)
            session_u = _session_usage(session)
            if session.get("sandbox_started_at") and not session.get("sandbox_stopped"):
                live = dict(session_u)
                elapsed = time.time() - float(session["sandbox_started_at"])
                tier = session.get("sandbox_tier") or _tier()
                live["sandbox_seconds"] = round(
                    float(live.get("sandbox_seconds", 0)) + elapsed, 2
                )
                live["estimated_usd"] = round(
                    float(live.get("estimated_usd", 0))
                    + _estimate_sandbox_cost(elapsed, tier),
                    4,
                )
                session_u = live
        except FileNotFoundError:
            session_u = None

    return {
        "ok": True,
        "pricing": {
            "sandbox_small_per_hour": SANDBOX_HOURLY_USD["small"],
            "sandbox_medium_per_hour": SANDBOX_HOURLY_USD["medium"],
            "note": "Hackathon credits: ~$1000/team. Stop sandbox when idle.",
        },
        "global": global_u,
        "session": session_u,
        "active_tier": _tier(),
    }


def _session_response_payload(
    session_id: str,
    session: dict[str, Any],
    *,
    last_moves: list[dict[str, Any]],
    coach: ig.CoachResult,
    flux: dict[str, Any],
    sandbox_id: str | None,
    opponent_move: dict[str, Any] | None = None,
) -> dict[str, Any]:
    game_type = _normalize_game_type(session.get("game_type"))
    st = session["state"]
    last = last_moves[-1] if last_moves else {}
    flux_media = dict(flux) if isinstance(flux, dict) else flux
    if isinstance(flux_media, dict) and flux_media.get("flux_pending"):
        flux_media = {**flux_media, "flux_pending": True}

    payload: dict[str, Any] = {
        "session_id": session_id,
        "game_type": game_type,
        "state": st,
        "finished": st.get("finished", False),
        "winner": st.get("winner"),
        "last_move": last,
        "opponent_move": opponent_move,
        "moves_logged": last_moves,
        "suggestion_text": coach.suggestion_text,
        "suggested_action": coach.suggested_action,
        "turn_media": flux_media,
        "flux_pending": bool(
            isinstance(flux_media, dict) and flux_media.get("flux_pending")
        ),
        "sandbox_id": sandbox_id,
        "sandbox_status": session.get("sandbox_status"),
        "usage": _session_usage(session),
        "games": ig.GAME_CATALOG,
    }
    if game_type == "tic_tac_toe":
        payload["board"] = st.get("board", [])
        payload["current_player"] = st.get("current_player")
        payload["highlight_cell"] = coach.highlight
    else:
        payload["board"] = None
        payload["current_player"] = None
        payload["highlight_cell"] = None
    return payload


def start_sandbox_session(game_type: str = "tic_tac_toe") -> dict[str, Any]:
    import uuid

    game_type = _normalize_game_type(game_type)
    session_id = str(uuid.uuid4())[:8]
    session: dict[str, Any] = {
        "session_id": session_id,
        "kind": "sandbox",
        "game_type": game_type,
        "state": ig.initial_state(game_type),
        "moves": [],
        "usage": _empty_usage(),
        "sandbox_id": None,
        "sandbox_tier": _tier(),
        "sandbox_status": None,
        "sandbox_started_at": None,
        "sandbox_stopped": False,
        "recap_stream_url": None,
        "recap_player_url": None,
        "recap_embed_url": None,
    }
    prov = provision_sandbox(session)
    save_session(session_id, session)
    st = session["state"]
    return {
        "session_id": session_id,
        "game_type": game_type,
        "state": st,
        "board": st.get("board"),
        "current_player": st.get("current_player"),
        "sandbox": prov,
        "usage": _session_usage(session),
        "games": ig.GAME_CATALOG,
    }


def _apply_flux_to_session_move(session_id: str) -> None:
    """Background worker: generate FLUX for the latest move and persist."""
    try:
        session = load_session(session_id)
        game_type = _normalize_game_type(session.get("game_type"))
        moves = session.get("moves") or []
        if not moves:
            return
        target = moves[-1]
        if target.get("flux_status") == "done":
            return
        sandbox_id = session.get("sandbox_id")
        if not sandbox_id:
            target["flux_status"] = "failed"
            target["flux_error"] = "No sandbox"
            save_session(session_id, session)
            return
        coach = ig.CoachResult(
            narrative=target.get("narrative") or "",
            suggestion_text=target.get("suggestion_text") or "",
            suggested_action=target.get("suggested_action") or "",
            highlight=target.get("highlight_cell"),
        )
        flux = generate_flux_turn_art(
            game_type,
            session["state"],
            target,
            coach,
            sandbox_id,
            session=session,
        )
        target["flux_image_url"] = flux.get("image_url")
        target["flux_image_id"] = flux.get("image_id")
        target["flux_status"] = "done" if flux.get("image_url") else "failed"
        target["flux_error"] = flux.get("error")
        if flux.get("generation_ok"):
            usage = _session_usage(session)
            usage["flux_images"] = int(usage.get("flux_images", 0)) + 1
        save_session(session_id, session)
    except Exception as e:
        logger.exception("FLUX background job failed for %s", session_id)
        try:
            session = load_session(session_id)
            if session.get("moves"):
                session["moves"][-1]["flux_status"] = "failed"
                session["moves"][-1]["flux_error"] = _clean_error(str(e))
                save_session(session_id, session)
        except Exception:
            pass


def _schedule_flux_job(session_id: str) -> None:
    thread = threading.Thread(
        target=_apply_flux_to_session_move,
        args=(session_id,),
        daemon=True,
        name=f"flux-{session_id}",
    )
    thread.start()


def play_sandbox_action(session_id: str, action: dict[str, Any]) -> dict[str, Any]:
    session = load_session(session_id)
    game_type = _normalize_game_type(session.get("game_type"))

    new_state, move_records, coach = ig.apply_action(
        game_type, session["state"], action
    )
    session["state"] = new_state
    session["moves"].extend(move_records)

    sandbox_id = session.get("sandbox_id")
    if not _sandbox_is_active(session):
        prov = provision_sandbox(session)
        if not prov.get("ok"):
            save_session(session_id, session)
            raise ValueError(prov.get("error") or "Sandbox not available")
        sandbox_id = session.get("sandbox_id")

    flux: dict[str, Any]
    flux_pending = False
    if _use_async_flux():
        for m in move_records:
            m["flux_status"] = "pending"
        flux = {
            "image_url": None,
            "image_id": None,
            "error": None,
            "generation_ok": None,
            "flux_pending": True,
        }
        flux_pending = True
        save_session(session_id, session)
        _schedule_flux_job(session_id)
    else:
        flux = generate_flux_turn_art(
            game_type,
            new_state,
            move_records[-1],
            coach,
            sandbox_id or "",
            session=session,
        )
        target = session["moves"][-1]
        target["flux_image_url"] = flux.get("image_url")
        target["flux_image_id"] = flux.get("image_id")
        target["flux_status"] = "done" if flux.get("image_url") else "failed"
        if flux.get("generation_ok"):
            usage = _session_usage(session)
            usage["flux_images"] = int(usage.get("flux_images", 0)) + 1
        save_session(session_id, session)

    opponent = move_records[1] if len(move_records) > 1 else None
    payload = _session_response_payload(
        session_id,
        session,
        last_moves=move_records,
        coach=coach,
        flux=flux,
        sandbox_id=sandbox_id,
        opponent_move=opponent,
    )
    payload["flux_pending"] = flux_pending
    return payload


def play_sandbox_move(session_id: str, cell: int) -> dict[str, Any]:
    return play_sandbox_action(session_id, {"cell": cell})


def _apply_recap_to_session(session_id: str) -> None:
    """Background worker: OmniVoice + timeline recap."""
    try:
        session = load_session(session_id)
        session["recap_status"] = "building"
        save_session(session_id, session)
        recap = build_sandbox_recap(session)
        session["recap_stream_url"] = recap.get("stream_url")
        session["recap_player_url"] = recap.get("player_url")
        session["recap_embed_url"] = recap.get("embed_url")
        session["recap_error"] = recap.get("error")
        session["recap_status"] = "done" if recap.get("stream_url") else "failed"
        stop_session_sandbox(session)
        _merge_session_usage_to_global(session)
        save_session(session_id, session)
    except Exception as e:
        logger.exception("Recap background job failed for %s", session_id)
        try:
            session = load_session(session_id)
            session["recap_status"] = "failed"
            session["recap_error"] = _clean_error(str(e))
            save_session(session_id, session)
        except Exception:
            pass


def _schedule_recap_job(session_id: str) -> None:
    thread = threading.Thread(
        target=_apply_recap_to_session,
        args=(session_id,),
        daemon=True,
        name=f"recap-{session_id}",
    )
    thread.start()


def _use_async_recap() -> bool:
    return _use_async_flux()


def finish_sandbox_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    game_type = _normalize_game_type(session.get("game_type"))
    winner = session["state"].get("winner")

    if _use_async_recap():
        session["recap_status"] = "pending"
        save_session(session_id, session)
        _schedule_recap_job(session_id)
        return {
            "session_id": session_id,
            "game_type": game_type,
            "state": session["state"],
            "winner": winner,
            "moves": session["moves"],
            "recap_stream_url": None,
            "recap_player_url": None,
            "recap_embed_url": None,
            "recap_error": None,
            "recap_pending": True,
            "usage": _session_usage(session),
            "global_usage": load_global_usage(),
            "message": "Building cloud recap on sandbox (1–3 min)…",
        }

    recap = build_sandbox_recap(session)
    session["recap_stream_url"] = recap.get("stream_url")
    session["recap_player_url"] = recap.get("player_url")
    session["recap_embed_url"] = recap.get("embed_url")
    session["recap_status"] = "done" if recap.get("stream_url") else "failed"
    session["recap_error"] = recap.get("error")
    stop_session_sandbox(session)
    _merge_session_usage_to_global(session)
    save_session(session_id, session)
    return {
        "session_id": session_id,
        "game_type": game_type,
        "state": session["state"],
        "winner": winner,
        "moves": session["moves"],
        "recap_stream_url": recap.get("stream_url"),
        "recap_player_url": recap.get("player_url"),
        "recap_embed_url": recap.get("embed_url"),
        "recap_error": recap.get("error"),
        "recap_pending": False,
        "usage": _session_usage(session),
        "global_usage": load_global_usage(),
        "message": (
            "Sandbox recap ready in VideoDB cloud."
            if recap.get("stream_url")
            else recap.get("error") or "Recap failed"
        ),
    }


def get_status_payload() -> dict[str, Any]:
    configured = vdb.is_videodb_configured()
    tier_name = _tier()
    limit = _tier_limit(tier_name)
    sandboxes: list[dict[str, str]] = []
    active_count = 0
    if configured:
        try:
            conn = _connect()
            for sb in conn.list_sandboxes():
                try:
                    sb.refresh()
                except Exception:
                    pass
                st = str(sb.status)
                is_active = sb.is_active
                if _tier_matches(sb, tier_name) and is_active:
                    active_count += 1
                sandboxes.append(
                    {
                        "id": sb.id,
                        "tier": str(sb.tier),
                        "status": st,
                        "name": str(getattr(sb, "name", "") or ""),
                        "is_active": is_active,
                    }
                )
        except Exception:
            pass
    return {
        "configured": configured,
        "tier": tier_name,
        "active_limit": limit,
        "active_count": active_count,
        "at_limit": active_count >= limit,
        "models": {
            "flux": SandboxModel.FLUX.value,
            "omnivoice": SandboxModel.OMNIVOICE.value,
        },
        "sandboxes": sandboxes,
        "games": ig.GAME_CATALOG,
        "docs_url": "https://hackday.videodb.io/sandbox.html",
        "usage": load_global_usage(),
    }
