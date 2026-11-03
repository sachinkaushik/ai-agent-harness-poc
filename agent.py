"""Complete configuration for Sachin Tech Assist, the Sachin Tech harness.

The four harness pillars:
  Context     - company/AGENTS.md (always loaded) + skills/ (loaded on demand)
  Actions     - role-bound company tools, planning (write_todos), a quote-reviewer subagent
  Boundaries  - role filtering, protected reference files, human approval, model-call limits
  Persistence - writable /work/ files, SQLite checkpoints, context summarization
"""
from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import ModelCallLimitMiddleware, TodoListMiddleware

from workspace import prepare_workspace

# Only our explicitly configured specialist; no automatic general-purpose delegate.
for provider in ("openai", "sachintech", "sachintech:preview"):
    register_harness_profile(provider, HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ))

APPROVAL_REQUIRED = ("send_quote", "issue_refund")


def company_context():
    """Context: always-loaded conventions plus procedures discovered when relevant."""
    return {
        "memory": ["/company/AGENTS.md"],
        "skills": ["/skills/company/", "/skills/team/"],
    }


def specialist(model, lookup):
    """Actions: a quote reviewer with customer lookup only and no sending authority."""
    return {
        "name": "quote-reviewer",
        "description": "Review a quote or commitment against customer records and pricing; flag unsupported promises.",
        "system_prompt": ("Look up the customer. Check plan, device count and price against the facts. "
                          "Return evidence (record IDs), assumptions and corrections. You cannot send anything."),
        "model": model,
        "tools": [lookup],
        "middleware": [ModelCallLimitMiddleware(run_limit=4, exit_behavior="end")],
    }


def execution_middleware():
    """Actions + Boundaries: planning and a bounded parent-agent run."""
    return [
        TodoListMiddleware(),
        ModelCallLimitMiddleware(run_limit=12, exit_behavior="end"),
    ]


def protected_files():
    """Boundaries: the model may read but never change company references."""
    return [FilesystemPermission(operations=["write"], paths=["/company/**", "/skills/**"], mode="deny")]


def approvals():
    """Boundaries: pause for a human before any external-effect action."""
    return {name: {"allowed_decisions": ["approve", "reject"]} for name in APPROVAL_REQUIRED}


def build_harness(model, company, role, checkpointer, reviewer_model=None, workspace=None):
    """Full harness. The role comes from the application; each task uses its own thread."""
    workspace = prepare_workspace(workspace or company.database.parent / "workspace")
    tools = company.tools_for(role)
    lookup = next(t for t in tools if t.name == "customer_lookup")
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    middleware = execution_middleware()
    middleware.append(SummarizationMiddleware(
        model=model, backend=backend,
        trigger=("tokens", 12000), keep=("messages", 6),
        trim_tokens_to_summarize=None,
    ))
    return create_deep_agent(
        model=model,
        **company_context(),
        tools=tools,
        subagents=[specialist(reviewer_model or model, lookup)],
        permissions=protected_files(),
        interrupt_on=approvals(),
        middleware=middleware,
        backend=backend,
        checkpointer=checkpointer,
    )
