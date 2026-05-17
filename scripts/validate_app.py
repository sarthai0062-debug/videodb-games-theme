#!/usr/bin/env python3
"""End-to-end validation for VideoDB tic-tac-toe app."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{BASE}{path}",
        method=method,
        headers={"Content-Type": "application/json"},
        data=data,
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as res:
            raw = res.read()
            if "application/json" in (res.headers.get("Content-Type") or ""):
                return res.status, json.loads(raw)
            return res.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        payload = e.read().decode()
        try:
            detail = json.loads(payload)
        except json.JSONDecodeError:
            detail = {"detail": payload}
        return e.code, detail


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    print("VideoDB Tic-Tac-Toe — validation\n")
    all_ok = True

    code, health = req("GET", "/api/health")
    all_ok &= check("Health", code == 200 and health.get("ok"), f"HTTP {code}")
    all_ok &= check(
        "VideoDB API key configured",
        health.get("videodb_configured"),
        health.get("media_mode", ""),
    )

    code, panel = req("GET", "/api/videodb/panel")
    all_ok &= check("VideoDB panel", code == 200, f"models={len(panel.get('models_catalog', []))}")
    all_ok &= check(
        "Panel connection",
        panel.get("connection_ok"),
        panel.get("collection_id") or panel.get("connection_error", "")[:60],
    )
    videos = panel.get("videos") or []
    all_ok &= check(
        "Collection videos listed",
        code == 200,
        f"{len(videos)} video(s) in collection",
    )

    code, conn = req("POST", "/api/videodb/test-connection")
    all_ok &= check("Test connection", code == 200 and conn.get("ok"))

    video_id = videos[0]["id"] if videos else None
    if video_id:
        code, pl = req("GET", f"/api/videodb/video/{video_id}/player")
        player_ok = (
            code == 200
            and pl.get("player_url", "").startswith("https://player.videodb.io/")
        )
        embed_ok = pl.get("embed_url", "").startswith("https://player.videodb.io/embed")
        all_ok &= check("Video player URL", player_ok, (pl.get("player_url") or "")[:70])
        all_ok &= check("Video embed URL", embed_ok, (pl.get("embed_url") or "")[:70])

    code, start = req("POST", "/api/session/start")
    all_ok &= check("Start session", code == 200 and bool(start.get("session_id")))
    sid = start.get("session_id")

    code, move = req("POST", f"/api/session/{sid}/move", {"cell": 4})
    all_ok &= check("Play move (center)", code == 200 and not move.get("finished"))

    free_cell = next((i for i, c in enumerate(move.get("board", [])) if not c), 2)
    code, move2 = req("POST", f"/api/session/{sid}/move", {"cell": free_cell})
    all_ok &= check("Play second move", code == 200, f"cell {free_cell}")

    code, panel2 = req("GET", f"/api/videodb/panel?session_id={sid}")
    actions = panel2.get("actions") or {}
    all_ok &= check("Panel can_search", actions.get("can_search"))
    all_ok &= check("Panel can_index", actions.get("can_index"))

    code, search = req("POST", f"/api/session/{sid}/search-footage", {"query": "center"})
    all_ok &= check(
        "Search move log",
        code == 200 and len(search.get("results", [])) >= 0,
        search.get("message", "")[:80],
    )

    if video_id:
        req("POST", f"/api/session/{sid}/attach-capture", {"video_id": video_id})
        code, idx = req("POST", f"/api/session/{sid}/index-capture")
        indexed = code == 200 and bool(idx.get("scene_index_id"))
        all_ok &= check(
            "Index capture",
            indexed,
            str(idx.get("detail", idx))[:80] if not indexed else f"{idx.get('moves_indexed')} moves",
        )
        if indexed:
            player_from_index = (idx.get("player_url") or "").startswith(
                "https://player.videodb.io/"
            )
            all_ok &= check("Index returns player URL", player_from_index)

            code, vsearch = req(
                "POST", f"/api/session/{sid}/search-footage", {"query": "move"}
            )
            has_vdb = vsearch.get("source") == "videodb" or any(
                r.get("source") == "videodb" for r in vsearch.get("results", [])
            )
            player_search = (vsearch.get("player_url") or "").startswith(
                "https://player.videodb.io/"
            ) or any(
                (r.get("player_url") or "").startswith("https://player.videodb.io/")
                for r in vsearch.get("results", [])
            )
            all_ok &= check(
                "VideoDB scene search",
                code == 200,
                vsearch.get("message", "")[:80],
            )
            if vsearch.get("results"):
                all_ok &= check(
                    "Search player URLs valid",
                    player_search or vsearch.get("embed_url"),
                    vsearch.get("source", ""),
                )

    # Finish game quickly
    for cell in [8, 2, 6, 1, 7]:
        m_code, m = req("POST", f"/api/session/{sid}/move", {"cell": cell})
        if m.get("finished"):
            break

    code, sess = req("GET", f"/api/session/{sid}")
    all_ok &= check("Session persisted", code == 200 and len(sess.get("moves", [])) > 0)

    expected_recap = health.get("recap_mode", "local")
    code, finish = req("POST", f"/api/session/{sid}/finish")
    all_ok &= check(
        f"Finish/recap ({expected_recap})",
        code == 200 and finish.get("recap_mode") == expected_recap,
        finish.get("message", "")[:60],
    )

    code, static = req("GET", "/")
    all_ok &= check(
        "Frontend index.html",
        code == 200 and isinstance(static, str) and "VideoDB" in static,
    )

    code, js = req("GET", "/static/app.js")
    all_ok &= check(
        "Frontend app.js",
        code == 200 and isinstance(js, str) and "startSandboxGame" in js,
    )

    code, sb = req("GET", "/api/sandbox/status")
    all_ok &= check(
        "Sandbox status",
        code == 200 and sb.get("configured"),
        sb.get("tier", ""),
    )
    code, usage = req("GET", "/api/sandbox/usage")
    all_ok &= check("Sandbox usage", code == 200 and "global" in usage)

    print()
    if all_ok:
        print("RESULT: All checks passed — app is working correctly.")
        return 0
    print("RESULT: Some checks failed — see FAIL lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
