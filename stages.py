"""Build the same harness at each stage, without settings from later stages."""
from deepagents import create_deep_agent

from agent import approvals, build_harness, company_context, execution_middleware, protected_files, specialist
from workspace import reference_backend

STAGES = ("base", "context", "actions", "boundaries", "persistence")

STAGE_NOTES = {
    "base": "Model + agent loop only. No company knowledge, tools or limits.",
    "context": "Adds company/AGENTS.md and skills (read-only references).",
    "actions": "Adds ALL company tools, planning and the quote-reviewer subagent (tool-level role checks still apply).",
    "boundaries": "Shows only role-allowed tools, protects reference files, requires approval for send/refund.",
    "persistence": "Adds writable /work/ files, SQLite checkpoints and context summarization.",
}


def build_stage(stage, model, company, role, checkpointer, reviewer_model=None, workspace=None):
    """Compile the selected stage. Persistence uses the full builder in agent.py."""
    if stage not in STAGES:
        raise ValueError(f"Unknown harness stage: {stage}. Choose one of {STAGES}.")
    if stage == "persistence":
        return build_harness(model, company, role, checkpointer, reviewer_model, workspace)
    settings = {"model": model, "checkpointer": checkpointer}
    if stage != "base":
        settings.update(company_context())
        settings["backend"] = reference_backend(workspace or company.database.parent / "workspace")
        settings["system_prompt"] = "Return drafts and findings in chat. Company reference files are read-only."
    if stage in {"actions", "boundaries"}:
        all_tools = company.all_tools_for(role)
        settings.update(
            tools=list(all_tools.values()),
            subagents=[specialist(reviewer_model or model, all_tools["customer_lookup"])],
            middleware=execution_middleware(),
        )
    if stage == "boundaries":
        settings.update(
            tools=company.tools_for(role),
            permissions=protected_files(),
            interrupt_on=approvals(),
        )
    return create_deep_agent(**settings)
