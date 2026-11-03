"""Finance lookups and the approval-gated refund action."""
import hashlib

from langchain.tools import tool
from langchain_core.tools import ToolException

from .binding import current_company


@tool
def invoice_lookup(customer: str) -> list[dict]:
    """Look up a customer's invoices.

    Args:
        customer: Company name or a distinctive part of it, such as "Beacon".

    Returns:
        Invoices with id, month, amount_usd and status (paid, open or overdue); an empty list
        if none exist. Available to finance. This tool does not change data."""
    return current_company().query(
        "SELECT * FROM invoices WHERE customer LIKE ? COLLATE NOCASE ORDER BY month", (f"%{customer.strip()}%",))


@tool
def revenue_summary(quarter: str) -> list[dict]:
    """Read the recorded revenue total for a quarter, without estimating missing data.

    Args:
        quarter: Reporting quarter in YYYY-QN form, such as 2026-Q3.

    Returns:
        The quarter, amount_usd and new_customers, or an empty list when no record exists.
        Available to finance. This tool does not change data."""
    return current_company().query("SELECT * FROM revenue WHERE quarter = ?", (quarter.strip().upper(),))


@tool
def issue_refund(invoice_id: str, amount_usd: int, reason: str) -> dict:
    """Record a refund against a paid invoice in the local ledger after human approval.

    Args:
        invoice_id: Invoice ID, such as INV-5002.
        amount_usd: Whole-dollar amount to refund; cannot exceed the invoice amount.
        reason: Short business reason citing the evidence (for example a ticket ID).

    Returns:
        A receipt and status. Repeating the identical refund reuses the receipt.
        This tool does not move real money."""
    company = current_company()
    rows = company.query("SELECT * FROM invoices WHERE id = ? COLLATE NOCASE", (invoice_id.strip(),))
    if not rows:
        raise ToolException("Unknown invoice. Look up the customer's invoices first.")
    invoice = rows[0]
    if invoice["status"] != "paid":
        raise ToolException(f"{invoice['id']} is {invoice['status']}; only paid invoices can be refunded.")
    if not 0 < amount_usd <= invoice["amount_usd"]:
        raise ToolException(f"Refund must be between 1 and {invoice['amount_usd']} USD.")
    key = hashlib.sha256(f"{invoice['id']}\0{amount_usd}\0{reason}".encode()).hexdigest()[:16]
    company.write("INSERT OR IGNORE INTO refund_ledger VALUES (?, ?, ?, ?)", (key, invoice["id"], amount_usd, reason))
    return {"status": "simulated_refund", "receipt": key, "invoice": invoice["id"], "amount_usd": amount_usd}
