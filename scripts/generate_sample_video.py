#!/usr/bin/env python3
"""Generate one tic-tac-toe clip in the configured VideoDB collection."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app import videodb_game as v


def main() -> int:
    if not v.is_videodb_configured():
        print("ERROR: Set VIDEO_DB_API_KEY in .env")
        return 1

    gen_sec = v.get_video_generate_duration()
    playback_sec = v.get_video_playback_seconds()
    print(f"Mode: video · generate {gen_sec}s · playback {playback_sec}s")

    from app.game_engine import GameState, apply_move, suggest_move

    state = GameState()
    apply_move(state, 4)
    o_cell = suggest_move(state.board, "O")
    analysis = apply_move(state, o_cell)

    print("Generating (this can take 30–90s)…")
    media = v.attach_turn_media(analysis)

    if media.get("error") and not media.get("suggestion_stream_url"):
        print(f"FAILED: {media['error']}")
        return 1

    print("OK")
    if media.get("error"):
        print(f"Note: {media['error']}")
    print(f"Video ID: {media.get('suggestion_video_id')}")
    print(f"Stream:   {media.get('suggestion_stream_url')}")
    print(f"Player:   {media.get('suggestion_player_url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
