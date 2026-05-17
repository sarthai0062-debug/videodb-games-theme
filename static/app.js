const API = (typeof window !== "undefined" && window.__API_BASE__
  ? String(window.__API_BASE__).replace(/\/$/, "")
  : "");

const boardEl = document.getElementById("board");
const statusBar = document.getElementById("status-bar");
const sessionLabel = document.getElementById("session-label");
const turnLabel = document.getElementById("turn-label");
const narrativeEl = document.getElementById("narrative");
const suggestionText = document.getElementById("suggestion-text");
const resultEl = document.getElementById("result");
const btnNew = document.getElementById("btn-new");
const btnFinish = document.getElementById("btn-finish");
const recapWrap = document.getElementById("recap-wrap");
const recapSlideshow = document.getElementById("recap-slideshow");
const recapTitle = document.getElementById("recap-title");
const recapBoard = document.getElementById("recap-board");
const recapMoveMeta = document.getElementById("recap-move-meta");
const recapMoveText = document.getElementById("recap-move-text");
const recapCounter = document.getElementById("recap-counter");
const recapPrev = document.getElementById("recap-prev");
const recapNext = document.getElementById("recap-next");
const recapPlayBtn = document.getElementById("recap-play");

const pageTitle = document.getElementById("page-title");
const navTabs = document.querySelectorAll(".nav-tab");
const views = {
  videodb: document.getElementById("section-videodb"),
  play: document.getElementById("section-play"),
  "sandbox-game": document.getElementById("section-sandbox-game"),
  "sandbox-usage": document.getElementById("section-sandbox-usage"),
};

const SECTION_TITLES = {
  videodb: "Play with VideoDB",
  play: "Tic-Tac-Toe",
  "sandbox-game": "Sandbox · Immersive game",
  "sandbox-usage": "Sandbox · Usage",
};

let recapMoves = [];
let recapIndex = 0;
let recapTimer = null;
let recapMode = "local";

let sessionId = null;
let board = Array(9).fill("");
let finished = false;
let busy = false;
let highlightCell = null;
let mediaMode = "economy";
let sessionMoves = [];

const vdbDot = document.getElementById("vdb-dot");
const vdbConnLabel = document.getElementById("vdb-conn-label");
const vdbCollection = document.getElementById("vdb-collection");
const vdbConnError = document.getElementById("vdb-conn-error");
const vdbTestBtn = document.getElementById("vdb-test-btn");
const vdbRefreshBtn = document.getElementById("vdb-refresh-btn");
const vdbSessionIdEl = document.getElementById("vdb-session-id");
const hubConfigTags = document.getElementById("hub-config-tags");
const hubModels = document.getElementById("hub-models");
const vdbVideoSelect = document.getElementById("vdb-video-select");
const vdbIndexStatus = document.getElementById("vdb-index-status");
const vdbMoveCount = document.getElementById("vdb-move-count");
const vdbSceneIndex = document.getElementById("vdb-scene-index");
const vdbExportBtn = document.getElementById("vdb-export-btn");
const vdbCloudRecapBtn = document.getElementById("vdb-cloud-recap-btn");
const vdbVideoId = document.getElementById("vdb-video-id");
const vdbAttachBtn = document.getElementById("vdb-attach-btn");
const vdbMoveLog = document.getElementById("vdb-move-log");
const hubPitch = document.getElementById("hub-pitch");
const hubSessionStatus = document.getElementById("hub-session-status");
const hubKeyLine = document.getElementById("hub-key-line");
const hubVideoCount = document.getElementById("hub-video-count");
const hubCapabilities = document.getElementById("hub-capabilities");
const hubUseCases = document.getElementById("hub-use-cases");
const hubDocs = document.getElementById("hub-docs");
const vdbSearchQuery = document.getElementById("vdb-search-query");
const vdbSearchBtn = document.getElementById("vdb-search-btn");
const vdbSearchMsg = document.getElementById("vdb-search-msg");
const vdbSearchResults = document.getElementById("vdb-search-results");
const vdbPlayerWrap = document.getElementById("vdb-player-wrap");
const vdbPlayerIframe = document.getElementById("vdb-player-iframe");
const vdbPlayerVideo = document.getElementById("vdb-player-video");
const vdbPlayerLabel = document.getElementById("vdb-player-label");
const vdbOpenPlayer = document.getElementById("vdb-open-player");
const vdbOpenVideoBtn = document.getElementById("vdb-open-video-btn");
const vdbTurnWrap = document.getElementById("vdb-turn-wrap");
const vdbTurnVideo = document.getElementById("vdb-turn-video");
const vdbTurnImage = document.getElementById("vdb-turn-image");
const vdbTurnNarrative = document.getElementById("vdb-turn-narrative");
const vdbCollName = document.getElementById("vdb-coll-name");
const vdbCollId = document.getElementById("vdb-coll-id");
const vdbCollCount = document.getElementById("vdb-coll-count");
const vdbCollStatus = document.getElementById("vdb-coll-status");
const vdbCollGrid = document.getElementById("vdb-coll-grid");
const vdbCollEmpty = document.getElementById("vdb-coll-empty");
const vdbUtilTable = document.getElementById("vdb-util-table");
const vdbCollLocalNote = document.getElementById("vdb-coll-local-note");
const vdbCollConsole = document.getElementById("vdb-coll-console");
const vdbTurnSuggestion = document.getElementById("vdb-turn-suggestion");
const suggestionBox = document.getElementById("suggestion-box");
const playTurnWrap = document.getElementById("play-turn-wrap");
const playTurnImage = document.getElementById("play-turn-image");
const playTurnVideo = document.getElementById("play-turn-video");
const mediaModeBadge = document.getElementById("media-mode-badge");
const playMediaError = document.getElementById("play-media-error");
const playMediaFallback = document.getElementById("play-media-fallback");
const vdbMediaError = document.getElementById("vdb-media-error");
const vdbMediaFallback = document.getElementById("vdb-media-fallback");

const CELL_NAMES = [
  "top-left",
  "top-center",
  "top-right",
  "middle-left",
  "center",
  "middle-right",
  "bottom-left",
  "bottom-center",
  "bottom-right",
];

let hubData = null;
let sceneIndexId = null;

function showVdbPlayer({ label, streamUrl, playerUrl, embedUrl } = {}) {
  if (vdbPlayerLabel) {
    vdbPlayerLabel.textContent =
      label || "Playing in VideoDB player (embed below · full player in new tab).";
  }
  if (!vdbPlayerWrap) return;

  if (embedUrl && vdbPlayerIframe) {
    vdbPlayerIframe.src = embedUrl;
    vdbPlayerIframe.hidden = false;
    if (vdbPlayerVideo) {
      vdbPlayerVideo.hidden = true;
      vdbPlayerVideo.removeAttribute("src");
    }
    vdbPlayerWrap.classList.remove("empty");
  } else if (streamUrl && vdbPlayerVideo) {
    vdbPlayerVideo.src = streamUrl;
    vdbPlayerVideo.hidden = false;
    if (vdbPlayerIframe) {
      vdbPlayerIframe.hidden = true;
      vdbPlayerIframe.removeAttribute("src");
    }
    vdbPlayerWrap.classList.remove("empty");
  } else {
    vdbPlayerWrap.classList.add("empty");
    if (vdbPlayerIframe) {
      vdbPlayerIframe.hidden = true;
      vdbPlayerIframe.removeAttribute("src");
    }
    if (vdbPlayerVideo) {
      vdbPlayerVideo.hidden = true;
      vdbPlayerVideo.removeAttribute("src");
    }
  }

  if (vdbOpenPlayer) {
    if (playerUrl && playerUrl.startsWith("http")) {
      vdbOpenPlayer.href = playerUrl;
      vdbOpenPlayer.hidden = false;
    } else {
      vdbOpenPlayer.hidden = true;
    }
  }
}

function updateOpenVideoBtn() {
  if (!vdbOpenVideoBtn) return;
  const id = getSelectedVideoId();
  vdbOpenVideoBtn.disabled = !(id && hubData?.connection_ok);
}

async function openCollectionVideo() {
  const videoId = getSelectedVideoId();
  if (!videoId) {
    setStatus("Select or enter a video ID", "warn");
    return;
  }
  if (vdbOpenVideoBtn) vdbOpenVideoBtn.disabled = true;
  try {
    const data = await api(
      `/api/videodb/video/${encodeURIComponent(videoId)}/player`
    );
    showVdbPlayer({
      label: data.name ? `${data.name} · ${data.video_id}` : data.video_id,
      streamUrl: data.stream_url,
      playerUrl: data.player_url,
      embedUrl: data.embed_url,
    });
    switchSection("videodb");
    setStatus("Video loaded in player", "ok");
  } catch (e) {
    setStatus(e.message, "warn");
  } finally {
    updateOpenVideoBtn();
  }
}

