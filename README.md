# VideoDB Tic-Tac-Toe (Play-by-Play)

Interactive tic-tac-toe where **each move is a semantic “play”** (like the [NFL case study](https://docs.videodb.io/examples-and-tutorials/video-rag/case-study-nfl)): structured metadata per move, VideoDB-generated suggestion clips, and a final recap timeline.

## Prerequisites

1. **VideoDB API key** — [console.videodb.io](https://console.videodb.io) (free tier).
2. **Python 3.10+**

```bash
cp .env.example .env
# Add VIDEO_DB_API_KEY to .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload --port 8765
```

Open http://localhost:8765

## Deploy to the web

Recommended split: **API on Render**, **UI on Vercel**. The frontend reads `window.__API_BASE__` from `config.js` (injected at Vercel build time).

### 1. Push to GitHub

```bash
git init && git add . && git commit -m "Initial commit"
git remote add origin https://github.com/YOU/videodb-play.git
git push -u origin main
```

### 2. Render (backend API)

1. [render.com](https://render.com) → **New** → **Blueprint** → connect the repo (`render.yaml` is included).
2. Set secrets when prompted:
   - `VIDEO_DB_API_KEY`
   - `VIDEODB_COLLECTION_ID` (your real collection ID from the console)
3. After deploy, copy the service URL, e.g. `https://videodb-play-api.onrender.com`.
4. In Render **Environment**, set:
   - `CORS_ORIGINS` = your Vercel URL (set after step 3), e.g. `https://videodb-play.vercel.app`
5. Defaults in `render.yaml`: `VIDEODB_MEDIA_MODE=economy`, `VIDEODB_RECAP=local`, `SERVE_STATIC=false`.

**Free tier:** HTTP requests time out after **30 seconds**. Economy play + local recap work; **Sandbox FLUX** (30–90s per action) needs a paid Render instance or Railway.

### 3. Vercel (frontend)

1. [vercel.com](https://vercel.com) → **Add New** → **Project** → import the same GitHub repo.
2. Framework preset: **Other** (uses root `vercel.json`).
3. **Environment variable** (Production + Preview):

   | Name | Value |
   |------|--------|
   | `VIDEODB_API_BASE` | `https://your-service.onrender.com` (no trailing slash) |

4. Deploy. Open the Vercel URL — the UI calls the Render API.
5. Update Render `CORS_ORIGINS` to match the Vercel URL if you have not already.

Local Vercel build smoke test:

```bash
VIDEODB_API_BASE=https://your-api.onrender.com node scripts/build-vercel-frontend.js
npx serve dist
```

### GitHub Actions (git deployment)

Every push to `main` runs [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml):

1. Install deps, import-check the API, build the Vercel `dist/` bundle.
2. **Render** — auto-deploys when the Render service is connected to this repo; optionally set a **Deploy Hook** URL as repo secret `RENDER_DEPLOY_HOOK` to force a deploy from CI.
3. **Vercel** — auto-deploys when the Vercel project is connected to this repo; for CLI deploy from Actions, add secrets:
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
   - (optional) `VIDEODB_API_BASE` if not using the default Render URL in the workflow.

Manual redeploy: **Actions** → **Deploy** → **Run workflow**.

### 4. Docker (API only, local)

```bash
docker build -t videodb-play-api .
docker run --rm -p 8000:8000 \
  -e VIDEO_DB_API_KEY="your-key" \
  -e VIDEODB_COLLECTION_ID="c-your-collection-id" \
  -e SERVE_STATIC=false \
  -e CORS_ORIGINS=http://localhost:3000 \
  videodb-play-api
```

### 5. All-in-one (local or single host)

`uvicorn` still serves API + static on one port (`SERVE_STATIC` defaults to `true`). Same as **Run** above.

### Railway (optional — long sandbox jobs)

For **Sandbox compute** without a 30s cap, deploy the same `Dockerfile` on [Railway](https://railway.app) and point Vercel `VIDEODB_API_BASE` at the Railway URL instead of Render.

### Environment variables (production)

| Variable | Required | Notes |
|----------|----------|--------|
| `VIDEO_DB_API_KEY` | Yes | From [console.videodb.io](https://console.videodb.io) |
| `VIDEODB_COLLECTION_ID` | Yes | Your collection ID from the console |
| `VIDEODB_MEDIA_MODE` | No | `economy` recommended on free hosts |
| `VIDEODB_RECAP` | No | `local` = no extra credits |
| `VIDEODB_SANDBOX_TIER` | No | `medium` for FLUX + cloud recap |

Session JSON under `data/` is stored on the container disk (ephemeral on most PaaS — fine for demos).

## Cost control

| Setting | Default | Cost |
|---------|---------|------|
| `VIDEODB_MEDIA_MODE=economy` | yes | **$0** per move (local board + analysis) |
| `VIDEODB_RECAP=local` | yes | **$0** recap (browser slideshow from move log) |
| `VIDEODB_RECAP=cloud` | no | VideoDB Timeline compile (uses credits) |

**Recommended:** keep both defaults. Play-by-play JSON is still saved (NFL-style); recap is an instant local slideshow with Prev/Play/Next.

Cloud recap only if you need a hosted HLS video: set `VIDEODB_RECAP=cloud` or `POST /finish?cloud_recap=true`.

## Hackathon collection

All VideoDB calls use **one collection** (set in `.env`):

| | |
|--|--|
| **Name** | `test tic tac toe` |
| **ID** | `c-3cb42f31-1525-4170-9180-0d49a207b1bb` |
| **Console** | [console.videodb.io](https://console.videodb.io) → open this collection |

The **VideoDB** tab lists every asset in that collection and how the app uses VideoDB (generative clips, scene index, timeline recap). Move JSON under `data/sessions/` stays local and is not uploaded.

## How it maps to VideoDB

| NFL analysis | This game |
|--------------|-----------|
| Play-by-play timestamps | `scene_start` / `scene_end` per move |
| Structured stats JSON | Move log in `data/sessions/{id}.json` |
| Custom `Scene` boundaries | `video.index_scenes(scenes=...)` after desktop capture |
| VLM per play | `generate_video` suggestion clip per move |
| Final montage | Editor `Timeline` recap with voiceover |

## Optional: desktop capture mode

Record the browser while playing (macOS/Windows via [Capture SDK](https://docs.videodb.io/pages/ingest/capture-sdks/overview)), upload the session video, then:

```bash
POST /api/session/{id}/attach-capture
{"video_id": "vid-...", "move_timestamps": [{"start": 0, "end": 4}, ...]}
POST /api/session/{id}/finish
```

VideoDB indexes each move as its own scene and can `describe()` what happened on screen.

## Agent skill

VideoDB agent skill is installed at `.agents/skills/videodb` via:

```bash
npx skills add video-db/skills
```

## Docs

- [Welcome](https://docs.videodb.io/pages/getting-started/welcome)
- [Examples](https://docs.videodb.io/examples-and-tutorials)
- [Why agents are blind](https://docs.videodb.io/pages/philosophy/why-agents-are-blind)
