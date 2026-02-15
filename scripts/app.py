"""
Phalidae v2 - Self-Learning Crypto Trading Bot
Entry point: DB init + Scheduler start + Streamlit multi-page navigation.
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
    page_title="Phalidae v2",
    page_icon="🦋",
    layout="wide",
    initial_sidebar_state="expanded",
)


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

# ─── Sidebar Navigation ───
st.sidebar.title("Phalidae v2")
st.sidebar.caption("Self-Learning Crypto Trading Bot")
st.sidebar.divider()

page = st.sidebar.radio(
    "Sayfa",
    ["Dashboard", "Sinyaller", "Paper Trades", "Strategy Lab", "Data Explorer"],
    index=0,
)

st.sidebar.divider()

# Scheduler status
from worker.scheduler import get_scheduler_status
status = get_scheduler_status()
if status["running"]:
    st.sidebar.success("Sistem aktif")
    for job in status["jobs"]:
        next_run = job["next_run"][:19] if job["next_run"] else "?"
        st.sidebar.caption(f"{job['name']}: {next_run}")
else:
    st.sidebar.warning("Scheduler baslatiliyor...")

# ─── Page Router ───
if page == "Dashboard":
    from pages import page_dashboard
    page_dashboard.render()
elif page == "Sinyaller":
    from pages import page_signals
    page_signals.render()
elif page == "Paper Trades":
    from pages import page_paper_trades
    page_paper_trades.render()
elif page == "Strategy Lab":
    from pages import page_strategy_lab
    page_strategy_lab.render()
elif page == "Data Explorer":
    from pages import page_data_explorer
    page_data_explorer.render()