function switchSection(name) {
  navTabs.forEach((tab) => {
    const active = tab.dataset.section === name;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  Object.entries(views).forEach(([key, el]) => {
    if (!el) return;
    const active = key === name;
    el.classList.toggle("active", active);
    el.hidden = !active;
  });
  if (pageTitle && SECTION_TITLES[name]) {
    pageTitle.textContent = SECTION_TITLES[name];
  }
}

navTabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const section = tab.dataset.section;
    switchSection(section);
    if (section === "videodb") refreshVdbHub();
    if (section === "sandbox-game") refreshSandboxPanel();
    if (section === "sandbox-usage") refreshUsagePanel();
  });
});

function setConnUi(ok, label, collectionId, error, collectionName) {
  if (vdbDot) {
    vdbDot.className = "status-dot " + (ok ? "ok" : error ? "error" : "warn");
  }
  if (vdbConnLabel) vdbConnLabel.textContent = label;
  if (vdbCollection) {
    if (collectionName && collectionId) {
      vdbCollection.textContent = `${collectionName} · ${collectionId}`;
    } else if (collectionId) {
      vdbCollection.textContent = `Collection ${collectionId}`;
    } else {
      vdbCollection.textContent = "";
    }
  }
  if (vdbConnError) {
    if (error) {
      vdbConnError.hidden = false;
      vdbConnError.textContent = error;
    } else {
      vdbConnError.hidden = true;
      vdbConnError.textContent = "";
    }
  }
}

function renderConfigTags(data) {
  if (!hubConfigTags) return;
  const tags = [
    { label: "Media", value: data.media_mode || "economy" },
    { label: "Recap", value: data.recap_mode || "local" },
    { label: "Scene model", value: data.scene_model || "basic" },
  ];
  hubConfigTags.innerHTML = tags
    .map(
      (t) =>
        `<span class="tag"><strong>${t.label}</strong> ${escapeHtml(t.value)}</span>`
    )
    .join("");
}

function renderModelsTable(catalog) {
  if (!hubModels) return;
  const tbody = hubModels.querySelector("tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  (catalog || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.feature)}</td>
      <td><code>${escapeHtml(row.api)}</code></td>
      <td>${escapeHtml(row.model)}</td>`;
    tbody.appendChild(tr);
  });
}

function renderVideoSelect(videos, videosError) {
  if (!vdbVideoSelect) return;
  vdbVideoSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  if (videosError) {
    placeholder.textContent = videosError.slice(0, 60);
  } else if (!videos?.length) {
    placeholder.textContent = "No videos in collection";
  } else {
    placeholder.textContent = "Select a video…";
  }
  vdbVideoSelect.appendChild(placeholder);
  (videos || []).forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = v.label || v.name || v.id;
    vdbVideoSelect.appendChild(opt);
  });
  vdbVideoSelect.disabled = !videos?.length;
}

function renderVdbStatus(data) {
  mediaMode = data.media_mode || mediaMode;
  recapMode = data.recap_mode || recapMode;
  renderConfigTags(data);

  if (data.connection_ok) {
    let label = data.collection_name || "Collection";
    if (data.collection_id_resolved) {
      label += " (resolved from account default)";
    } else if (data.collection_name_ok === false && data.collection_name_expected) {
      label += ` (env name: ${data.collection_name_expected})`;
    }
    setConnUi(true, "Connected", data.collection_id, null, label);
  } else if (data.api_configured) {
    setConnUi(false, "Not connected", null, data.connection_error);
  } else {
    setConnUi(false, "No API key", null, "Add VIDEO_DB_API_KEY");
  }
}

function renderAssetCard(asset, type) {
  const card = document.createElement("article");
  card.className = "asset-card";
  const thumb = document.createElement("div");
  thumb.className = "asset-thumb";
  const badge = document.createElement("span");
  badge.className = `asset-badge ${type}`;
  badge.textContent = type;
  thumb.appendChild(badge);
  if (asset.preview_url) {
    const img = document.createElement("img");
    img.src = asset.preview_url;
    img.alt = asset.name || asset.id;
    img.loading = "lazy";
    img.onerror = () => {
      img.remove();
      const fb = document.createElement("span");
      fb.className = "asset-fallback";
      fb.textContent = type === "video" ? "▶" : "🖼";
      thumb.appendChild(fb);
    };
    thumb.appendChild(img);
  } else {
    const fb = document.createElement("span");
    fb.className = "asset-fallback";
    fb.textContent = type === "video" ? "▶" : "🖼";
    thumb.appendChild(fb);
  }
  const body = document.createElement("div");
  body.className = "asset-body";
  const title = document.createElement("div");
  title.className = "asset-title";
  title.textContent = asset.name || asset.id;
  const idEl = document.createElement("div");
  idEl.className = "asset-id";
  idEl.textContent = asset.id;
  body.appendChild(title);
  body.appendChild(idEl);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn ghost";
  btn.textContent = type === "video" ? "Play" : "View";
  btn.addEventListener("click", async () => {
    if (type === "video") {
      if (vdbVideoId) vdbVideoId.value = asset.id;
      await openCollectionVideo();
    } else if (asset.preview_url) {
      showTurnMediaPanels({
        imageUrl: asset.preview_url,
        narrative: asset.name || "Collection image",
        media: { fallback: "collection_image" },
      });
      switchSection("videodb");
    }
  });
  body.appendChild(btn);
  card.appendChild(thumb);
  card.appendChild(body);
  return card;
}

function renderCollectionInventory(inv) {
  if (!inv || !inv.ok) {
    if (vdbCollStatus) {
      vdbCollStatus.textContent = inv?.error || "Connect to load collection";
    }
    if (vdbCollGrid) vdbCollGrid.innerHTML = "";
    if (vdbCollEmpty) vdbCollEmpty.hidden = false;
    return;
  }
  if (vdbCollName) vdbCollName.textContent = inv.collection_name || "—";
  if (vdbCollId) vdbCollId.textContent = inv.collection_id || "—";
  const vCount = inv.video_count ?? (inv.videos || []).length;
  const iCount = inv.image_count ?? (inv.images || []).length;
  const total = inv.asset_count ?? vCount + iCount;
  if (vdbCollCount) {
    vdbCollCount.textContent = `${total} (${vCount} video · ${iCount} image)`;
  }
  if (vdbCollStatus) {
    const parts = [];
    if (inv.collection_match) {
      parts.push(`Connected · ${inv.collection_name || inv.collection_id}`);
    } else {
      parts.push("Collection ID mismatch — update VIDEODB_COLLECTION_ID on Render");
    }
    if (
      inv.collection_name_expected &&
      inv.collection_name_ok === false
    ) {
      parts.push(`display name is "${inv.collection_name}"`);
    }
    parts.push(`mode ${inv.current_media_mode} · recap ${inv.current_recap_mode}`);
    vdbCollStatus.textContent = parts.join(" · ");
  }
  if (vdbCollLocalNote) vdbCollLocalNote.textContent = inv.local_only_note || "";
  if (vdbCollConsole && inv.console_url) vdbCollConsole.href = inv.console_url;

  if (vdbCollGrid) {
    vdbCollGrid.innerHTML = "";
    (inv.videos || []).forEach((v) => vdbCollGrid.appendChild(renderAssetCard(v, "video")));
    (inv.images || []).forEach((img) => vdbCollGrid.appendChild(renderAssetCard(img, "image")));
  }
  const hasAssets = (inv.videos?.length || 0) + (inv.images?.length || 0) > 0;
  if (vdbCollEmpty) vdbCollEmpty.hidden = hasAssets;

  if (vdbUtilTable) {
    const tbody = vdbUtilTable.querySelector("tbody");
    if (tbody) {
      tbody.innerHTML = "";
      (inv.active_utilization || inv.utilization || []).forEach((row) => {
        const tr = document.createElement("tr");
        const active = row.active !== false;
        tr.innerHTML = `
          <td>${active ? "●" : "○"} ${escapeHtml(row.artifact)}</td>
          <td><code>${escapeHtml(row.api)}</code></td>
          <td>${escapeHtml(row.in_console)}</td>`;
        if (!active) tr.className = "util-inactive";
        tbody.appendChild(tr);
      });
    }
  }
}

function applyPanelActions(actions) {
  const a = actions || {};
  if (vdbSearchBtn) vdbSearchBtn.disabled = !a.can_search;
  if (vdbAttachBtn) {
    vdbAttachBtn.disabled = !a.can_index;
  }
  if (vdbExportBtn) vdbExportBtn.disabled = !a.can_export;
  if (vdbCloudRecapBtn) vdbCloudRecapBtn.disabled = !a.can_cloud_recap;
}

function updateMediaModeBadge(mode) {
  if (mediaModeBadge && mode) {
    mediaModeBadge.textContent = mode;
    mediaModeBadge.title = `VIDEODB_MEDIA_MODE=${mode}`;
  }
}

function renderHub(data) {
  hubData = data;
  if (data.media_mode) {
    mediaMode = data.media_mode;
    updateMediaModeBadge(mediaMode);
  }
  renderModelsTable(data.models_catalog);
  renderVideoSelect(data.videos, data.videos_error);
  if (hubPitch) {
    let pitch = data.hackathon_pitch || "";
    const gen = data.generation;
    if (gen?.active && gen.collection_images === 0 && gen.mode === "image") {
      pitch += " No images in collection yet — first successful generate_image will appear here.";
    }
    if (gen?.active && gen.mode !== "economy") {
      pitch += ` ${gen.detail || ""}`;
    }
    hubPitch.textContent = pitch;
  }
  if (hubKeyLine) {
    hubKeyLine.textContent = data.api_key_hint
      ? `API key ${data.api_key_hint}`
      : "No VIDEO_DB_API_KEY in .env — get one at console.videodb.io";
  }
  if (hubCapabilities && data.capabilities) {
    hubCapabilities.innerHTML = "";
    data.capabilities.forEach((cap) => {
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="cap-dot ${cap.ok ? "ok" : "fail"}"></span>
        <div class="cap-body">
          <div class="cap-label">${cap.label}</div>
          <div class="cap-detail">${cap.detail || ""}</div>
        </div>`;
      hubCapabilities.appendChild(li);
    });
  }
  if (hubUseCases && data.use_cases) {
    hubUseCases.innerHTML = "";
    data.use_cases.forEach((uc) => {
      const el = document.createElement("article");
      el.className = "use-case";
      const steps = (uc.steps || [])
        .map((s) => `<li>${s}</li>`)
        .join("");
      el.innerHTML = `
        <div class="use-case-top">
          <span class="use-case-tier">${uc.tier}</span>
          <span class="use-case-layer">${uc.see_understand_act}</span>
        </div>
        <h3>${uc.title}</h3>
        <p>${uc.summary}</p>
        <ol>${steps}</ol>
        <a href="${uc.doc_url}" target="_blank" rel="noopener">VideoDB docs →</a>`;
      hubUseCases.appendChild(el);
    });
  }
  if (hubDocs && data.docs) {
    hubDocs.innerHTML = "";
    data.docs.forEach((doc) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = doc.url;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = doc.title;
      li.appendChild(a);
      hubDocs.appendChild(li);
    });
  }
  if (hubVideoCount) {
    const inv = data.collection_inventory;
    if (inv?.ok) {
      hubVideoCount.textContent = `${inv.video_count ?? 0} video(s) · ${inv.image_count ?? 0} image(s) in collection`;
    } else if (data.video_count != null) {
      hubVideoCount.textContent = `${data.video_count} video(s) in collection`;
    } else {
      hubVideoCount.textContent = "";
    }
  }
  renderSessionHubStatus(data.session);
  renderVdbStatus(data);
  applyPanelActions(data.actions);
  updateSearchUi();
  updateIndexUi(data.session);
  updateOpenVideoBtn();
  renderCollectionInventory(data.collection_inventory);
}

