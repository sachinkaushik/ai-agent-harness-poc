"""Command-line runner for the Sachin Tech Assist harness.

Examples:
  python cli.py --preview                                   # compile every stage x role, no model calls
  python cli.py --stage persistence --role sales            # interactive chat (needs OPENAI_API_KEY)
  python cli.py --role finance -p "What was revenue in 2026-Q3? Cite the record."
  python cli.py --role sales --thread sales-1a2b3c4d        # resume a saved persistence thread
"""
import argparse
import sys

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from company import ACCESS, ROOT, Company
from runtime import make_model, model_name, new_thread, show
from stages import STAGE_NOTES, STAGES, build_stage
from tools import COMPANY_TOOLS

RUNTIME = ROOT / ".runtime"
COMPANY_TOOL_NAMES = {tool.name for tool in COMPANY_TOOLS}


def describe(graph):
    """List the tools the compiled graph exposes to the model."""
    tools = graph.get_graph().nodes.get("tools")
    names = sorted(getattr(getattr(tools, "data", None), "tools_by_name", {}) or [])
    company = [n for n in names if n in COMPANY_TOOL_NAMES]
    harness = [n for n in names if n not in COMPANY_TOOL_NAMES]
    return company, harness


def preview():
    """Compile all stages for all roles without credentials or model calls."""
    company = Company(RUNTIME / "company.sqlite")
    for stage in STAGES:
        print(f"\n=== {stage.upper()}: {STAGE_NOTES[stage]}")
        for role in ACCESS:
            graph = build_stage(stage, make_model(False), company, role, InMemorySaver(),
                                workspace=RUNTIME / "preview" / f"{stage}-{role}")
            company_tools, harness_tools = describe(graph)
            print(f"  {role:<8} company tools: {', '.join(company_tools) or '-'}")
            print(f"  {'':<8} harness tools: {', '.join(harness_tools) or '-'}")
    print("\nAll stages compiled. No model requests were made.")


def resolve_approvals(graph, result, config):
    """Ask the human to approve or reject each paused action, then resume."""
    while result.get("__interrupt__"):
        resume = {}
        for interrupt in result["__interrupt__"]:
            decisions = []
            for request in interrupt.value["action_requests"]:
                answer = input(f"Approve {request['name']}? [y/N] ").strip().lower()
                decisions.append({"type": "approve" if answer in {"y", "yes"} else "reject"})
            resume[interrupt.id] = {"decisions": decisions}
        result = graph.invoke(Command(resume=resume), config=config)
        show(result)
    return result


def chat(graph, config, prompt):
    result = graph.invoke({"messages": [{"role": "user", "content": prompt}]}, config=config)
    show(result)
    resolve_approvals(graph, result, config)


def run(args):
    company = Company(RUNTIME / "company.sqlite")
    config = new_thread(args.role)
    if args.thread:
        config["configurable"]["thread_id"] = args.thread
    thread = config["configurable"]["thread_id"]
    workspace = RUNTIME / "cli-workspace" / thread

    def session(saver):
        graph = build_stage(args.stage, make_model(True), company, args.role, saver,
                            make_model(True, specialist=True), workspace)
        print(f"Sachin Tech Assist | stage={args.stage} role={args.role} model={model_name()} thread={thread}")
        print(f"  {STAGE_NOTES[args.stage]}")
        if args.prompt:
            chat(graph, config, args.prompt)
            return
        print("Type a request (blank line or 'exit' to quit).")
        while True:
            try:
                prompt = input("\nyou> ").strip()
            except EOFError:
                break
            if prompt in {"", "exit", "quit"}:
                break
            chat(graph, config, prompt)

    if args.stage == "persistence":
        RUNTIME.mkdir(exist_ok=True)
        with SqliteSaver.from_conn_string(str(RUNTIME / "cli-checkpoints.sqlite")) as saver:
            session(saver)
        print(f"\nSaved. Resume with: python cli.py --role {args.role} --thread {thread}")
        print(f"Working files: {workspace / 'work'}")
    else:
        session(InMemorySaver())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=STAGES, default="persistence")
    parser.add_argument("--role", choices=list(ACCESS), default="sales")
    parser.add_argument("-p", "--prompt", help="Send one request and exit.")
    parser.add_argument("--thread", help="Reuse a thread ID (persistence stage keeps it across runs).")
    parser.add_argument("--preview", action="store_true", help="Compile all stages without model calls.")
    args = parser.parse_args()
    try:
        preview() if args.preview else run(args)
    except (ValueError, KeyboardInterrupt) as error:
        print(f"\n{error}" if str(error) else "", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
