#!/usr/bin/env python3
"""Validate deployed API (Vercel frontend + Render backend)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = os.getenv("PROD_API", "https://videodb-play-api.onrender.com").rstrip("/")
ORIGIN = os.getenv("PROD_ORIGIN", "https://videodb-games-theme.vercel.app")


def req(method: str, path: str, body: dict | None = None, timeout: int = 120) -> tuple[int, dict | str]:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{API}{path}",
        method=method,
        headers={
            "Content-Type": "application/json",
            "Origin": ORIGIN,
        },
        data=data,
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as res:
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
    print(f"Production validation\n  API: {API}\n  Origin: {ORIGIN}\n")
    all_ok = True

    code, health = req("GET", "/api/health")
    all_ok &= check("Health", code == 200 and health.get("ok"), f"HTTP {code}")

    code, conn = req("POST", "/api/videodb/test-connection")
    all_ok &= check(
        "VideoDB connection",
        code == 200 and conn.get("ok") and conn.get("collection_id_ok", True),
        conn.get("collection_name", ""),
    )

    code, panel = req("GET", "/api/videodb/panel")
    all_ok &= check("Panel", code == 200 and panel.get("connection_ok"))

    code, sb = req("GET", "/api/sandbox/status")
    all_ok &= check(
        "Sandbox status",
        code == 200 and sb.get("configured"),
        f"active {sb.get('active_count')}/{sb.get('active_limit')}",
    )

    code, start = req("POST", "/api/sandbox/session/start", {"game_type": "tic_tac_toe"})
    all_ok &= check("Sandbox start", code == 200 and bool(start.get("session_id")))
    sid = start.get("session_id")

    code, move = req("POST", f"/api/sandbox/session/{sid}/action", {"cell": 4}, timeout=45)
    move_ok = code == 200
    flux_pending = move.get("flux_pending") if isinstance(move, dict) else False
    all_ok &= check(
        "Sandbox move",
        move_ok,
        f"flux_pending={flux_pending}" if move_ok else str(move)[:80],
    )

    if flux_pending and sid:
        import time

        for i in range(15):
            time.sleep(3)
            code, snap = req("GET", f"/api/sandbox/session/{sid}")
            if code == 200:
                moves = snap.get("moves") or []
                if moves and moves[-1].get("flux_image_url"):
                    all_ok &= check("FLUX async complete", True, moves[-1].get("flux_image_id", "")[:20])
                    break
                if moves and moves[-1].get("flux_status") == "failed":
                    all_ok &= check("FLUX async complete", False, moves[-1].get("flux_error", "")[:60])
                    break
        else:
            all_ok &= check("FLUX async complete", False, "timeout waiting for image")

    code, cleanup = req("POST", "/api/sandbox/cleanup?keep=1")
    all_ok &= check("Sandbox cleanup", code == 200 and cleanup.get("ok"))

    print()
    if all_ok:
        print("RESULT: Production checks passed.")
        return 0
    print("RESULT: Some production checks failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