function renderSessionHubStatus(session) {
  if (!hubSessionStatus) return;
  if (!session || !session.found) {
    hubSessionStatus.textContent = sessionId
      ? "Session not found"
      : "Start a game on Play";
    return;
  }
  const parts = [
    `${session.move_count} move(s) logged`,
    session.finished
      ? session.winner
        ? `Finished · ${session.winner} wins`
        : "Finished"
      : "In progress",
  ];
  if (session.scene_index_id) {
    parts.push("VideoDB index ready");
  } else if (session.capture_video_id) {
    parts.push("Video attached — index below");
  }
  hubSessionStatus.textContent = parts.join(" · ");
}

function updateIndexUi(session) {
  if (!vdbIndexStatus) return;
  if (!sessionId) {
    vdbIndexStatus.textContent = "Start a game on Play";
    return;
  }
  if (session?.scene_index_id) {
    vdbIndexStatus.textContent = `Indexed · ${session.scene_index_id}`;
  } else if (session?.capture_video_id) {
    vdbIndexStatus.textContent = `Video ${session.capture_video_id} — click Index moves`;
  } else if ((session?.move_count || 0) > 0) {
    vdbIndexStatus.textContent = "Ready — pick a video and index";
  } else {
    vdbIndexStatus.textContent = "Play at least one move before indexing";
  }
}

async function refreshVdbHub() {
  try {
    const path = sessionId
      ? `/api/videodb/panel?session_id=${encodeURIComponent(sessionId)}`
      : "/api/videodb/panel";
    const data = await api(path);
    renderHub(data);
    if (data.connection_ok) {
      setStatus(`VideoDB connected · ${data.media_mode}`, "ok");
    } else if (data.api_configured) {
      setStatus(data.connection_error || "Test connection", "warn");
    } else {
      setStatus("Add API key on Render", "warn");
    }
  } catch (e) {
    setConnUi(false, "Offline", null, formatApiError(e));
    setStatus("API unreachable — retrying…", "warn");
  }
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text || "";
  return d.innerHTML;
}

function updateSearchUi() {
  const hasMoves = sessionMoves.length > 0;
  const canSearch =
    hubData?.actions?.can_search ?? (sessionId && hasMoves);
  if (vdbSearchBtn) vdbSearchBtn.disabled = !canSearch;
  const hasResults =
    vdbSearchResults && vdbSearchResults.children.length > 0;
  if (vdbSearchMsg && !canSearch && !hasResults) {
    vdbSearchMsg.textContent = sessionId
      ? "Play at least one move to enable search"
      : "Waiting for session…";
  }
}

async function searchFootage() {
  if (!sessionId || !vdbSearchQuery?.value.trim()) return;
  vdbSearchBtn.disabled = true;
  if (vdbSearchMsg) vdbSearchMsg.textContent = "Searching…";
  if (vdbSearchResults) vdbSearchResults.innerHTML = "";

  try {
    const data = await api(`/api/session/${sessionId}/search-footage`, {
      method: "POST",
      body: JSON.stringify({ query: vdbSearchQuery.value.trim() }),
    });
    if (vdbSearchMsg) {
      let msg = data.message || "";
      if (data.warning) msg += ` (${data.warning})`;
      vdbSearchMsg.textContent = msg;
    }
    if (vdbSearchResults) {
      vdbSearchResults.innerHTML = "";
      (data.results || []).forEach((r) => {
        const li = document.createElement("li");
        const meta =
          r.move_number != null
            ? `Move ${r.move_number} · ${r.player} → cell ${r.cell}`
            : r.start != null
              ? `${Number(r.start).toFixed(1)}s – ${Number(r.end).toFixed(1)}s`
              : "";
        const src = r.source ? ` · ${r.source}` : "";
        li.innerHTML = `<div class="sr-meta">${meta}${src}</div><div>${escapeHtml(r.description || r.narrative || "Match")}</div>`;
        if (r.player_url || r.embed_url || r.stream_url) {
          const playBtn = document.createElement("button");
          playBtn.type = "button";
          playBtn.className = "btn ghost sr-play";
          playBtn.textContent = "Play in player";
          playBtn.addEventListener("click", () => {
            showVdbPlayer({
              label: r.description || r.narrative || "Search clip",
              streamUrl: r.stream_url,
              playerUrl: r.player_url,
              embedUrl: r.embed_url,
            });
            switchSection("videodb");
          });
          li.appendChild(playBtn);
        }
        vdbSearchResults.appendChild(li);
      });
    }
    if (data.embed_url || data.player_url || data.stream_url) {
      showVdbPlayer({
        label: data.message || "Compiled search clip",
        streamUrl: data.stream_url,
        playerUrl: data.player_url,
        embedUrl: data.embed_url,
      });
      switchSection("videodb");
    }
  } catch (e) {
    if (vdbSearchMsg) vdbSearchMsg.textContent = e.message;
  } finally {
    updateSearchUi();
  }
}

async function refreshVdbStatus() {
  try {
    const data = await api("/api/videodb/status");
    if (!hubData) renderVdbStatus(data);
    else {
      hubData.connection_ok = data.connection_ok;
      hubData.collection_id = data.collection_id;
      renderVdbStatus(data);
    }
    if (data.api_configured && data.connection_ok) {
      setStatus(`VideoDB · ${data.media_mode}`, "ok");
    } else if (data.api_configured) {
      setStatus("Test connection", "warn");
    } else {
      setStatus("Add API key", "warn");
    }
  } catch (e) {
    setConnUi(false, "Offline", null, formatApiError(e));
    setStatus("API unreachable", "warn");
  }
}

