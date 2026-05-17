"""
Immersive sandbox games — shared play-by-play + coach + FLUX prompts.

Each game logs structured "moves" for VideoDB recap (NFL-style metadata).
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from typing import Any, Literal

from app.game_engine import GameState, MoveAnalysis, apply_move, suggest_move

GameType = Literal["tic_tac_toe", "fps", "car"]

GAME_CATALOG: list[dict[str, str]] = [
    {
        "id": "tic_tac_toe",
        "title": "Tic-Tac-Toe",
        "tagline": "Classic grid duel with AI coach on every turn.",
        "icon": "▦",
    },
    {
        "id": "fps",
        "title": "Arena FPS",
        "tagline": "Top-down shooter — clear waves, save ammo, chase high score.",
        "icon": "◎",
    },
    {
        "id": "car",
        "title": "Neon Drift",
        "tagline": "Three-lane dodge runner — weave traffic at rising speed.",
        "icon": "▸",
    },
]


@dataclass
class CoachResult:
    narrative: str
    suggestion_text: str | None
    suggested_action: str | None
    highlight: Any = None
    blunder: bool = False


def initial_state(game_type: GameType) -> dict[str, Any]:
    if game_type == "tic_tac_toe":
        return {
            "board": [""] * 9,
            "current_player": "X",
            "move_number": 0,
            "winner": None,
            "finished": False,
        }
    if game_type == "fps":
        return {
            "hp": 100,
            "ammo": 24,
            "max_ammo": 24,
            "score": 0,
            "wave": 1,
            "kills": 0,
            "player": {"x": 50, "y": 75},
            "enemies": _spawn_fps_wave(1),
            "finished": False,
            "winner": None,
            "move_number": 0,
        }
    if game_type == "car":
        return {
            "lane": 1,
            "distance": 0.0,
            "speed": 1.0,
            "score": 0,
            "crashes": 0,
            "obstacles": _spawn_car_obstacles(3),
            "finished": False,
            "winner": None,
            "move_number": 0,
        }
    raise ValueError(f"Unknown game: {game_type}")


def apply_action(
    game_type: GameType,
    state: dict[str, Any],
    action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], CoachResult]:
    """Returns new state, move records (1+), and coach for FLUX."""
    if game_type == "tic_tac_toe":
        return _ttt_action(state, action)
    if game_type == "fps":
        return _fps_action(state, action)
    if game_type == "car":
        return _car_action(state, action)
    raise ValueError(f"Unknown game: {game_type}")


def flux_prompt(
    game_type: GameType,
    state: dict[str, Any],
    move: dict[str, Any],
    coach: CoachResult,
) -> str:
    if game_type == "tic_tac_toe":
        board = move.get("board_after") or state.get("board", [])
        from app import videodb_game as vdb

        return vdb._board_prompt(
            [str(c) for c in board],
            move.get("cell", 0),
            move.get("player", "X"),
            move.get("suggested_cell"),
            move.get("narrative", coach.narrative),
            coach.suggestion_text,
        )
    if game_type == "fps":
        return (
            "Cinematic first-person shooter HUD, neon cyberpunk arena, "
            "top-down tactical view with crosshair and enemy silhouettes. "
            f"Wave {state.get('wave')}, HP {state.get('hp')}, ammo {state.get('ammo')}, "
            f"score {state.get('score')}, {len(state.get('enemies', []))} hostiles. "
            f"Last action: {move.get('action_label')}. {coach.narrative} "
            f"Coach overlay: {coach.suggestion_text or 'hold position'}."
        )
    if game_type == "car":
        return (
            "Top-down arcade racing, neon highway at night, three lanes, "
            "glowing sports car, motion blur, synthwave palette. "
            f"Lane {state.get('lane')}, speed {state.get('speed', 1):.1f}x, "
            f"distance {int(state.get('distance', 0))}m, score {state.get('score')}. "
            f"Last action: {move.get('action_label')}. {coach.narrative} "
            f"Coach: {coach.suggestion_text or 'stay center'}."
        )
    return coach.narrative


def recap_script_line(game_type: GameType, move: dict[str, Any]) -> str:
    if game_type == "tic_tac_toe":
        return (
            f"Move {move['move_number']}. {move['player']} played cell {move['cell']}. "
            f"{move.get('narrative', '')}"
        )
    return (
        f"Play {move['move_number']}. {move.get('action_label', 'action')}. "
        f"{move.get('narrative', '')}"
    )


# —— Tic-tac-toe ——


def _ttt_action(
    state: dict[str, Any],
    action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], CoachResult]:
    if state.get("finished"):
        raise ValueError("Game already finished")
    cell = action.get("cell")
    if cell is None:
        raise ValueError("tic_tac_toe requires action.cell (0-8)")
    cell = int(cell)

    gs = GameState()
    gs.board = list(state["board"])
    gs.current_player = state["current_player"]
    gs.move_number = state["move_number"]
    gs.winner = state.get("winner")
    gs.finished = state["finished"]

    if gs.current_player != "X":
        raise ValueError("Only human (X) moves via this endpoint")

    analysis = apply_move(gs, cell)
    moves: list[dict[str, Any]] = []
    record = _ttt_record(analysis, gs.move_number)
    moves.append(record)

    if not gs.finished and gs.current_player == "O":
        ai_cell = suggest_move(gs.board, "O")
        if ai_cell is not None:
            ai_analysis = apply_move(gs, ai_cell)
            moves.append(_ttt_record(ai_analysis, gs.move_number))

    new_state = {
        "board": gs.board,
        "current_player": gs.current_player,
        "move_number": gs.move_number,
        "winner": gs.winner,
        "finished": gs.finished,
    }

    last = moves[-1]
    coach = CoachResult(
        narrative=last["narrative"],
        suggestion_text=last.get("suggestion_text"),
        suggested_action=str(last.get("suggested_cell"))
        if last.get("suggested_cell") is not None
        else None,
        highlight=last.get("suggested_cell"),
        blunder=last.get("blunder", False),
    )
    return new_state, moves, coach


def _ttt_record(analysis: MoveAnalysis, move_number: int) -> dict[str, Any]:
    return {
        "move_number": move_number,
        "player": analysis.player,
        "cell": analysis.cell,
        "action_label": f"{analysis.player} → cell {analysis.cell}",
        "board_after": [str(c) for c in analysis.board_after],
        "suggested_cell": analysis.suggested_cell,
        "suggestion_text": analysis.suggestion_text,
        "narrative": analysis.narrative,
        "blunder": analysis.blunder,
        "flux_image_url": None,
        "flux_image_id": None,
    }


# —— FPS ——


def _spawn_fps_wave(wave: int) -> list[dict[str, Any]]:
    count = min(2 + wave, 6)
    enemies = []
    for i in range(count):
        enemies.append(
            {
                "id": f"e{i}",
                "x": random.randint(15, 85),
                "y": random.randint(10, 45),
                "hp": 20 + wave * 5,
            }
        )
    return enemies


def _fps_action(
    state: dict[str, Any],
    action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], CoachResult]:
    if state.get("finished"):
        raise ValueError("Game already finished")

    st = copy.deepcopy(state)
    st["move_number"] = int(st.get("move_number", 0)) + 1
    kind = (action.get("type") or "move").lower()
    label = ""
    narrative_parts: list[str] = []

    px, py = st["player"]["x"], st["player"]["y"]
    step = 12

    if kind == "move":
        d = (action.get("direction") or "").lower()
        if d == "up":
            py = max(20, py - step)
            label = "Advance north"
        elif d == "down":
            py = min(90, py + step)
            label = "Fall back south"
        elif d == "left":
            px = max(10, px - step)
            label = "Strafe left"
        elif d == "right":
            px = min(90, px + step)
            label = "Strafe right"
        else:
            raise ValueError("fps move needs direction: up|down|left|right")
        st["player"] = {"x": px, "y": py}
        narrative_parts.append(f"Repositioned to ({px}, {py}).")

    elif kind == "shoot":
        if st["ammo"] <= 0:
            raise ValueError("Out of ammo — pick up by clearing a wave")
        st["ammo"] -= 1
        label = "Fire weapon"
        if not st["enemies"]:
            narrative_parts.append("Shot into empty air — no targets.")
        else:
            target = min(
                st["enemies"],
                key=lambda e: (e["x"] - px) ** 2 + (e["y"] - py) ** 2,
            )
            dist = ((target["x"] - px) ** 2 + (target["y"] - py) ** 2) ** 0.5
            dmg = 35 if dist < 35 else 18
            target["hp"] -= dmg
            narrative_parts.append(
                f"Engaged hostile at ({target['x']}, {target['y']}) for {dmg} damage."
            )
            if target["hp"] <= 0:
                st["enemies"] = [e for e in st["enemies"] if e["id"] != target["id"]]
                st["kills"] = int(st.get("kills", 0)) + 1
                st["score"] = int(st.get("score", 0)) + 100
                narrative_parts.append("Target eliminated.")

        if not st["enemies"]:
            st["wave"] = int(st.get("wave", 1)) + 1
            st["enemies"] = _spawn_fps_wave(st["wave"])
            st["ammo"] = min(st["max_ammo"], st["ammo"] + 8)
            narrative_parts.append(f"Wave {st['wave']} inbound — resupply +8 ammo.")

    elif kind == "reload":
        gain = min(st["max_ammo"] - st["ammo"], 12)
        st["ammo"] += gain
        label = "Tactical reload"
        narrative_parts.append(f"Reloaded +{gain} rounds.")

    else:
        raise ValueError("fps action type: move | shoot | reload")

    # Enemy fire
    if st["enemies"] and not st.get("finished"):
        hits = random.randint(0, min(2, len(st["enemies"])))
        if hits:
            dmg = hits * random.randint(8, 14)
            st["hp"] = max(0, st["hp"] - dmg)
            narrative_parts.append(f"Took {dmg} return fire from {hits} hostile(s).")

    if st["hp"] <= 0:
        st["finished"] = True
        st["winner"] = "defeat"
        narrative_parts.append("Operator down — mission failed.")
    elif int(st.get("score", 0)) >= 500:
        st["finished"] = True
        st["winner"] = "victory"
        narrative_parts.append("Score threshold reached — extraction authorized.")

    coach = _fps_coach(st)
    move = {
        "move_number": st["move_number"],
        "player": "operator",
        "action_label": label,
        "action_type": kind,
        "narrative": " ".join(narrative_parts),
        "suggestion_text": coach.suggestion_text,
        "suggested_action": coach.suggested_action,
        "blunder": coach.blunder,
        "flux_image_url": None,
        "flux_image_id": None,
        "snapshot": {
            "hp": st["hp"],
            "ammo": st["ammo"],
            "score": st["score"],
            "wave": st["wave"],
            "enemies": len(st["enemies"]),
            "player": st["player"],
        },
    }
    return st, [move], coach


def _fps_coach(st: dict[str, Any]) -> CoachResult:
    enemies = st.get("enemies") or []
    px, py = st["player"]["x"], st["player"]["y"]
    if st["hp"] < 30:
        return CoachResult(
            "Critical health — disengage and reload behind cover.",
            "Fall back (down) and reload before re-engaging.",
            "reload",
        )
    if st["ammo"] < 4 and enemies:
        return CoachResult(
            "Magazine nearly dry with hostiles active.",
            "Reload now or risk being overrun.",
            "reload",
        )
    if not enemies:
        return CoachResult(
            "Lane clear — next wave incoming.",
            "Advance and prep for the next spawn.",
            "move:up",
        )
    nearest = min(enemies, key=lambda e: (e["x"] - px) ** 2 + (e["y"] - py) ** 2)
    if st["ammo"] > 0:
        return CoachResult(
            f"Nearest threat at ({nearest['x']}, {nearest['y']}) with {nearest['hp']} HP.",
            "Line up the shot — fire when centered.",
            "shoot",
        )
    return CoachResult(
        "Out of ammo with enemies on field.",
        "Reload immediately.",
        "reload",
    )


# —— Car ——


def _spawn_car_obstacles(n: int) -> list[dict[str, Any]]:
    obs = []
    for i in range(n):
        obs.append({"id": f"o{i}", "lane": random.randint(0, 2), "y": 20 + i * 28})
    return obs


def _car_action(
    state: dict[str, Any],
    action: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], CoachResult]:
    if state.get("finished"):
        raise ValueError("Game already finished")

    st = copy.deepcopy(state)
    st["move_number"] = int(st.get("move_number", 0)) + 1
    kind = (action.get("type") or "steer").lower()
    lane = int(st.get("lane", 1))
    label = ""

    if kind == "steer":
        d = (action.get("direction") or "").lower()
        if d == "left" and lane > 0:
            lane -= 1
            label = "Steer left"
        elif d == "right" and lane < 2:
            lane += 1
            label = "Steer right"
        elif d in ("left", "right"):
            label = f"Lane hold ({d} blocked)"
        else:
            raise ValueError("car steer needs direction: left | right")
        st["lane"] = lane
    elif kind == "boost":
        st["speed"] = min(3.0, float(st.get("speed", 1)) + 0.25)
        label = "Boost"
    else:
        raise ValueError("car action type: steer | boost")

    advance = 18 * float(st.get("speed", 1))
    st["distance"] = float(st.get("distance", 0)) + advance
    st["score"] = int(st.get("score", 0)) + int(advance // 2)

    obstacles = st.get("obstacles") or []
    for o in obstacles:
        o["y"] = float(o["y"]) + advance * 0.85
    obstacles = [o for o in obstacles if o["y"] < 100]
    while len(obstacles) < 4:
        obstacles.append(
            {
                "id": f"o{random.randint(0, 999)}",
                "lane": random.randint(0, 2),
                "y": random.randint(-15, 15),
            }
        )
    st["obstacles"] = obstacles

    crash = any(o["lane"] == st["lane"] and 72 <= o["y"] <= 92 for o in obstacles)
    narrative_parts = [f"{label}. Traveled +{int(advance)}m at {st['speed']:.1f}x."]
    if crash:
        st["crashes"] = int(st.get("crashes", 0)) + 1
        st["speed"] = max(1.0, float(st["speed"]) - 0.3)
        narrative_parts.append("Collision — speed reduced.")
        if st.get("crashes", 0) >= 3:
            st["finished"] = True
            st["winner"] = "defeat"
            narrative_parts.append("Three strikes — run over.")
    elif st["distance"] >= 800:
        st["finished"] = True
        st["winner"] = "victory"
        narrative_parts.append("Finish line — legendary run.")

    coach = _car_coach(st)
    move = {
        "move_number": st["move_number"],
        "player": "driver",
        "action_label": label,
        "action_type": kind,
        "narrative": " ".join(narrative_parts),
        "suggestion_text": coach.suggestion_text,
        "suggested_action": coach.suggested_action,
        "blunder": coach.blunder,
        "flux_image_url": None,
        "flux_image_id": None,
        "snapshot": {
            "lane": st["lane"],
            "distance": st["distance"],
            "speed": st["speed"],
            "score": st["score"],
            "obstacles": st["obstacles"],
        },
    }
    return st, [move], coach


def _car_coach(st: dict[str, Any]) -> CoachResult:
    lane = int(st.get("lane", 1))
    threats = [
        o
        for o in (st.get("obstacles") or [])
        if 50 <= float(o.get("y", 0)) <= 95
    ]
    if not threats:
        return CoachResult(
            "Open road ahead — build speed carefully.",
            "Boost when the center lane is clear.",
            "boost",
        )
    urgent = min(threats, key=lambda o: o["y"])
    tl = int(urgent["lane"])
    if tl == lane:
        dodge = "right" if lane < 2 else "left"
        return CoachResult(
            f"Obstacle dead ahead in lane {lane}.",
            f"Steer {dodge} immediately.",
            f"steer:{dodge}",
            blunder=True,
        )
    if tl < lane:
        return CoachResult(
            f"Threat in left lane — you're in lane {lane}.",
            "Hold or steer right to widen gap.",
            "steer:right",
        )
    return CoachResult(
        f"Threat in right lane — you're in lane {lane}.",
        "Hold or steer left to widen gap.",
        "steer:left",
    )
