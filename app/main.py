"""
Tic-tac-toe + VideoDB play-by-play API.

Run: uvicorn app.main:app --reload --port 8765
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.game_engine import GameState, apply_move, suggest_move
from app.models import (
    AttachCaptureRequest,
    FinishResponse,
    MoveRecord,
    MoveRequest,
    MoveResponse,
    SandboxActionRequest,
    SandboxActionResponse,
    SandboxFinishResponse,
    SandboxStartRequest,
    SandboxStartResponse,
    SearchFootageRequest,
    StartSessionResponse,
    TurnMedia,
)
from app import videodb_game as vdb
from app import sandbox_game as sandbox

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

vdb._load_env()


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    if not raw or raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="VideoDB Tic-Tac-Toe",
    description="Play-by-play tic-tac-toe with VideoDB move clips and recap",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

_serve_static = os.getenv("SERVE_STATIC", "true").lower() in ("1", "true", "yes")
if _serve_static and STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _new_session(capture_mode: bool = False) -> dict[str, Any]:
    session_id = str(uuid.uuid4())[:8]
    state = GameState()
    return {
        "session_id": session_id,
        "state": {
            "board": state.board,
            "current_player": state.current_player,
            "move_number": state.move_number,
            "winner": state.winner,
            "finished": state.finished,
        },
        "moves": [],
        "capture_mode": capture_mode,
        "capture_video_id": None,
        "session_started_at": time.time(),
        "scene_index_id": None,
    }


def _state_from_dict(data: dict[str, Any]) -> GameState:
    s = GameState()
    s.board = list(data["board"])
    s.current_player = data["current_player"]
    s.move_number = data["move_number"]
    s.winner = data.get("winner")
    s.finished = data["finished"]
    return s


def _move_to_record(
    analysis,
    move_number: int,
    *,
    scene_start: float | None = None,
    scene_end: float | None = None,
    media: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m = media or {}
    return {
        "move_number": move_number,
        "player": analysis.player,
        "cell": analysis.cell,
        "board_after": [str(c) for c in analysis.board_after],
        "suggested_cell": analysis.suggested_cell,
        "suggestion_text": analysis.suggestion_text,
        "narrative": analysis.narrative,
        "blunder": analysis.blunder,
        "suggestion_stream_url": m.get("suggestion_stream_url"),
        "suggestion_player_url": m.get("suggestion_player_url"),
        "suggestion_image_url": m.get("suggestion_image_url"),
        "suggestion_image_id": m.get("suggestion_image_id"),
        "suggestion_video_id": m.get("suggestion_video_id"),
        "scene_start": scene_start,
        "scene_end": scene_end,
    }


@app.get("/")
async def index():
    if not _serve_static:
        return {
            "message": "API only — open the Vercel frontend.",
            "health": "/api/health",
        }
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Place frontend in static/index.html"}


@app.get("/api/health")
async def health():
    mode = vdb.get_media_mode()
    gen = vdb.get_generation_status()
    if vdb.is_videodb_configured() and mode.value == "economy":
        try:
            inv = vdb.get_collection_inventory()
            if inv.get("ok"):
                gen = {
                    **gen,
                    "collection_images": inv.get("image_count", 0),
                    "collection_videos": inv.get("video_count", 0),
                }
        except Exception:
            pass
    return {
        "ok": True,
        "videodb_configured": vdb.is_videodb_configured(),
        "media_mode": mode.value,
        "recap_mode": vdb.get_recap_mode(),
        "generation": gen,
        "cost_hint": (
            "economy + local recap: zero VideoDB generative calls. "
            "Set VIDEODB_RECAP=cloud only if you need a hosted timeline video."
        ),
    }


@app.get("/api/videodb/status")
async def videodb_status():
    """VideoDB connection, config, and capability info for the sidebar."""
    return vdb.get_status_payload()


@app.get("/api/videodb/hub")
async def videodb_hub(session_id: str | None = None):
    """Play with VideoDB: connection, capabilities, docs, hackathon use cases."""
    return vdb.get_hub_payload(session_id)


@app.get("/api/videodb/panel")
async def videodb_panel(session_id: str | None = None):
    """Unified VideoDB sidebar: hub + collection videos + action flags."""
    return vdb.get_videodb_panel(session_id)


@app.get("/api/videodb/collection")
async def videodb_collection_inventory():
    """Manifest of the configured hackathon collection (visible in VideoDB Console)."""
    result = vdb.get_collection_inventory()
    if not result.get("ok"):
        raise HTTPException(404, result.get("error") or "Collection unavailable")
    return result


@app.get("/api/videodb/video/{video_id}/player")
async def videodb_video_player(video_id: str):
    """Resolve stream + player.videodb.io URLs for a collection video."""
    result = vdb.get_video_player(video_id)
    if not result.get("ok"):
        raise HTTPException(404, result.get("error") or "Video not found")
    return result


@app.post("/api/session/{session_id}/search-footage")
async def search_footage(session_id: str, body: SearchFootageRequest):
    """Semantic search on indexed capture video for this session."""
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None
    return vdb.search_session_footage(session, body.query)


@app.post("/api/videodb/test-connection")
async def videodb_test_connection():
    """Explicit connection test (calls VideoDB connect + get_collection)."""
    result = vdb.test_connection()
    if not result.get("ok"):
        raise HTTPException(
            503,
            result.get("error") or "VideoDB connection failed",
        )
    return result


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None
    return {
        "session_id": session_id,
        "state": session["state"],
        "moves": session["moves"],
        "move_count": len(session["moves"]),
        "capture_video_id": session.get("capture_video_id"),
        "scene_index_id": session.get("scene_index_id"),
        "log_path": str(vdb.session_path(session_id)),
    }


@app.post("/api/session/{session_id}/index-capture")
async def index_capture(session_id: str):
    """Run play-by-play scene indexing on an attached capture video."""
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None

    video_id = session.get("capture_video_id")
    if not video_id:
        raise HTTPException(400, "Attach a capture video_id first")

    if not vdb.is_videodb_configured():
        raise HTTPException(400, "VIDEO_DB_API_KEY not configured")

    idx = vdb.index_session_video(video_id, session["moves"], session_id)
    scene_index_id = idx.get("scene_index_id")
    session["scene_index_id"] = scene_index_id
    vdb.save_session(session_id, session)

    if not scene_index_id:
        raise HTTPException(
            503,
            idx.get("error") or "Scene indexing failed — check API key and video_id",
        )
    player = vdb.get_video_player(video_id) if scene_index_id else {}
    return {
        "ok": True,
        "scene_index_id": scene_index_id,
        "video_id": video_id,
        "moves_indexed": idx.get("moves_indexed", len(session["moves"])),
        "player_url": player.get("player_url"),
        "embed_url": player.get("embed_url"),
        "stream_url": player.get("stream_url"),
    }


@app.post("/api/session/start", response_model=StartSessionResponse)
async def start_session(capture_mode: bool = False):
    session = _new_session(capture_mode=capture_mode)
    vdb.save_session(session["session_id"], session)
    state = session["state"]
    return StartSessionResponse(
        session_id=session["session_id"],
        board=state["board"],
        current_player=state["current_player"],
        videodb_enabled=vdb.is_videodb_configured(),
        capture_mode=capture_mode,
        media_mode=vdb.get_media_mode().value,
    )


@app.post("/api/session/{session_id}/move", response_model=MoveResponse)
async def play_move(session_id: str, body: MoveRequest):
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None

    state = _state_from_dict(session["state"])
    if state.finished:
        raise HTTPException(400, "Game already finished")

    if state.current_player != "X":
        raise HTTPException(400, "Only human (X) moves via this endpoint; O is AI")

    elapsed = time.time() - session["session_started_at"]
    scene_start = elapsed
    try:
        analysis = apply_move(state, body.cell)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    scene_end = time.time() - session["session_started_at"]

    move_number = state.move_number
    record = _move_to_record(
        analysis, move_number, scene_start=scene_start, scene_end=scene_end
    )
    session["moves"].append(record)

    opponent_record: dict[str, Any] | None = None
    if not state.finished and state.current_player == "O":
        ai_cell = suggest_move(state.board, "O")
        if ai_cell is not None:
            ai_start = time.time() - session["session_started_at"]
            ai_analysis = apply_move(state, ai_cell)
            ai_end = time.time() - session["session_started_at"]
            opponent_record = _move_to_record(
                ai_analysis,
                state.move_number,
                scene_start=ai_start,
                scene_end=ai_end,
            )
            session["moves"].append(opponent_record)

    session["state"] = {
        "board": state.board,
        "current_player": state.current_player,
        "move_number": state.move_number,
        "winner": state.winner,
        "finished": state.finished,
    }

    from app.game_engine import MoveAnalysis

    # One optional VideoDB call per human turn (not per piece)
    if opponent_record:
        turn_analysis_obj = MoveAnalysis(
            cell=opponent_record["cell"],
            player=opponent_record["player"],
            board_before=[],
            board_after=opponent_record["board_after"],
            suggested_cell=opponent_record["suggested_cell"],
            suggestion_text=opponent_record.get("suggestion_text"),
            blocking_required=False,
            winning_move_available=False,
            blunder=opponent_record["blunder"],
            narrative=opponent_record["narrative"],
        )
    else:
        turn_analysis_obj = analysis

    turn_media_dict = vdb.attach_turn_media(turn_analysis_obj)
    if turn_media_dict.get("suggestion_stream_url") or turn_media_dict.get(
        "suggestion_image_url"
    ) or turn_media_dict.get("fallback"):
        target = session["moves"][-1]
        target.update(
            {
                k: turn_media_dict.get(k)
                for k in (
                    "suggestion_stream_url",
                    "suggestion_player_url",
                    "suggestion_embed_url",
                    "suggestion_image_url",
                    "suggestion_image_id",
                    "suggestion_video_id",
                )
            }
        )

    vdb.save_session(session_id, session)

    highlight = turn_analysis_obj.suggested_cell
    mode = vdb.get_media_mode().value

    return MoveResponse(
        session_id=session_id,
        board=session["state"]["board"],
        current_player=session["state"]["current_player"],
        finished=session["state"]["finished"],
        winner=session["state"].get("winner"),
        last_move=MoveRecord(**record),
        opponent_suggestion=MoveRecord(**opponent_record) if opponent_record else None,
        highlight_cell=highlight,
        suggestion_text=turn_analysis_obj.suggestion_text,
        turn_media=TurnMedia(**turn_media_dict),
        media_mode=mode,
    )


@app.post("/api/session/{session_id}/finish", response_model=FinishResponse)
async def finish_session(session_id: str, cloud_recap: bool = False):
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None

    scene_index_id = session.get("scene_index_id")
    if session.get("capture_video_id") and not scene_index_id:
        idx = vdb.index_session_video(
            session["capture_video_id"],
            session["moves"],
            session_id,
        )
        scene_index_id = idx.get("scene_index_id")
        session["scene_index_id"] = scene_index_id
        vdb.save_session(session_id, session)

    recap_mode = vdb.get_recap_mode()
    recap_stream, recap_player = None, None
    recap_error: str | None = None
    recap_embed: str | None = None
    if vdb.should_build_cloud_recap(cloud_recap):
        tl = vdb.build_recap_timeline(session)
        recap_stream = tl.get("stream_url")
        recap_player = tl.get("player_url")
        recap_embed = tl.get("embed_url")
        recap_error = tl.get("error")
        recap_mode = "cloud"

    log_path = str(vdb.save_session(session_id, session))

    if recap_stream:
        msg = "Cloud recap ready (VideoDB timeline)."
    elif cloud_recap and recap_error:
        msg = f"Cloud recap failed: {recap_error}"
    elif recap_mode == "local":
        msg = "Play-by-play recap ready in browser (no VideoDB charge)."
    elif vdb.is_videodb_configured():
        msg = "Session saved. Cloud recap failed — use local recap or check plan limits."
    else:
        msg = "Session saved."

    return FinishResponse(
        session_id=session_id,
        winner=session["state"].get("winner"),
        moves=[MoveRecord(**m) for m in session["moves"]],
        recap_stream_url=recap_stream,
        recap_player_url=recap_player,
        recap_embed_url=recap_embed,
        recap_mode=recap_mode,
        move_log_path=log_path,
        scene_index_id=scene_index_id,
        message=msg,
    )


@app.get("/api/sandbox/status")
async def sandbox_status():
    return sandbox.get_status_payload()


@app.get("/api/sandbox/usage")
async def sandbox_usage(session_id: str | None = None):
    return sandbox.get_usage_payload(session_id)


@app.get("/api/sandbox/games")
async def sandbox_games():
    from app import immersive_games as ig

    return {"games": ig.GAME_CATALOG}


@app.post("/api/sandbox/session/start", response_model=SandboxStartResponse)
async def sandbox_start(body: SandboxStartRequest | None = None, game_type: str = "tic_tac_toe"):
    if not vdb.is_videodb_configured():
        raise HTTPException(400, "VIDEO_DB_API_KEY not configured")
    gt = body.game_type if body else game_type
    result = sandbox.start_sandbox_session(gt)
    if not result.get("sandbox", {}).get("ok"):
        raise HTTPException(
            503,
            result.get("sandbox", {}).get("error") or "Sandbox provisioning failed",
        )
    return SandboxStartResponse(**result)


@app.get("/api/sandbox/session/{session_id}")
async def sandbox_get_session(session_id: str):
    try:
        session = sandbox.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Sandbox session not found") from None
    return {
        "session_id": session_id,
        "game_type": session.get("game_type", "tic_tac_toe"),
        "state": session["state"],
        "moves": session["moves"],
        "sandbox_id": session.get("sandbox_id"),
        "sandbox_status": session.get("sandbox_status"),
        "usage": session.get("usage"),
        "recap_status": session.get("recap_status"),
        "recap_stream_url": session.get("recap_stream_url"),
        "recap_player_url": session.get("recap_player_url"),
        "recap_embed_url": session.get("recap_embed_url"),
        "recap_error": session.get("recap_error"),
    }


def _sandbox_action_body(body: SandboxActionRequest) -> dict[str, Any]:
    if body.action:
        return body.action
    if body.cell is not None:
        return {"cell": body.cell}
    raise HTTPException(400, "Provide action or cell")


@app.post("/api/sandbox/session/{session_id}/action", response_model=SandboxActionResponse)
async def sandbox_play_action(session_id: str, body: SandboxActionRequest):
    try:
        result = sandbox.play_sandbox_action(session_id, _sandbox_action_body(body))
    except FileNotFoundError:
        raise HTTPException(404, "Sandbox session not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return SandboxActionResponse(**result)


@app.post("/api/sandbox/session/{session_id}/move", response_model=SandboxActionResponse)
async def sandbox_play_move(session_id: str, body: MoveRequest):
    try:
        result = sandbox.play_sandbox_move(session_id, body.cell)
    except FileNotFoundError:
        raise HTTPException(404, "Sandbox session not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return SandboxActionResponse(**result)


@app.post("/api/sandbox/session/{session_id}/finish", response_model=SandboxFinishResponse)
async def sandbox_finish(session_id: str):
    try:
        result = sandbox.finish_sandbox_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Sandbox session not found") from None
    return SandboxFinishResponse(**result)


@app.post("/api/sandbox/session/{session_id}/stop")
async def sandbox_stop(session_id: str):
    try:
        session = sandbox.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Sandbox session not found") from None
    stop = sandbox.stop_session_sandbox(session)
    sandbox._merge_session_usage_to_global(session)
    sandbox.save_session(session_id, session)
    return {"ok": True, **stop, "usage": session.get("usage")}


@app.post("/api/sandbox/cleanup")
async def sandbox_cleanup(keep: int = 1):
    """Stop extra active sandboxes so new immersive sessions can start (tier limit 3)."""
    result = sandbox.cleanup_extra_sandboxes(keep=max(0, min(keep, 2)))
    if not result.get("ok"):
        raise HTTPException(400, result.get("error") or "Cleanup failed")
    return result


@app.post("/api/session/{session_id}/attach-capture")
async def attach_capture(session_id: str, body: AttachCaptureRequest):
    """Link a desktop-capture or uploaded session video for play-by-play indexing."""
    try:
        session = vdb.load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found") from None

    try:
        vdb.assert_video_in_collection(body.video_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    session["capture_video_id"] = body.video_id
    if body.move_timestamps:
        for i, ts in enumerate(body.move_timestamps):
            if i < len(session["moves"]):
                session["moves"][i]["scene_start"] = ts.get("start")
                session["moves"][i]["scene_end"] = ts.get("end")

    vdb.save_session(session_id, session)
    return {"ok": True, "video_id": body.video_id}