async function testVdbConnection() {
  if (vdbTestBtn) vdbTestBtn.disabled = true;
  setConnUi(false, "Testing…", null, null);
  try {
    const data = await api("/api/videodb/test-connection", { method: "POST" });
    if (!data.ok) {
      throw new Error(data.error || "Connection failed");
    }
    let label = data.collection_name || "Collection";
    if (data.collection_name_expected && !data.collection_name_ok) {
      label += ` (API name; optional env: ${data.collection_name_expected})`;
    }
    setConnUi(true, "Connected", data.collection_id, null, label);
    await refreshVdbHub();
  } catch (e) {
    setConnUi(false, "Failed", null, formatApiError(e));
  } finally {
    if (vdbTestBtn) vdbTestBtn.disabled = false;
  }
}

function updateMoveLogPreview(moves) {
  sessionMoves = moves || [];
  if (vdbMoveCount) vdbMoveCount.textContent = String(sessionMoves.length);

  if (vdbMoveLog) {
    vdbMoveLog.textContent = sessionMoves.length
      ? JSON.stringify(sessionMoves, null, 2)
      : "Play a game first.";
  }
}

async function refreshSidebarSession() {
  if (!sessionId) {
    sceneIndexId = null;
    if (vdbSessionIdEl) vdbSessionIdEl.textContent = "—";
    if (vdbSceneIndex) vdbSceneIndex.textContent = "—";
    updateMoveLogPreview([]);
    updateSearchUi();
    return;
  }
  if (vdbSessionIdEl) vdbSessionIdEl.textContent = sessionId;
  try {
    const data = await api(`/api/session/${sessionId}`);
    sceneIndexId = data.scene_index_id || null;
    if (vdbSceneIndex) {
      vdbSceneIndex.textContent = sceneIndexId || "—";
    }
    if (data.capture_video_id && vdbVideoId && !vdbVideoId.value) {
      vdbVideoId.value = data.capture_video_id;
    }
    updateMoveLogPreview(data.moves);
    updateSearchUi();
    updateIndexUi({
      move_count: data.moves?.length,
      scene_index_id: data.scene_index_id,
      capture_video_id: data.capture_video_id,
    });
  } catch {
    updateMoveLogPreview(sessionMoves);
    updateSearchUi();
  }
}

