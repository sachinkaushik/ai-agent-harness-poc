"""Support ticket lookup."""
from langchain.tools import tool

from .binding import current_company


@tool
def ticket_lookup(customer: str) -> list[dict]:
    """Look up a customer's support tickets to guide an investigation.

    Args:
        customer: Company name or a distinctive part of it, such as "Beacon".

    Returns:
        Matching tickets with id, symptom, severity, status and owning team; an empty list if
        none exist. Available to support. This lookup does not change or resolve tickets."""
    return current_company().query(
        "SELECT * FROM tickets WHERE customer LIKE ? COLLATE NOCASE", (f"%{customer.strip()}%",))
