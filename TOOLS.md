# Sachin Tech Assist tools

## Company tools

| Tool | Purpose | Input | Access | Approval | Source |
|---|---|---|---|---|---|
| `customer_lookup` | Read a customer's need, plan, devices and contact | Customer name | Sales, support, finance | No | `tools/customers.py` |
| `ticket_lookup` | Read a customer's support tickets | Customer name | Support | No | `tools/tickets.py` |
| `invoice_lookup` | Read a customer's invoices | Customer name | Finance | No | `tools/finance.py` |
| `revenue_summary` | Read a quarter's revenue | Quarter, such as `2026-Q3` | Finance | No | `tools/finance.py` |
| `send_quote` | Record a quote in the local outbox | Customer name, body | Sales | **Yes** | `tools/quotes.py` |
| `issue_refund` | Record a refund on a paid invoice in the local ledger | Invoice ID, amount, reason | Finance | **Yes** | `tools/finance.py` |

`tools/binding.py` binds each tool to the company data and the employee's role. The model never passes a role or a
database path. Calling a tool outside your role returns `Access denied`.

## Harness tools (from Deep Agents)

- **Files:** `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` read skills and company docs, and save drafts under `/work/`. `/company/**` and `/skills/**` are write-protected.
- **Planning:** `write_todos` (from `TodoListMiddleware`).
- **Delegation:** `task` sends work to the `quote-reviewer` subagent, which can only use `customer_lookup`.

## Dummy data

| Customers | Tickets | Invoices | Revenue |
|---|---|---|---|
| C-201 Acme Logistics (Growth, 400 devices) | T-1001 Beacon: alerts delayed after firmware 4.2 (high) | INV-5001 Acme 2026-09 $4,800 paid | 2026-Q2 $1,120,000 |
| C-202 Beacon Foods (Growth, 120 devices) | T-1002 Cobalt: gateway resync after 6h offline (medium) | INV-5002 Beacon 2026-09 $1,440 paid | 2026-Q3 $1,265,000 |
| C-203 Cobalt Mining (Enterprise, 60 devices) | T-1003 Acme: CSV export timeout (low) | INV-5003 Beacon 2026-10 $1,440 overdue | |
| | | INV-5004 Cobalt 2026-10 $9,000 paid | |
