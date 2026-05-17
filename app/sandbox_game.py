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
import os
import time
from pathlib import Path
from typing import Any

from videodb import SandboxModel, SandboxTier, connect

from app import immersive_games as ig
from app import videodb_game as vdb

VALID_GAMES = frozenset({"tic_tac_toe", "fps", "car"})

ROOT_DIR = Path(__file__).resolve().parent.parent
USAGE_PATH = ROOT_DIR / "data" / "sandbox_usage.json"
SANDBOX_SESSION_DIR = ROOT_DIR / "data" / "sandbox_sessions"

SANDBOX_HOURLY_USD = {"small": 1.0, "medium": 3.5}
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
    return cfg


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
    """Create sandbox if missing; wait until active."""
    if not vdb.is_videodb_configured():
        return {"ok": False, "error": "VIDEO_DB_API_KEY not configured"}

    tier_name = _tier()

    if session.get("sandbox_id"):
        try:
            conn = _connect()
            sb = conn.get_sandbox(session["sandbox_id"])
            sb.refresh()
            if sb.is_active:
                session["sandbox_status"] = sb.status
                return {"ok": True, "sandbox_id": sb.id, "status": sb.status, "reused": True}
        except Exception:
            pass

    try:
        conn = _connect()
        sandbox = conn.create_sandbox(tier=tier_name)
        session["sandbox_id"] = sandbox.id
        session["sandbox_tier"] = tier_name
        session["sandbox_status"] = sandbox.status
        session["sandbox_started_at"] = time.time()
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
        return {"ok": False, "error": str(e)[:300]}


def generate_flux_turn_art(
    game_type: str,
    state: dict[str, Any],
    move: dict[str, Any],
    coach: ig.CoachResult,
    sandbox_id: str,
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

    prompt = ig.flux_prompt(game_type, state, move, coach)
    try:
        conn = _connect()
        coll = _collection(conn)
        job = coll.generate_image(
            prompt=prompt,
            model_name=SandboxModel.FLUX,
            sandbox_id=sandbox_id,
            config=_flux_config(),
        )
        image = job.wait(timeout=900, interval=5) if hasattr(job, "wait") else job
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
        err = str(e).replace("\n", " ")[:240]
        try:
            conn = _connect()
            coll = _collection(conn)
            url, img_id = vdb._fallback_collection_image(coll)
            if url:
                return {
                    **empty,
                    "image_url": url,
                    "image_id": img_id,
                    "error": f"FLUX failed — collection fallback. ({err})",
                    "fallback": "collection_image",
                }
        except Exception:
            pass
        return {**empty, "error": err}


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
        "turn_media": flux,
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

    flux = generate_flux_turn_art(
        game_type,
        new_state,
        move_records[-1],
        coach,
        sandbox_id or "",
    )
    target = session["moves"][-1]
    target["flux_image_url"] = flux.get("image_url")
    target["flux_image_id"] = flux.get("image_id")
    if flux.get("generation_ok"):
        usage = _session_usage(session)
        usage["flux_images"] = int(usage.get("flux_images", 0)) + 1

    save_session(session_id, session)

    opponent = move_records[1] if len(move_records) > 1 else None
    return _session_response_payload(
        session_id,
        session,
        last_moves=move_records,
        coach=coach,
        flux=flux,
        sandbox_id=sandbox_id,
        opponent_move=opponent,
    )


def play_sandbox_move(session_id: str, cell: int) -> dict[str, Any]:
    return play_sandbox_action(session_id, {"cell": cell})


def finish_sandbox_session(session_id: str) -> dict[str, Any]:
    session = load_session(session_id)
    recap = build_sandbox_recap(session)
    session["recap_stream_url"] = recap.get("stream_url")
    session["recap_player_url"] = recap.get("player_url")
    session["recap_embed_url"] = recap.get("embed_url")
    stop_session_sandbox(session)
    _merge_session_usage_to_global(session)
    save_session(session_id, session)
    return {
        "session_id": session_id,
        "game_type": _normalize_game_type(session.get("game_type")),
        "state": session["state"],
        "winner": session["state"].get("winner"),
        "moves": session["moves"],
        "recap_stream_url": recap.get("stream_url"),
        "recap_player_url": recap.get("player_url"),
        "recap_embed_url": recap.get("embed_url"),
        "recap_error": recap.get("error"),
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
    sandboxes: list[dict[str, str]] = []
    if configured:
        try:
            conn = _connect()
            for sb in conn.list_sandboxes():
                sandboxes.append(
                    {
                        "id": sb.id,
                        "tier": str(sb.tier),
                        "status": str(sb.status),
                        "name": str(getattr(sb, "name", "") or ""),
                    }
                )
        except Exception:
            pass
    return {
        "configured": configured,
        "tier": _tier(),
        "models": {
            "flux": SandboxModel.FLUX.value,
            "omnivoice": SandboxModel.OMNIVOICE.value,
        },
        "sandboxes": sandboxes,
        "games": ig.GAME_CATALOG,
        "docs_url": "https://hackday.videodb.io/sandbox.html",
        "usage": load_global_usage(),
    }
