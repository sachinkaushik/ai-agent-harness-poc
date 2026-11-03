---
name: write-quote
description: Prepare or revise a SachinFleet customer quote using customer facts, plan pricing, assumptions and next steps.
---

# Prepare a customer quote

1. Establish the customer's need and device count from their customer record (customer_lookup) when access is available; otherwise use the brief supplied by the employee. If neither is available, ask before drafting.
2. Draft five sections: Customer need, Recommended plan, Estimated price, Assumptions, Next steps.
3. Price from the plan list in company/AGENTS.md: devices x per-device monthly price. Enterprise pricing is never estimated; mark it "requires finance sign-off".
4. Cite record IDs for company facts. Mark anything not in a record (discounts, timelines, custom features) as requiring confirmation. Standard onboarding is 4 weeks.
5. Present the draft in chat. When the employee asks to save it and a writable workspace is available, write /work/quote.md.
6. Sending is a separate step, only on the employee's explicit request, through send_quote, which pauses for human approval.
