"""Company operations and their application-owned binding."""
from .binding import bind_company_tools
from .customers import customer_lookup
from .finance import invoice_lookup, issue_refund, revenue_summary
from .quotes import send_quote
from .tickets import ticket_lookup

COMPANY_TOOLS = (customer_lookup, ticket_lookup, invoice_lookup, revenue_summary, send_quote, issue_refund)

__all__ = ["COMPANY_TOOLS", "bind_company_tools"]
