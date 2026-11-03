"""Customer lookup."""
from langchain.tools import tool

from .binding import current_company


@tool
def customer_lookup(customer: str) -> list[dict]:
    """Look up a customer's need, plan, device count and contact before answering or drafting.

    Args:
        customer: Company name or a distinctive part of it, such as "Acme" or "Beacon Foods".

    Returns:
        Matching records with id, name, industry, need, plan, devices and contact; an empty
        list if unknown. Cite the record ID when using these facts. This tool does not change data."""
    return current_company().query(
        "SELECT * FROM customers WHERE name LIKE ? COLLATE NOCASE", (f"%{customer.strip()}%",))
