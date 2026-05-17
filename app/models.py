from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Player = Literal["X", "O"]


class StartSessionResponse(BaseModel):
    session_id: str
    board: list[str]
    current_player: Player
    videodb_enabled: bool
    capture_mode: bool
    media_mode: str = "economy"


class TurnMedia(BaseModel):
    mode: str
    suggestion_stream_url: str | None = None
    suggestion_player_url: str | None = None
    suggestion_embed_url: str | None = None
    suggestion_image_url: str | None = None
    suggestion_image_id: str | None = None
    suggestion_video_id: str | None = None
    error: str | None = None
    fallback: str | None = None
    generation_ok: bool | None = None


class MoveRequest(BaseModel):
    cell: int = Field(ge=0, le=8)


class MoveRecord(BaseModel):
    move_number: int
    player: Player
    cell: int
    board_after: list[str]
    suggested_cell: int | None
    suggestion_text: str | None = None
    narrative: str
    blunder: bool
    suggestion_stream_url: str | None = None
    suggestion_player_url: str | None = None
    suggestion_image_url: str | None = None
    suggestion_video_id: str | None = None
    scene_start: float | None = None
    scene_end: float | None = None


class MoveResponse(BaseModel):
    session_id: str
    board: list[str]
    current_player: Player
    finished: bool
    winner: str | None
    last_move: MoveRecord
    opponent_suggestion: MoveRecord | None = None
    highlight_cell: int | None = None
    suggestion_text: str | None = None
    turn_media: TurnMedia | None = None
    media_mode: str = "economy"


class FinishResponse(BaseModel):
    session_id: str
    winner: str | None
    moves: list[MoveRecord]
    recap_stream_url: str | None
    recap_player_url: str | None
    recap_embed_url: str | None = None
    recap_mode: str = "local"
    move_log_path: str
    scene_index_id: str | None = None
    message: str


class AttachCaptureRequest(BaseModel):
    video_id: str
    move_timestamps: list[dict[str, Any]] | None = None


class SearchFootageRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class SandboxFluxMedia(BaseModel):
    image_url: str | None = None
    image_id: str | None = None
    error: str | None = None
    generation_ok: bool | None = None
    fallback: str | None = None
    flux_pending: bool = False


class SandboxStartRequest(BaseModel):
    game_type: str = "tic_tac_toe"


class SandboxActionRequest(BaseModel):
    cell: int | None = Field(default=None, ge=0, le=8)
    action: dict[str, Any] | None = None


class SandboxStartResponse(BaseModel):
    session_id: str
    game_type: str
    state: dict[str, Any]
    board: list[str] | None = None
    current_player: str | None = None
    sandbox: dict[str, Any]
    usage: dict[str, Any]
    games: list[dict[str, str]] = []


class SandboxActionResponse(BaseModel):
    session_id: str
    game_type: str
    state: dict[str, Any]
    board: list[str] | None = None
    current_player: str | None = None
    finished: bool
    winner: str | None = None
    last_move: dict[str, Any]
    opponent_move: dict[str, Any] | None = None
    highlight_cell: int | None = None
    suggestion_text: str | None = None
    suggested_action: str | None = None
    turn_media: SandboxFluxMedia
    flux_pending: bool = False
    sandbox_id: str | None = None
    sandbox_status: str | None = None
    usage: dict[str, Any]
    games: list[dict[str, str]] = []


# Backward-compatible alias
SandboxMoveResponse = SandboxActionResponse


class SandboxFinishResponse(BaseModel):
    session_id: str
    winner: str | None = None
    moves: list[dict[str, Any]] = []
    recap_stream_url: str | None = None
    recap_player_url: str | None = None
    recap_embed_url: str | None = None
    recap_error: str | None = None
    recap_pending: bool = False
    usage: dict[str, Any] = {}
    global_usage: dict[str, Any] = {}
    message: str = ""
