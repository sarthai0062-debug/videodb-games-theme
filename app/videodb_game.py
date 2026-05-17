"""
VideoDB orchestration for tic-tac-toe play-by-play.

Cost tiers (VIDEODB_MEDIA_MODE in .env):
  economy (default) — no generative calls per move; text recap via Timeline only
  voice            — economy recap + one voiceover for the full game
  image            — one still image per turn (after X+O), not per move
  video            — legacy: generate_video each move (expensive)
"""

from __future__ import annotations

import json
import os
import re
from enum import Enum
from pathlib import Path
from typing import Any

from app.game_engine import MoveAnalysis, Player

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data" / "sessions"
PLAYER_WATCH_BASE = "https://player.videodb.io/watch?v="

# economy < voice < image < video (increasing cost)
MEDIA_MODES = ("economy", "voice", "image", "video")
# local = browser slideshow (free); cloud = VideoDB Timeline compile (costs credits)
RECAP_MODES = ("local", "cloud")
SCENE_MODELS = ("basic", "pro", "ultra")

# VideoDB APIs used by this game (see docs: generative + index_scenes model_name)
MODELS_CATALOG: list[dict[str, str]] = [
    {
        "feature": "Play-by-play index",
        "api": "video.index_scenes(scenes=…)",
        "model": "basic / pro / ultra (VIDEODB_SCENE_MODEL)",
        "when": "After attaching a capture video",
    },
    {
        "feature": "Scene search",
        "api": "video.search(IndexType.scene)",
        "model": "Embeddings from scene index",
        "when": "After indexing",
    },
    {
        "feature": "Timeline recap",
        "api": "Timeline + TextAsset",
        "model": "No generative model (text slides)",
        "when": "Cloud recap at game end",
    },
    {
        "feature": "Voice recap",
        "api": "coll.generate_voice()",
        "model": "voice_name=Default",
        "when": "VIDEODB_MEDIA_MODE=voice + cloud recap",
    },
    {
        "feature": "Turn image",
        "api": "coll.generate_image()",
        "model": "Default image model",
        "when": "VIDEODB_MEDIA_MODE=image",
    },
    {
        "feature": "Turn video",
        "api": "coll.generate_video()",
        "model": "Default video model · 5s clip",
        "when": "VIDEODB_MEDIA_MODE=video (costly)",
    },
]


class MediaMode(str, Enum):
    ECONOMY = "economy"
    VOICE = "voice"
    IMAGE = "image"
    VIDEO = "video"


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")


def get_media_mode() -> MediaMode:
    _load_env()
    raw = (os.getenv("VIDEODB_MEDIA_MODE") or "economy").strip().lower()
    if raw not in MEDIA_MODES:
        return MediaMode.ECONOMY
    return MediaMode(raw)


def get_recap_mode() -> str:
    _load_env()
    raw = (os.getenv("VIDEODB_RECAP") or "local").strip().lower()
    return raw if raw in RECAP_MODES else "local"


def get_scene_model() -> str:
    _load_env()
    raw = (os.getenv("VIDEODB_SCENE_MODEL") or "basic").strip().lower()
    return raw if raw in SCENE_MODELS else "basic"


def get_video_generate_duration() -> int:
    """
    VideoDB generate_video() only accepts integer seconds from 5 to 8 inclusive.
    If VIDEODB_VIDEO_DURATION=3, we still generate at 5 and trim playback separately.
    """
    _load_env()
    raw = (
        os.getenv("VIDEODB_VIDEO_GENERATE_SEC")
        or os.getenv("VIDEODB_VIDEO_DURATION")
        or "5"
    )
    try:
        val = int(float(raw))
    except ValueError:
        val = 5
    return max(5, min(8, val))


def get_video_playback_seconds() -> float:
    """Target length for the clip shown in the UI (trim via Timeline when < generate duration)."""
    _load_env()
    raw = (
        os.getenv("VIDEODB_VIDEO_PLAYBACK_SEC")
        or os.getenv("VIDEODB_VIDEO_TRIM_SEC")
        or os.getenv("VIDEODB_VIDEO_DURATION")
        or "3"
    )
    try:
        val = float(raw)
    except ValueError:
        val = 3.0
    return max(1.0, min(8.0, val))


def trim_video_clip(conn: Any, video_id: str, seconds: float) -> dict[str, Any]:
    """Shorten a collection video to `seconds` using the Editor Timeline."""
    from videodb.editor import Clip, Timeline, Track, VideoAsset

    timeline = Timeline(conn)
    timeline.resolution = "1280x720"
    track = Track()
    track.add_clip(0, Clip(asset=VideoAsset(id=video_id, start=0), duration=seconds))
    timeline.add_track(track)
    stream = timeline.generate_stream()
    return player_payload(stream, getattr(timeline, "player_url", None))


def get_collection_id() -> str:
    """Target VideoDB collection for all ingest, generative, and index calls."""
    _load_env()
    return (os.getenv("VIDEODB_COLLECTION_ID") or "").strip()


def get_collection_name() -> str:
    """Optional display name check — empty means accept any collection name from API."""
    _load_env()
    return (os.getenv("VIDEODB_COLLECTION_NAME") or "").strip()


def collection_name_matches(expected: str, actual: str | None) -> bool:
    if not expected:
        return True
    return expected.strip().lower() == (actual or "").strip().lower()


