import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, date


def _compute_range(preset: str, custom):
    """Return start, end datetimes (end exclusive)."""
    now = datetime.utcnow()
    if preset == "Last 30 days":
        start = now - timedelta(days=30)
        end = now
    elif preset == "Last 90 days":
        start = now - timedelta(days=90)
        end = now
    elif preset == "Year to date":
        start = datetime(now.year, 1, 1)
        end = now
    elif preset == "Last 1 year":
        start = now - timedelta(days=365)
        end = now
    elif preset == "Last 3 years":
        start = now - timedelta(days=365 * 3)
        end = now
    elif preset == "Last 5 years":
        start = now - timedelta(days=365 * 5)
        end = now
    elif preset == "Last 8 years":
        start = now - timedelta(days=365 * 8)
        end = now
    elif preset == "Custom range" and custom and len(custom) == 2:
        start = datetime.combine(custom[0], datetime.min.time())
        end = datetime.combine(custom[1], datetime.min.time()) + timedelta(days=1)
    else:
        start = now - timedelta(days=30)
        end = now
    return start, end


def _date_filter(alias: str, start: datetime, end: datetime) -> str:
    start_str = start.isoformat()
    end_str = end.isoformat()
    return f"{alias}.CREATED_AT >= '{start_str}' AND {alias}.CREATED_AT < '{end_str}'"


def _summary_metrics(conn, where_clause: str, prev_where: str):
    current = conn.query(
        f"""
        WITH stats AS (
            SELECT
                COUNT(*) AS orders,
                SUM(o.TOTAL_AMOUNT) AS revenue
            FROM ORDERS o
            WHERE {where_clause}
        ),
        items AS (
            SELECT SUM(oi.QTY) AS items
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
            WHERE {where_clause}
        ),
        costs AS (
            SELECT SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM) AS cogs
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
            JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
            JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
            WHERE {where_clause}
        )
        SELECT
            stats.orders,
            stats.revenue,
            items.items,
            costs.cogs
        FROM stats, items, costs
        """,
        ttl=30,
    )

    previous = conn.query(
        f"""
        WITH stats AS (
            SELECT
                COUNT(*) AS orders,
                SUM(o.TOTAL_AMOUNT) AS revenue
            FROM ORDERS o
            WHERE {prev_where}
        ),
        items AS (
            SELECT SUM(oi.QTY) AS items
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
            WHERE {prev_where}
        ),
        costs AS (
            SELECT SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM) AS cogs
            FROM ORDER_ITEMS oi
            JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
            JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
            JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
            WHERE {prev_where}
        )
        SELECT
            stats.orders,
            stats.revenue,
            items.items,
            costs.cogs
        FROM stats, items, costs
        """,
        ttl=30,
    )

    def safe_get(df, col):
        if df.empty:
            return 0.0
        val = df[col][0]
        if pd.isna(val):
            return 0.0
        return float(val)

    def safe_int(df, col):
        if df.empty:
            return 0
        val = df[col][0]
        if pd.isna(val):
            return 0
        return int(val)

    orders = safe_int(current, "ORDERS")
    revenue = safe_get(current, "REVENUE")
    items = safe_get(current, "ITEMS")
    cogs = safe_get(current, "COGS")

    prev_orders = safe_int(previous, "ORDERS")
    prev_revenue = safe_get(previous, "REVENUE")
    prev_items = safe_get(previous, "ITEMS")
    prev_cogs = safe_get(previous, "COGS")

    aov = revenue / orders if orders else 0
    items_per_order = items / orders if orders else 0
    gross_profit = revenue - cogs
    margin_pct = (gross_profit / revenue * 100) if revenue else 0
    net_profit = gross_profit  # No other expenses tracked yet

    prev_aov = prev_revenue / prev_orders if prev_orders else 0
    prev_items_per_order = prev_items / prev_orders if prev_orders else 0
    prev_gross_profit = prev_revenue - prev_cogs
    prev_margin_pct = (prev_gross_profit / prev_revenue * 100) if prev_revenue else 0
    prev_net_profit = prev_gross_profit

    return {
        "orders": orders,
        "revenue": revenue,
        "items": items,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "margin_pct": margin_pct,
        "net_profit": net_profit,
        "aov": aov,
        "items_per_order": items_per_order,
        "prev": {
            "orders": prev_orders,
            "revenue": prev_revenue,
            "items": prev_items,
            "cogs": prev_cogs,
            "gross_profit": prev_gross_profit,
            "margin_pct": prev_margin_pct,
            "net_profit": prev_net_profit,
            "aov": prev_aov,
            "items_per_order": prev_items_per_order,
        },
    }


