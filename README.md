# GetU.Coffee POS (Snowflake Streamlit)

Modular Streamlit app for GetU.Coffee: customer ordering, order management, menu management, inventory with live stock deductions, analytics (revenue, COGS, margin), and groundwork for AI insights.

## Features
- Customer order flow with category filters and confirmation dialog.
- Order management with status/paid updates.
- Menu management (add/edit, soft delete).
- Inventory: live stock + cost per UOM, ledgered adjustments, consumption view, inline editing.
- Automatic ingredient deduction per order via `MENU_RECIPES` + `INVENTORY_LEDGER`.
- Analytics dashboard with time presets, deltas, category mix, top items, peak-hour heatmap, COGS/gross/net profit.
- AI Ops Assistant (chat): quick prompts and questions about sales, profit/margin, top items, categories, busiest hours, low stock, and low-margin items. Handles small talk with friendly replies.

## Prerequisites
- Python 3.9+
- Snowflake account with an existing connection configured in Streamlit (see `.streamlit/secrets.toml`) named `snowflake`.
- Tables present (from your schema):
  - `MENUS`, `MENU_RECIPES`, `INGREDIENTS` (with `COST_PER_UOM`), `ORDERS`, `ORDER_ITEMS`, `INVENTORY_LEDGER`, `AUDIT_LOG`.

## Setup
```bash
# 1) Create and activate env
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt  # or pip install streamlit pandas altair snowflake-connector-python
```

Snowflake connection: create `.streamlit/secrets.toml`:
```toml
[connections.snowflake]
account = "<account>"
user = "<user>"
password = "<password>"
warehouse = "<warehouse>"
database = "GETU_POS"
schema = "PUBLIC"
role = "<role>"
```

## Run locally
```bash
streamlit run streamlit_app.py
```

## Core tables and expectations
- `INGREDIENTS`: `INGREDIENT_ID`, `NAME`, `UOM`, `STOCK_QTY`, `REORDER_THRESHOLD`, `COST_PER_UOM`.
- `MENU_RECIPES`: maps `MENU_ID` → `INGREDIENT_ID` with `QTY_REQUIRED` (drives stock consumption and COGS).
- `ORDERS` / `ORDER_ITEMS`: sales records; analytics and consumption use `CREATED_AT` timestamps.
- `INVENTORY_LEDGER`: captures stock and cost updates, order consumption, manual adjustments.

## Notes
- Ingredient stock is decremented when an order is confirmed; ledger entries are created.
- Gross/net profit currently equal revenue minus ingredient costs (no overhead modeled).
- Inline inventory edits and stock adjustments write to the ledger; use cautiously in production.
- AI chat uses predefined, safe SQL templates (no arbitrary SQL). Quick prompts available on the chat page.