function exportMoveLog() {
  if (!sessionMoves.length) return;
  const blob = new Blob([JSON.stringify(sessionMoves, null, 2)], {
    type: "application/json",
  });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `videodb-ttt-${sessionId || "session"}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function getSelectedVideoId() {
  const fromSelect = vdbVideoSelect?.value?.trim();
  const fromInput = vdbVideoId?.value?.trim();
  return fromSelect || fromInput || "";
}

async function attachAndIndexCapture() {
  const videoId = getSelectedVideoId();
  if (!sessionId || !videoId) {
    setStatus("Select or enter a VideoDB video ID", "warn");
    return;
  }
  if (!sessionMoves.length) {
    setStatus("Play at least one move before indexing", "warn");
    return;
  }
  if (vdbAttachBtn) vdbAttachBtn.disabled = true;
  if (vdbIndexStatus) vdbIndexStatus.textContent = "Indexing scenes…";
  try {
    await api(`/api/session/${sessionId}/attach-capture`, {
      method: "POST",
      body: JSON.stringify({ video_id: videoId }),
    });
    if (vdbVideoId) vdbVideoId.value = videoId;
    const idx = await api(`/api/session/${sessionId}/index-capture`, {
      method: "POST",
    });
    sceneIndexId = idx.scene_index_id || null;
    if (vdbSceneIndex) vdbSceneIndex.textContent = sceneIndexId || "—";
    if (vdbIndexStatus) {
      vdbIndexStatus.textContent = `Indexed ${idx.moves_indexed} move(s)`;
    }
    if (idx.embed_url || idx.player_url || idx.stream_url) {
      showVdbPlayer({
        label: "Indexed capture video",
        streamUrl: idx.stream_url,
        playerUrl: idx.player_url,
        embedUrl: idx.embed_url,
      });
    }
    setStatus(`Indexed ${idx.moves_indexed} moves`, "ok");
    switchSection("videodb");
    await refreshSidebarSession();
    await refreshVdbHub();
  } catch (e) {
    if (vdbIndexStatus) vdbIndexStatus.textContent = e.message;
    setStatus(e.message, "warn");
  } finally {
    await refreshVdbHub();
  }
}

async function buildCloudRecap() {
  if (!sessionId || !finished) return;
  vdbCloudRecapBtn.disabled = true;
  setStatus("Building VideoDB timeline…");
  switchSection("videodb");
  try {
    const data = await api(
      `/api/session/${sessionId}/finish?cloud_recap=true`,
      { method: "POST" }
    );
    if (data.recap_stream_url || data.recap_embed_url) {
      if (recapSlideshow) recapSlideshow.hidden = true;
      showVdbPlayer({
        label: "Cloud play-by-play timeline",
        streamUrl: data.recap_stream_url,
        playerUrl: data.recap_player_url,
        embedUrl: data.recap_embed_url,
      });
    } else {
      showLocalRecap(data.moves, data.winner);
    }
    setStatus(data.message, "ok");
    await refreshSidebarSession();
    await refreshVdbHub();
  } catch (e) {
    setStatus(e.message, "warn");
  } finally {
    vdbCloudRecapBtn.disabled = !finished;
  }
}

function renderBoard() {
  boardEl.innerHTML = "";
  board.forEach((cell, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    let cls = "cell" + (cell ? ` ${cell.toLowerCase()}` : "");
    if (highlightCell === i) cls += " suggested";
    btn.className = cls;
    btn.textContent = cell || "";
    btn.disabled = busy || finished || !!cell;
    btn.setAttribute("aria-label", `Cell ${i}`);
    btn.addEventListener("click", () => onCellClick(i));
    boardEl.appendChild(btn);
  });
}

function setStatus(text, kind = "") {
  statusBar.textContent = text;
  statusBar.className = "status-pill" + (kind ? ` ${kind}` : "");
}

function applySuggestionUi(data, move) {
  const text =
    data.suggestion_text ||
    move?.suggestion_text ||
    (data.highlight_cell != null
      ? `Play cell ${data.highlight_cell}`
      : move?.suggested_cell != null
        ? `Play cell ${move.suggested_cell}`
        : "");

  if (data.highlight_cell != null) {
    highlightCell = data.highlight_cell;
  } else if (move?.suggested_cell != null) {
    highlightCell = move.suggested_cell;
  }

  if (text && suggestionBox && suggestionText) {
    suggestionBox.hidden = false;
    suggestionText.textContent = text;
  } else if (suggestionBox) {
    suggestionBox.hidden = true;
    if (suggestionText) suggestionText.textContent = "";
  }

  if (vdbTurnSuggestion) {
    if (text) {
      vdbTurnSuggestion.hidden = false;
      vdbTurnSuggestion.textContent = text;
    } else {
      vdbTurnSuggestion.hidden = true;
      vdbTurnSuggestion.textContent = "";
    }
  }
}

function boardToSvgDataUrl(board, highlightCell = null) {
  const cells = (board || []).map((c) => c || "");
  const xColor = "#f472b6";
  const oColor = "#22d3ee";
  const cellsSvg = cells
    .map((mark, i) => {
      const col = i % 3;
      const row = Math.floor(i / 3);
      const x = 48 + col * 104;
      const y = 48 + row * 104;
      const highlight =
        highlightCell === i
          ? `<rect x="${x - 6}" y="${y - 6}" width="92" height="92" rx="10" fill="none" stroke="#a78bfa" stroke-width="3"/>`
          : "";
      let text = "";
      if (mark === "X") {
        text = `<text x="${x + 46}" y="${y + 62}" text-anchor="middle" font-size="52" font-weight="700" fill="${xColor}">X</text>`;
      } else if (mark === "O") {
        text = `<text x="${x + 46}" y="${y + 62}" text-anchor="middle" font-size="52" font-weight="700" fill="${oColor}">O</text>`;
      } else {
        text = `<text x="${x + 46}" y="${y + 58}" text-anchor="middle" font-size="22" fill="#52525b">${i}</text>`;
      }
      return highlight + text;
    })
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
    <rect width="400" height="400" fill="#0c0c10"/>
    <rect x="24" y="24" width="352" height="352" rx="16" fill="#121218" stroke="#3f3f46"/>
    ${[1, 2].map((i) => `<line x1="${48 + i * 104}" y1="48" x2="${48 + i * 104}" y2="352" stroke="#27272a" stroke-width="2"/>`).join("")}
    ${[1, 2].map((i) => `<line x1="48" y1="${48 + i * 104}" x2="352" y2="${48 + i * 104}" stroke="#27272a" stroke-width="2"/>`).join("")}
    ${cellsSvg}
    <text x="200" y="388" text-anchor="middle" font-size="11" fill="#71717a">Local board preview</text>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function setMediaMessages(media, board, highlightCell) {
  const err = media?.error || "";
  const fallback = media?.fallback;
  const isLimit = /quota|maximum limit|plan/i.test(err);
  const localSvg =
    !media?.suggestion_image_url &&
    !media?.suggestion_stream_url &&
    (mediaMode === "image" || mediaMode === "video") &&
    board?.length === 9
      ? boardToSvgDataUrl(board, highlightCell)
      : null;

  const showErr = (el, noteEl) => {
    if (!el) return localSvg;
    if (err) {
      el.hidden = false;
      el.textContent = err;
    } else {
      el.hidden = true;
      el.textContent = "";
    }
    if (noteEl) {
      if (fallback) {
        noteEl.hidden = false;
        noteEl.textContent =
          fallback === "collection_image" || fallback === "collection_video"
            ? "Showing an existing asset from your VideoDB collection."
            : fallback === "local_board"
              ? "Live board preview (VideoDB generation unavailable)."
              : "";
      } else if (localSvg && isLimit) {
        noteEl.hidden = false;
        noteEl.textContent =
          "Plan limit reached — showing live board preview. Free up quota at console.videodb.io or use existing collection assets.";
      } else {
        noteEl.hidden = true;
        noteEl.textContent = "";
      }
    }
    return localSvg;
  };

  const localPlay = showErr(playMediaError, playMediaFallback);
  const localVdb = showErr(vdbMediaError, vdbMediaFallback);
  return localPlay || localVdb;
}

function setTurnMediaOnWrap(
  wrap,
  imgEl,
  vidEl,
  { imageUrl, streamUrl, localSvgUrl } = {}
) {
  if (!wrap) return;
  wrap.classList.remove("is-local-preview");
  if (imgEl) {
    imgEl.hidden = true;
    imgEl.removeAttribute("src");
    imgEl.onerror = null;
  }
  if (vidEl) {
    vidEl.hidden = true;
    vidEl.removeAttribute("src");
  }
  if (streamUrl && vidEl) {
    wrap.classList.remove("empty");
    vidEl.hidden = false;
    vidEl.src = streamUrl;
    vidEl.onerror = () => setStatus("Video failed to load — try Open in VideoDB", "warn");
  } else if (imageUrl && imgEl) {
    wrap.classList.remove("empty");
    imgEl.hidden = false;
    imgEl.src = imageUrl;
    imgEl.onerror = () => {
      if (localSvgUrl) {
        imgEl.onerror = null;
        imgEl.src = localSvgUrl;
        wrap.classList.add("is-local-preview");
      } else {
        setStatus("Image failed to load", "warn");
      }
    };
  } else if (localSvgUrl && imgEl) {
    wrap.classList.remove("empty");
    wrap.classList.add("is-local-preview");
    imgEl.hidden = false;
    imgEl.src = localSvgUrl;
  } else {
    wrap.classList.add("empty");
  }
}

function showTurnMediaPanels({
  imageUrl,
  streamUrl,
  narrative,
  playerUrl,
  embedUrl,
  media,
  board,
  highlightCell,
} = {}) {
  if (narrative && vdbTurnNarrative) vdbTurnNarrative.textContent = narrative;
  const localSvg = setMediaMessages(media, board, highlightCell);
  const opts = { imageUrl, streamUrl, localSvgUrl: localSvg };
  setTurnMediaOnWrap(vdbTurnWrap, vdbTurnImage, vdbTurnVideo, opts);
  setTurnMediaOnWrap(playTurnWrap, playTurnImage, playTurnVideo, opts);
  if (streamUrl) {
    showVdbPlayer({
      label: narrative || "Turn clip",
      streamUrl,
      playerUrl,
      embedUrl,
    });
  }
}

function showTurnResult(data) {
  const move = data.opponent_suggestion || data.last_move;
  if (!move) return;

  narrativeEl.textContent = move.narrative;
  if (vdbTurnNarrative) vdbTurnNarrative.textContent = move.narrative;
  applySuggestionUi(data, move);
  renderBoard();

  const media = data.turn_media || {};
  const stream = media.suggestion_stream_url || move.suggestion_stream_url;
  const imageUrl = media.suggestion_image_url || move.suggestion_image_url;
  const player = media.suggestion_player_url || move.suggestion_player_url;
  const embed = media.suggestion_embed_url;

  showTurnMediaPanels({
    imageUrl,
    streamUrl: stream,
    narrative: move.narrative,
    playerUrl: player,
    embedUrl: embed,
    media,
    board: data.board,
    highlightCell: data.highlight_cell ?? move.suggested_cell,
  });

  if (media.error) {
    const kind = media.generation_ok === false ? "warn" : "ok";
    setStatus(
      media.fallback ? "Using collection fallback" : media.error.slice(0, 120),
      kind
    );
  } else if (imageUrl || stream) {
    setStatus(
      mediaMode === "video" ? "VideoDB clip ready" : "VideoDB image ready",
      "ok"
    );
  }
}

function formatApiError(err) {
  const msg = err?.message || String(err);
  if (msg === "Failed to fetch" || msg.includes("NetworkError")) {
    return API
      ? "Cannot reach API (Render may be waking up — wait 30s and refresh)"
      : "API URL missing — set VIDEODB_API_BASE on Vercel";
  }
  return msg;
}

async function api(path, options = {}, attempt = 0) {
  const maxAttempts = 3;
  const url = `${API}${path}`;
  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail || res.statusText;
      if (res.status >= 500 && attempt < maxAttempts - 1) {
        await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
        return api(path, options, attempt + 1);
      }
      throw new Error(detail);
    }
    return res.json();
  } catch (e) {
    if (attempt < maxAttempts - 1 && (e.message === "Failed to fetch" || e.name === "TypeError")) {
      await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
      return api(path, options, attempt + 1);
    }
    throw e;
  }
}

async function init() {
  switchSection("videodb");
  if (!API) {
    setConnUi(false, "No API URL", null, "Set VIDEODB_API_BASE on Vercel to your Render URL");
    setStatus("Frontend misconfigured", "warn");
    return;
  }
  try {
    await refreshVdbHub();
  } catch (e) {
    setConnUi(false, "Offline", null, formatApiError(e));
  }
  try {
    await startGame();
  } catch (e) {
    setStatus(formatApiError(e), "warn");
  }
}

async function startGame() {
  busy = true;
  highlightCell = null;
  renderBoard();
  finished = false;
  resultEl.hidden = true;
  btnFinish.disabled = true;
  if (recapWrap) recapWrap.classList.add("empty");
  if (recapSlideshow) recapSlideshow.hidden = true;
  stopRecapAutoplay();
  recapMoves = [];
  showVdbPlayer({});
  showTurnMediaPanels({});
  if (vdbTurnNarrative) {
    vdbTurnNarrative.textContent =
      "Play moves on the Play tab — generative clips appear here when enabled.";
  }
  narrativeEl.textContent = "Make a move to log play-by-play context.";
  if (suggestionBox) suggestionBox.hidden = true;
  if (suggestionText) suggestionText.textContent = "";
  if (vdbTurnSuggestion) {
    vdbTurnSuggestion.hidden = true;
    vdbTurnSuggestion.textContent = "";
  }
  [playMediaError, vdbMediaError, playMediaFallback, vdbMediaFallback].forEach((el) => {
    if (el) {
      el.hidden = true;
      el.textContent = "";
    }
  });

  try {
    const data = await api("/api/session/start", { method: "POST" });
    sessionId = data.session_id;
    board = data.board;
    mediaMode = data.media_mode || mediaMode;
    updateMediaModeBadge(mediaMode);
    sessionLabel.textContent = sessionId;
    turnLabel.textContent = "Your turn (X)";
    await refreshSidebarSession();
    await refreshVdbHub();
  } catch (e) {
    setStatus(e.message || "Could not start", "warn");
  } finally {
    busy = false;
    renderBoard();
  }
}

async function onCellClick(cell) {
  if (busy || finished || board[cell]) return;
  busy = true;
  renderBoard();
  setStatus(
    mediaMode === "video"
      ? "Generating…"
      : mediaMode === "image"
        ? "Generating image…"
        : "Playing turn…"
  );

  try {
    const data = await api(`/api/session/${sessionId}/move`, {
      method: "POST",
      body: JSON.stringify({ cell }),
    });
    board = data.board;
    finished = data.finished;
    mediaMode = data.media_mode || mediaMode;
    updateMediaModeBadge(mediaMode);
    showTurnResult(data);

    if (finished) {
      const w = data.winner;
      resultEl.hidden = false;
      resultEl.textContent =
        w === "draw" ? "Draw" : w ? `${w} wins` : "Game over";
      turnLabel.textContent = "Finished";
      btnFinish.disabled = false;
      setStatus("View recap", "ok");
    } else {
      turnLabel.textContent = "Your turn (X)";
      setStatus("Your turn", "ok");
    }
    await refreshSidebarSession();
    await refreshVdbHub();
  } catch (e) {
    setStatus(e.message, "warn");
  } finally {
    busy = false;
    renderBoard();
  }
}

function renderRecapBoard(boardState, suggested) {
  recapBoard.innerHTML = "";
  boardState.forEach((cell, i) => {
    const div = document.createElement("div");
    div.className = "cell" + (cell ? ` ${cell.toLowerCase()}` : "");
    if (suggested === i) div.className += " suggested";
    div.textContent = cell || "";
    recapBoard.appendChild(div);
  });
}

function showRecapSlide(i) {
  if (!recapMoves.length) return;
  recapIndex = Math.max(0, Math.min(i, recapMoves.length - 1));
  const move = recapMoves[recapIndex];
  renderRecapBoard(move.board_after, move.suggested_cell);
  recapMoveMeta.textContent = `Move ${move.move_number} · ${move.player} → ${move.cell}`;
  recapMoveText.textContent =
    move.suggestion_text || move.narrative;
  recapCounter.textContent = `${recapIndex + 1} / ${recapMoves.length}`;
}

function stopRecapAutoplay() {
  if (recapTimer) {
    clearInterval(recapTimer);
    recapTimer = null;
  }
  if (recapPlayBtn) recapPlayBtn.textContent = "Play";
}

function startRecapAutoplay() {
  stopRecapAutoplay();
  recapPlayBtn.textContent = "Pause";
  recapTimer = setInterval(() => {
    if (recapIndex >= recapMoves.length - 1) {
      stopRecapAutoplay();
      return;
    }
    showRecapSlide(recapIndex + 1);
  }, 2500);
}

function showLocalRecap(moves, winner) {
  recapMoves = moves || [];
  if (recapWrap) recapWrap.classList.remove("empty");
  if (recapSlideshow) recapSlideshow.hidden = false;

  let title = "Play-by-play";
  if (winner === "draw") title += " · Draw";
  else if (winner) title += ` · ${winner} wins`;
  recapTitle.textContent = title;

  showRecapSlide(0);
}

async function finishRecap() {
  busy = true;
  btnFinish.disabled = true;
  stopRecapAutoplay();
  setStatus("Loading recap…");
  switchSection("videodb");
  try {
    const data = await api(`/api/session/${sessionId}/finish`, { method: "POST" });
    recapMode = data.recap_mode || "local";

    if (data.recap_stream_url || data.recap_embed_url) {
      if (recapSlideshow) recapSlideshow.hidden = true;
      showVdbPlayer({
        label: "Cloud play-by-play timeline",
        streamUrl: data.recap_stream_url,
        playerUrl: data.recap_player_url,
        embedUrl: data.recap_embed_url,
      });
    } else {
      showLocalRecap(data.moves, data.winner);
    }
    setStatus(data.message, "ok");
    await refreshSidebarSession();
    await refreshVdbHub();
  } catch (e) {
    setStatus(e.message, "warn");
  } finally {
    busy = false;
    btnFinish.disabled = !finished;
  }
}

if (vdbTestBtn) vdbTestBtn.addEventListener("click", testVdbConnection);
if (vdbRefreshBtn) vdbRefreshBtn.addEventListener("click", refreshVdbHub);
if (vdbExportBtn) vdbExportBtn.addEventListener("click", exportMoveLog);
if (vdbCloudRecapBtn) vdbCloudRecapBtn.addEventListener("click", buildCloudRecap);
if (vdbAttachBtn) vdbAttachBtn.addEventListener("click", attachAndIndexCapture);
if (vdbSearchBtn) vdbSearchBtn.addEventListener("click", searchFootage);
if (vdbSearchQuery) {
  vdbSearchQuery.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !vdbSearchBtn.disabled) searchFootage();
  });
}
if (vdbVideoSelect) {
  vdbVideoSelect.addEventListener("change", () => {
    if (vdbVideoSelect.value && vdbVideoId) {
      vdbVideoId.value = vdbVideoSelect.value;
    }
    updateOpenVideoBtn();
  });
}
if (vdbOpenVideoBtn) vdbOpenVideoBtn.addEventListener("click", openCollectionVideo);
if (vdbVideoId) vdbVideoId.addEventListener("input", updateOpenVideoBtn);

if (recapPrev) recapPrev.addEventListener("click", () => showRecapSlide(recapIndex - 1));
if (recapNext) recapNext.addEventListener("click", () => showRecapSlide(recapIndex + 1));
if (recapPlayBtn) {
  recapPlayBtn.addEventListener("click", () => {
    if (recapTimer) stopRecapAutoplay();
    else startRecapAutoplay();
  });
}

btnNew.addEventListener("click", startGame);
btnFinish.addEventListener("click", finishRecap);

/* —— Sandbox compute plan —— */
let sandboxSessionId = null;
let sbBoard = Array(9).fill("");
let sbFinished = false;
let sbBusy = false;
let sbHighlight = null;
let sbMoves = [];
let sbGameType = "tic_tac_toe";
let sbState = {};
let sbCatalog = [];

const sbBoardEl = document.getElementById("sb-board");
const sbTurnLabel = document.getElementById("sb-turn-label");
const sbNarrative = document.getElementById("sb-narrative");
const sbSuggestionBox = document.getElementById("sb-suggestion-box");
const sbSuggestionText = document.getElementById("sb-suggestion-text");
const sbFluxError = document.getElementById("sb-flux-error");
const sbTurnWrap = document.getElementById("sb-turn-wrap");
const sbTurnImage = document.getElementById("sb-turn-image");
const sbMoveGallery = document.getElementById("sb-move-gallery");
const sbBtnNew = document.getElementById("sb-btn-new");
const sbBtnFinish = document.getElementById("sb-btn-finish");
const sbResult = document.getElementById("sb-result");
const sbSandboxId = document.getElementById("sb-sandbox-id");
const sbPlayerWrap = document.getElementById("sb-player-wrap");
const sbPlayerIframe = document.getElementById("sb-player-iframe");
const sbPlayerVideo = document.getElementById("sb-player-video");
const sbPlayerLabel = document.getElementById("sb-player-label");
const sbOpenPlayer = document.getElementById("sb-open-player");
const sbTierTag = document.getElementById("sb-tier-tag");
const sbUFlux = document.getElementById("sb-u-flux");
const sbUVoice = document.getElementById("sb-u-voice");
const sbURuntime = document.getElementById("sb-u-runtime");
const sbUCost = document.getElementById("sb-u-cost");
const ugSessions = document.getElementById("ug-sessions");
const ugFlux = document.getElementById("ug-flux");
const ugVoice = document.getElementById("ug-voice");
const ugTimelines = document.getElementById("ug-timelines");
const ugRuntime = document.getElementById("ug-runtime");
const ugCost = document.getElementById("ug-cost");
const usageSandboxStatus = document.getElementById("usage-sandbox-status");
const usageSandboxList = document.getElementById("usage-sandbox-list");
const usageRefreshBtn = document.getElementById("usage-refresh-btn");
const usageCleanupBtn = document.getElementById("usage-cleanup-btn");
const sbGamePicker = document.getElementById("sb-game-picker");
const sbArenaTtt = document.getElementById("sb-arena-ttt");
const sbArenaFps = document.getElementById("sb-arena-fps");
const sbArenaCar = document.getElementById("sb-arena-car");
const fpsHp = document.getElementById("fps-hp");
const fpsAmmo = document.getElementById("fps-ammo");
const fpsScore = document.getElementById("fps-score");
const fpsWave = document.getElementById("fps-wave");
const fpsPlayer = document.getElementById("fps-player");
const fpsEnemies = document.getElementById("fps-enemies");
const carLane = document.getElementById("car-lane");
const carSpeed = document.getElementById("car-speed");
const carDistance = document.getElementById("car-distance");
const carScore = document.getElementById("car-score");
const carPlayer = document.getElementById("car-player");
const carObstacles = document.getElementById("car-obstacles");

function renderGamePicker(games) {
  if (!sbGamePicker) return;
  sbCatalog = games || sbCatalog;
  sbGamePicker.innerHTML = "";
  sbCatalog.forEach((g) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "game-pick" + (g.id === sbGameType ? " active" : "");
    btn.dataset.game = g.id;
    btn.innerHTML = `<span class="game-pick-icon">${g.icon || "▸"}</span>
      <span class="game-pick-title">${g.title}</span>
      <span class="game-pick-tag">${g.tagline}</span>`;
    btn.addEventListener("click", () => selectSbGame(g.id));
    sbGamePicker.appendChild(btn);
  });
}

function selectSbGame(gameId) {
  sbGameType = gameId;
  renderGamePicker(sbCatalog);
  showSbArena();
  if (sbTurnLabel) {
    const titles = { tic_tac_toe: "Tic-Tac-Toe", fps: "Arena FPS", car: "Neon Drift" };
    sbTurnLabel.textContent = sandboxSessionId
      ? `Playing ${titles[gameId] || gameId}`
      : `Selected ${titles[gameId] || gameId} — start sandbox`;
  }
}

function showSbArena() {
  if (sbArenaTtt) sbArenaTtt.hidden = sbGameType !== "tic_tac_toe";
  if (sbArenaFps) sbArenaFps.hidden = sbGameType !== "fps";
  if (sbArenaCar) sbArenaCar.hidden = sbGameType !== "car";
  renderSbBoard();
  renderFpsArena();
  renderCarArena();
}

function renderFpsArena() {
  if (!fpsPlayer || sbGameType !== "fps") return;
  const st = sbState;
  const p = st.player || { x: 50, y: 75 };
  fpsPlayer.style.left = `${p.x}%`;
  fpsPlayer.style.top = `${p.y}%`;
  if (fpsHp) fpsHp.textContent = String(st.hp ?? 100);
  if (fpsAmmo) fpsAmmo.textContent = String(st.ammo ?? 0);
  if (fpsScore) fpsScore.textContent = String(st.score ?? 0);
  if (fpsWave) fpsWave.textContent = String(st.wave ?? 1);
  if (fpsEnemies) {
    fpsEnemies.innerHTML = "";
    (st.enemies || []).forEach((e) => {
      const el = document.createElement("div");
      el.className = "fps-enemy";
      el.style.left = `${e.x}%`;
      el.style.top = `${e.y}%`;
      fpsEnemies.appendChild(el);
    });
  }
}

function renderCarArena() {
  if (!carPlayer || sbGameType !== "car") return;
  const st = sbState;
  const lane = Number(st.lane ?? 1);
  carPlayer.style.left = `${lane * 33.33 + 16.66}%`;
  if (carLane) carLane.textContent = String(lane);
  if (carSpeed) carSpeed.textContent = `${Number(st.speed ?? 1).toFixed(1)}×`;
  if (carDistance) carDistance.textContent = `${Math.floor(st.distance ?? 0)}m`;
  if (carScore) carScore.textContent = String(st.score ?? 0);
  if (carObstacles) {
    carObstacles.innerHTML = "";
    (st.obstacles || []).forEach((o) => {
      const el = document.createElement("div");
      el.className = "car-obstacle";
      el.style.left = `${Number(o.lane) * 33.33 + 16.66}%`;
      el.style.top = `${Math.min(92, Math.max(0, o.y))}%`;
      carObstacles.appendChild(el);
    });
  }
}

function galleryCaption(m) {
  if (m.action_label) return `#${m.move_number} ${m.action_label}`;
  if (m.cell != null) return `#${m.move_number} ${m.player} → ${m.cell}`;
  return `#${m.move_number}`;
}

