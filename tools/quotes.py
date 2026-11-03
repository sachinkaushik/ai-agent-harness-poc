"""Approval-gated quote sending."""
import hashlib

from langchain.tools import tool
from langchain_core.tools import ToolException

from .binding import current_company


@tool
def send_quote(customer: str, body: str) -> dict:
    """Record a customer quote in the local outbox after human approval.

    Args:
        customer: Existing customer name, such as "Acme Logistics".
        body: Quote with Customer need, Recommended plan, Estimated price, Assumptions and Next steps.

    Returns:
        A receipt, customer name and local-send status. Repeating an identical quote reuses
        the receipt. This tool does not send email."""
    company = current_company()
    rows = company.query("SELECT name FROM customers WHERE name LIKE ? COLLATE NOCASE", (f"%{customer.strip()}%",))
    if len(rows) != 1:
        raise ToolException("Unknown or ambiguous customer. Look up the customer before sending.")
    name = rows[0]["name"]
    # A stable ID avoids duplicating the same outbox entry after a replay.
    key = hashlib.sha256(f"{name}\0{body}".encode()).hexdigest()[:16]
    company.write("INSERT OR IGNORE INTO quote_outbox VALUES (?, ?, ?)", (key, name, body))
    return {"status": "simulated_send", "receipt": key, "customer": name}
