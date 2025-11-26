import streamlit as st


@st.cache_resource
def get_connection():
    """Create or return cached Snowflake connection."""
    return st.connection("snowflake")


def test_connection(conn) -> bool:
    """Validate the Snowflake connection."""
    try:
        conn.query("SELECT CURRENT_TIMESTAMP() as NOW", ttl=0)
        return True
    except Exception as exc:  # pragma: no cover - surface error to UI
        st.error(f"❌ Database connection failed: {exc}")
        return False


def execute_query(conn, query: str, show_success: bool = False) -> bool:
    """Execute a non-query SQL statement."""
    try:
        conn.session().sql(query).collect()
        if show_success:
            st.success("✅ Operation successful!")
        return True
    except Exception as exc:  # pragma: no cover - surface error to UI
        st.error(f"Error: {exc}")
        return False


def get_menus(conn, active_only: bool = True):
    """Get menu items."""
    query = "SELECT MENU_ID, NAME, PRICE, CATEGORY, ACTIVE FROM MENUS"
    if active_only:
        query += " WHERE ACTIVE = TRUE"
    query += " ORDER BY CATEGORY, NAME"
    return conn.query(query, ttl=60)


def get_ingredients(conn):
    """Get ingredients."""
    return conn.query(
        """
        SELECT INGREDIENT_ID, NAME, UOM, STOCK_QTY, REORDER_THRESHOLD, COST_PER_UOM
        FROM INGREDIENTS
        ORDER BY NAME
        """,
        ttl=60,
    )


def get_orders(conn, limit: int = 50):
    """Get recent orders."""
    return conn.query(
        f"""
        SELECT ORDER_ID, TOTAL_AMOUNT, STATUS, IS_PAID, CREATED_AT
        FROM ORDERS
        ORDER BY CREATED_AT DESC
        LIMIT {limit}
        """,
        ttl=10,
    )


def get_order_items(conn, order_id: int):
    """Get items for an order."""
    return conn.query(
        f"""
        SELECT oi.ORDER_ITEM_ID, m.NAME, oi.QTY, oi.PRICE, (oi.QTY * oi.PRICE) as SUBTOTAL
        FROM ORDER_ITEMS oi
        JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
        WHERE oi.ORDER_ID = {order_id}
        """,
        ttl=10,
    )


def get_menu_recipes(conn, menu_ids):
    """Fetch recipe rows for given menu IDs."""
    if not menu_ids:
        return None
    id_list = ",".join(map(str, set(menu_ids)))
    return conn.query(
        f"""
        SELECT MENU_ID, INGREDIENT_ID, QTY_REQUIRED
        FROM MENU_RECIPES
        WHERE MENU_ID IN ({id_list})
        """,
        ttl=0,
    )


def get_ingredient_stocks(conn, ingredient_ids):
    """Fetch stock for a list of ingredient IDs."""
    if not ingredient_ids:
        return None
    id_list = ",".join(map(str, set(ingredient_ids)))
    return conn.query(
        f"""
        SELECT INGREDIENT_ID, STOCK_QTY
        FROM INGREDIENTS
        WHERE INGREDIENT_ID IN ({id_list})
        """,
        ttl=0,
    )


def update_ingredient_stock(conn, ingredient_id: int, new_qty: float, created_by: str = "admin"):
    """Set an ingredient's stock and log the change."""
    current = conn.query(
        f"SELECT STOCK_QTY FROM INGREDIENTS WHERE INGREDIENT_ID = {ingredient_id}",
        ttl=0,
    )
    if current.empty:
        raise ValueError("Ingredient not found")
    current_qty = float(current["STOCK_QTY"][0] or 0)
    delta = new_qty - current_qty

    conn.session().sql(
        f"""
        UPDATE INGREDIENTS
        SET STOCK_QTY = {new_qty}, MODIFIED_AT = CURRENT_TIMESTAMP()
        WHERE INGREDIENT_ID = {ingredient_id}
        """
    ).collect()

    conn.session().sql(
        f"""
        INSERT INTO INVENTORY_LEDGER (INGREDIENT_ID, DELTA_QTY, SOURCE, REF_ORDER_ID, CREATED_BY, CREATED_AT)
        VALUES ({ingredient_id}, {delta}, 'manual_adjust', NULL, '{created_by}', CURRENT_TIMESTAMP())
        """
    ).collect()

    return {"delta": delta, "old_qty": current_qty, "new_qty": new_qty}


