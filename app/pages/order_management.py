import streamlit as st

from app import data


def render(conn) -> None:
    st.title("📋 Order Management")
    st.markdown("### Manage orders and update status")

    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox("Status", ["All", "created", "in_progress", "completed", "closed"])

    with col2:
        payment_filter = st.selectbox("Payment", ["All", "Paid", "Unpaid"])

    with col3:
        limit = st.number_input("Show orders", min_value=10, max_value=100, value=50, step=10)

    query = "SELECT ORDER_ID, TOTAL_AMOUNT, STATUS, IS_PAID, CREATED_AT FROM ORDERS WHERE 1=1"

    if status_filter != "All":
        query += f" AND STATUS = '{status_filter}'"

    if payment_filter == "Paid":
        query += " AND IS_PAID = TRUE"
    elif payment_filter == "Unpaid":
        query += " AND IS_PAID = FALSE"

    query += f" ORDER BY CREATED_AT DESC LIMIT {limit}"

    orders = conn.query(query, ttl=10)

    if orders.empty:
        st.info("No orders found.")
        return

    st.markdown(f"### Found {len(orders)} orders")

    for _, order in orders.iterrows():
        header = (
            f"Order #{order['ORDER_ID']} • Rp {order['TOTAL_AMOUNT']:,.0f} • "
            f"{order['STATUS'].upper()} • {'✅ PAID' if order['IS_PAID'] else '❌ UNPAID'}"
        )

        with st.expander(header):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.write(f"**Order ID:** {order['ORDER_ID']}")
                st.write(f"**Total:** Rp {order['TOTAL_AMOUNT']:,.0f}")
                st.write(f"**Status:** {order['STATUS']}")
                st.write(f"**Paid:** {'Yes' if order['IS_PAID'] else 'No'}")
                st.write(f"**Created:** {order['CREATED_AT']}")

                items = data.get_order_items(conn, order["ORDER_ID"])
                if not items.empty:
                    st.markdown("**Items:**")
                    for _, item in items.iterrows():
                        st.write(f"• {item['NAME']} x{item['QTY']} = Rp {item['SUBTOTAL']:,.0f}")

            with col2:
                st.markdown("**Actions**")
                new_status = st.selectbox(
                    "Status",
                    ["created", "in_progress", "completed", "closed"],
                    index=["created", "in_progress", "completed", "closed"].index(order["STATUS"]),
                    key=f"status_{order['ORDER_ID']}",
                )

                if st.button("💾 Update Status", key=f"update_{order['ORDER_ID']}"):
                    update_query = f"""
                        UPDATE ORDERS
                        SET STATUS = '{new_status}', MODIFIED_AT = CURRENT_TIMESTAMP()
                        WHERE ORDER_ID = {order['ORDER_ID']}
                    """
                    data.execute_query(conn, update_query, show_success=True)
                    st.rerun()

                if not order["IS_PAID"]:
                    if st.button("✅ Mark Paid", key=f"paid_{order['ORDER_ID']}", type="primary"):
                        paid_query = f"""
                            UPDATE ORDERS
                            SET IS_PAID = TRUE, PAID_AT = CURRENT_TIMESTAMP(), MODIFIED_AT = CURRENT_TIMESTAMP()
                            WHERE ORDER_ID = {order['ORDER_ID']}
                        """
                        data.execute_query(conn, paid_query, show_success=True)
                        st.rerun()
