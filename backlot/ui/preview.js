// Backlot Preview — plays a HyperFrames composition in the browser.
//
// The composition iframe is same-origin (served via /media/), so we grab the
// GSAP timeline it registers on window.__timelines and drive it ourselves:
// pause on load, then scrub/play with the narration audio as the clock.

const $ = (id) => document.getElementById(id);

const projectId = decodeURIComponent(location.pathname.split("/")[2] || "");
const params = new URLSearchParams(location.search);
const embedded = params.has("embed");   // hosted inside the board modal
const wantedComp = params.get("c");     // preselect a composition by path
if (embedded) document.querySelector(".pv-back").style.display = "none";
$("title").textContent = projectId;
document.title = `Preview — ${projectId}`;

const state = {
  comps: [],
  comp: null,      // active composition entry
  tl: null,        // GSAP timeline inside the iframe (null => free-run mode)
  audio: null,     // HTMLAudioElement or null
  duration: 0,
  playing: false,
  raf: 0,
  t: 0,            // current time in seconds (timeline-driven mode)
  lastTick: 0,
};

function fmt(t) { return `${t.toFixed(1)} / ${state.duration.toFixed(1)}s`; }

function mediaURL(rel) {
  return `/media/${encodeURIComponent(projectId)}/` +
    rel.split("/").map(encodeURIComponent).join("/");
}

// -- timeline discovery ------------------------------------------------------

function findTimeline(win) {
  try {
    const tls = win.__timelines;
    if (tls) {
      const key = Object.keys(tls)[0];
      if (key) return tls[key];
    }
  } catch { /* cross-origin or not ready */ }
  return null;
}

function attachComposition(comp) {
  cancelAnimationFrame(state.raf);
  state.comp = comp;
  state.tl = null;
  state.playing = false;
  state.t = 0;
  state.duration = comp.duration || 0;
  $("playBtn").textContent = "▶ Play";
  $("playBtn").disabled = true;
  $("scrub").disabled = true;
  $("scrub").value = 0;

  if (state.audio) { state.audio.pause(); state.audio = null; }
  if (comp.audio) {
    state.audio = new Audio(mediaURL(comp.audio));
    state.audio.preload = "auto";
  }

  const meta = [];
  if (comp.resolution) meta.push(`${comp.resolution.width}×${comp.resolution.height}`);
  if (comp.fps) meta.push(`${comp.fps}fps`);
  if (comp.duration) meta.push(`${comp.duration}s`);
  meta.push(comp.audio ? "♪ narration" : "no audio");
  $("metaNote").textContent = meta.join(" · ");

  const frame = $("compFrame");
  $("frameBox").style.display = "";
  $("emptyNote").style.display = "none";
  frame.onload = () => {
    // The timeline may register a tick after load; retry briefly.
    let tries = 0;
    const grab = () => {
      const tl = findTimeline(frame.contentWindow);
      if (tl) {
        state.tl = tl;
        tl.pause();
        tl.time(0);
        state.duration = comp.duration || tl.duration() || 0;
      } else if (tries++ < 20) {
        setTimeout(grab, 100);
        return;
      }
      // With no controllable timeline we still allow free-run + audio restart.
      $("playBtn").disabled = false;
      $("scrub").disabled = !state.tl;
      $("timeLabel").textContent = fmt(0);
      sizeFrame();
    };
    grab();
  };
  frame.src = mediaURL(`${comp.path}/index.html`);
}

function sizeFrame() {
  const res = state.comp && state.comp.resolution;
  if (!res || !res.width || !res.height) return;
  const box = $("frameBox");
  const stage = box.parentElement;
  const maxH = stage.clientHeight - 28;
  const maxW = stage.clientWidth - 28;
  const scale = Math.min(maxH / res.height, maxW / res.width);
  const frame = $("compFrame");
  frame.style.width = `${res.width}px`;
  frame.style.height = `${res.height}px`;
  frame.style.transform = `scale(${scale})`;
  frame.style.transformOrigin = "top left";
  box.style.width = `${res.width * scale}px`;
  box.style.height = `${res.height * scale}px`;
}
window.addEventListener("resize", sizeFrame);

// -- transport ---------------------------------------------------------------

function seek(t) {
  state.t = Math.min(Math.max(t, 0), state.duration || 0);
  if (state.tl) state.tl.time(state.t);
  if (state.audio) state.audio.currentTime = state.t;
  $("scrub").value = state.duration ? (state.t / state.duration) * 1000 : 0;
  $("timeLabel").textContent = fmt(state.t);
}

function tick(now) {
  if (!state.playing) return;
  // Audio is the master clock when present; otherwise wall time.
  if (state.audio && !state.audio.paused) {
    state.t = state.audio.currentTime;
  } else {
    state.t += (now - state.lastTick) / 1000;
  }
  state.lastTick = now;
  if (state.duration && state.t >= state.duration) {
    pause();
    seek(state.duration);
    return;
  }
  if (state.tl) state.tl.time(state.t);
  $("scrub").value = state.duration ? (state.t / state.duration) * 1000 : 0;
  $("timeLabel").textContent = fmt(state.t);
  state.raf = requestAnimationFrame(tick);
}

function play() {
  if (state.duration && state.t >= state.duration - 0.05) seek(0);
  state.playing = true;
  state.lastTick = performance.now();
  if (state.audio) { state.audio.currentTime = state.t; state.audio.play().catch(() => {}); }
  if (!state.tl) $("compFrame").contentWindow.location.reload();  // free-run restart
  $("playBtn").textContent = "❚❚ Pause";
  state.raf = requestAnimationFrame(tick);
}

function pause() {
  state.playing = false;
  cancelAnimationFrame(state.raf);
  if (state.audio) state.audio.pause();
  $("playBtn").textContent = "▶ Play";
}

$("playBtn").addEventListener("click", () => (state.playing ? pause() : play()));
$("scrub").addEventListener("input", (e) => {
  if (!state.tl) return;
  const wasPlaying = state.playing;
  if (wasPlaying) pause();
  seek((Number(e.target.value) / 1000) * (state.duration || 0));
  if (wasPlaying) play();
});
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !$("playBtn").disabled) {
    e.preventDefault();
    state.playing ? pause() : play();
  }
  // Embedded in the board modal: let Escape close it even when focus is here.
  if (e.key === "Escape" && embedded && window.parent !== window) {
    window.parent.postMessage({ type: "pv-close" }, location.origin);
  }
});

// -- boot --------------------------------------------------------------------

async function boot() {
  let comps = [];
  try {
    const res = await fetch(`/api/project/${encodeURIComponent(projectId)}/compositions`);
    if (res.ok) comps = await res.json();
  } catch { /* fall through to empty note */ }
  state.comps = comps;
  if (!comps.length) {
    $("emptyNote").textContent =
      "No HyperFrames composition found in this project yet.";
    return;
  }
  const select = $("compSelect");
  if (comps.length > 1) {
    select.style.display = "";
    for (const c of comps) {
      const opt = document.createElement("option");
      opt.value = c.path;
      opt.textContent = c.name;
      select.append(opt);
    }
    select.addEventListener("change", () => {
      const comp = comps.find((c) => c.path === select.value);
      if (comp) attachComposition(comp);
    });
  }
  const initial = (wantedComp && comps.find((c) => c.path === wantedComp)) || comps[0];
  if (comps.length > 1) $("compSelect").value = initial.path;
  attachComposition(initial);
}

boot();
