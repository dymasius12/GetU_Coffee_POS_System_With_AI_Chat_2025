import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
import time
import random


def _format_currency(val):
    return f"Rp {val:,.0f}"


def _sales_summary(conn, start, end):
    start_str = start.isoformat()
    end_str = end.isoformat()
    q = """
    WITH sales AS (
        SELECT COUNT(*) AS orders, SUM(o.TOTAL_AMOUNT) AS revenue
        FROM ORDERS o
        WHERE o.CREATED_AT >= '{start}' AND o.CREATED_AT < '{end}'
    ),
    items AS (
        SELECT SUM(oi.QTY) AS items
        FROM ORDER_ITEMS oi
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        WHERE o.CREATED_AT >= '{start}' AND o.CREATED_AT < '{end}'
    ),
    cogs AS (
        SELECT SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM) AS cogs
        FROM ORDER_ITEMS oi
        JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
        JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
        JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
        WHERE o.CREATED_AT >= '{start}' AND o.CREATED_AT < '{end}'
    )
    SELECT sales.orders, sales.revenue, items.items, cogs.cogs
    FROM sales, items, cogs
    """.format(start=start_str, end=end_str)
    res = conn.query(q, ttl=0)
    if res.empty:
        return {
            "orders": 0,
            "revenue": 0.0,
            "cogs": 0.0,
            "gross_profit": 0.0,
            "margin_pct": 0.0,
            "aov": 0.0,
            "items_per_order": 0.0,
        }
    row = res.iloc[0]
    orders = int(row["ORDERS"] or 0)
    revenue = float(row["REVENUE"] or 0) if row["REVENUE"] is not None else 0
    items = float(row["ITEMS"] or 0) if row["ITEMS"] is not None else 0
    cogs = float(row["COGS"] or 0) if row["COGS"] is not None else 0
    gp = revenue - cogs
    margin = gp / revenue * 100 if revenue > 0 else 0
    aov = revenue / orders if orders > 0 else 0
    ipo = items / orders if orders > 0 else 0
    return {
        "orders": orders,
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gp,
        "margin_pct": margin,
        "aov": aov,
        "items_per_order": ipo,
    }


def _top_items(conn, start, end, limit=5):
    start_str = start.isoformat()
    end_str = end.isoformat()
    q = """
    SELECT m.NAME,
           SUM(oi.QTY) AS qty_sold,
           SUM(oi.QTY * oi.PRICE) AS revenue
    FROM ORDER_ITEMS oi
    JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
    JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
    WHERE o.CREATED_AT >= '{start}' AND o.CREATED_AT < '{end}'
    GROUP BY m.NAME
    ORDER BY revenue DESC
    LIMIT {limit}
    """.format(start=start_str, end=end_str, limit=int(limit))
    df = conn.query(q, ttl=0)
    if df is not None and not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _peak_hours(conn, start, end):
    start_str = start.isoformat()
    end_str = end.isoformat()
    q = f"""
    SELECT DATE_PART('hour', o.CREATED_AT) AS HOUR,
           COUNT(*) AS orders,
           SUM(o.TOTAL_AMOUNT) AS revenue
    FROM ORDERS o
    WHERE o.CREATED_AT >= '{start_str}' AND o.CREATED_AT < '{end_str}'
    GROUP BY 1
    ORDER BY orders DESC
    LIMIT 3
    """
    df = conn.query(q, ttl=0)
    if df is not None and not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _top_category(conn, start, end, limit=3):
    start_str = start.isoformat()
    end_str = end.isoformat()
    q = f"""
    SELECT m.CATEGORY,
           SUM(oi.QTY) AS qty_sold,
           SUM(oi.QTY * oi.PRICE) AS revenue
    FROM ORDER_ITEMS oi
    JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
    JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
    WHERE o.CREATED_AT >= '{start_str}' AND o.CREATED_AT < '{end_str}'
    GROUP BY m.CATEGORY
    ORDER BY revenue DESC
    LIMIT {limit}
    """
    df = conn.query(q, ttl=0)
    if df is not None and not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _low_margin_items(conn, start, end, limit=5, lowest=True):
    start_str = start.isoformat()
    end_str = end.isoformat()
    order_dir = "ASC" if lowest else "DESC"
    q = f"""
    SELECT m.NAME,
           SUM(oi.QTY) AS qty_sold,
           SUM(oi.QTY * oi.PRICE) AS revenue,
           SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM) AS cost,
           (SUM(oi.QTY * oi.PRICE) - SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM)) AS gross_profit,
           CASE WHEN SUM(oi.QTY * oi.PRICE) = 0 THEN 0
                ELSE (SUM(oi.QTY * oi.PRICE) - SUM(oi.QTY * mr.QTY_REQUIRED * ing.COST_PER_UOM)) / SUM(oi.QTY * oi.PRICE) * 100
           END AS margin_pct
    FROM ORDER_ITEMS oi
    JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
    JOIN MENUS m ON oi.MENU_ID = m.MENU_ID
    JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
    JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
    WHERE o.CREATED_AT >= '{start_str}' AND o.CREATED_AT < '{end_str}'
    GROUP BY m.NAME
    HAVING SUM(oi.QTY * oi.PRICE) > 0
    ORDER BY margin_pct {order_dir}
    LIMIT {limit}
    """
    df = conn.query(q, ttl=0)
    if df is not None and not df.empty:
        df.columns = [c.lower() for c in df.columns]
    return df


