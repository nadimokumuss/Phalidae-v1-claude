"""
Phalidae v2 - Self-Learning Crypto Trading Bot
Entry point: DB init + Scheduler start + Streamlit multi-page navigation.
Phase 6: TradingView-style UI redesign — 3 pages.
"""

import sys
import os

# Ensure scripts/ is on sys.path so internal imports (db.*, worker.*, etc.) resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
import streamlit as st

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("phalidae")

# Page config must be first Streamlit call
st.set_page_config(
    page_title="Phalidae",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Global CSS (TradingView dark theme) ---
from views.theme import get_global_css
st.markdown(get_global_css(), unsafe_allow_html=True)


def _init_system():
    """Initialize DB and scheduler once per Streamlit session."""
    if st.session_state.get("_system_initialized"):
        return

    # Create all DB tables
    from db.engine import create_all
    create_all()
    logger.info("Database initialized")

    # Generate seed strategy variants if none exist
    from db.engine import get_session
    from db.models import StrategyVariant
    session = get_session()
    try:
        count = session.query(StrategyVariant).count()
        if count == 0:
            from strategy.variants import generate_seed_variants
            n = generate_seed_variants()
            logger.info(f"Generated {n} seed strategy variants")
    finally:
        session.close()

    # Start background scheduler
    from worker.scheduler import start_scheduler
    start_scheduler()
    logger.info("Scheduler started")

    st.session_state["_system_initialized"] = True


# Initialize on first load
_init_system()

# ─── Horizontal Navigation (3 pages) ───
page = st.radio(
    "nav",
    ["Trading Terminal", "Strategy Lab", "Data & Analytics"],
    horizontal=True,
    label_visibility="collapsed",
)

# ─── Page Router ───
if page == "Trading Terminal":
    from views.page_terminal import render
    render()
elif page == "Strategy Lab":
    from views.page_strategy_lab_v2 import render
    render()
elif page == "Data & Analytics":
    from views.page_data_analytics import render
    render()
