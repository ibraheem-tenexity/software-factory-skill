"""SOF-108: seed the six default scope-genre recipes (sow rows, status='Template').

Idempotent: upserts by (status='Template', lower(title)) — safe to re-run; edits made on the SOW
admin screen are preserved unless --force overwrites bodies. Run with the service env:
    railway run --service factory-console .venv/bin/python scripts/seed_genre_recipes.py [--force]
"""
import sys

sys.path.insert(0, "src")

from software_factory.sow import SowStore  # noqa: E402

RECIPES = {
    "Quoting / RFQ": (
        "Quoting/RFQ tools turn a customer request into a priced, approvable quote. Typical "
        "screens: quote list (status: draft/sent/accepted/expired), quote builder with line items "
        "(product/service, qty, unit price, discounts, taxes), customer picker, PDF/email "
        "quote view the customer can accept, and quote-to-order conversion. Entities: quotes, "
        "line items, customers, price lists, follow-ups. Flows: create → price → internal "
        "approval (over threshold) → send → remind/follow up → accept/decline → convert. "
        "Common integrations: CRM for customers, ERP/price lists, e-signature, email."
    ),
    "Order entry": (
        "Order-entry tools capture confirmed orders and drive them to fulfillment. Typical "
        "screens: order list with status pipeline (received/confirmed/picking/shipped/invoiced), "
        "order form with line items and delivery details, customer account view with order "
        "history, and backorder/exception views. Entities: orders, line items, customers, "
        "shipments, inventory reservations. Flows: create/import → validate stock & credit → "
        "confirm → allocate → ship → invoice. Integrations: inventory/ERP, shipping carriers, "
        "invoicing/AR."
    ),
    "Pricing & approvals": (
        "Pricing & approval tools govern who may sell what at which price. Typical screens: "
        "price-list management (tiers, customer-specific pricing, effective dates), discount "
        "rules, approval queue (requests over threshold with context: margin, history), and an "
        "audit log. Entities: price lists, rules, approval requests, approvers, margins. Flows: "
        "request → auto-check against rules → route to approver chain → approve/reject with "
        "comment → apply. Integrations: quoting/CRM, ERP cost data, notifications (email/Slack)."
    ),
    "Inventory": (
        "Inventory tools track stock across locations in real time. Typical screens: stock "
        "overview by item/location with low-stock alerts, item detail (movements, lots/serials), "
        "receiving (against POs), transfers, cycle counts/adjustments with reason codes. "
        "Entities: items, locations/warehouses, stock movements, purchase orders, suppliers, "
        "reorder rules. Flows: receive → putaway → pick/consume → count → reorder at minimums. "
        "Integrations: barcode scanners, purchasing/ERP, order entry, label printing."
    ),
    "AP / AR": (
        "AP/AR tools manage money owed and owing. Typical screens: invoice list (AR) and bill "
        "list (AP) with aging buckets (current/30/60/90+), invoice/bill detail with line items "
        "and payment history, payment recording/matching, dunning/reminder queue, and cash-flow "
        "dashboard. Entities: invoices, bills, payments, credit notes, customers/vendors, terms. "
        "Flows: issue/receive → send/schedule → remind → collect/pay → reconcile. Integrations: "
        "accounting systems (QuickBooks/Xero), banks/payment processors, email."
    ),
    "Customer comms": (
        "Customer-communication tools keep every customer touchpoint in one place. Typical "
        "screens: unified inbox/timeline per customer (email, SMS, calls, notes), templated "
        "campaigns/sequences, notification rules (order status, quote follow-up), and response "
        "tracking. Entities: customers, conversations/messages, templates, sequences, events. "
        "Flows: event or agent triggers message → template merge → send → track opens/replies → "
        "escalate to human. Integrations: email providers, SMS (Twilio), CRM, the app's own "
        "order/quote events."
    ),
}


def main(force: bool = False) -> None:
    store = SowStore()
    existing = {
        (r.get("title") or "").strip().lower(): r
        for r in store.list_all() if r.get("status") == "Template"
    }
    for title, body in RECIPES.items():
        row = existing.get(title.lower())
        if row is None:
            store.create(title, status="Template", body=body)
            print(f"created recipe: {title}")
        elif force and (row.get("body") or "") != body:
            store.update(row["id"], {"body": body})
            print(f"updated recipe: {title}")
        else:
            print(f"kept recipe:    {title}")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
