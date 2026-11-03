"""Model creation, thread helpers and console output shared by the CLI and the web server."""
import os
from uuid import uuid4

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage

from company import ROOT

DEFAULT_MODEL = "openai:gpt-5.4"


class PreviewModel(BaseChatModel):
    """Compile configurations without credentials. Never pretends to answer prompts."""

    model_name: str = "sachintech:preview"

    @property
    def _llm_type(self):
        return "configuration-preview-only"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("Preview mode cannot generate responses. Use --live with OPENAI_API_KEY set.")


def model_name(specialist=False):
    load_dotenv(ROOT / ".env", override=True)
    name = os.getenv("HARNESS_MODEL") or DEFAULT_MODEL
    if specialist:
        name = os.getenv("HARNESS_SPECIALIST_MODEL") or name
    if not name.startswith("openai:"):
        name = f"openai:{name}"
    return name


def make_model(live, specialist=False):
    """Create the configured OpenAI model, or a non-generating model for inspecting configuration."""
    if not live:
        return PreviewModel()
    name = model_name(specialist)
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in .env. Never paste keys into code.")
    options = {"max_tokens": 2000, "timeout": 90, "max_retries": 1}
    if os.getenv("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    if name.startswith(("openai:gpt-5", "openai:o")):
        options.update(max_tokens=6000, reasoning_effort="low", use_responses_api=True)
    return init_chat_model(name, **options)


def new_thread(label):
    """Create a unique conversation ID so its messages and working files stay together."""
    return {"configurable": {"thread_id": f"{label}-{uuid4().hex[:8]}"}, "recursion_limit": 200}


def text_content(content):
    """Extract public text blocks without exposing provider reasoning blocks."""
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content
                     if isinstance(p, dict) and p.get("type") in {"text", "output_text"})


def show(result):
    """Print the new messages of the latest turn and any pending approval."""
    messages = result.get("messages", [])
    start = max((i for i, m in enumerate(messages) if m.type == "human"), default=-1)
    for message in messages[start + 1:]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                print(f"  → {call['name']}: {str(call['args'])[:250]}")
            if text_content(message.content):
                print(text_content(message.content))
        elif isinstance(message, ToolMessage):
            print(f"  ← {message.name or 'tool'}: {str(message.content)[:300]}")
    for interrupt in result.get("__interrupt__", []):
        for request in interrupt.value.get("action_requests", []):
            print(f"\n⏸  APPROVAL NEEDED: {request.get('name')} {str(request.get('args'))[:400]}")