def _delta_text(current: float, previous: float) -> str:
    if previous == 0:
        return f"{current:+.0f}"
    delta = current - previous
    pct = (delta / previous) * 100 if previous else 0
    return f"{delta:+,.0f} ({pct:+.1f}%)"


def _trend_chart(trend_df: pd.DataFrame):
    if trend_df.empty:
        st.info("No trend data for this period.")
        return
    trend_df["DATE"] = pd.to_datetime(trend_df["DATE"])
    base = alt.Chart(trend_df).encode(x="DATE:T")
    revenue_line = base.mark_line(color="#6F4E37").encode(
        y=alt.Y("REVENUE:Q", title="Revenue"),
        tooltip=["DATE:T", alt.Tooltip("REVENUE:Q", format=",.0f")],
    )
    orders_line = base.mark_line(color="#A05D56", strokeDash=[4, 4]).encode(
        y=alt.Y("ORDERS:Q", title="Orders"),
        tooltip=["DATE:T", alt.Tooltip("ORDERS:Q", format=",")],
    )
    st.altair_chart((revenue_line + orders_line).resolve_scale(y="independent"), use_container_width=True)


def render(conn) -> None:
    st.title("📊 Analytics Dashboard")
    st.markdown("### Actionable insights across sales and operations")

    presets = [
        "Last 30 days",
        "Last 90 days",
        "Year to date",
        "Last 1 year",
        "Last 3 years",
        "Last 5 years",
        "Last 8 years",
        "Custom range",
    ]
    col_range, col_note = st.columns([3, 2])
    with col_range:
        preset = st.selectbox("Time range", presets, index=0)
        custom_dates = ()
        if preset == "Custom range":
            custom_dates = st.date_input("Select custom date range", [])
    with col_note:
        st.markdown(
            "Use the time range to compare trends. Deltas are vs the prior period of the same length."
        )

    start, end = _compute_range(preset, custom_dates)
    window_days = max((end - start).days, 1)
    prev_start = start - timedelta(days=window_days)
    prev_end = start

    where_orders = _date_filter("o", start, end)
    where_orders_prev = _date_filter("o", prev_start, prev_end)

    metrics = _summary_metrics(conn, where_orders, where_orders_prev)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Revenue",
            f"Rp {metrics['revenue']:,.0f}",
            delta=_delta_text(metrics["revenue"], metrics["prev"]["revenue"]),
        )
        st.caption("Top-line for selected period.")
    with col2:
        st.metric(
            "Orders",
            f"{metrics['orders']:,}",
            delta=_delta_text(metrics["orders"], metrics["prev"]["orders"]),
        )
        st.caption("Ticket volume; big swings flag demand shifts.")
    with col3:
        st.metric(
            "Avg Order Value",
            f"Rp {metrics['aov']:,.0f}",
            delta=_delta_text(metrics["aov"], metrics["prev"]["aov"]),
        )
        st.caption("Pricing/mix indicator.")
    with col4:
        st.metric(
            "Items / Order",
            f"{metrics['items_per_order']:.2f}",
            delta=_delta_text(metrics["items_per_order"], metrics["prev"]["items_per_order"]),
        )
        st.caption("Bundling strength; watch upsell/cross-sell.")

    col5, col6 = st.columns(2)
    with col5:
        st.metric(
            "Cost (COGS)",
            f"Rp {metrics['cogs']:,.0f}",
            delta=_delta_text(metrics["cogs"], metrics["prev"]["cogs"]),
        )
        st.caption("Ingredient cost for sold items.")
    with col6:
        st.metric(
            "Gross Profit",
            f"Rp {metrics['gross_profit']:,.0f}",
            delta=_delta_text(metrics["gross_profit"], metrics["prev"]["gross_profit"]),
        )
        st.caption("Revenue minus ingredient costs.")
    col7, col8 = st.columns(2)
    with col7:
        st.metric(
            "Gross Margin %",
            f"{metrics['margin_pct']:.1f}%",
            delta=_delta_text(metrics["margin_pct"], metrics["prev"]["margin_pct"]),
        )
        st.caption("Health of pricing/cost structure.")
    with col8:
        st.metric(
            "Net Profit",
            f"Rp {metrics['net_profit']:,.0f}",
            delta=_delta_text(metrics["net_profit"], metrics["prev"]["net_profit"]),
        )
        st.caption("Currently same as gross profit (no overhead tracked).")

    st.markdown("---")
    st.markdown("### 📈 Revenue & Orders Trend")
    trend = conn.query(
        f"""
        SELECT DATE_TRUNC('day', o.CREATED_AT) AS DATE,
               SUM(o.TOTAL_AMOUNT) AS REVENUE,
               COUNT(*) AS ORDERS
        FROM ORDERS o
        WHERE {where_orders}
        GROUP BY 1
        ORDER BY 1
        """,
        ttl=30,
    )
    _trend_chart(trend)
    st.caption("Is momentum up or down? Look for consistent slope; spikes hint promos/events.")

    st.markdown("---")
    st.markdown("### 🍰 Category Mix")
    category_mix = conn.query(
        f"""
        SELECT m.CATEGORY,
               SUM(oi.QTY * oi.PRICE) AS REVENUE,
               SUM(oi.QTY) AS ITEMS
        FROM ORDER_ITEMS oi
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
        WHERE {where_orders}
        GROUP BY m.CATEGORY
        ORDER BY REVENUE DESC
        """,
        ttl=30,
    )
    if not category_mix.empty:
        st.bar_chart(category_mix.set_index("CATEGORY")["REVENUE"])
        st.dataframe(category_mix, use_container_width=True, hide_index=True)
        st.caption("Watch which categories gain share; rebalance menu and promos accordingly.")
    else:
        st.info("No category data for this period.")

    st.markdown("---")
    st.markdown("### 🏆 Top 10 Items")
    top_items = conn.query(
        f"""
        SELECT m.NAME,
               SUM(oi.QTY) AS TOTAL_SOLD,
               SUM(oi.QTY * oi.PRICE) AS REVENUE
        FROM ORDER_ITEMS oi
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
        WHERE {where_orders}
        GROUP BY m.NAME
        ORDER BY REVENUE DESC
        LIMIT 10
        """,
        ttl=30,
    )
    if not top_items.empty:
        st.bar_chart(top_items.set_index("NAME")["REVENUE"])
        st.dataframe(top_items, use_container_width=True, hide_index=True)
        st.caption("Double down on winners; reprice or refresh laggards.")
    else:
        st.info("No item data for this period.")

    st.markdown("---")
    st.markdown("### ⏰ Peak Hours Heatmap")
    heat = conn.query(
        f"""
        SELECT
            DAYNAME(o.CREATED_AT) AS DOW,
            DATE_PART('hour', o.CREATED_AT) AS HOUR,
            SUM(oi.QTY * oi.PRICE) AS REVENUE,
            COUNT(DISTINCT o.ORDER_ID) AS ORDERS
        FROM ORDERS o
        JOIN ORDER_ITEMS oi ON o.ORDER_ID = oi.ORDER_ID
        WHERE {where_orders}
        GROUP BY 1,2
        """,
        ttl=30,
    )
    if not heat.empty:
        heat["HOUR"] = heat["HOUR"].astype(int)
        heat_chart = (
            alt.Chart(heat)
            .mark_rect()
            .encode(
                x=alt.X("HOUR:O", title="Hour of day"),
                y=alt.Y("DOW:O", title="Day of week"),
                color=alt.Color("REVENUE:Q", title="Revenue", scale=alt.Scale(scheme="brownbluegreen")),
                tooltip=[
                    alt.Tooltip("DOW:O", title="Day"),
                    alt.Tooltip("HOUR:O", title="Hour"),
                    alt.Tooltip("REVENUE:Q", title="Revenue", format=",.0f"),
                    alt.Tooltip("ORDERS:Q", title="Orders", format=","),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(heat_chart, use_container_width=True)
        st.caption("Staff for dark cells (peaks); target promos in slow hours.")
    else:
        st.info("No hourly data for this period.")

    st.markdown("---")
    st.markdown("### 📝 Quick takeaways")
    bullets = []
    if metrics["orders"] > metrics["prev"]["orders"]:
        bullets.append("Demand up vs prior window; ensure staffing covers peak hours.")
    else:
        bullets.append("Demand down vs prior window; check pricing/promos and category mix.")

    if metrics["aov"] > metrics["prev"]["aov"]:
        bullets.append("AOV improving; current pricing/mix is working.")
    else:
        bullets.append("AOV down; consider upsells or bundle offers.")

    if metrics["items_per_order"] < metrics["prev"]["items_per_order"]:
        bullets.append("Fewer items per ticket; add small add-on prompts.")
    else:
        bullets.append("Basket size growing; keep promoting combos.")

    st.markdown("\n".join([f"- {b}" for b in bullets]))