# What this hackathon app stores in VideoDB (visible in Console under the collection).
VIDEODB_UTILIZATION: list[dict[str, str]] = [
    {
        "artifact": "Turn clips (video mode)",
        "api": "collection.generate_video()",
        "in_console": "New video assets named from move prompts",
        "when": "VIDEODB_MEDIA_MODE=video — each human turn",
    },
    {
        "artifact": "Turn stills (image mode)",
        "api": "collection.generate_image()",
        "in_console": "Image assets in collection",
        "when": "VIDEODB_MEDIA_MODE=image",
    },
    {
        "artifact": "Play-by-play scene index",
        "api": "video.index_scenes()",
        "in_console": "Scene index on capture video (searchable segments)",
        "when": "Index moves after attaching a collection video",
    },
    {
        "artifact": "Game recap timeline",
        "api": "Timeline.compile → generate_stream()",
        "in_console": "Hosted recap stream / timeline output",
        "when": "Build cloud timeline or VIDEODB_RECAP=cloud",
    },
    {
        "artifact": "Voiceover (optional)",
        "api": "collection.generate_voice()",
        "in_console": "Audio asset used in cloud recap",
        "when": "VIDEODB_MEDIA_MODE=voice + cloud recap",
    },
]


def should_build_cloud_recap(cloud_recap_query: bool = False) -> bool:
    return cloud_recap_query or get_recap_mode() == "cloud"


