"""
GetU.Coffee POS System - Snowflake Streamlit Version
Modularized version for easier maintenance and growth.
"""

import streamlit as st

from app.config import configure_page
from app import data
from app.pages import analytics, chat_ai, customer_order, home, inventory, menu_management, order_management

# Apply global config and styles
configure_page()

# Database connection
conn = data.get_connection()

if not data.test_connection(conn):
    st.stop()

# Navigation
st.sidebar.markdown("# 🧭 Navigation")
page_options = [
    "🏠 Home",
    "🛒 Customer Order",
    "📋 Order Management",
    "🍰 Menu Management",
    "📦 Inventory",
    "📊 Analytics",
    "🤖 AI Chat",
]

default_page = st.session_state.get("nav_page", page_options[0])
page_index = page_options.index(default_page) if default_page in page_options else 0
page = st.sidebar.radio("Select Page", page_options, index=page_index, key="nav_page")

PAGES = {
    "🏠 Home": home.render,
    "🛒 Customer Order": customer_order.render,
    "📋 Order Management": order_management.render,
    "🍰 Menu Management": menu_management.render,
    "📦 Inventory": inventory.render,
    "📊 Analytics": analytics.render,
    "🤖 AI Chat": chat_ai.render,
}

# Render selected page
PAGES[page](conn)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    """
    **GetU.Coffee POS**

    Complete Point of Sale system for coffee shops.

    Features:
    - Customer ordering
    - Order management
    - Menu management
    - Inventory tracking
    - Sales analytics
    """
)

st.sidebar.markdown("---")
st.sidebar.caption("© 2025 GetU.Coffee POS")
