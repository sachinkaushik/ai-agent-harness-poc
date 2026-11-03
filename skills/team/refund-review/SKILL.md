---
name: refund-review
description: Review whether a customer invoice qualifies for a refund or credit and prepare a refund request for approval.
---

# Review a refund request

1. Look up the customer's invoices with invoice_lookup. Cite the invoice ID, amount and status.
2. Only paid invoices can be refunded. Open or overdue invoices need a credit note or collection follow-up instead; say so.
3. Check the related support history if the employee supplies it; otherwise list it as an open question.
4. Refunds above $5,000 need a finance manager's written approval (company/AGENTS.md). State this before requesting the refund.
5. Present a recommendation: Invoice, Amount, Reason, Policy check, Recommendation.
6. Call issue_refund only when the employee explicitly asks. It pauses for human approval and records the refund in the local ledger.
