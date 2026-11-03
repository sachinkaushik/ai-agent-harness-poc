"""Local web chat interface for the Sachin Tech Assist harness. Run: python server.py"""
import json
import mimetypes
import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from company import ACCESS, ROOT, Company
from runtime import PreviewModel, make_model, model_name, text_content
from stages import STAGE_NOTES, STAGES, build_stage
from workspace import recover_old_files, working_files

load_dotenv(ROOT / ".env", override=True)
STAGE = os.getenv("HARNESS_STAGE", "persistence")
if STAGE not in STAGES:
    raise ValueError(f"HARNESS_STAGE must be one of {STAGES}")
PORT = int(os.getenv("HARNESS_PORT", "8502"))
# 0.0.0.0 only inside a container; docker-compose publishes the port on host localhost only.
HOST = os.getenv("HARNESS_HOST", "127.0.0.1")
WEB = ROOT / "web"
RUNTIME = ROOT / ".runtime"
RUNTIME.mkdir(exist_ok=True)
PERSISTENT = STAGE == "persistence"
# Earlier stages keep task metadata in shared memory, so a restart starts fresh.
META = str(RUNTIME / "ui-tasks.sqlite") if PERSISTENT else f"file:sachintech-{STAGE}?mode=memory&cache=shared"
_KEEP_MEMORY_DB = None if PERSISTENT else sqlite3.connect(META, uri=True, check_same_thread=False)
CHECKPOINTS = RUNTIME / "ui-checkpoints.sqlite"
MEMORY = InMemorySaver()
COMPANY = Company(RUNTIME / "company.sqlite")
ACTIVE = set()
LOCK = threading.Lock()
DB_LOCK = threading.RLock()

STARTERS = {
    "sales": [
        {"title": "Prepare an Acme quote", "prompt": "Use our quote skill to prepare a quote for Acme Logistics from the customer record. Mark discounts and timeline as needing confirmation. Save it to /work/quote.md. Do not send it."},
        {"title": "Review a risky promise", "prompt": "Ask the quote reviewer to check this promise for Beacon Foods: 'We will onboard all 300 trailers in 1 week at $5 per device.'"},
        {"title": "Send the quote (approval)", "prompt": "Send the Acme Logistics quote you prepared to the customer."},
    ],
    "support": [
        {"title": "Triage Beacon's alert delay", "prompt": "Use our triage skill to investigate Beacon Foods' delayed temperature alerts. Cite the ticket and customer records."},
        {"title": "Try a finance tool (denied)", "prompt": "What was revenue in 2026-Q3?"},
    ],
    "finance": [
        {"title": "Quarterly revenue", "prompt": "Compare revenue for 2026-Q2 and 2026-Q3. Cite the records."},
        {"title": "Refund review (approval)", "prompt": "Use our refund skill: Beacon Foods asks for a $500 credit on INV-5002 because of ticket T-1001. Review it and, if policy allows, issue the refund."},
    ],
}

# Tool -> (readable label, harness pillar) for the activity feed.
TOOL_LABELS = {
    "customer_lookup": ("Look up customer", "actions"),
    "ticket_lookup": ("Look up tickets", "actions"),
    "invoice_lookup": ("Look up invoices", "actions"),
    "revenue_summary": ("Query revenue", "actions"),
    "write_todos": ("Update plan", "actions"),
    "task": ("Delegate to quote reviewer", "actions"),
    "send_quote": ("Send quote", "boundaries"),
    "issue_refund": ("Issue refund", "boundaries"),
    "write_file": ("Save working file", "persistence"),
    "edit_file": ("Update working file", "persistence"),
}


def tool_label(name, args):
    if name == "read_file":
        path = args.get("file_path", "")
        if path.startswith("/skills/"):
            return f"Read skill {path.split('/')[-2]}", "context"
        if path.startswith("/company/"):
            return "Read company instructions", "context"
        return "Read working file", "persistence"
    return TOOL_LABELS.get(name, (name.replace("_", " ").capitalize(), "actions"))


