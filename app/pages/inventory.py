import streamlit as st

from app import data


def render(conn) -> None:
    st.title("📦 Inventory Management")
    st.markdown("### Monitor stock levels and ingredients")

    ingredients = data.get_ingredients(conn)

    if ingredients.empty:
        st.info("No ingredients yet.")
        return

    low_stock = ingredients[ingredients["STOCK_QTY"] <= ingredients["REORDER_THRESHOLD"]]

    if not low_stock.empty:
        st.warning(f"⚠️ {len(low_stock)} ingredient(s) below reorder threshold!")

        with st.expander("View Low Stock Items", expanded=True):
            for _, item in low_stock.iterrows():
                st.write(
                    f"**{item['NAME']}**: {item['STOCK_QTY']} {item['UOM']} "
                    f"(Threshold: {item['REORDER_THRESHOLD']})"
                )

    st.markdown("---")
    st.markdown("### Adjust Stock")

    ingredient_options = {f"{row['NAME']} ({row['UOM']})": row for _, row in ingredients.iterrows()}
    if ingredient_options:
        with st.form("adjust_stock_form"):
            selected_label = st.selectbox("Select ingredient", list(ingredient_options.keys()))
            selected_row = ingredient_options[selected_label]
            current_qty = float(selected_row["STOCK_QTY"] or 0)
            current_cost = float(selected_row.get("COST_PER_UOM") or 0)

            selected_id = int(selected_row["INGREDIENT_ID"])
            # Reset input default when switching ingredient or when stock/cost changed in DB
            if (
                st.session_state.get("last_selected_ing") != selected_id
                or st.session_state.get("last_current_qty") != current_qty
                or st.session_state.get("last_current_cost") != current_cost
            ):
                st.session_state["last_selected_ing"] = selected_id
                st.session_state["last_current_qty"] = current_qty
                st.session_state["last_current_cost"] = current_cost
                st.session_state["new_qty_value"] = current_qty
                st.session_state["new_cost_value"] = current_cost

            new_qty = st.number_input(
                "Set stock quantity",
                min_value=0.0,
                value=st.session_state.get("new_qty_value", current_qty),
                step=0.5,
                help="Update stock and log to inventory ledger.",
                key="new_qty_input",
            )
            new_cost = st.number_input(
                "Set cost per UOM",
                min_value=0.0,
                value=st.session_state.get("new_cost_value", current_cost),
                step=100.0,
                help="Cost per UOM is used to calculate COGS and margins.",
                key="new_cost_input",
            )
            if st.form_submit_button("💾 Update Stock & Cost", type="primary"):
                try:
                    result = data.update_ingredient_stock(conn, selected_id, new_qty)
                    data.update_ingredient_cost(conn, selected_id, new_cost)
                    change = "increased" if result["delta"] >= 0 else "decreased"
                    st.success(
                        f"{selected_row['NAME']} stock {change} from {result['old_qty']:.2f} to {result['new_qty']:.2f} "
                        f"({result['delta']:+.2f}); cost set to {new_cost:.2f}."
                    )
                    st.rerun()
                except Exception as exc:  # pragma: no cover - UI feedback only
                    st.error(f"Failed to update: {exc}")

    st.markdown("---")
    st.markdown("### All Ingredients")

    editable = st.checkbox("Enable inline edit", value=False, help="Toggle to edit stock, cost, and thresholds.")
    if editable:
        editable_df = st.data_editor(
            ingredients[["INGREDIENT_ID", "NAME", "STOCK_QTY", "COST_PER_UOM", "REORDER_THRESHOLD"]],
            hide_index=True,
            disabled=["INGREDIENT_ID", "NAME"],
            use_container_width=True,
        )
        if st.button("💾 Save table changes", type="primary"):
            updates = 0
            for _, row in editable_df.iterrows():
                orig = ingredients[ingredients["INGREDIENT_ID"] == row["INGREDIENT_ID"]].iloc[0]
                ing_id = int(row["INGREDIENT_ID"])
                new_stock = float(row["STOCK_QTY"] or 0)
                new_cost = float(row["COST_PER_UOM"] or 0)
                new_thresh = float(row["REORDER_THRESHOLD"] or 0)

                # Stock
                if float(orig["STOCK_QTY"] or 0) != new_stock:
                    data.update_ingredient_stock(conn, ing_id, new_stock)
                    updates += 1

                # Cost
                if float(orig["COST_PER_UOM"] or 0) != new_cost:
                    data.update_ingredient_cost(conn, ing_id, new_cost)
                    updates += 1

                # Threshold
                if float(orig["REORDER_THRESHOLD"] or 0) != new_thresh:
                    conn.session().sql(
                        f"""
                        UPDATE INGREDIENTS
                        SET REORDER_THRESHOLD = {new_thresh}, MODIFIED_AT = CURRENT_TIMESTAMP()
                        WHERE INGREDIENT_ID = {ing_id}
                        """
                    ).collect()
                    updates += 1

            if updates:
                st.success(f"Saved {updates} change(s).")
                st.rerun()
            else:
                st.info("No changes detected.")
    else:
        st.dataframe(
            ingredients[["NAME", "STOCK_QTY", "UOM", "COST_PER_UOM", "REORDER_THRESHOLD"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.markdown("### Ingredient consumption (last 30 days)")
    usage = data.get_ingredient_usage_last_30(conn)
    if not usage.empty:
        st.dataframe(
            usage[["NAME", "USED_QTY", "UOM"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No consumption data for the last 30 days yet.")
