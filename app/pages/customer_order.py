import streamlit as st

from app import data


def render(conn) -> None:
    st.title("🛒 Customer Order")
    st.markdown("### Browse menu and place your order")

    if "cart" not in st.session_state:
        st.session_state.cart = {}
    if "pending_order" not in st.session_state:
        st.session_state.pending_order = None
    if "added_message" not in st.session_state:
        st.session_state.added_message = None

    menus = data.get_menus(conn, active_only=True)

    if menus.empty:
        st.warning("No menu items available. Please add items in Menu Management.")
        st.stop()

    # Show add feedback
    if st.session_state.added_message:
        st.success(st.session_state.added_message)
        st.session_state.added_message = None

    col_menu, col_cart = st.columns([2, 1])

    with col_menu:
        st.markdown("### Menu Items")
        st.markdown("#### Filter by Category (click below):")
        categories = ["All"] + sorted(menus["CATEGORY"].unique().tolist())

        if "category_filter" not in st.session_state:
            st.session_state.category_filter = "All"

        cat_cols = st.columns(len(categories)) if categories else [st]
        for idx, cat in enumerate(categories):
            col = cat_cols[idx]
            is_active = st.session_state.category_filter == cat
            button_label = f"✅ {cat}" if is_active else cat
            if col.button(button_label, key=f"cat_{cat}"):
                st.session_state.category_filter = cat
                st.session_state.pending_order = None
                st.rerun()

        st.divider()

        display_menus = (
            menus if st.session_state.category_filter == "All" else menus[menus["CATEGORY"] == st.session_state.category_filter]
        )

        for _, row in display_menus.iterrows():
            col1, col2, col3 = st.columns([3, 2, 2])

            with col1:
                st.markdown(f"**{row['NAME']}**")
                st.caption(f"{row['CATEGORY']} • Rp {row['PRICE']:,.0f}")

            with col2:
                current_qty = st.session_state.cart.get(row["MENU_ID"], 0)
                st.write(f"Qty: {current_qty}")

            with col3:
                col_minus, col_plus = st.columns(2)

                with col_minus:
                    if st.button("➖", key=f"minus_{row['MENU_ID']}"):
                        if row["MENU_ID"] in st.session_state.cart and st.session_state.cart[row["MENU_ID"]] > 0:
                            st.session_state.pending_order = None
                            st.session_state.cart[row["MENU_ID"]] -= 1
                            if st.session_state.cart[row["MENU_ID"]] == 0:
                                del st.session_state.cart[row["MENU_ID"]]
                            st.rerun()

                with col_plus:
                    if st.button("➕", key=f"plus_{row['MENU_ID']}"):
                        st.session_state.pending_order = None
                        st.session_state.cart[row["MENU_ID"]] = st.session_state.cart.get(row["MENU_ID"], 0) + 1
                        st.session_state.added_message = f"✅ Added {row['NAME']} to cart"
                        st.rerun()

            st.markdown("---")

    with col_cart:
        st.markdown("### 🛒 Your Cart")

        if not st.session_state.cart:
            st.info("Cart is empty")
            return

        total = 0
        cart_items = []

        for menu_id, qty in st.session_state.cart.items():
            item = menus[menus["MENU_ID"] == menu_id].iloc[0]
            subtotal = item["PRICE"] * qty
            total += subtotal

            st.write(f"**{item['NAME']}**")
            st.write(f"{qty} x Rp {item['PRICE']:,.0f} = Rp {subtotal:,.0f}")
            st.markdown("---")

            cart_items.append({"menu_id": menu_id, "qty": qty, "price": item["PRICE"]})

        st.markdown(f"### Total: Rp {total:,.0f}")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🗑️ Clear", use_container_width=True):
                st.session_state.cart = {}
                st.session_state.pending_order = None
                st.rerun()

        with col2:
            if st.button("✅ Place Order", type="primary", use_container_width=True):
                st.session_state.pending_order = {"total": total, "items": cart_items}
                st.balloons()
                st.rerun()

        # If an order is staged, show confirmation step
        if st.session_state.pending_order:
            staged = st.session_state.pending_order
            st.markdown("### Confirm Order")
            for item in staged["items"]:
                menu_row = menus[menus["MENU_ID"] == item["menu_id"]].iloc[0]
                st.write(f"- {menu_row['NAME']} x{item['qty']} = Rp {item['price'] * item['qty']:,.0f}")
            st.markdown(f"**Total: Rp {staged['total']:,.0f}**")

            if st.button("📦 Confirm Order", type="primary"):
                order_query = f"""
                    INSERT INTO ORDERS (TOTAL_AMOUNT, STATUS, IS_PAID, PAYMENT_METHOD, CREATED_BY)
                    VALUES ({staged['total']}, 'created', FALSE, 'manual_qris', 'customer')
                """

                if data.execute_query(conn, order_query):
                    order_id_result = conn.query("SELECT MAX(ORDER_ID) as ORDER_ID FROM ORDERS", ttl=0)
                    order_id = order_id_result["ORDER_ID"][0]

                    for item in staged["items"]:
                        item_query = f"""
                            INSERT INTO ORDER_ITEMS (ORDER_ID, MENU_ID, QTY, PRICE)
                            VALUES ({order_id}, {item['menu_id']}, {item['qty']}, {item['price']})
                        """
                        data.execute_query(conn, item_query)

                    warnings = data.consume_ingredients_for_order(conn, order_id, staged["items"], created_by="customer")

                    st.session_state.cart = {}
                    st.session_state.pending_order = None
                    st.balloons()
                    st.success("✅ Order has been placed!")
                    for warn in warnings:
                        st.warning(warn)
                    order_lines = []
                    for item in staged["items"]:
                        menu_row = menus[menus["MENU_ID"] == item["menu_id"]].iloc[0]
                        order_lines.append(
                            f"{menu_row['NAME']} x{item['qty']} = Rp {item['price'] * item['qty']:,.0f}"
                        )

                    @st.dialog("Order confirmed - take screenshot")
                    def confirmation_dialog():
                        st.markdown(
                            "<div style='font-size:2.2rem; color:red; font-weight:bold; text-align:center;'>"
                            f"Order #{order_id}</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<div style='font-size:1.2rem; font-weight:bold; text-align:center;'>📸 Please take a screenshot or photo to show to the cashier.</div>",
                            unsafe_allow_html=True,
                        )
                        st.markdown("---")
                        st.markdown("**Items:**")
                        for line in order_lines:
                            st.write(f"- {line}")
                        st.markdown(f"**Total:** Rp {staged['total']:,.0f}")
                        st.info("Please pay at the cashier with QRIS and show the payment success to the cashier.")
                        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
                        if st.button("✅ Done", type="primary"):
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

                    confirmation_dialog()