def test_connection() -> dict[str, Any]:
    """Live VideoDB API check — connect and resolve configured collection."""
    if not is_videodb_configured():
        return {
            "ok": False,
            "error": "VIDEO_DB_API_KEY not set in .env",
        }
    try:
        conn = _connect()
        coll_id = resolve_collection_id(conn)
        coll = conn.get_collection(coll_id)
        name = getattr(coll, "name", None) or ""
        expected = get_collection_name()
        configured = get_collection_id()
        id_ok = not configured or coll_id == configured
        return {
            "ok": True,
            "collection_id": getattr(coll, "id", None),
            "collection_name": name,
            "collection_name_expected": expected or None,
            "collection_name_ok": collection_name_matches(expected, name),
            "collection_id_configured": configured or None,
            "collection_id_resolved": bool(configured) and coll_id != configured,
            "collection_id_ok": id_ok,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _mask_api_key() -> str | None:
    _load_env()
    key = (os.getenv("VIDEO_DB_API_KEY") or "").strip()
    if not key:
        return None
    if len(key) <= 8:
        return "••••••••"
    return f"{key[:4]}…{key[-4:]}"


def _collection_video_count() -> int | None:
    try:
        conn = _connect()
        coll = _collection(conn)
        videos = coll.get_videos()
        return len(videos) if videos is not None else 0
    except Exception:
        return None


def _is_generation_limit_error(err: str) -> bool:
    low = err.lower()
    return "maximum limit" in low or "plan" in low or "not allowed" in low


def _resolve_image_url(image: Any) -> str | None:
    """Signed URL for browser display (prefer generate_url per VideoDB docs)."""
    try:
        signed = image.generate_url()
        if signed:
            return signed
    except Exception:
        pass
    return getattr(image, "url", None)


def _fallback_collection_image(coll: Any) -> tuple[str | None, str | None]:
    """Use newest collection image when generate_image fails (e.g. plan limit)."""
    try:
        images = coll.get_images() or []
        if not images:
            return None, None
        img = images[-1]
        url = _resolve_image_url(img)
        return url, getattr(img, "id", None)
    except Exception:
        return None, None


def _fallback_collection_video(coll: Any) -> dict[str, Any]:
    """Use newest collection video stream when generate_video fails."""
    empty: dict[str, Any] = {
        "suggestion_stream_url": None,
        "suggestion_player_url": None,
        "suggestion_embed_url": None,
        "suggestion_video_id": None,
    }
    try:
        videos = coll.get_videos() or []
        if not videos:
            return empty
        video = videos[-1]
        if not video.stream_url:
            video.generate_stream()
        pl = player_payload(video.stream_url, getattr(video, "player_url", None))
        return {
            **empty,
            "suggestion_stream_url": pl.get("stream_url"),
            "suggestion_player_url": pl.get("player_url"),
            "suggestion_embed_url": pl.get("embed_url"),
            "suggestion_video_id": video.id,
        }
    except Exception:
        return empty


def get_generation_status() -> dict[str, Any]:
    """
    Non-destructive status for image/video modes (does not call generate_*).
  Uses collection inventory so the UI can warn before the user plays a move.
    """
    mode = get_media_mode()
    if mode == MediaMode.ECONOMY:
        return {
            "mode": mode.value,
            "active": False,
            "detail": "Economy — no per-turn generative calls",
            "collection_images": 0,
            "collection_videos": 0,
        }
    if not is_videodb_configured():
        return {
            "mode": mode.value,
            "active": False,
            "detail": "Set VIDEO_DB_API_KEY in .env",
            "collection_images": 0,
            "collection_videos": 0,
        }
    imgs = list_collection_images()
    vids = list_collection_videos()
    n_img = len(imgs.get("images", []))
    n_vid = len(vids.get("videos", []))
    detail = (
        f"Per-turn {mode.value} generation enabled. "
        f"Collection has {n_img} image(s) and {n_vid} video(s) for fallback if plan limit is hit."
    )
    return {
        "mode": mode.value,
        "active": True,
        "detail": detail,
        "collection_images": n_img,
        "collection_videos": n_vid,
        "has_fallback_assets": (n_img > 0 if mode == MediaMode.IMAGE else n_vid > 0),
    }


def _image_preview_url(image: Any) -> str | None:
    """Signed or public URL for collection image thumbnails."""
    return _resolve_image_url(image)


def _video_preview_url(video: Any, *, generate: bool = False) -> str | None:
    """Thumbnail URL for a collection video (skip generate_thumbnail unless requested)."""
    thumb = getattr(video, "thumbnail_url", None)
    if thumb:
        return thumb
    if not generate:
        return None
    try:
        generated = video.generate_thumbnail()
        if isinstance(generated, str):
            return generated
        return _image_preview_url(generated)
    except Exception:
        return getattr(video, "thumbnail_url", None)


def list_collection_images(limit: int = 40) -> dict[str, Any]:
    """List AI-generated and uploaded images in the collection."""
    if not is_videodb_configured():
        return {"ok": False, "images": [], "error": "VIDEO_DB_API_KEY not set"}
    try:
        conn = _connect()
        coll = _collection(conn)
        raw = coll.get_images() or []
        images: list[dict[str, Any]] = []
        for img in raw[:limit]:
            iid = getattr(img, "id", None)
            if not iid:
                continue
            name = getattr(img, "name", None) or iid
            preview = _image_preview_url(img)
            images.append(
                {
                    "id": iid,
                    "name": name,
                    "preview_url": preview,
                    "collection_id": getattr(img, "collection_id", coll.id),
                    "label": name,
                }
            )
        return {
            "ok": True,
            "images": images,
            "collection_id": coll.id,
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "images": [], "error": str(e)[:300]}


def list_collection_videos(limit: int = 25) -> dict[str, Any]:
    """List videos in the configured collection for the capture picker."""
    if not is_videodb_configured():
        return {"ok": False, "videos": [], "error": "VIDEO_DB_API_KEY not set"}
    try:
        conn = _connect()
        coll = _collection(conn)
        raw = coll.get_videos() or []
        videos: list[dict[str, Any]] = []
        for v in raw[:limit]:
            vid = getattr(v, "id", None)
            if not vid:
                continue
            name = getattr(v, "name", None) or vid
            length = getattr(v, "length", None)
            preview = _video_preview_url(v)
            videos.append(
                {
                    "id": vid,
                    "name": name,
                    "duration_sec": length,
                    "preview_url": preview,
                    "collection_id": getattr(v, "collection_id", coll.id),
                    "label": f"{name}" + (f" · {length:.0f}s" if length else ""),
                }
            )
        return {
            "ok": True,
            "videos": videos,
            "collection_id": coll.id,
            "collection_name": getattr(coll, "name", None),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "videos": [], "error": str(e)[:300]}


def _build_collection_inventory(
    listed: dict[str, Any],
    images_listed: dict[str, Any],
) -> dict[str, Any]:
    """Assemble inventory payload without extra VideoDB round-trips."""
    target_id = get_collection_id()
    target_name = get_collection_name()
    videos = listed.get("videos", [])
    images = images_listed.get("images", [])
    coll_id = listed.get("collection_id") or resolve_collection_id(_connect())
    name = listed.get("collection_name") or ""
    mode = get_media_mode().value
    recap = get_recap_mode()

    def _util_active(when: str) -> bool:
        if "VIDEODB_MEDIA_MODE=video" in when:
            return mode == "video"
        if "VIDEODB_MEDIA_MODE=image" in when:
            return mode == "image"
        if "VIDEODB_MEDIA_MODE=voice" in when:
            return mode == "voice"
        if "VIDEODB_RECAP=cloud" in when or "cloud recap" in when.lower():
            return recap == "cloud"
        return True

    active_utilization = [
        {**row, "active": _util_active(row["when"])} for row in VIDEODB_UTILIZATION
    ]

    return {
        "ok": True,
        "collection_id": coll_id,
        "collection_name": name,
        "collection_name_expected": target_name,
        "collection_id_configured": target_id,
        "collection_match": (not target_id) or coll_id == target_id,
        "collection_name_ok": collection_name_matches(target_name, name),
        "console_url": "https://console.videodb.io",
        "video_count": len(videos),
        "image_count": len(images),
        "asset_count": len(videos) + len(images),
        "videos": videos,
        "images": images,
        "utilization": VIDEODB_UTILIZATION,
        "active_utilization": active_utilization,
        "current_media_mode": mode,
        "current_recap_mode": recap,
        "local_only_note": (
            "Move JSON in data/sessions/ is local only — not uploaded to VideoDB. "
            "Everything in the table below is what appears in your collection."
        ),
    }


def get_collection_inventory() -> dict[str, Any]:
    """
    Full manifest of the hackathon collection — what judges see in VideoDB Console.
    """
    if not is_videodb_configured():
        return {"ok": False, "error": "VIDEO_DB_API_KEY not set"}

    try:
        listed = list_collection_videos()
        images_listed = list_collection_images()
        if not listed.get("ok"):
            return {"ok": False, "error": listed.get("error") or "Could not list videos"}
        return _build_collection_inventory(listed, images_listed)
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def assert_video_in_collection(video_id: str) -> None:
    """Reject capture IDs from another collection."""
    conn = _connect()
    coll = _collection(conn)
    video = coll.get_video(video_id)
    if getattr(video, "collection_id", None) != coll.id:
        raise ValueError(
            f"Video {video_id} is not in collection {coll.id} ({get_collection_name()})"
        )


def _capabilities_for_session(
    session: dict[str, Any] | None,
    *,
    configured: bool,
    connection_ok: bool,
    collection_id: str | None,
    connection_error: str | None,
) -> list[dict[str, Any]]:
    moves = (session or {}).get("moves") or []
    has_moves = len(moves) > 0
    has_video = bool((session or {}).get("capture_video_id"))
    has_index = bool((session or {}).get("scene_index_id"))
    finished = bool((session or {}).get("state", {}).get("finished"))

    return [
        {
            "id": "api_key",
            "label": "API key",
            "ok": configured,
            "detail": _mask_api_key() or "Set VIDEO_DB_API_KEY in .env",
        },
        {
            "id": "connect",
            "label": "Connection",
            "ok": connection_ok,
            "detail": collection_id or connection_error or "—",
        },
        {
            "id": "move_log",
            "label": "Move log",
            "ok": has_moves,
            "detail": f"{len(moves)} move(s) in session" if has_moves else "Play on Play tab",
        },
        {
            "id": "play_by_play",
            "label": "Scene index",
            "ok": has_index,
            "detail": (session or {}).get("scene_index_id") or (
                "Attach video + Index moves" if has_video and has_moves else "—"
            ),
        },
        {
            "id": "search",
            "label": "Search",
            "ok": has_moves or has_index,
            "detail": "Move log + VideoDB scene search when indexed",
        },
        {
            "id": "timeline",
            "label": "Cloud recap",
            "ok": configured and connection_ok and finished,
            "detail": "Timeline compile when game finished"
            if finished
            else "Finish game first",
        },
    ]


def get_videodb_panel(session_id: str | None = None) -> dict[str, Any]:
    """Single payload for the VideoDB sidebar — connection, models, videos, actions."""
    hub = get_hub_payload(session_id)
    videos_payload = (
        list_collection_videos() if hub.get("connection_ok") else {"ok": False, "videos": []}
    )
    session = None
    if session_id:
        try:
            session = load_session(session_id)
        except FileNotFoundError:
            session = None

    if session:
        hub["capabilities"] = _capabilities_for_session(
            session,
            configured=hub["api_configured"],
            connection_ok=hub["connection_ok"],
            collection_id=hub.get("collection_id"),
            connection_error=hub.get("connection_error"),
        )

    sess = hub.get("session") or {}
    hub["models_catalog"] = MODELS_CATALOG
    hub["scene_model"] = get_scene_model()
    hub["collection_id_configured"] = get_collection_id()
    hub["collection_name_expected"] = get_collection_name()
    if hub.get("connection_ok"):
        listed = videos_payload if videos_payload.get("ok") else list_collection_videos()
        images_listed = list_collection_images()
        hub["collection_inventory"] = _build_collection_inventory(
            listed, images_listed
        )
        hub["video_count"] = len(listed.get("videos") or [])
    else:
        hub["collection_inventory"] = None
    hub["generation"] = get_generation_status() if hub.get("connection_ok") else None
    hub["videos"] = videos_payload.get("videos", [])
    hub["videos_error"] = videos_payload.get("error")
    hub["actions"] = {
        "can_search": bool(sess.get("can_search_moves")),
        "can_index": bool(sess.get("can_index")) if sess else False,
        "can_cloud_recap": bool(sess.get("can_cloud_recap")) if sess else False,
        "can_export": bool(sess.get("move_count", 0) > 0) if sess else False,
    }
    return hub


def _session_hub_context(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    try:
        session = load_session(session_id)
    except FileNotFoundError:
        return {"session_id": session_id, "found": False}
    moves = session.get("moves", [])
    return {
        "session_id": session_id,
        "found": True,
        "move_count": len(moves),
        "finished": session.get("state", {}).get("finished", False),
        "winner": session.get("state", {}).get("winner"),
        "capture_video_id": session.get("capture_video_id"),
        "scene_index_id": session.get("scene_index_id"),
        "can_search_footage": bool(
            session.get("capture_video_id") and session.get("scene_index_id")
        ),
        "can_search_moves": len(moves) > 0,
        "can_index": (
            len(moves) > 0
            and not session.get("scene_index_id")
            and is_videodb_configured()
        ),
        "can_cloud_recap": (
            session.get("state", {}).get("finished", False) and is_videodb_configured()
        ),
    }


def search_move_log(session: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Fallback search over structured play-by-play JSON (no VideoDB index required)."""
    q = query.strip().lower()
    if not q:
        return []
    tokens = [t for t in q.split() if len(t) > 1]
    out: list[dict[str, Any]] = []
    for move in session.get("moves", []):
        haystack = " ".join(
            [
                str(move.get("narrative", "")),
                str(move.get("player", "")),
                f"cell {move.get('cell', '')}",
                " ".join(str(c) for c in move.get("board_after", [])),
            ]
        ).lower()
        if q in haystack or all(t in haystack for t in tokens):
            out.append(
                {
                    "source": "move_log",
                    "move_number": move.get("move_number"),
                    "player": move.get("player"),
                    "cell": move.get("cell"),
                    "narrative": move.get("narrative"),
                    "description": move.get("narrative"),
                    "board_after": move.get("board_after"),
                }
            )
    return out


def get_hub_payload(session_id: str | None = None) -> dict[str, Any]:
    """
    VideoDB hackathon hub: connection, capabilities, docs, and game-specific use cases.
    Curated from VideoDB skill + docs (See · Understand · Act).
    """
    configured = is_videodb_configured()
    conn = test_connection() if configured else {"ok": False, "error": "No API key"}
    video_count = None

    capabilities: list[dict[str, Any]] = [
        {
            "id": "api_key",
            "label": "API key",
            "ok": configured,
            "detail": _mask_api_key() or "Set VIDEO_DB_API_KEY in .env",
        },
        {
            "id": "connect",
            "label": "Connection",
            "ok": bool(conn.get("ok")),
            "detail": conn.get("collection_id") or conn.get("error") or "—",
        },
        {
            "id": "play_by_play",
            "label": "Play-by-play index",
            "ok": configured,
            "detail": "index_scenes() with per-move metadata",
        },
        {
            "id": "timeline",
            "label": "Timeline recap",
            "ok": configured,
            "detail": "Editor API · TextAsset slides + voice",
        },
        {
            "id": "search",
            "label": "Scene search",
            "ok": configured,
            "detail": "Semantic search on indexed moves",
        },
        {
            "id": "capture",
            "label": "Capture ingest",
            "ok": configured,
            "detail": "Attach screen-recording video_id",
        },
    ]

    use_cases: list[dict[str, Any]] = [
        {
            "id": "nfl_index",
            "tier": "Best demo",
            "title": "Play-by-play scene indexing",
            "see_understand_act": "Understand",
            "summary": (
                "Each move becomes a VideoDB scene with timestamps and structured metadata "
                "(player, cell, board state) — the same pattern as the NFL case study."
            ),
            "steps": [
                "Record your screen while playing (Capture SDK or upload).",
                "Paste the video ID in Index → Index moves.",
                "Search footage: “X blocks winning line” or “near miss”.",
            ],
            "doc_url": "https://docs.videodb.io/examples-and-tutorials/video-rag/case-study-nfl",
        },
        {
            "id": "timeline_recap",
            "tier": "Best for judges",
            "title": "Programmatic game recap",
            "see_understand_act": "Act",
            "summary": (
                "Compile every move into a hosted VideoDB Timeline (text slides + optional "
                "voiceover) — one shareable stream URL for the whole game."
            ),
            "steps": [
                "Finish a game on Play.",
                "Open Recap → Cloud timeline.",
                "Open the stream in the VideoDB player.",
            ],
            "doc_url": "https://docs.videodb.io/pages/core-concepts/programmable-editing",
        },
        {
            "id": "economy_loop",
            "tier": "Smart default",
            "title": "Zero-cost play loop",
            "see_understand_act": "See + Understand",
            "summary": (
                "Economy mode logs structured play-by-play JSON locally with no generative "
                "calls per move; cloud recap only when you choose it."
            ),
            "steps": [
                "Keep VIDEODB_MEDIA_MODE=economy in .env.",
                "Play moves — analysis + move log update instantly.",
                "Use local recap for demos; cloud for the wow moment.",
            ],
            "doc_url": "https://docs.videodb.io/pages/getting-started/welcome",
        },
    ]

    docs: list[dict[str, str]] = [
        {
            "title": "Getting started",
            "url": "https://docs.videodb.io/pages/getting-started/welcome",
        },
        {
            "title": "Scene indexing",
            "url": "https://docs.videodb.io/pages/understand/indexing-pipelines/create-an-index",
        },
        {
            "title": "NFL play-by-play case study",
            "url": "https://docs.videodb.io/examples-and-tutorials/video-rag/case-study-nfl",
        },
        {
            "title": "Programmable editing (Timeline)",
            "url": "https://docs.videodb.io/pages/core-concepts/programmable-editing",
        },
        {
            "title": "Desktop capture",
            "url": "https://docs.videodb.io/pages/see/capture-sdk",
        },
        {
            "title": "Python SDK",
            "url": "https://docs.videodb.io/pages/developers/python-sdk",
        },
        {
            "title": "Console",
            "url": "https://console.videodb.io",
        },
    ]

    pitch = (
        "Tic-tac-toe as a micro sports broadcast: VideoDB indexes every move like an NFL "
        "play, lets you search your session footage, and compiles a hosted recap — "
        "See (capture), Understand (scene index + metadata), Act (Timeline stream)."
    )

    session_ctx = _session_hub_context(session_id)

    return {
        "api_configured": configured,
        "api_key_hint": _mask_api_key(),
        "connection_ok": bool(conn.get("ok")),
        "collection_id": conn.get("collection_id"),
        "collection_id_configured": conn.get("collection_id_configured"),
        "collection_id_resolved": conn.get("collection_id_resolved"),
        "collection_name": conn.get("collection_name"),
        "collection_name_ok": conn.get("collection_name_ok"),
        "connection_error": conn.get("error"),
        "video_count": video_count,
        "media_mode": get_media_mode().value,
        "recap_mode": get_recap_mode(),
        "scene_model": get_scene_model(),
        "capabilities": capabilities,
        "use_cases": use_cases,
        "docs": docs,
        "hackathon_pitch": pitch,
        "site_url": "https://videodb.io",
        "session": session_ctx,
    }


def search_session_footage(
    session: dict[str, Any],
    query: str,
    *,
    score_threshold: float = 0.25,
) -> dict[str, Any]:
    """Search indexed VideoDB scenes; falls back to move-log keyword search."""
    if not query.strip():
        return {"results": [], "message": "Enter a search query", "source": "none"}

    video_id = session.get("capture_video_id")
    scene_index_id = session.get("scene_index_id")

    if video_id and scene_index_id and is_videodb_configured():
        try:
            from videodb import IndexType, SearchType
            from videodb.exceptions import InvalidRequestError

            conn = _connect()
            coll = _collection(conn)
            video = coll.get_video(video_id)

            try:
                results = video.search(
                    query=query.strip(),
                    search_type=SearchType.semantic,
                    index_type=IndexType.scene,
                    scene_index_id=scene_index_id,
                    score_threshold=score_threshold,
                )
                shots = results.get_shots()
                stream_url = None
                compiled_player = getattr(results, "player_url", None)
                try:
                    stream_url = results.compile()
                    compiled_player = getattr(results, "player_url", None) or compiled_player
                except Exception:
                    pass
            except InvalidRequestError as e:
                if "No results found" not in str(e):
                    raise
                shots = []
                stream_url = None

            if shots:
                out: list[dict[str, Any]] = []
                moves = session.get("moves", [])
                for shot in shots:
                    start = getattr(shot, "start", None)
                    end = getattr(shot, "end", None)
                    text = getattr(shot, "text", None) or ""
                    meta_move = None
                    if start is not None:
                        for m in moves:
                            if abs(float(m.get("scene_start", -1)) - float(start)) < 1.5:
                                meta_move = m
                                break
                    shot_player = getattr(shot, "player_url", None)
                    shot_stream = getattr(shot, "stream_url", None)
                    pl = player_payload(shot_stream, shot_player)
                    out.append(
                        {
                            "source": "videodb",
                            "start": start,
                            "end": end,
                            "description": text,
                            "move_number": meta_move.get("move_number") if meta_move else None,
                            "player": meta_move.get("player") if meta_move else None,
                            "cell": meta_move.get("cell") if meta_move else None,
                            "narrative": meta_move.get("narrative") if meta_move else None,
                            **pl,
                        }
                    )
                compiled = player_payload(stream_url, compiled_player)
                return {
                    "results": out,
                    **compiled,
                    "message": f"{len(out)} scene(s) from VideoDB index",
                    "source": "videodb",
                }
        except Exception as e:
            err = str(e)[:200]
            local = search_move_log(session, query)
            if local:
                return {
                    "results": local,
                    "message": f"VideoDB search failed; {len(local)} move(s) from log",
                    "source": "move_log",
                    "warning": err,
                }
            return {"results": [], "message": err, "source": "error"}

    local = search_move_log(session, query)
    if local:
        return {
            "results": local,
            "message": f"{len(local)} move(s) from play-by-play log",
            "source": "move_log",
        }
    if not session.get("moves"):
        return {
            "results": [],
            "message": "Play a game first, or index capture footage on the Index tab",
            "source": "none",
        }
    if not video_id or not scene_index_id:
        return {
            "results": [],
            "message": "No matches in move log. Index capture video for VideoDB scene search.",
            "source": "none",
        }
    return {"results": [], "message": "No matches found", "source": "none"}


def get_status_payload() -> dict[str, Any]:
    """Full VideoDB panel data for the sidebar."""
    media = get_media_mode()
    recap = get_recap_mode()
    configured = is_videodb_configured()
    conn = test_connection() if configured else {"ok": False, "error": "No API key"}

    return {
        "api_configured": configured,
        "connection_ok": conn.get("ok", False),
        "collection_id": conn.get("collection_id"),
        "connection_error": conn.get("error"),
        "media_mode": media.value,
        "recap_mode": recap,
        "scene_model": get_scene_model(),
        "media_modes": [
            {
                "id": "economy",
                "label": "Economy",
                "cost": "Free",
                "desc": "No generative calls per move",
            },
            {
                "id": "voice",
                "label": "Voice",
                "cost": "Low",
                "desc": "Local recap + one voiceover if cloud recap",
            },
            {
                "id": "image",
                "label": "Image",
                "cost": "Medium",
                "desc": "One AI image per turn",
            },
            {
                "id": "video",
                "label": "Video",
                "cost": "High",
                "desc": "One AI video per turn",
            },
        ],
        "recap_modes": [
            {
                "id": "local",
                "label": "Local slideshow",
                "cost": "Free",
                "desc": "Browser play-by-play from move log",
            },
            {
                "id": "cloud",
                "label": "Cloud timeline",
                "cost": "Credits",
                "desc": "VideoDB Timeline compile",
            },
        ],
        "cost_hint": (
            "economy + local recap = zero generative VideoDB calls during play."
        ),
        "docs_url": "https://docs.videodb.io/pages/getting-started/welcome",
        "console_url": "https://console.videodb.io",
    }


def board_to_ascii(board: list[str]) -> str:
    rows = []
    for r in range(3):
        row = " | ".join(board[r * 3 + c] or str(r * 3 + c) for c in range(3))
        rows.append(row)
    return "\n".join(rows)


def board_to_display_text(board: list[str], suggested: int | None = None) -> str:
    lines = ["TIC-TAC-TOE", "───────────"]
    for r in range(3):
        cells = []
        for c in range(3):
            i = r * 3 + c
            mark = board[i] or str(i)
            if suggested is not None and i == suggested:
                mark = f"[{mark}]"
            cells.append(f" {mark} ")
        lines.append("|" + "|".join(cells) + "|")
        if r < 2:
            lines.append("───────────")
    if suggested is not None:
        lines.append(f"Suggested next: cell {suggested}")
    return "\n".join(lines)


def resolve_player_url(
    stream_url: str | None = None,
    api_player_url: str | None = None,
) -> str | None:
    """Prefer API player_url (player.videodb.io); fallback from stream URL."""
    if api_player_url and str(api_player_url).startswith("http"):
        return api_player_url
    if stream_url:
        from urllib.parse import quote

        return f"{PLAYER_WATCH_BASE}{quote(stream_url, safe='')}"
    return None


def get_embed_url(player_url: str | None) -> str | None:
    if not player_url:
        return None
    try:
        from videodb._utils._video import player_url_to_embed_url

        return player_url_to_embed_url(player_url)
    except ValueError:
        return None


def player_payload(
    stream_url: str | None = None,
    api_player_url: str | None = None,
) -> dict[str, Any]:
    player = resolve_player_url(stream_url, api_player_url)
    return {
        "stream_url": stream_url,
        "player_url": player,
        "embed_url": get_embed_url(player),
    }


def get_video_player(video_id: str) -> dict[str, Any]:
    """Stream + player URLs for a collection video (opens in VideoDB player)."""
    if not is_videodb_configured():
        return {"ok": False, "error": "VIDEO_DB_API_KEY not configured"}
    try:
        conn = _connect()
        video = _collection(conn).get_video(video_id)
        if not video.stream_url:
            video.generate_stream()
        pl = player_payload(video.stream_url, video.player_url)
        return {
            "ok": True,
            "video_id": video_id,
            "name": video.name,
            **pl,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def is_videodb_configured() -> bool:
    _load_env()
    return bool(os.getenv("VIDEO_DB_API_KEY"))


def _connect():
    _load_env()
    import videodb

    return videodb.connect()


_resolved_collection_id: str | None = None


def resolve_collection_id(conn: Any) -> str:
    """Use configured collection, else default / first available on the account."""
    global _resolved_collection_id
    if _resolved_collection_id:
        return _resolved_collection_id

    configured = get_collection_id()
    if configured:
        try:
            coll = conn.get_collection(configured)
            _resolved_collection_id = coll.id
            return _resolved_collection_id
        except Exception:
            pass

    try:
        coll = conn.get_collection("default")
        _resolved_collection_id = coll.id
        return _resolved_collection_id
    except Exception:
        pass

    collections = conn.get_collections()
    if not collections:
        raise ValueError("No VideoDB collections on this account")
    _resolved_collection_id = collections[0].id
    return _resolved_collection_id


def _collection(conn):
    return conn.get_collection(resolve_collection_id(conn))


def session_path(session_id: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{session_id}.json"


def save_session(session_id: str, payload: dict[str, Any]) -> Path:
    path = session_path(session_id)
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_session(session_id: str) -> dict[str, Any]:
    path = session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session {session_id} not found")
    return json.loads(path.read_text())


def _board_prompt(
    board: list[str],
    last_cell: int,
    player: Player,
    suggested: int | None,
    narrative: str,
    suggestion_text: str | None = None,
) -> str:
    from app.game_engine import CELL_NAMES, cell_label

    grid = board_to_ascii(board)
    last_name = cell_label(last_cell)
    sug_line = ""
    if suggested is not None:
        sug_name = cell_label(suggested)
        coach = suggestion_text or f"Next best move: {sug_name} (cell {suggested})"
        sug_line = (
            f"Coach overlay: highlight {sug_name} square (index {suggested}) with a glow. "
            f"{coach}"
        )
    marks = []
    for i, c in enumerate(board):
        if c:
            marks.append(f"{CELL_NAMES[i]}={c}")
    state = ", ".join(marks) if marks else "empty board"
    return (
        "Broadcast-style tic-tac-toe graphic, dark purple UI, clean 3x3 grid, "
        "neon X in pink and O in cyan, sports broadcast lower-third. "
        f"Board state: {state}. Grid:\n{grid}\n"
        f"{player} just played {last_name} (cell {last_cell}). {narrative} {sug_line}"
    )


def attach_turn_media(analysis: MoveAnalysis) -> dict[str, Any]:
    """
    Optional media for the completed turn (one call per human click, not per piece).
    Returns dict with keys: mode, suggestion_stream_url, suggestion_player_url,
    suggestion_image_url, suggestion_video_id, error.
    """
    mode = get_media_mode()
    empty: dict[str, Any] = {
        "mode": mode.value,
        "suggestion_stream_url": None,
        "suggestion_player_url": None,
        "suggestion_embed_url": None,
        "suggestion_image_url": None,
        "suggestion_image_id": None,
        "suggestion_video_id": None,
        "error": None,
        "fallback": None,
        "generation_ok": None,
    }
    if not is_videodb_configured():
        return {**empty, "error": "VIDEO_DB_API_KEY not configured", "generation_ok": False}
    if mode == MediaMode.ECONOMY:
        return empty
    if mode == MediaMode.VOICE:
        return {**empty, "error": "Voice mode has no per-turn visual — use image or video"}

    board = [str(c) for c in analysis.board_after]
    try:
        conn = _connect()
        coll = _collection(conn)

        if mode == MediaMode.VIDEO:
            prompt = _board_prompt(
                board,
                analysis.cell,
                analysis.player,
                analysis.suggested_cell,
                analysis.narrative,
                analysis.suggestion_text,
            )
            gen_sec = get_video_generate_duration()
            playback_sec = get_video_playback_seconds()
            clip = coll.generate_video(prompt=prompt, duration=gen_sec)
            if not clip or not getattr(clip, "id", None):
                raise ValueError("generate_video returned no video")
            if playback_sec < gen_sec:
                pl = trim_video_clip(conn, clip.id, playback_sec)
            else:
                stream = clip.generate_stream()
                if not stream:
                    raise ValueError("Video stream not ready — try again in a few seconds")
                pl = player_payload(stream, getattr(clip, "player_url", None))
            return {
                **empty,
                "suggestion_stream_url": pl["stream_url"],
                "suggestion_player_url": pl["player_url"],
                "suggestion_embed_url": pl["embed_url"],
                "suggestion_video_id": clip.id,
                "generation_ok": True,
                "video_generate_sec": gen_sec,
                "video_playback_sec": playback_sec,
            }

        if mode == MediaMode.IMAGE:
            prompt = _board_prompt(
                board,
                analysis.cell,
                analysis.player,
                analysis.suggested_cell,
                analysis.narrative,
                analysis.suggestion_text,
            )
            image = coll.generate_image(prompt=prompt, aspect_ratio="16:9")
            if not image or not getattr(image, "id", None):
                raise ValueError("generate_image returned no image")
            url = _resolve_image_url(image)
            if not url:
                raise ValueError("Image URL not available — retry in a few seconds")
            return {
                **empty,
                "suggestion_image_url": url,
                "suggestion_image_id": image.id,
                "generation_ok": True,
            }
    except Exception as e:
        err = str(e).replace("\n", " ")[:240]
        conn = _connect()
        coll = _collection(conn)
        if mode == MediaMode.IMAGE:
            url, img_id = _fallback_collection_image(coll)
            if url:
                hint = (
                    "VideoDB image quota reached — showing latest image from your collection. "
                    "Upgrade at console.videodb.io or delete old images."
                    if _is_generation_limit_error(err)
                    else f"Generation failed — showing collection fallback. ({err})"
                )
                return {
                    **empty,
                    "suggestion_image_url": url,
                    "suggestion_image_id": img_id,
                    "error": hint,
                    "fallback": "collection_image",
                    "generation_ok": False,
                }
        if mode == MediaMode.VIDEO:
            fb = _fallback_collection_video(coll)
            if fb.get("suggestion_stream_url"):
                hint = (
                    "VideoDB video quota reached — playing latest video in your collection. "
                    "Upgrade at console.videodb.io."
                    if _is_generation_limit_error(err)
                    else f"Generation failed — showing collection fallback. ({err})"
                )
                return {
                    **empty,
                    **fb,
                    "error": hint,
                    "fallback": "collection_video",
                    "generation_ok": False,
                }
        return {**empty, "error": err, "generation_ok": False}
    return empty


def generate_suggestion_clip(
    analysis: MoveAnalysis,
) -> tuple[str | None, str | None, str | None]:
    """Deprecated path — use attach_turn_media. Kept for video mode callers."""
    media = attach_turn_media(analysis)
    return (
        media.get("suggestion_stream_url"),
        media.get("suggestion_player_url"),
        media.get("suggestion_video_id"),
    )


def build_recap_timeline(session: dict[str, Any]) -> dict[str, Any]:
    """
    One Timeline compile at game end (cheap vs N× generate_video).
    economy/voice: TextAsset slides from structured move log (NFL play-by-play data).
    image/video: reuse stored media IDs when present.
    """
    empty = {"stream_url": None, "player_url": None, "error": None}
    if not is_videodb_configured():
        return {**empty, "error": "VIDEO_DB_API_KEY not configured"}

    moves = session.get("moves", [])
    if not moves:
        return {**empty, "error": "No moves to compile"}

    mode = get_media_mode()
    try:
        from videodb.editor import (
            AudioAsset,
            Clip,
            Font,
            ImageAsset,
            TextAsset,
            Timeline,
            Track,
            VideoAsset,
        )

        conn = _connect()
        coll = _collection(conn)
        timeline = Timeline(conn)
        timeline.resolution = "1280x720"

        visual = Track()
        audio = Track()
        cursor = 0.0
        slide_duration = 3.0

        for move in moves:
            board = move.get("board_after", [])
            suggested = move.get("suggested_cell")
            body = board_to_display_text(board, suggested)
            body += f"\n\n{move['narrative']}"

            vid_id = move.get("suggestion_video_id")
            image_url = move.get("suggestion_image_url")

            if mode == MediaMode.VIDEO and vid_id:
                visual.add_clip(
                    cursor,
                    Clip(asset=VideoAsset(id=vid_id, start=0), duration=5.0),
                )
                seg = 5.0
            elif image_url and mode == MediaMode.IMAGE:
                # Re-use uploaded image id if stored on move
                img_id = move.get("suggestion_image_id")
                if img_id:
                    visual.add_clip(
                        cursor,
                        Clip(asset=ImageAsset(id=img_id), duration=slide_duration),
                    )
                    seg = slide_duration
                else:
                    visual.add_clip(
                        cursor,
                        Clip(
                            asset=TextAsset(text=body, font=Font(size=36)),
                            duration=slide_duration,
                        ),
                    )
                    seg = slide_duration
            else:
                visual.add_clip(
                    cursor,
                    Clip(
                        asset=TextAsset(text=body, font=Font(size=36)),
                        duration=slide_duration,
                    ),
                )
                seg = slide_duration

            cursor += seg

        if not visual.clips:
            return {**empty, "error": "No timeline clips built"}

        if mode == MediaMode.VOICE:
            script = _full_game_script(session)
            try:
                voice = coll.generate_voice(text=script, voice_name="Default")
                audio.add_clip(0, Clip(asset=AudioAsset(id=voice.id), duration=min(cursor, 60.0)))
            except Exception as e:
                return {**empty, "error": f"Voice generation failed: {e}"[:120]}

        timeline.add_track(visual)
        if audio.clips:
            timeline.add_track(audio)
        stream = timeline.generate_stream()
        pl = player_payload(stream, timeline.player_url)
        return {
            **pl,
            "error": None,
        }
    except Exception as e:
        return {**empty, "error": str(e)[:300]}


def _full_game_script(session: dict[str, Any]) -> str:
    winner = session.get("state", {}).get("winner")
    lines = ["Tic-tac-toe recap."]
    if winner and winner != "draw":
        lines.append(f"Winner: {winner}.")
    elif winner == "draw":
        lines.append("The game ended in a draw.")
    for move in session.get("moves", []):
        lines.append(
            f"Move {move['move_number']}. {move['player']} played cell {move['cell']}. "
            f"{move['narrative']}"
        )
    return " ".join(lines)


def index_session_video(
    video_id: str,
    moves: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    """Play-by-play indexing from desktop capture (NFL-style custom scenes)."""
    if not is_videodb_configured():
        return {"scene_index_id": None, "error": "VIDEO_DB_API_KEY not configured"}
    if not moves:
        return {"scene_index_id": None, "error": "No moves to index — play a game first"}
    if not video_id:
        return {"scene_index_id": None, "error": "No video_id provided"}

    try:
        from videodb.scene import Scene

        conn = _connect()
        coll = _collection(conn)
        video = coll.get_video(video_id)

        scenes = []
        for i, move in enumerate(moves):
            start = float(move.get("scene_start", i * 5))
            end = float(move.get("scene_end", start + 4))
            if end <= start:
                end = start + 3.0
            board_txt = board_to_ascii(move.get("board_after", []))
            description = (
                f"Move {move['move_number']}: {move['player']} played cell {move['cell']}. "
                f"{move.get('narrative', '')} Board:\n{board_txt}"
            )
            scenes.append(
                Scene(
                    video_id=video.id,
                    start=start,
                    end=end,
                    description=description[:2000],
                    metadata={
                        "move_number": move["move_number"],
                        "player": str(move["player"])[:30],
                        "cell": move["cell"],
                    },
                )
            )

        index_name = f"ttt_{session_id}"
        scene_index_id = None
        try:
            scene_index_id = video.index_scenes(
                scenes=scenes,
                name=index_name,
                prompt="Tic-tac-toe board state and the move just played.",
                model_name=get_scene_model(),
            )
        except Exception as e:
            match = re.search(r"id\s+([a-f0-9-]+)", str(e))
            if match:
                scene_index_id = match.group(1)
            else:
                return {"scene_index_id": None, "error": str(e)[:300]}

        if not scene_index_id:
            return {"scene_index_id": None, "error": "index_scenes returned no id"}

        return {
            "scene_index_id": scene_index_id,
            "error": None,
            "moves_indexed": len(moves),
        }
    except Exception as e:
        return {"scene_index_id": None, "error": str(e)[:300]}