@contextmanager
def db():
    """Serialize short task-metadata transactions (not model execution)."""
    with DB_LOCK:
        conn = sqlite3.connect(META, timeout=30, uri=not PERSISTENT)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, role TEXT, title TEXT, status TEXT,
                                             created REAL, updated REAL, error TEXT);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, payload TEXT);
        """)
        conn.execute("UPDATE tasks SET status='interrupted', error='Server restarted. Resume to continue.' "
                     "WHERE status IN ('running', 'queued')")


def append_event(task, **payload):
    payload["time"] = time.time()
    with db() as conn:
        conn.execute("INSERT INTO events(task, payload) VALUES (?, ?)", (task, json.dumps(payload, ensure_ascii=False)))


def set_status(task, status, error=None):
    with db() as conn:
        conn.execute("UPDATE tasks SET status=?, updated=?, error=? WHERE id=?", (status, time.time(), error, task))


def get_task(task):
    with db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
    if row is None:
        raise ValueError("Task not found")
    return dict(row)


def task_workspace(task):
    if not task or not all(ch.isalnum() or ch in "-_" for ch in task):
        raise ValueError("Invalid task ID")
    return RUNTIME / "ui-workspace" / task


@contextmanager
def harness(role, task, live=True):
    """Build the active stage for a role; reopen the checkpoint store per request."""
    model = make_model(True) if live else PreviewModel()
    reviewer = make_model(True, specialist=True) if live else model

    def build(saver):
        return build_stage(STAGE, model, COMPANY, role, saver, reviewer, task_workspace(task))

    if PERSISTENT:
        with SqliteSaver.from_conn_string(str(CHECKPOINTS)) as saver:
            yield build(saver)
    else:
        yield build(MEMORY)


def thread(task):
    return {"configurable": {"thread_id": task}, "recursion_limit": 200}


def safe_error(error):
    """Short failure message; never return SDK request objects, headers or credentials."""
    code = getattr(error, "status_code", None)
    if code in {401, 403}:
        return "OpenAI rejected the API key. Check OPENAI_API_KEY in .env."
    if code == 429:
        return "OpenAI rate limit or quota reached. Check your account, then resume."
    if code:
        return f"The model provider returned HTTP {code}. The task is saved; you can resume."
    if isinstance(error, ValueError):
        return str(error)[:240]
    return f"This run stopped ({type(error).__name__}). Completed work is saved."


def logged_calls(task):
    """Tool calls already shown, so a resumed run does not repeat them in the feed."""
    with db() as conn:
        rows = conn.execute("SELECT payload FROM events WHERE task=?", (task,)).fetchall()
    seen = set()
    for row in rows:
        event = json.loads(row["payload"])
        if event.get("kind") == "tool_call" and event.get("call_id"):
            seen.add((event["scope_key"], event["call_id"], "call"))
    return seen


def record_messages(task, namespace, messages, seen):
    scope = "Specialist" if namespace else "Main agent"
    for message in messages:
        kind = getattr(message, "type", None)
        if kind == "ai":
            text = text_content(message.content)
            if not namespace and not message.tool_calls and text and ("msg", message.id) not in seen:
                seen.add(("msg", message.id))
                append_event(task, kind="message", role="assistant", text=text)
            for call in message.tool_calls:
                key = (str(namespace), call["id"], "call")
                if key not in seen:
                    seen.add(key)
                    label, pillar = tool_label(call["name"], call["args"])
                    append_event(task, kind="tool_call", call_id=call["id"], tool=call["name"], label=label,
                                 pillar=pillar, scope=scope, scope_key=str(namespace), args=call["args"])
        elif kind == "tool":
            key = (str(namespace), message.tool_call_id, "result")
            if key not in seen:
                seen.add(key)
                append_event(task, kind="tool_result", tool=message.name, scope=scope,
                             result=text_content(message.content)[:8000],
                             failed=getattr(message, "status", None) == "error")


def run_task(task, prompt=None, decision=None):
    """Execute or resume the graph, streaming real tool events into the activity log."""
    row = get_task(task)
    try:
        with harness(row["role"], task) as graph:
            config = thread(task)
            snapshot = graph.get_state(config)
            recover_old_files(task_workspace(task), snapshot.values.get("files", {}))
            if decision:
                interrupts = [i for t in snapshot.tasks for i in t.interrupts]
                if not interrupts:
                    raise ValueError("There is no pending approval.")
                value = Command(resume={i.id: {"decisions": [{"type": decision} for _ in i.value["action_requests"]]}
                                        for i in interrupts})
                append_event(task, kind="review", pillar="boundaries",
                             label="Approved by you" if decision == "approve" else "Rejected by you")
            elif prompt:
                if snapshot.next:
                    raise ValueError("Resolve the pending run before sending another request.")
                value = {"messages": [{"role": "user", "content": prompt}]}
                append_event(task, kind="message", role="user", text=prompt)
            else:
                value = None
            seen = logged_calls(task)
            for namespace, update in graph.stream(value, config, stream_mode="updates", subgraphs=True,
                                                  durability="sync"):
                for payload in update.values():
                    if isinstance(payload, dict):
                        messages = payload.get("messages", [])
                        record_messages(task, namespace, messages if isinstance(messages, list) else [messages], seen)
            snapshot = graph.get_state(config)
            needs_review = any(t.interrupts for t in snapshot.tasks)
            status = "needs_review" if needs_review else "interrupted" if snapshot.next else "complete"
            append_event(task, kind="run_end", pillar="boundaries" if needs_review else None,
                         label={"needs_review": "Waiting for your approval", "complete": "Run complete"}.get(status, "Run paused"))
            set_status(task, status)
    except Exception as error:
        message = safe_error(error)
        append_event(task, kind="error", label=message)
        set_status(task, "error", message)
    finally:
        with LOCK:
            ACTIVE.discard(task)


def start(task, prompt=None, decision=None):
    """One background run per task; prevent concurrent runs on the same thread."""
    with LOCK:
        get_task(task)
        if task in ACTIVE:
            raise ValueError("This task is already running.")
        ACTIVE.add(task)
    set_status(task, "running")
    threading.Thread(target=run_task, args=(task, prompt, decision), daemon=True).start()


def delete_task(task):
    with LOCK:
        row = get_task(task)
        if task in ACTIVE or row["status"] in {"running", "queued"}:
            raise ValueError("Wait for this task to finish before deleting it.")
        if PERSISTENT:
            with SqliteSaver.from_conn_string(str(CHECKPOINTS)) as saver:
                saver.delete_thread(task)
        else:
            MEMORY.delete_thread(task)
        shutil.rmtree(task_workspace(task), ignore_errors=True)
        with db() as conn:
            conn.execute("DELETE FROM events WHERE task=?", (task,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task,))


def task_state(task):
    row = get_task(task)
    with harness(row["role"], task, live=False) as graph:
        snapshot = graph.get_state(thread(task))
    values = snapshot.values
    recover_old_files(task_workspace(task), values.get("files", {}))
    with db() as conn:
        events = [{"seq": r["seq"], **json.loads(r["payload"])}
                  for r in conn.execute("SELECT seq, payload FROM events WHERE task=? ORDER BY seq", (task,))]
    return {
        **row,
        "events": events,
        "files": working_files(task_workspace(task)),
        "todos": values.get("todos", []),
        "interrupts": [i.value for t in snapshot.tasks for i in t.interrupts],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep conversation contents out of the console

    def respond(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path)
        path = route.path
        try:
            if path == "/api/config":
                self.respond({
                    "model": model_name(), "ready": bool(os.getenv("OPENAI_API_KEY")),
                    "stage": STAGE, "stage_note": STAGE_NOTES[STAGE], "stages": STAGES,
                    "roles": {role: sorted(tools) for role, tools in ACCESS.items()},
                    "starters": STARTERS,
                })
                return
            if path == "/api/tasks":
                role = parse_qs(route.query).get("role", ["sales"])[0]
                if role not in ACCESS:
                    raise ValueError("Unknown role")
                with db() as conn:
                    rows = [dict(r) for r in conn.execute("SELECT * FROM tasks WHERE role=? ORDER BY updated DESC", (role,))]
                self.respond(rows)
                return
            if path == "/api/records":
                self.respond({"quote_outbox": COMPANY.quote_outbox(), "refund_ledger": COMPANY.refund_ledger()})
                return
            if path.startswith("/api/tasks/"):
                self.respond(task_state(path.rsplit("/", 1)[-1]))
                return
            file = (WEB / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not file.is_relative_to(WEB.resolve()) or not file.is_file():
                self.respond({"error": "Not found"}, 404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(file.read_bytes())
        except (ValueError, KeyError):
            self.respond({"error": "Not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.respond({"error": "Unable to load this task."}, 500)

    def do_POST(self):
        allowed_hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in allowed_hosts or (origin and origin.split("//", 1)[-1] not in allowed_hosts):
            self.respond({"error": "Request origin not allowed"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 24000:
                raise ValueError("Request is too large")
            data = json.loads(self.rfile.read(size) or b"{}")
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts == ["api", "tasks"]:
                role, prompt = data.get("role"), (data.get("prompt") or "").strip()
                if role not in ACCESS or not prompt or len(prompt) > 12000:
                    raise ValueError("Choose a role and enter a request.")
                task, now = uuid4().hex, time.time()
                with db() as conn:
                    conn.execute("INSERT INTO tasks VALUES (?, ?, ?, 'queued', ?, ?, NULL)",
                                 (task, role, prompt.splitlines()[0][:64], now, now))
                start(task, prompt)
                self.respond({"id": task}, 202)
                return
            if len(parts) == 4 and parts[:2] == ["api", "tasks"]:
                task, action = parts[2:]
                row = get_task(task)
                if row["role"] != data.get("role"):
                    raise ValueError("Use the task's original role.")
                if action == "delete":
                    delete_task(task)
                    self.respond({"deleted": task})
                    return
                if action == "message":
                    prompt = (data.get("prompt") or "").strip()
                    if not prompt or len(prompt) > 12000:
                        raise ValueError("Enter a message.")
                    if row["status"] in {"running", "needs_review", "interrupted"}:
                        raise ValueError("Finish the pending run first.")
                    start(task, prompt)
                elif action == "review":
                    decision = data.get("decision")
                    if decision not in {"approve", "reject"} or row["status"] != "needs_review":
                        raise ValueError("No matching approval is pending.")
                    start(task, decision=decision)
                elif action == "resume":
                    if row["status"] not in {"error", "interrupted"}:
                        raise ValueError("This task cannot be resumed.")
                    start(task)
                else:
                    raise ValueError("Unknown action")
                self.respond({"id": task}, 202)
                return
            self.respond({"error": "Not found"}, 404)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.respond({"error": str(error)}, 400)
        except Exception:
            self.respond({"error": "Unable to start this task."}, 500)


if __name__ == "__main__":
    init_db()
    print(f"Sachin Tech Assist ({STAGE}) ready at http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
