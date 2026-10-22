// Backlot Studio — chat workbench for the embedded OpenMontage agent.
//
// Everything renders off the session event feed (SSE replays history from
// seq 0, then streams live), so a page reload or server restart rebuilds the
// exact same chat. Event types handled here mirror sessions.py:
//   user / assistant / status / tool_call / tool_result / todos /
//   approval_request / project / state / turn_done / error

import { el, getJSON, fmtAgo } from "/ui/lib.js";

const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  source: null,        // active EventSource
  lastSeq: 0,          // dedupe cursor (EventSource reconnects replay)
  running: false,
  projectId: null,
  toolCards: new Map(),     // tool_use_id -> card element
  approvalCards: new Map(), // tool_use_id -> approval element
};

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* noop */ }
    throw new Error(detail);
  }
  return res.json();
}

// Minimal markdown: escape everything, then fenced code, inline code, bold.
function renderMarkdown(text) {
  const escaped = String(text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const withFences = escaped.replace(/```([\s\S]*?)```/g, (_m, body) => {
    const inner = body.replace(/^[a-zA-Z0-9_-]*\n/, "");
    return `<pre>${inner}</pre>`;
  });
  return withFences
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

function scrollToBottom() {
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

function addNode(node) {
  const welcome = $("welcome");
  if (welcome) welcome.remove();
  $("messages").append(node);
  scrollToBottom();
  return node;
}

function toolArgSummary(name, input) {
  if (!input) return "";
  if (name === "bash") return input.command || "";
  if (input.path) return input.path;
  if (input.pattern) return input.pattern;
  if (input.skill_id) return input.skill_id;
  try { return JSON.stringify(input).slice(0, 160); } catch { return ""; }
}

// ---------------------------------------------------------------------------
// event rendering
// ---------------------------------------------------------------------------

function onUser(data) {
  addNode(el("div", { class: "st-msg user" }, data.text || ""));
}

function onAssistant(data) {
  const node = el("div", { class: "st-msg assistant" });
  node.innerHTML = renderMarkdown(data.text || "");
  addNode(node);
}

function onStatus(data) {
  addNode(el("div", { class: "st-status" }, data.text || ""));
}

function onError(data) {
  addNode(el("div", { class: "st-error" }, data.text || "Unknown error"));
}

function onToolCall(data) {
  const card = el("details", { class: "st-tool" },
    el("summary", {},
      el("span", { class: "st-tool-name" }, data.name || "tool"),
      el("span", { class: "st-tool-arg" }, toolArgSummary(data.name, data.input)),
      el("span", { class: "st-tool-flag" }, "…")),
    el("pre", {}, JSON.stringify(data.input || {}, null, 2)));
  state.toolCards.set(data.id, card);
  addNode(card);
}

function onToolResult(data) {
  const card = state.toolCards.get(data.id);
  const output = data.output || "(no output)";
  if (card) {
    card.classList.add(data.denied ? "denied" : "done");
    card.querySelector(".st-tool-flag").textContent = data.denied ? "✕ denied" : "✓";
    card.querySelector("pre").textContent = output;
  } else {
    addNode(el("div", { class: "st-tool done" }, el("pre", {}, output)));
  }
  resolveApprovalCard(data.id);
  scrollToBottom();
}

function onTodos(data) {
  const todos = data.todos || [];
  const strip = $("todoStrip");
  strip.style.display = todos.length ? "" : "none";
  const list = $("todoList");
  list.innerHTML = "";
  const MARKS = { completed: "✓", in_progress: "◉", pending: "○" };
  for (const t of todos) {
    list.append(el("li", { class: t.status || "pending" },
      el("span", { class: "st-todo-mark" }, MARKS[t.status] || "○"),
      t.content || ""));
  }
}

function onApprovalRequest(data) {
  const id = data.tool_use_id;
  const card = el("div", { class: "st-approval" },
    el("div", { class: "st-approval-title" }, `Approval — ${data.name}`),
    el("pre", {}, toolArgSummary(data.name, data.input) ||
      JSON.stringify(data.input || {}, null, 2)),
    el("div", { class: "st-approval-btns" },
      el("button", {
        class: "st-btn st-btn-green",
        onclick: () => decide(true),
      }, "Approve"),
      el("button", {
        class: "st-btn st-btn-red",
        onclick: () => decide(false),
      }, "Deny")));

  async function decide(approve) {
    try {
      await postJSON(`/api/chat/${state.sessionId}/approve`, { approve });
      card.classList.add("resolved");
    } catch (e) {
      onError({ text: `Approval failed: ${e.message}` });
    }
  }

  state.approvalCards.set(id, card);
  addNode(card);
}

function resolveApprovalCard(toolUseId) {
  const card = state.approvalCards.get(toolUseId);
  if (card) card.classList.add("resolved");
}

function resolveAllApprovals() {
  for (const card of state.approvalCards.values()) card.classList.add("resolved");
}

function onProject(data) {
  if (data.project_id) loadBoard(data.project_id);
}

function onState(data) {
  setRunning(data.status === "running" || data.status === "awaiting_approval");
}

function onTurnDone() {
  resolveAllApprovals();
  setRunning(false);
}

const HANDLERS = {
  user: onUser,
  assistant: onAssistant,
  status: onStatus,
  error: onError,
  tool_call: onToolCall,
  tool_result: onToolResult,
  todos: onTodos,
  approval_request: onApprovalRequest,
  project: onProject,
  state: onState,
  turn_done: onTurnDone,
};

function handleEvent(event) {
  if (event.seq <= state.lastSeq) return; // reconnect replay dedupe
  state.lastSeq = event.seq;
  const handler = HANDLERS[event.type];
  if (handler) handler(event.data || {});
}

// ---------------------------------------------------------------------------
// run state / composer
// ---------------------------------------------------------------------------

function setRunning(running) {
  state.running = running;
  const badge = $("stateBadge");
  badge.classList.toggle("idle", !running);
  $("stateText").textContent = running ? "WORKING" : "IDLE";
  $("interruptBtn").style.display = running ? "" : "none";
  $("sendBtn").disabled = running;
}

async function sendMessage() {
  const input = $("input");
  const text = input.value.trim();
  if (!text || state.running) return;
  try {
    if (!state.sessionId) await createSession();
    await postJSON(`/api/chat/${state.sessionId}/message`, { text });
    input.value = "";
    input.style.height = "";
  } catch (e) {
    onError({ text: `Send failed: ${e.message}` });
  }
}

// ---------------------------------------------------------------------------
// sessions
// ---------------------------------------------------------------------------

async function createSession() {
  const mode = $("confirmMode").checked ? "confirm" : "auto";
  const summary = await postJSON("/api/chat/sessions", { permission_mode: mode });
  attachSession(summary.id, { push: true });
  refreshSessionList();
  return summary;
}

function attachSession(sessionId, { push = false } = {}) {
  if (state.source) { state.source.close(); state.source = null; }
  state.sessionId = sessionId;
  state.lastSeq = 0;
  state.toolCards.clear();
  state.approvalCards.clear();
  state.projectId = null;
  $("messages").innerHTML = "";
  $("todoStrip").style.display = "none";
  $("sessionChip").textContent = sessionId || "";
  setRunning(false);
  if (push) history.pushState({}, "", `/studio/${sessionId}`);
  if (!sessionId) return;

  const source = new EventSource(`/api/chat/${sessionId}/events?after=0`);
  state.source = source;
  source.onmessage = (msg) => {
    let data;
    try { data = JSON.parse(msg.data); } catch { return; }
    if (data.type === "hello") {
      const summary = data.summary || {};
      setRunning(summary.status === "running" || summary.status === "awaiting_approval");
      if (summary.todos && summary.todos.length) onTodos({ todos: summary.todos });
      if (summary.project_id) loadBoard(summary.project_id);
    } else if (data.type === "event") {
      handleEvent(data.event);
    }
    // heartbeats keep the connection warm; nothing to render
  };
  refreshSessionList();
}

async function refreshSessionList() {
  let sessions = [];
  try { sessions = await getJSON("/api/chat/sessions"); } catch { return; }
  const list = $("sessionList");
  list.innerHTML = "";
  for (const s of sessions) {
    const item = el("div", {
      class: "st-session-item"
        + (s.id === state.sessionId ? " active" : "")
        + (s.status !== "idle" ? " running" : ""),
      onclick: () => { if (s.id !== state.sessionId) attachSession(s.id, { push: true }); },
      oncontextmenu: (e) => showSessionMenu(e, s),
      title: s.title,
    },
      s.title,
      el("span", { class: "st-session-meta" },
        `${s.status !== "idle" ? "● working · " : ""}${fmtAgo(s.created_at)}`));
    list.append(item);
  }
}

// -- session context menu (right-click) -------------------------------------

let ctxMenu = null;

function closeCtxMenu() {
  if (ctxMenu) { ctxMenu.remove(); ctxMenu = null; }
}
document.addEventListener("click", closeCtxMenu);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCtxMenu(); });
window.addEventListener("blur", closeCtxMenu);

function showSessionMenu(e, session) {
  e.preventDefault();
  e.stopPropagation();
  closeCtxMenu();
  ctxMenu = el("div", { class: "st-ctx-menu" },
    el("button", {
      class: "st-ctx-item danger",
      onclick: () => { closeCtxMenu(); deleteSession(session); },
    }, "🗑 Delete session"));
  document.body.append(ctxMenu);
  // Clamp inside the viewport (menu is tiny, a simple flip is enough).
  const rect = ctxMenu.getBoundingClientRect();
  const x = Math.min(e.clientX, window.innerWidth - rect.width - 8);
  const y = Math.min(e.clientY, window.innerHeight - rect.height - 8);
  ctxMenu.style.left = `${x}px`;
  ctxMenu.style.top = `${y}px`;
}

async function deleteSession(session) {
  const label = session.title || session.id;
  if (!window.confirm(`Delete session “${label}”?\nIts saved history will be removed.`)) return;
  try {
    const res = await fetch(`/api/chat/${session.id}`, { method: "DELETE" });
    if (!res.ok) {
      let detail = `${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch { /* noop */ }
      throw new Error(detail);
    }
    if (session.id === state.sessionId) {
      attachSession(null);
      history.replaceState({}, "", "/studio");
    }
    refreshSessionList();
  } catch (err) {
    onError({ text: `Delete failed: ${err.message}` });
  }
}

// ---------------------------------------------------------------------------
// board panel
// ---------------------------------------------------------------------------

function loadBoard(projectId) {
  if (!projectId || projectId === state.projectId) return;
  state.projectId = projectId;
  $("boardFrame").src = `/p/${encodeURIComponent(projectId)}`;
  $("boardEmpty").style.display = "none";
  const open = $("boardOpen");
  open.href = `/p/${encodeURIComponent(projectId)}`;
  open.style.display = "";
  const select = $("projectSelect");
  if (![...select.options].some((o) => o.value === projectId)) {
    select.append(el("option", { value: projectId }, projectId));
  }
  select.value = projectId;
  refreshPreviewLink(projectId);
}

async function refreshPreviewLink(projectId) {
  const link = $("previewOpen");
  link.style.display = "none";
  if (!projectId) return;
  try {
    const comps = await getJSON(`/api/project/${encodeURIComponent(projectId)}/compositions`);
    if (projectId === state.projectId && comps.length) {
      link.href = `/preview/${encodeURIComponent(projectId)}`;
      link.style.display = "";
    }
  } catch { /* keep hidden */ }
}

async function populateProjects() {
  let projects = [];
  try { projects = await getJSON("/api/projects"); } catch { return; }
  const select = $("projectSelect");
  const current = select.value;
  select.innerHTML = "";
  select.append(el("option", { value: "" }, "— no project —"));
  for (const p of projects) {
    select.append(el("option", { value: p.project_id },
      `${p.project_id}${p.live ? " ●" : ""}`));
  }
  select.value = current || state.projectId || "";
}

// ---------------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------------

$("sendBtn").addEventListener("click", sendMessage);
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
$("input").addEventListener("input", (e) => {
  const t = e.target;
  t.style.height = "";
  t.style.height = `${Math.min(t.scrollHeight, 160)}px`;
});
$("interruptBtn").addEventListener("click", async () => {
  if (!state.sessionId) return;
  try { await postJSON(`/api/chat/${state.sessionId}/interrupt`); } catch { /* noop */ }
});
$("newSessionBtn").addEventListener("click", () => {
  attachSession(null);
  history.pushState({}, "", "/studio");
});
$("projectSelect").addEventListener("change", (e) => {
  const id = e.target.value;
  if (id) loadBoard(id);
});
window.addEventListener("popstate", () => {
  const match = location.pathname.match(/^\/studio\/([^/]+)/);
  attachSession(match ? match[1] : null);
});

// initial route: /studio/<sid> resumes that session
const routed = location.pathname.match(/^\/studio\/([^/]+)/);
if (routed) attachSession(routed[1]);
else refreshSessionList();
populateProjects();
setInterval(populateProjects, 30_000);
setInterval(refreshSessionList, 30_000);
// compositions appear mid-production — keep the preview link fresh
setInterval(() => refreshPreviewLink(state.projectId), 30_000);
