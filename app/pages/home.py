import streamlit as st

from app import data


def render(conn) -> None:
    st.markdown('<div class="main-header">☕ GetU.Coffee POS</div>', unsafe_allow_html=True)
    st.markdown("### Last 30 days performance")
    st.markdown("---")

    metrics = conn.query(
        """
        SELECT
            SUM(IFF(CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP()), 1, 0)) AS ORDERS_30,
            SUM(IFF(CREATED_AT >= DATEADD('day', -60, CURRENT_TIMESTAMP())
                AND CREATED_AT < DATEADD('day', -30, CURRENT_TIMESTAMP()), 1, 0)) AS ORDERS_PREV_30,
            SUM(IFF(CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP()), TOTAL_AMOUNT, 0)) AS REVENUE_30,
            SUM(IFF(CREATED_AT >= DATEADD('day', -60, CURRENT_TIMESTAMP())
                AND CREATED_AT < DATEADD('day', -30, CURRENT_TIMESTAMP()), TOTAL_AMOUNT, 0)) AS REVENUE_PREV_30
        FROM ORDERS
        """,
        ttl=10,
    )

    monthly = conn.query(
        """
        SELECT DATE_TRUNC('month', CREATED_AT) AS MONTH, SUM(TOTAL_AMOUNT) AS REVENUE, COUNT(*) AS ORDERS
        FROM ORDERS
        GROUP BY 1
        ORDER BY 1 DESC
        """,
        ttl=60,
    )

    orders_30 = int(metrics["ORDERS_30"][0]) if not metrics.empty else 0
    orders_prev_30 = int(metrics["ORDERS_PREV_30"][0]) if not metrics.empty else 0
    revenue_30 = float(metrics["REVENUE_30"][0]) if not metrics.empty else 0.0
    revenue_prev_30 = float(metrics["REVENUE_PREV_30"][0]) if not metrics.empty else 0.0

    current_month_revenue = 0.0
    last_month_revenue = 0.0
    avg_month_revenue = 0.0

    if not monthly.empty:
        current_month = monthly.iloc[0]
        current_month_revenue = float(current_month["REVENUE"])
        if len(monthly) > 1:
            last_month_revenue = float(monthly.iloc[1]["REVENUE"])
        avg_month_revenue = float(monthly["REVENUE"].mean())

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        orders_delta = orders_30 - orders_prev_30
        orders_delta_pct = (orders_delta / orders_prev_30 * 100) if orders_prev_30 else 0
        delta_text = f"{orders_delta:+,} ({orders_delta_pct:+.1f}%) vs prior 30d"
        st.metric("Orders (last 30d)", f"{orders_30:,}", delta=delta_text)

    with col2:
        revenue_delta = revenue_30 - revenue_prev_30
        revenue_delta_pct = (revenue_delta / revenue_prev_30 * 100) if revenue_prev_30 else 0
        delta_text = f"{revenue_delta:+,.0f} ({revenue_delta_pct:+.1f}%) vs prior 30d"
        st.metric("Revenue (last 30d)", f"Rp {revenue_30:,.0f}", delta=delta_text)

    with col3:
        menus_count = conn.query("SELECT COUNT(*) as CNT FROM MENUS WHERE ACTIVE = TRUE", ttl=60)
        st.metric("Active Menu Items", menus_count["CNT"][0])

    with col4:
        ingredients_count = conn.query("SELECT COUNT(*) as CNT FROM INGREDIENTS", ttl=60)
        st.metric("Ingredients", ingredients_count["CNT"][0])

    st.markdown("---")
    st.markdown("### 📈 Month-to-date vs trends")

    col1, col2 = st.columns(2)
    with col1:
        delta_val = current_month_revenue - last_month_revenue
        delta_pct = (delta_val / last_month_revenue * 100) if last_month_revenue else 0
        delta_text = f"{delta_val:+,.0f} ({delta_pct:+.1f}%) vs last month"
        st.metric("Month-to-date revenue", f"Rp {current_month_revenue:,.0f}", delta=delta_text)
        st.caption(f"Avg monthly revenue: Rp {avg_month_revenue:,.0f}")

    with col2:
        orders_month = int(monthly.iloc[0]["ORDERS"]) if not monthly.empty else 0
        orders_last_month = int(monthly.iloc[1]["ORDERS"]) if len(monthly) > 1 else 0
        orders_delta = orders_month - orders_last_month
        orders_delta_pct = (orders_delta / orders_last_month * 100) if orders_last_month else 0
        delta_text = f"{orders_delta:+,} ({orders_delta_pct:+.1f}%) vs last month"
        st.metric("Month-to-date orders", f"{orders_month:,}", delta=delta_text)
        avg_orders = int(monthly["ORDERS"].mean()) if not monthly.empty else 0
        st.caption(f"Avg monthly orders: {avg_orders:,}")

    st.markdown("---")
    st.markdown("### 📊 Recent Activity (last 20)")

    recent_orders = data.get_orders(conn, 20)
    if not recent_orders.empty:
        status_map = {
            "completed": "🟢 completed",
            "in_progress": "🟡 in progress",
            "created": "⚪ created",
            "closed": "⚫ closed",
        }
        recent_orders = recent_orders.copy()
        recent_orders["STATUS"] = recent_orders["STATUS"].apply(lambda s: status_map.get(s, s))
        recent_orders["PAID"] = recent_orders["IS_PAID"].apply(lambda p: "✅ paid" if p else "❌ unpaid")
        st.dataframe(
            recent_orders[["ORDER_ID", "TOTAL_AMOUNT", "STATUS", "PAID", "CREATED_AT"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No orders yet. Start by placing an order!")

    st.markdown("---")
    st.markdown("### 🏆 Top 10 Best Sellers (last 30d)")

    top_items = conn.query(
        """
        SELECT m.NAME, SUM(oi.QTY) as TOTAL_SOLD, SUM(oi.QTY * oi.PRICE) as REVENUE
        FROM ORDER_ITEMS oi
        JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        WHERE o.CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
        GROUP BY m.NAME
        ORDER BY TOTAL_SOLD DESC
        LIMIT 10
        """,
        ttl=60,
    )
    if not top_items.empty:
        st.bar_chart(top_items.set_index("NAME")["TOTAL_SOLD"])
        st.dataframe(top_items, use_container_width=True, hide_index=True)
    else:
        st.info("No sales data yet for the last 30 days.")

    st.markdown("---")
    st.markdown("### 💰 Revenue by Category (last 30d)")

    category_revenue = conn.query(
        """
        SELECT m.CATEGORY,
               SUM(oi.QTY) as ITEMS_SOLD,
               SUM(oi.QTY * oi.PRICE) as REVENUE
        FROM ORDER_ITEMS oi
        JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        WHERE o.CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
        GROUP BY m.CATEGORY
        ORDER BY REVENUE DESC
        """,
        ttl=60,
    )

    if not category_revenue.empty:
        st.bar_chart(category_revenue.set_index("CATEGORY")["REVENUE"])
        st.dataframe(category_revenue, use_container_width=True, hide_index=True)
    else:
        st.info("No revenue data yet for the last 30 days.")
