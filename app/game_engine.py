"""Tic-tac-toe logic and move analysis for VideoDB play-by-play metadata."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Literal

Player = Literal["X", "O"]
Cell = Literal["X", "O", ""]

# Human-friendly cell labels (0–8, row-major)
CELL_NAMES = (
    "top-left",
    "top-center",
    "top-right",
    "middle-left",
    "center",
    "middle-right",
    "bottom-left",
    "bottom-center",
    "bottom-right",
)

WIN_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def cell_label(cell: int | None) -> str:
    if cell is None or cell < 0 or cell > 8:
        return "—"
    return CELL_NAMES[cell]


@dataclass
class MoveAnalysis:
    cell: int
    player: Player
    board_before: list[Cell]
    board_after: list[Cell]
    suggested_cell: int | None
    suggestion_text: str | None
    blocking_required: bool
    winning_move_available: bool
    blunder: bool
    narrative: str


@dataclass
class GameState:
    board: list[Cell] = field(default_factory=lambda: [""] * 9)
    current_player: Player = "X"
    move_number: int = 0
    winner: Player | Literal["draw"] | None = None
    finished: bool = False

    def copy_board(self) -> list[Cell]:
        return copy.deepcopy(self.board)


def check_winner(board: list[Cell]) -> Player | None:
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]  # type: ignore[return-value]
    return None


def empty_cells(board: list[Cell]) -> list[int]:
    return [i for i, v in enumerate(board) if v == ""]


def minimax(board: list[Cell], player: Player, ai: Player) -> tuple[int, int | None]:
    winner = check_winner(board)
    if winner == ai:
        return 10, None
    if winner and winner != ai:
        return -10, None
    if not empty_cells(board):
        return 0, None

    best_score = -1000
    best_move: int | None = None
    for cell in empty_cells(board):
        next_board = board.copy()
        next_board[cell] = player
        score, _ = minimax(next_board, "O" if player == "X" else "X", ai)
        score = -score
        if score > best_score:
            best_score = score
            best_move = cell
    return best_score, best_move


def suggest_move(board: list[Cell], for_player: Player) -> int | None:
    _, move = minimax(board, for_player, for_player)
    return move


def opponent(p: Player) -> Player:
    return "O" if p == "X" else "X"


def _winning_cell(board: list[Cell], player: Player) -> int | None:
    """Return the empty cell that completes a line for player, if any."""
    for a, b, c in WIN_LINES:
        line = [board[a], board[b], board[c]]
        if line.count(player) == 2 and line.count("") == 1:
            for cell in (a, b, c):
                if not board[cell]:
                    return cell
    return None


def _threat_cells(board: list[Cell], player: Player) -> list[int]:
    """Cells where player has two in a line with one empty (setup / block targets)."""
    threats: list[int] = []
    for a, b, c in WIN_LINES:
        line = [board[a], board[b], board[c]]
        if line.count(player) == 2 and line.count("") == 1:
            for cell in (a, b, c):
                if not board[cell] and cell not in threats:
                    threats.append(cell)
    return threats


def build_suggestion_text(board: list[Cell], for_player: Player) -> tuple[int | None, str]:
    """
    Optimal next cell plus coach-style advice for the human player.
    Uses minimax for the cell and heuristics for readable strategy copy.
    """
    cell = suggest_move(board, for_player)
    if cell is None:
        if not empty_cells(board):
            return None, "Board is full — no moves left."
        return None, "No legal moves available."

    name = cell_label(cell)
    opp = opponent(for_player)
    win_now = _winning_cell(board, for_player)
    block = _winning_cell(board, opp)

    if win_now is not None:
        if cell == win_now:
            return cell, f"Play {name} ({cell}) — you can win this turn."
        return cell, f"Play {name} ({cell}) — finish the game at {cell_label(win_now)}."

    if block is not None and cell == block:
        return cell, f"Play {name} ({cell}) — block {opp}'s winning line."

    if cell == 4 and not board[4]:
        return cell, f"Take the {name} ({cell}) — strongest opening / endgame anchor."

    corners = {0, 2, 6, 8}
    if cell in corners:
        return cell, f"Play {name} ({cell}) — corner pressure keeps two winning lines alive."

    threats = _threat_cells(board, for_player)
    if cell in threats:
        return cell, f"Play {name} ({cell}) — build a fork (two ways to win next)."

    return cell, f"Play {name} ({cell}) — best engine line for {for_player} from here."


def analyze_move(
    board_before: list[Cell],
    cell: int,
    player: Player,
    board_after: list[Cell],
) -> MoveAnalysis:
    suggested, suggestion_text = build_suggestion_text(board_after, opponent(player))
    opp_win = suggest_move(board_before, opponent(player))
    blocking = opp_win == cell if opp_win is not None else False
    win_avail = suggest_move(board_before, player) == cell
    optimal_before = suggest_move(board_before, player)
    blunder = (
        optimal_before is not None
        and cell != optimal_before
        and check_winner(board_after) is None
        and len(empty_cells(board_after)) > 0
    )

    if check_winner(board_after) == player:
        narrative = f"{player} played cell {cell} and secured the win."
    elif check_winner(board_after):
        narrative = f"{player} played cell {cell}; the game ended."
    elif blunder:
        narrative = (
            f"{player} chose cell {cell} instead of the stronger cell "
            f"{optimal_before}, leaving a better line for {opponent(player)}."
        )
    elif blocking:
        narrative = f"{player} blocked {opponent(player)} at cell {cell}."
    elif win_avail:
        narrative = f"{player} took a winning opportunity at cell {cell}."
    else:
        narrative = f"{player} placed at cell {cell}; position remains balanced."

    return MoveAnalysis(
        cell=cell,
        player=player,
        board_before=board_before,
        board_after=board_after,
        suggested_cell=suggested,
        suggestion_text=suggestion_text,
        blocking_required=blocking,
        winning_move_available=win_avail,
        blunder=blunder,
        narrative=narrative,
    )


def apply_move(state: GameState, cell: int) -> MoveAnalysis:
    if state.finished:
        raise ValueError("Game is already finished")
    if cell < 0 or cell > 8 or state.board[cell]:
        raise ValueError("Invalid cell")

    before = state.copy_board()
    player = state.current_player
    state.board[cell] = player
    state.move_number += 1
    analysis = analyze_move(before, cell, player, state.copy_board())

    winner = check_winner(state.board)
    if winner:
        state.winner = winner
        state.finished = True
    elif not empty_cells(state.board):
        state.winner = "draw"
        state.finished = True
    else:
        state.current_player = opponent(player)

    return analysis