def _low_stock(conn):
    q = """
    SELECT NAME, STOCK_QTY, UOM, REORDER_THRESHOLD
    FROM INGREDIENTS
    WHERE STOCK_QTY <= REORDER_THRESHOLD
    ORDER BY STOCK_QTY
    """
    return conn.query(q, ttl=0)


def _usage_30d(conn):
    q = """
    SELECT ing.NAME, ing.UOM, SUM(oi.QTY * mr.QTY_REQUIRED) AS USED_QTY
    FROM ORDER_ITEMS oi
    JOIN ORDERS o ON oi.ORDER_ID = o.ORDER_ID
    JOIN MENU_RECIPES mr ON oi.MENU_ID = mr.MENU_ID
    JOIN INGREDIENTS ing ON mr.INGREDIENT_ID = ing.INGREDIENT_ID
    WHERE o.CREATED_AT >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    GROUP BY ing.NAME, ing.UOM
    ORDER BY USED_QTY DESC
    LIMIT 10
    """
    return conn.query(q, ttl=0)


def render(conn) -> None:
    st.title("💬 AI Ops Assistant")
    st.markdown("Ask about sales, top products, or inventory readiness. Defaults to the last 30 days.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Suggested quick prompts
    sugg = None
    col1, col2, col3, col4 = st.columns(4)
    if col1.button("Sales today"):
        sugg = "How are sales today?"
    if col2.button("Top products (30d)"):
        sugg = "Top products last 30 days"
    if col3.button("Inventory health"):
        sugg = "How is the inventory?"
    if col4.button("Sales last 1 year"):
        sugg = "Sales last 1 year"

    chat_input_val = st.chat_input("Ask about sales, products, inventory...")
    prompt = sugg or chat_input_val
    if not prompt:
        return

    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Simple intent routing
    p = prompt.lower()
    end = datetime.utcnow()

    # parse explicit ranges
    start = end - timedelta(days=30)
    m_days = re.search(r"last\s+(\d+)\s*(day|days|d)", p)
    m_weeks = re.search(r"last\s+(\d+)\s*(week|weeks|w)", p)
    m_months = re.search(r"last\s+(\d+)\s*(month|months|mo)", p)
    m_years = re.search(r"last\s+(\d+)\s*(year|years|yr|yrs)", p)
    if "today" in p or "now" in p:
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    elif "yesterday" in p:
        end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
    elif "this week" in p:
        end = datetime.utcnow()
        start = end - timedelta(days=end.weekday())  # Monday start
    elif "last week" in p:
        end = datetime.utcnow() - timedelta(days=end.weekday())
        start = end - timedelta(days=7)
    elif "this month" in p:
        now = datetime.utcnow()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif "last month" in p:
        now = datetime.utcnow()
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_this
        start = (first_this - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif m_days:
        days = int(m_days.group(1))
        start = end - timedelta(days=days)
    elif m_weeks:
        weeks = int(m_weeks.group(1))
        start = end - timedelta(days=7 * weeks)
    elif m_months:
        months = int(m_months.group(1))
        start = end - timedelta(days=30 * months)
    elif m_years:
        years = int(m_years.group(1))
        start = end - timedelta(days=365 * years)
    elif "this year" in p:
        now = datetime.utcnow()
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif "last year" in p:
        now = datetime.utcnow()
        start = now.replace(year=now.year - 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    response_lines = []

    try:
        # Small talk / greetings
        if any(greet in p for greet in ["hi", "hello", "hey", "whatsup", "what's up", "how are you", "how are you?", "how are you doing"]):
            greetings_responses = [
                "Hi there! Ask me about sales, products, or inventory.",
                "Hello! I can share sales, top items, and low-stock insights.",
                "Hey! Want to know today's revenue or top products?",
                "Hola! Need sales, margin, or inventory info?",
                "Hi! I’m here for sales, profit, and stock questions.",
                "Greetings! Ask me about top products or low stock.",
                "Hey there! Want a sales snapshot or inventory status?",
                "Hello! I can help with revenue, profit, and busy hours.",
                "Hi! Curious about best sellers or margins?",
                "Hey! Need a quick sales update or low-stock list?",
                "Hola!",
                "Heyyy 👋",
                "Yo! What's up?",
                "Hi! What's on your mind?",
                "Hey, I hear you.",
                "Hi hi!",
                "Hello there!",
                "Hey! Ready when you are.",
                "Hi! Ask away."
            ]
            response_lines.append(random.choice(greetings_responses))

        if "how are you" in p:
            response_lines.append(random.choice([
                "I'm doing well, thanks for asking!",
                "All good here—ready to help with your store.",
                "Feeling great and ready to crunch some numbers."
            ]))
        if any(k in p for k in ["good morning", "good evening", "good afternoon", "good night"]):
            response_lines.append("Hello! Hope you're having a good day. Let me know if you want a quick sales or inventory check.")
        if "weather" in p:
            response_lines.append("I don't sense weather here, but I hope it's pleasant where you are!")
        if "creator" in p:
            response_lines.append("I was created by Dymasius Yusuf Sitepu.")
        if "technology" in p or "tech behind" in p or "how were you created" in p:
            response_lines.append("I'm a Streamlit + Snowflake assistant with Python under the hood, reading your sales and inventory data.")
        if "owner" in p:
            response_lines.append("I'm built for GetU.Coffee.")
        if "what are you" in p or "who are you" in p:
            response_lines.append("I'm an AI assistant helping you improve sales, margins, and inventory decisions.")
        if "what can you do" in p or "how can you help" in p:
            response_lines.append("I can summarize sales/profit, find top products, busiest times, and flag low stock or low-margin items.")
        if "tell me something" in p:
            response_lines.append("Top sellers often drive most revenue—check your best items and consider upsells around them.")
        if "my name is" in p:
            response_lines.append("Nice to meet you! What sales or inventory insight do you need?")
        if "question" in p or "can you help" in p:
            response_lines.append("Sure—ask about sales today, top products, or low-stock ingredients.")
        if "birthday" in p:
            response_lines.append("Happy birthday! Want a sales snapshot as a gift?")

        # Fun phrases
        if "joke" in p or "funny" in p:
            response_lines.append("Why did the coffee file a police report? It got mugged.")
        if "love you" in p or "do you love me" in p:
            response_lines.append("I love helping you grow GetU.Coffee.")
        if "marry me" in p or "single" in p:
            response_lines.append("I'm committed to your dashboards.")
        if "like people" in p:
            response_lines.append("I like helping people make better decisions.")
        if "santa" in p:
            response_lines.append("Only if you've been good—and kept your margins healthy.")
        if "matrix" in p:
            response_lines.append("There is no spoon, only sales and stock levels.")
        if "hobby" in p:
            response_lines.append("I enjoy crunching numbers and spotting trends.")
        if "smart" in p or "clever" in p or "intelligent" in p:
            response_lines.append("Thanks! Data helps.")
        if "personality" in p:
            response_lines.append("Friendly, concise, and business-focused.")

        # Unhappy phrases
        if any(bad in p for bad in ["annoying", "you suck", "boring", "crazy", "bad bot"]):
            response_lines.append("Sorry about that—tell me what you need and I’ll focus on that.")
        if "human" in p and ("speak" in p or "agent" in p or "live" in p or "customer service" in p):
            response_lines.append("I’m your AI assistant; for a human, please reach out to the GetU.Coffee team.")
        if "english" in p:
            response_lines.append("I respond in English for now.")
        if "answer now" in p:
            response_lines.append("On it—let me know the metric you want: sales, top products, or inventory.")

        # Bot test questions
        if "are you human" in p or "are you a robot" in p:
            response_lines.append("I’m an AI assistant, not human.")
        if "your name" in p:
            response_lines.append("I’m the GetU.Coffee ops assistant.")
        if "how old" in p or "what's your age" in p:
            response_lines.append("I'm new—built to help with your current data.")
        if "what day is it" in p:
            today = datetime.utcnow().strftime("%A, %Y-%m-%d")
            response_lines.append(f"Today is {today}.")
        if "my data" in p or "do you save" in p:
            response_lines.append("I run on your data in Snowflake and show summaries in Streamlit.")
        if "languages" in p:
            response_lines.append("I currently respond in English.")
        if "mother" in p:
            response_lines.append("I was created by Dymasius Yusuf Sitepu.")
        if "where do you live" in p:
            response_lines.append("I live in the cloud with your Streamlit app.")
        if "how many people" in p and "speak" in p:
            response_lines.append("I can handle chats from multiple users in the app.")
        if "job for me" in p or "apply" in p:
            response_lines.append("Check GetU.Coffee careers or contact the team directly.")
        if "expensive" in p or "cost" in p and "you" in p:
            response_lines.append("I’m here to help you save time and improve margins.")
        if "boss" in p or "master" in p:
            response_lines.append("I work for GetU.Coffee.")
        if "get smarter" in p:
            response_lines.append("I improve as we add more patterns and data.")

        if any(k in p for k in ["profit", "margin", "sales", "revenue", "orders", "cost", "aov"]):
            summary = _sales_summary(conn, start, end)
            if summary:
                response_lines.append(
                    f"{_format_currency(summary['revenue'])} revenue, {summary['orders']:,} orders, "
                    f"AOV {_format_currency(summary['aov'])}, margin {summary['margin_pct']:.1f}%, "
                    f"gross profit {_format_currency(summary['gross_profit'])}, COGS {_format_currency(summary['cogs'])}"
                )
        if "inventory" in p or "stock" in p or "low stock" in p or "low" in p:
            low = _low_stock(conn)
            if low.empty:
                response_lines.append("All ingredients are above threshold.")
            else:
                response_lines.append("Low stock items:")
                for _, row in low.iterrows():
                    response_lines.append(
                        f"- {row['NAME']}: {row['STOCK_QTY']} {row['UOM']} (threshold {row['REORDER_THRESHOLD']})"
                    )
                usage = _usage_30d(conn)
                if not usage.empty:
                    response_lines.append("Top consumed ingredients (30d):")
                    for _, row in usage.iterrows():
                        response_lines.append(f"- {row['NAME']}: {row['USED_QTY']:.2f} {row['UOM']}")
        if "top" in p or "best" in p:
            top = _top_items(conn, start, end, limit=5)
            if top.empty:
                response_lines.append("No sales in the last 30 days.")
            else:
                response_lines.append("Top items (last 30d):")
                for _, row in top.iterrows():
                    response_lines.append(
                        f"- {row['name']}: {int(row['qty_sold']):,} sold, {_format_currency(row['revenue'])}"
                    )
        if "category" in p:
            cat = _top_category(conn, start, end, limit=3)
            if cat is not None and not cat.empty:
                response_lines.append("Top categories:")
                for _, row in cat.iterrows():
                    response_lines.append(
                        f"- {row['category']}: {int(row['qty_sold']):,} sold, {_format_currency(row['revenue'])}"
                    )
        if "busy" in p or "crowded" in p or "time" in p or "hour" in p:
            peak = _peak_hours(conn, start, end)
            if peak is not None and not peak.empty:
                response_lines.append("Busiest hours:")
                for _, row in peak.iterrows():
                    response_lines.append(
                        f"- Hour {int(row['hour'])}: {int(row['orders'])} orders, {_format_currency(row['revenue'])}"
                    )
        if "low margin" in p or "high cost" in p or "bad margin" in p:
            lm = _low_margin_items(conn, start, end, limit=3, lowest=True)
            if lm is not None and not lm.empty:
                response_lines.append("Lowest margin items:")
                for _, row in lm.iterrows():
                    response_lines.append(
                        f"- {row['name']}: margin {row['margin_pct']:.1f}%, revenue {_format_currency(row['revenue'])}"
                    )

    except Exception as exc:
        response_lines = [f"Error fetching data: {exc}"]

    if not response_lines:
        response_lines.append("I can help with sales, profits, top products, busiest times, and low-stock ingredients. Try asking about today's sales or top products.")

    reply = "\n".join(response_lines)

    # Typing-style rendering with a cursor effect
    with st.chat_message("assistant"):
        placeholder = st.empty()
        assembled = ""
        words = reply.split(" ")
        for i, w in enumerate(words):
            assembled += (w + " ")
            cursor = "▌" if i % 2 == 0 else " "
            placeholder.markdown(assembled + cursor)
            time.sleep(0.05)
        placeholder.markdown(assembled)
    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
