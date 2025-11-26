import streamlit as st


PAGE_CONFIG = {
    "page_title": "GetU.Coffee POS",
    "page_icon": "☕",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

CSS = """
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #6F4E37;
        text-align: center;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #F5F5DC;
        padding: 1rem;
        border-radius: 10px;
        border-left: 5px solid #6F4E37;
    }
    .order-card {
        background-color: #FFF8DC;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
</style>
"""


def configure_page() -> None:
    """Apply shared Streamlit page config and styles."""
    st.set_page_config(**PAGE_CONFIG)
    st.markdown(CSS, unsafe_allow_html=True)
