"""Sachin Tech dummy company data and role-bound tools. The model never gets a database path or SQL."""
import sqlite3
from pathlib import Path

from langchain_core.tools import ToolException

from tools import COMPANY_TOOLS, bind_company_tools

ROOT = Path(__file__).resolve().parent

# Application-owned access rules. The model can never choose its own role.
ACCESS = {
    "sales": {"customer_lookup", "send_quote"},
    "support": {"customer_lookup", "ticket_lookup"},
    "finance": {"customer_lookup", "invoice_lookup", "revenue_summary", "issue_refund"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers
    (id TEXT PRIMARY KEY, name TEXT, industry TEXT, need TEXT, plan TEXT, devices INTEGER, contact TEXT);
CREATE TABLE IF NOT EXISTS tickets
    (id TEXT PRIMARY KEY, customer TEXT, symptom TEXT, severity TEXT, status TEXT, owner TEXT);
CREATE TABLE IF NOT EXISTS invoices
    (id TEXT PRIMARY KEY, customer TEXT, month TEXT, amount_usd INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS revenue
    (quarter TEXT PRIMARY KEY, amount_usd INTEGER, new_customers INTEGER);
CREATE TABLE IF NOT EXISTS quote_outbox
    (id TEXT PRIMARY KEY, customer TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS refund_ledger
    (id TEXT PRIMARY KEY, invoice TEXT, amount_usd INTEGER, reason TEXT);
"""

CUSTOMERS = [
    ("C-201", "Acme Logistics", "Logistics", "Real-time GPS tracking for 400 delivery trucks across 3 depots",
     "Growth", 400, "fleet-ops@acme-logistics.example"),
    ("C-202", "Beacon Foods", "Food distribution", "Cold-chain temperature alerts for 120 refrigerated trailers",
     "Growth", 120, "it@beaconfoods.example"),
    ("C-203", "Cobalt Mining", "Mining", "Offline-tolerant edge gateways for 60 vehicles at remote sites",
     "Enterprise", 60, "tech@cobaltmining.example"),
]
TICKETS = [
    ("T-1001", "Beacon Foods", "Temperature alerts arrive 15 minutes late after gateway firmware 4.2 upgrade",
     "high", "open", "Device Platform"),
    ("T-1002", "Cobalt Mining", "Gateway does not resync buffered data after more than 6 hours offline",
     "medium", "open", "Edge Team"),
    ("T-1003", "Acme Logistics", "Dashboard CSV export times out above 10,000 rows", "low", "investigating", "Web App"),
]
INVOICES = [
    ("INV-5001", "Acme Logistics", "2026-09", 4800, "paid"),
    ("INV-5002", "Beacon Foods", "2026-09", 1440, "paid"),
    ("INV-5003", "Beacon Foods", "2026-10", 1440, "overdue"),
    ("INV-5004", "Cobalt Mining", "2026-10", 9000, "paid"),
]
REVENUE = [("2026-Q2", 1120000, 7), ("2026-Q3", 1265000, 9)]


class Company:
    """Company data service. Role is bound by application code, never a model argument."""

    def __init__(self, database):
        self.access = {role: set(names) for role, names in ACCESS.items()}
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as db:
            db.executescript(SCHEMA)
            db.executemany("INSERT OR IGNORE INTO customers VALUES (?, ?, ?, ?, ?, ?, ?)", CUSTOMERS)
            db.executemany("INSERT OR IGNORE INTO tickets VALUES (?, ?, ?, ?, ?, ?)", TICKETS)
            db.executemany("INSERT OR IGNORE INTO invoices VALUES (?, ?, ?, ?, ?)", INVOICES)
            db.executemany("INSERT OR IGNORE INTO revenue VALUES (?, ?, ?)", REVENUE)

    def query(self, sql, parameters=()):
        """Run a parameterized read-only query and return rows as dictionaries."""
        with sqlite3.connect(f"{self.database.as_uri()}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql, parameters).fetchall()]

    def write(self, sql, parameters=()):
        """Run one parameterized write used by approval-gated tools."""
        with sqlite3.connect(self.database) as db:
            db.execute(sql, parameters)

    def tools_for(self, role):
        """Return only the tools this application-selected role may see."""
        return [tool for name, tool in self.all_tools_for(role).items() if name in self.access[role]]

    def all_tools_for(self, role):
        """Bind every company tool to this role; unauthorized calls return an access denial."""
        if role not in self.access:
            raise ValueError(f"Unknown employee role: {role}")

        def require(name):
            if name not in self.access[role]:
                raise ToolException(f"Access denied: {role} cannot use {name}.")

        return {tool.name: tool for tool in bind_company_tools(COMPANY_TOOLS, self, require)}

    def quote_outbox(self):
        return self.query("SELECT * FROM quote_outbox ORDER BY rowid")

    def refund_ledger(self):
        return self.query("SELECT * FROM refund_ledger ORDER BY rowid")
