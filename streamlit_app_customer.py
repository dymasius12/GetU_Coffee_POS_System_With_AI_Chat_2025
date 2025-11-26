"""
GetU.Coffee Customer Kiosk - Streamlit
Lightweight entrypoint focused on self-service ordering.
"""

import streamlit as st

from app.config import configure_page
from app import data
from app.pages import customer_order


def main():
    configure_page()
    conn = data.get_connection()
    if not data.test_connection(conn):
        st.stop()

    # Simple kiosk layout: hide sidebar, render customer order page
    st.session_state["nav_page"] = "🛒 Customer Order"
    customer_order.render(conn)


if __name__ == "__main__":
    main()