def update_ingredient_cost(conn, ingredient_id: int, new_cost: float, created_by: str = "admin"):
    """Update ingredient cost per UOM."""
    conn.session().sql(
        f"""
        UPDATE INGREDIENTS
        SET COST_PER_UOM = {new_cost}, MODIFIED_AT = CURRENT_TIMESTAMP()
        WHERE INGREDIENT_ID = {ingredient_id}
        """
    ).collect()
    conn.session().sql(
        f"""
        INSERT INTO INVENTORY_LEDGER (INGREDIENT_ID, DELTA_QTY, SOURCE, REF_ORDER_ID, CREATED_BY, CREATED_AT)
        VALUES ({ingredient_id}, 0, 'cost_update', NULL, '{created_by}', CURRENT_TIMESTAMP())
        """
    ).collect()


def consume_ingredients_for_order(conn, order_id: int, items: list, created_by: str = "customer"):
    """
    Deduct ingredient stock based on order items and recipes.

    items: list of dicts with keys menu_id, qty
    """
    menu_ids = [item["menu_id"] for item in items]
    recipes = get_menu_recipes(conn, menu_ids)
    if recipes is None or recipes.empty:
        return []

    usage = {}
    qty_lookup = {item["menu_id"]: item["qty"] for item in items}
    for _, row in recipes.iterrows():
        menu_id = int(row["MENU_ID"])
        ingredient_id = int(row["INGREDIENT_ID"])
        qty_required = float(row["QTY_REQUIRED"])
        ordered_qty = qty_lookup.get(menu_id, 0)
        usage[ingredient_id] = usage.get(ingredient_id, 0) + qty_required * ordered_qty

    stocks = get_ingredient_stocks(conn, list(usage.keys()))
    warnings = []

    for _, stock_row in stocks.iterrows():
        ing_id = int(stock_row["INGREDIENT_ID"])
        stock_qty = float(stock_row["STOCK_QTY"] or 0)
        consume_qty = usage.get(ing_id, 0)
        new_qty = stock_qty - consume_qty

        conn.session().sql(
            f"""
            UPDATE INGREDIENTS
            SET STOCK_QTY = {new_qty}, MODIFIED_AT = CURRENT_TIMESTAMP()
            WHERE INGREDIENT_ID = {ing_id}
            """
        ).collect()

        conn.session().sql(
            f"""
            INSERT INTO INVENTORY_LEDGER (INGREDIENT_ID, DELTA_QTY, SOURCE, REF_ORDER_ID, CREATED_BY, CREATED_AT)
            VALUES ({ing_id}, {-consume_qty}, 'order', {order_id}, '{created_by}', CURRENT_TIMESTAMP())
            """
        ).collect()

        if new_qty < 0:
            warnings.append(f"Ingredient {ing_id} stock went negative ({new_qty}).")

    return warnings


def get_ingredient_usage_last_30(conn):
    """Aggregate ingredient consumption over the last 30 days."""
    return conn.query(
        """
        SELECT
            mr.INGREDIENT_ID,
            ing.NAME,
            ing.UOM,
            SUM(oi.QTY * mr.QTY_REQUIRED) AS USED_QTY
        FROM ORDER_ITEMS oi
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
        JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
        WHERE o.CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
        GROUP BY mr.INGREDIENT_ID, ing.NAME, ing.UOM
        ORDER BY USED_QTY DESC
        """,
        ttl=30,
    )
