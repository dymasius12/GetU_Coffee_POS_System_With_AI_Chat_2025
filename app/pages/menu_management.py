import streamlit as st

from app import data


def render(conn) -> None:
    st.title("🍰 Menu Management")
    st.markdown("### Manage menu items and categories")

    tab1, tab2 = st.tabs(["📋 View Menu", "➕ Add/Edit Menu"])

    with tab1:
        menus = data.get_menus(conn, active_only=False)

        if menus.empty:
            st.info("No menu items yet.")
        else:
            categories = menus["CATEGORY"].unique()

            for category in sorted(categories):
                st.markdown(f"### {category}")
                category_items = menus[menus["CATEGORY"] == category]

                for _, item in category_items.iterrows():
                    col1, col2, col3, _ = st.columns([3, 2, 1, 1])

                    with col1:
                        status = "✅" if item["ACTIVE"] else "❌"
                        st.write(f"{status} **{item['NAME']}**")

                    with col2:
                        st.write(f"Rp {item['PRICE']:,.0f}")

                    with col3:
                        if item["ACTIVE"] and st.button("🗑️", key=f"delete_{item['MENU_ID']}"):
                            delete_query = f"""
                                UPDATE MENUS
                                SET ACTIVE = FALSE, MODIFIED_AT = CURRENT_TIMESTAMP()
                                WHERE MENU_ID = {item['MENU_ID']}
                            """
                            data.execute_query(conn, delete_query, show_success=True)
                            st.rerun()

                st.markdown("---")

    with tab2:
        st.markdown("### Add or Edit Menu Item")

        menus = data.get_menus(conn, active_only=False)
        menu_options = ["__new__"] + menus["MENU_ID"].tolist() if not menus.empty else ["__new__"]

        def format_option(option):
            if option == "__new__":
                return "➕ Add new menu"
            item = menus[menus["MENU_ID"] == option].iloc[0]
            status = "✅" if item["ACTIVE"] else "❌"
            return f"{status} {item['NAME']} (Rp {item['PRICE']:,.0f})"

        selected = st.selectbox("Choose menu to edit or add new", menu_options, format_func=format_option)

        # Dynamic keys reset inputs when switching between items
        name_default = ""
        price_default = 0.0
        category_default = ""
        active_default = True

        if selected != "__new__":
            selected_item = menus[menus["MENU_ID"] == selected].iloc[0]
            name_default = selected_item["NAME"]
            price_default = float(selected_item["PRICE"])
            category_default = selected_item["CATEGORY"]
            active_default = bool(selected_item["ACTIVE"])

        with st.form(f"menu_form_{selected}"):
            name = st.text_input("Menu Name *", value=name_default, key=f"name_{selected}")
            price = st.number_input("Price (Rp) *", min_value=0.0, step=1000.0, value=price_default, key=f"price_{selected}")
            category = st.text_input("Category *", value=category_default, placeholder="e.g., Hot Coffee, Cold Coffee, Tea", key=f"category_{selected}")
            active = st.checkbox("Active", value=active_default, key=f"active_{selected}")

            button_label = "➕ Add Menu Item" if selected == "__new__" else "💾 Update Menu Item"

            if st.form_submit_button(button_label, type="primary"):
                if name and price > 0 and category:
                    name_escaped = name.replace("'", "''")
                    category_escaped = category.replace("'", "''")

                    if selected == "__new__":
                        query = f"""
                            INSERT INTO MENUS (NAME, PRICE, CATEGORY, ACTIVE, CREATED_BY)
                            VALUES ('{name_escaped}', {price}, '{category_escaped}', {active}, 'admin')
                        """
                    else:
                        query = f"""
                            UPDATE MENUS
                            SET NAME = '{name_escaped}',
                                PRICE = {price},
                                CATEGORY = '{category_escaped}',
                                ACTIVE = {active},
                                MODIFIED_AT = CURRENT_TIMESTAMP()
                            WHERE MENU_ID = {selected}
                        """

                    if data.execute_query(conn, query):
                        action = "Added" if selected == "__new__" else "Updated"
                        st.success(f"✅ {action} {name}!")
                        st.rerun()
                else:
                    st.error("Please fill in all required fields.")
