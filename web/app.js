// Sachin Tech Assist UI. All server text is rendered with textContent (no HTML injection).
const $ = (id) => document.getElementById(id);
const state = { config: null, role: "sales", task: null, timer: null, lastSeq: -1 };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const options = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

async function init() {
  state.config = await api("/api/config");
  const { config } = state;
  $("stage").textContent = `Stage: ${config.stage}`;
  $("stage-note").textContent = config.stage_note;
  $("model").textContent = config.ready ? config.model : `${config.model} · OPENAI_API_KEY missing`;
  for (const role of Object.keys(config.roles)) $("role").append(new Option(role[0].toUpperCase() + role.slice(1), role));
  $("role").onchange = () => { state.role = $("role").value; newTask(); };
  $("new-task").onclick = newTask;
  $("composer").onsubmit = (e) => { e.preventDefault(); send(); };
  $("prompt").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); };
  $("resume").onclick = () => act("resume");
  $("delete").onclick = removeTask;
  newTask();
}

function renderAccess() {
  const box = $("access");
  box.replaceChildren(...state.config.roles[state.role].map((tool) => el("code", "", tool)));
}

function renderStarters(show) {
  const box = $("starters");
  box.replaceChildren();
  if (!show) return;
  for (const starter of state.config.starters[state.role] || []) {
    const button = el("button", "", starter.title);
    button.title = starter.prompt;
    button.onclick = () => { $("prompt").value = starter.prompt; $("prompt").focus(); };
    box.append(button);
  }
}

async function loadTasks() {
  const tasks = await api(`/api/tasks?role=${state.role}`);
  $("tasks").replaceChildren(...tasks.map((task) => {
    const item = el("li", task.id === state.task ? "active" : "");
    item.append(el("span", "", task.title), el("small", "", task.status.replace("_", " ")));
    item.onclick = () => openTask(task.id);
    return item;
  }));
}

function newTask() {
  clearTimeout(state.timer);
  state.task = null;
  state.lastSeq = -1;
  $("title").textContent = "New task";
  $("status").textContent = "";
  $("status").className = "status";
  $("feed").replaceChildren(el("p", "muted", "Pick a starter or type a request. Every tool call below is a real harness event."));
  $("approval").classList.add("hidden");
  $("resume").classList.add("hidden");
  $("delete").classList.add("hidden");
  renderSide({ todos: [], files: {} });
  renderAccess();
  renderStarters(true);
  loadTasks();
  loadRecords();
}

async function openTask(id) {
  clearTimeout(state.timer);
  state.task = id;
  state.lastSeq = -1;
  $("feed").replaceChildren();
  renderStarters(false);
  await refresh();
}

function renderEvent(event) {
  if (event.kind === "message") return el("div", `msg ${event.role}`, event.text);
  if (event.kind === "tool_call") {
    const node = el("div", `event ${event.pillar}`);
    const details = el("details");
    const prefix = event.scope === "Specialist" ? "↳ Specialist · " : "";
    details.append(el("summary", "", `${prefix}${event.label} (${event.tool})`), el("pre", "", JSON.stringify(event.args, null, 2)));
    node.append(details);
    return node;
  }
  if (event.kind === "tool_result") {
    const node = el("div", "event");
    const details = el("details");
    details.append(el("summary", event.failed ? "failed" : "", `${event.failed ? "✗" : "✓"} ${event.tool} result`), el("pre", "", event.result));
    node.append(details);
    return node;
  }
  if (event.kind === "error") return el("div", "event error", `⚠ ${event.label}`);
  return el("div", `event ${event.pillar || ""}`, event.label);
}

function renderSide(task) {
  const todos = task.todos || [];
  $("todos").replaceChildren(...(todos.length ? todos.map((t) =>
    el("li", "", `${t.status === "completed" ? "☑" : t.status === "in_progress" ? "◐" : "☐"} ${t.content}`))
    : [el("li", "muted", "No plan yet.")]));
  const files = Object.entries(task.files || {});
  $("files").replaceChildren(...(files.length ? files.map(([path, content]) => {
    const details = el("details", "file");
    details.append(el("summary", "", path), el("pre", "", content));
    return details;
  }) : [el("p", "muted", "No saved files.")]));
}

async function loadRecords() {
  const records = await api("/api/records");
  const rows = [
    ...records.quote_outbox.map((r) => `Quote → ${r.customer} (receipt ${r.id})`),
    ...records.refund_ledger.map((r) => `Refund $${r.amount_usd} on ${r.invoice} (receipt ${r.id})`),
  ];
  $("records").replaceChildren(...(rows.length ? rows.map((text) => el("div", "record", text))
    : [el("p", "muted", "Nothing approved yet. Approved quotes and refunds land here; nothing leaves your machine.")]));
}

function renderApproval(task) {
  const box = $("approval");
  const requests = (task.interrupts || []).flatMap((i) => i.action_requests || []);
  if (task.status !== "needs_review" || !requests.length) { box.classList.add("hidden"); return; }
  box.replaceChildren(el("strong", "", "⏸ Human approval required"));
  for (const request of requests) {
    box.append(el("p", "", `The agent wants to call ${request.name}:`), el("pre", "", JSON.stringify(request.args, null, 2)));
  }
  const buttons = el("div", "buttons");
  const approve = el("button", "primary", "Approve");
  const reject = el("button", "danger", "Reject");
  approve.onclick = () => act("review", { decision: "approve" });
  reject.onclick = () => act("review", { decision: "reject" });
  buttons.append(approve, reject);
  box.append(buttons);
  box.classList.remove("hidden");
}

async function refresh() {
  if (!state.task) return;
  const task = await api(`/api/tasks/${state.task}`);
  $("title").textContent = task.title;
  $("status").textContent = task.status.replace("_", " ");
  $("status").className = `status ${task.status}`;
  const feed = $("feed");
  for (const event of task.events.filter((e) => e.seq > state.lastSeq)) {
    feed.append(renderEvent(event));
    state.lastSeq = event.seq;
  }
  feed.scrollTop = feed.scrollHeight;
  renderSide(task);
  renderApproval(task);
  $("resume").classList.toggle("hidden", !["error", "interrupted"].includes(task.status));
  $("delete").classList.toggle("hidden", ["running", "queued"].includes(task.status));
  const busy = ["running", "queued"].includes(task.status);
  if (busy) state.timer = setTimeout(refresh, 1000);
  else { loadTasks(); loadRecords(); }
}

async function send() {
  const prompt = $("prompt").value.trim();
  if (!prompt) return;
  try {
    if (state.task) await api(`/api/tasks/${state.task}/message`, { role: state.role, prompt });
    else state.task = (await api("/api/tasks", { role: state.role, prompt })).id;
    $("prompt").value = "";
    renderStarters(false);
    if (state.lastSeq < 0) $("feed").replaceChildren();
    clearTimeout(state.timer);
    await refresh();
    loadTasks();
  } catch (error) { alert(error.message); }
}

async function act(action, extra = {}) {
  try {
    await api(`/api/tasks/${state.task}/${action}`, { role: state.role, ...extra });
    $("approval").classList.add("hidden");
    clearTimeout(state.timer);
    await refresh();
  } catch (error) { alert(error.message); }
}

async function removeTask() {
  if (!confirm("Delete this task, its checkpoints and its working files?")) return;
  try {
    await api(`/api/tasks/${state.task}/delete`, { role: state.role });
    newTask();
  } catch (error) { alert(error.message); }
}

init().catch((error) => { document.body.textContent = `Failed to load: ${error.message}`; });