function applySbResponse(data) {
  sbState = data.state || sbState;
  if (data.board) sbBoard = data.board;
  sbFinished = data.finished;
  sbHighlight = data.highlight_cell ?? null;
  if (data.moves_logged?.length) {
    sbMoves.push(...data.moves_logged);
  } else {
    sbMoves.push(data.last_move);
    if (data.opponent_move) sbMoves.push(data.opponent_move);
  }
  showSbTurn(data);
  renderSbGallery(sbMoves);
  showSbArena();
  if (data.finished) {
    sbResult.hidden = false;
    const w = data.winner;
    sbResult.textContent =
      w === "victory"
        ? "Victory!"
        : w === "defeat"
          ? "Defeat"
          : w === "draw"
            ? "Draw"
            : w
              ? `${w} wins`
              : "Game over";
    if (sbTurnLabel) sbTurnLabel.textContent = "Finished — build recap";
    sbBtnFinish.disabled = false;
    setStatus("Build cloud recap when ready", "ok");
  }
}

async function sbAction(action) {
  if (sbBusy || sbFinished || !sandboxSessionId) return;
  sbBusy = true;
  setStatus("FLUX on sandbox compute…", "warn");
  try {
    const data = await api(`/api/sandbox/session/${sandboxSessionId}/action`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    applySbResponse(data);
    if (!data.finished) setStatus("Play logged · FLUX updated", "ok");
    await refreshUsagePanel();
  } catch (e) {
    setStatus(e.message, "warn");
  } finally {
    sbBusy = false;
    renderSbBoard();
    renderFpsArena();
    renderCarArena();
  }
}

function formatUsd(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

function formatRuntime(sec) {
  const s = Math.round(Number(sec) || 0);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}

function renderSessionUsage(usage) {
  if (!usage) return;
  if (sbUFlux) sbUFlux.textContent = String(usage.flux_images ?? 0);
  if (sbUVoice) sbUVoice.textContent = String(usage.omnivoice_jobs ?? 0);
  if (sbURuntime) sbURuntime.textContent = formatRuntime(usage.sandbox_seconds);
  if (sbUCost) sbUCost.textContent = formatUsd(usage.estimated_usd);
}

function renderGlobalUsage(global) {
  if (!global) return;
  if (ugSessions) ugSessions.textContent = String(global.sessions ?? 0);
  if (ugFlux) ugFlux.textContent = String(global.flux_images ?? 0);
  if (ugVoice) ugVoice.textContent = String(global.omnivoice_jobs ?? 0);
  if (ugTimelines) ugTimelines.textContent = String(global.timelines ?? 0);
  if (ugRuntime) ugRuntime.textContent = formatRuntime(global.sandbox_seconds);
  if (ugCost) ugCost.textContent = formatUsd(global.estimated_usd);
}

function showSbPlayer({ label, streamUrl, playerUrl, embedUrl } = {}) {
  if (sbPlayerLabel) {
    sbPlayerLabel.textContent = label || "Sandbox recap in VideoDB player.";
  }
  if (!sbPlayerWrap) return;
  if (embedUrl && sbPlayerIframe) {
    sbPlayerIframe.src = embedUrl;
    sbPlayerIframe.hidden = false;
    if (sbPlayerVideo) {
      sbPlayerVideo.hidden = true;
      sbPlayerVideo.removeAttribute("src");
    }
    sbPlayerWrap.classList.remove("empty");
  } else if (streamUrl && sbPlayerVideo) {
    sbPlayerVideo.src = streamUrl;
    sbPlayerVideo.hidden = false;
    if (sbPlayerIframe) {
      sbPlayerIframe.hidden = true;
      sbPlayerIframe.removeAttribute("src");
    }
    sbPlayerWrap.classList.remove("empty");
  } else {
    sbPlayerWrap.classList.add("empty");
    if (sbPlayerIframe) {
      sbPlayerIframe.hidden = true;
      sbPlayerIframe.removeAttribute("src");
    }
    if (sbPlayerVideo) {
      sbPlayerVideo.hidden = true;
      sbPlayerVideo.removeAttribute("src");
    }
  }
  if (sbOpenPlayer) {
    if (playerUrl && playerUrl.startsWith("http")) {
      sbOpenPlayer.href = playerUrl;
      sbOpenPlayer.hidden = false;
    } else {
      sbOpenPlayer.hidden = true;
    }
  }
}

function renderSbBoard() {
  if (!sbBoardEl) return;
  sbBoardEl.innerHTML = "";
  sbBoard.forEach((cell, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    let cls = "cell" + (cell ? ` ${cell.toLowerCase()}` : "");
    if (sbHighlight === i) cls += " suggested";
    btn.className = cls;
    btn.textContent = cell || "";
    btn.disabled = sbBusy || sbFinished || !!cell;
    btn.setAttribute("aria-label", `Cell ${i}`);
    btn.addEventListener("click", () => onSbCellClick(i));
    sbBoardEl.appendChild(btn);
  });
}

function renderSbGallery(moves) {
  if (!sbMoveGallery) return;
  sbMoveGallery.innerHTML = "";
  const withImg = (moves || []).filter((m) => m.flux_image_url);
  if (!withImg.length) {
    sbMoveGallery.innerHTML = '<p class="hint">FLUX stills appear here after each turn.</p>';
    return;
  }
  withImg.forEach((m) => {
    const fig = document.createElement("figure");
    fig.className = "gallery-item";
    const img = document.createElement("img");
    img.src = m.flux_image_url;
    img.alt = `Move ${m.move_number}`;
    const cap = document.createElement("figcaption");
    cap.textContent = galleryCaption(m);
    fig.appendChild(img);
    fig.appendChild(cap);
    sbMoveGallery.appendChild(fig);
  });
}

function showSbTurn(data) {
  const move = data.opponent_move || data.last_move;
  if (!move) return;
  if (sbNarrative) sbNarrative.textContent = move.narrative;
  const text = data.suggestion_text || move.suggestion_text;
  sbHighlight = data.highlight_cell ?? move.suggested_cell;
  if (text && sbSuggestionBox && sbSuggestionText) {
    sbSuggestionBox.hidden = false;
    sbSuggestionText.textContent = text;
  } else if (sbSuggestionBox) {
    sbSuggestionBox.hidden = true;
  }
  const media = data.turn_media || {};
  const imageUrl = media.image_url || move.flux_image_url;
  if (sbFluxError) {
    if (media.error) {
      sbFluxError.hidden = false;
      sbFluxError.textContent = media.error;
    } else {
      sbFluxError.hidden = true;
      sbFluxError.textContent = "";
    }
  }
  if (sbTurnWrap && sbTurnImage) {
    if (imageUrl) {
      sbTurnWrap.classList.remove("empty");
      sbTurnImage.hidden = false;
      sbTurnImage.src = imageUrl;
    } else {
      sbTurnWrap.classList.add("empty");
      sbTurnImage.hidden = true;
      sbTurnImage.removeAttribute("src");
    }
  }
  if (sbSandboxId && data.sandbox_id) {
    sbSandboxId.textContent = `Sandbox ${data.sandbox_id} · ${data.sandbox_status || "active"}`;
  }
  renderSessionUsage(data.usage);
}

async function refreshUsagePanel() {
  try {
    const q = sandboxSessionId
      ? `?session_id=${encodeURIComponent(sandboxSessionId)}`
      : "";
    const data = await api(`/api/sandbox/usage${q}`);
    renderGlobalUsage(data.global);
    if (data.session) renderSessionUsage(data.session);
    if (data.active_tier && sbTierTag) {
      sbTierTag.textContent = `${data.active_tier} tier`;
    }
    const status = await api("/api/sandbox/status");
    if (usageSandboxStatus) {
      if (!status.configured) {
        usageSandboxStatus.textContent = "VIDEO_DB_API_KEY not configured";
      } else if (status.at_limit) {
        usageSandboxStatus.textContent =
          `Medium tier limit reached (${status.active_count}/${status.active_limit} active) — click Free sandbox slots or start game to reuse one`;
      } else {
        usageSandboxStatus.textContent =
          `${status.active_count || 0}/${status.active_limit || 3} active · ${status.sandboxes?.length || 0} total on account`;
      }
    }
    if (usageSandboxList) {
      usageSandboxList.innerHTML = "";
      (status.sandboxes || []).forEach((sb) => {
        const li = document.createElement("li");
        li.textContent = `${sb.id} · ${sb.tier} · ${sb.status}`;
        usageSandboxList.appendChild(li);
      });
      if (!status.sandboxes?.length) {
        const li = document.createElement("li");
        li.textContent = "No sandboxes listed (create one via Immersive game).";
        usageSandboxList.appendChild(li);
      }
    }
  } catch (e) {
    if (usageSandboxStatus) usageSandboxStatus.textContent = formatApiError(e);
  }
}

async function cleanupSandboxes() {
  if (usageCleanupBtn) usageCleanupBtn.disabled = true;
  setStatus("Stopping extra sandboxes…", "warn");
  try {
    const data = await api("/api/sandbox/cleanup?keep=1", { method: "POST" });
    setStatus(
      `Stopped ${data.stopped_count || 0} sandbox(es) · ${data.active_remaining ?? 0} active`,
      "ok"
    );
    await refreshUsagePanel();
  } catch (e) {
    setStatus(formatApiError(e), "warn");
  } finally {
    if (usageCleanupBtn) usageCleanupBtn.disabled = false;
  }
}

async function refreshSandboxPanel() {
  await refreshUsagePanel();
  if (!sbCatalog.length) await loadSbCatalog();
}

async function startSandboxGame() {
  sbBusy = true;
  sbFinished = false;
  sbHighlight = null;
  sbMoves = [];
  sbResult.hidden = true;
  sbBtnFinish.disabled = true;
  showSbPlayer({});
  showSbArena();
  setStatus("Provisioning sandbox (1–3 min first time)…", "warn");

  try {
    const data = await api("/api/sandbox/session/start", {
      method: "POST",
      body: JSON.stringify({ game_type: sbGameType }),
    });
    sandboxSessionId = data.session_id;
    sbGameType = data.game_type || sbGameType;
    sbState = data.state || {};
    sbBoard = data.board || sbState.board || Array(9).fill("");
    sbCatalog = data.games || sbCatalog;
    renderGamePicker(sbCatalog);
    sessionLabel.textContent = `Sandbox ${sandboxSessionId} · ${sbGameType}`;
    if (sbTurnLabel) {
      sbTurnLabel.textContent =
        sbGameType === "tic_tac_toe" ? "Your turn (X)" : "Take your action";
    }
    if (data.sandbox?.sandbox_id && sbSandboxId) {
      const reused = data.sandbox.reused ? " · reused" : "";
      sbSandboxId.textContent = `Sandbox ${data.sandbox.sandbox_id} · ${data.sandbox.status}${reused}`;
    }
    renderSessionUsage(data.usage);
    const reusedMsg = data.sandbox?.reused ? " (reused existing sandbox)" : "";
    setStatus(`Sandbox ready${reusedMsg} — play a move`, "ok");
  } catch (e) {
    const msg = formatApiError(e);
    if (msg.includes("Maximum active sandboxes")) {
      setStatus("At sandbox limit — open Usage → Free sandbox slots, then retry", "warn");
    } else {
      setStatus(msg || "Sandbox start failed", "warn");
    }
  } finally {
    sbBusy = false;
    renderSbBoard();
  }
}

async function onSbCellClick(cell) {
  if (sbBusy || sbFinished || sbBoard[cell] || !sandboxSessionId) return;
  await sbAction({ cell });
}

async function finishSandboxRecap() {
  if (!sandboxSessionId) return;
  sbBusy = true;
  sbBtnFinish.disabled = true;
  setStatus("Building OmniVoice + timeline recap on sandbox…");

  try {
    const data = await api(`/api/sandbox/session/${sandboxSessionId}/finish`, {
      method: "POST",
    });
    renderSbGallery(data.moves || sbMoves);
    renderSessionUsage(data.usage);
    renderGlobalUsage(data.global_usage);

    if (data.recap_stream_url || data.recap_embed_url) {
      showSbPlayer({
        label: "Full game recap — stored in VideoDB cloud",
        streamUrl: data.recap_stream_url,
        playerUrl: data.recap_player_url,
        embedUrl: data.recap_embed_url,
      });
      setStatus(data.message, "ok");
    } else {
      setStatus(data.recap_error || data.message || "Recap failed", "warn");
    }
    await refreshUsagePanel();
  } catch (e) {
    setStatus(e.message, "warn");
    sbBtnFinish.disabled = !sbFinished;
  } finally {
    sbBusy = false;
  }
}

if (sbBtnNew) sbBtnNew.addEventListener("click", startSandboxGame);
if (sbBtnFinish) sbBtnFinish.addEventListener("click", finishSandboxRecap);
if (usageRefreshBtn) usageRefreshBtn.addEventListener("click", refreshUsagePanel);
if (usageCleanupBtn) usageCleanupBtn.addEventListener("click", cleanupSandboxes);


document.querySelectorAll("[data-fps-action]").forEach((btn) => {
  btn.addEventListener("click", () => {
    try {
      sbAction(JSON.parse(btn.dataset.fpsAction));
    } catch (e) {
      setStatus("Invalid FPS action", "warn");
    }
  });
});
document.querySelectorAll("[data-car-action]").forEach((btn) => {
  btn.addEventListener("click", () => {
    try {
      sbAction(JSON.parse(btn.dataset.carAction));
    } catch (e) {
      setStatus("Invalid car action", "warn");
    }
  });
});

async function loadSbCatalog() {
  try {
    const data = await api("/api/sandbox/games");
    sbCatalog = data.games || [];
    renderGamePicker(sbCatalog);
    selectSbGame(sbGameType);
  } catch (e) {
    /* ignore */
  }
}
loadSbCatalog();

init();
