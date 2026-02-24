"""
Phalidae v2 - TradingView-Style Theme Module
Color constants, CSS generator, HTML helper functions.
"""

# ---------------------------------------------------------------------------
# Background hierarchy
# ---------------------------------------------------------------------------
BG_PRIMARY = "#131722"
BG_SECONDARY = "#1e222d"
BG_TERTIARY = "#2a2e39"
BG_SURFACE = "#363a45"

# ---------------------------------------------------------------------------
# Borders
# ---------------------------------------------------------------------------
BORDER_DEFAULT = "rgba(54, 58, 69, 0.8)"
BORDER_ACTIVE = "rgba(83, 89, 107, 1.0)"

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------
TEXT_PRIMARY = "#d1d4dc"
TEXT_SECONDARY = "#787b86"
TEXT_MUTED = "#4c525e"

# ---------------------------------------------------------------------------
# Trading colors
# ---------------------------------------------------------------------------
BULL = "#26a69a"
BEAR = "#ef5350"
BULL_BG = "rgba(38, 166, 154, 0.12)"
BEAR_BG = "rgba(239, 83, 80, 0.12)"

# ---------------------------------------------------------------------------
# Accent
# ---------------------------------------------------------------------------
ACCENT_BLUE = "#2962ff"
ACCENT_YELLOW = "#f7931a"
ACCENT_PURPLE = "#ab47bc"

# ---------------------------------------------------------------------------
# Regime colors (preserved from existing code)
# ---------------------------------------------------------------------------
REGIME_COLORS = {
    "TRENDING_UP": "#26a69a",
    "TRENDING_DOWN": "#ef5350",
    "RANGING": "#ffca28",
    "HIGH_VOLATILITY": "#ff7043",
    "LOW_VOLATILITY": "#78909c",
    "BREAKOUT": "#42a5f5",
}

REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay",
    "HIGH_VOLATILITY": "Yuksek Vol.",
    "LOW_VOLATILITY": "Dusuk Vol.",
    "BREAKOUT": "Kirilim",
}


def get_global_css() -> str:
    """Return ~120-line CSS string for TradingView-style dark theme."""
    return f"""<style>
/* ===== App background ===== */
[data-testid="stAppViewContainer"] {{
    background-color: {BG_PRIMARY};
}}
[data-testid="stHeader"] {{
    background-color: {BG_PRIMARY};
}}
html, body, [data-testid="stApp"] {{
    background-color: {BG_PRIMARY};
}}

/* ===== Hide sidebar ===== */
[data-testid="stSidebar"] {{
    display: none;
}}
[data-testid="collapsedControl"] {{
    display: none;
}}

/* ===== Compact block-container ===== */
.block-container {{
    padding: 0.5rem 1rem !important;
    max-width: 100% !important;
}}

/* ===== Metric styling ===== */
[data-testid="stMetricValue"] {{
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.95rem;
    color: {TEXT_PRIMARY};
}}
[data-testid="stMetricLabel"] {{
    font-size: 0.72rem;
    color: {TEXT_SECONDARY};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
[data-testid="stMetricDelta"] {{
    font-size: 0.75rem;
}}

/* ===== Compact tabs ===== */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0px;
    background-color: {BG_SECONDARY};
    border-radius: 4px;
    padding: 2px;
}}
.stTabs [data-baseweb="tab"] {{
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 500;
    color: {TEXT_SECONDARY};
    background-color: transparent;
    border-radius: 3px;
}}
.stTabs [aria-selected="true"] {{
    background-color: {BG_TERTIARY} !important;
    color: {TEXT_PRIMARY} !important;
}}

/* ===== DataTable hover ===== */
.stDataFrame tbody tr:hover {{
    background-color: rgba(38, 166, 154, 0.08) !important;
}}
.stDataFrame {{
    font-size: 0.8rem;
}}

/* ===== Scrollbar styling ===== */
::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
}}
::-webkit-scrollbar-track {{
    background: {BG_PRIMARY};
}}
::-webkit-scrollbar-thumb {{
    background: {BG_SURFACE};
    border-radius: 3px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: {BORDER_ACTIVE};
}}

/* ===== Divider ===== */
hr {{
    margin: 0.3rem 0;
    border-color: {BORDER_DEFAULT};
}}

/* ===== Radio buttons (nav) ===== */
[data-testid="stRadio"] > div {{
    gap: 0.3rem;
}}
[data-testid="stRadio"] label {{
    font-size: 0.8rem;
    padding: 4px 12px;
    border-radius: 3px;
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER_DEFAULT};
    color: {TEXT_SECONDARY};
}}
[data-testid="stRadio"] label[data-checked="true"] {{
    background-color: {ACCENT_BLUE} !important;
    color: white !important;
    border-color: {ACCENT_BLUE} !important;
}}

/* ===== Input fields ===== */
[data-testid="stTextInput"] input,
[data-baseweb="select"] {{
    background-color: {BG_SURFACE} !important;
    border-color: {BORDER_DEFAULT} !important;
    color: {TEXT_PRIMARY} !important;
    font-size: 0.82rem;
}}

/* ===== Header/footer padding reduction ===== */
.stApp header {{
    height: 0px;
}}
footer {{
    display: none;
}}

/* ===== Caption ===== */
.stCaption {{
    font-size: 0.75rem;
    color: {TEXT_SECONDARY};
}}

/* ===== Button base ===== */
.stButton > button {{
    font-size: 0.78rem;
    padding: 4px 12px;
    border-radius: 3px;
    border: 1px solid {BORDER_DEFAULT};
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
}}
.stButton > button:hover {{
    background-color: {BG_TERTIARY};
    border-color: {BORDER_ACTIVE};
}}

/* ===== Expander ===== */
[data-testid="stExpander"] {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
}}
</style>"""


# ---------------------------------------------------------------------------
# HTML Helper Functions
# ---------------------------------------------------------------------------

def metric_strip_html(items: list[dict]) -> str:
    """Horizontal metric strip. Each item: {label, value, delta?, color?}"""
    cells = []
    for item in items:
        label = item.get("label", "")
        value = item.get("value", "")
        delta = item.get("delta", "")
        color = item.get("color", TEXT_PRIMARY)

        delta_html = ""
        if delta:
            delta_color = BULL if str(delta).startswith("+") else BEAR if str(delta).startswith("-") else TEXT_SECONDARY
            delta_html = f'<span style="font-size:11px;color:{delta_color};margin-left:4px;">{delta}</span>'

        cells.append(
            f'<div style="display:inline-flex;flex-direction:column;align-items:flex-start;'
            f'margin-right:24px;padding:4px 0;">'
            f'<span style="font-size:10px;color:{TEXT_SECONDARY};text-transform:uppercase;'
            f'letter-spacing:0.5px;">{label}</span>'
            f'<span style="font-size:14px;font-family:monospace;color:{color};font-weight:600;">'
            f'{value}{delta_html}</span>'
            f'</div>'
        )

    return (
        f'<div style="display:flex;align-items:center;padding:6px 12px;'
        f'background:{BG_SECONDARY};border-bottom:1px solid {BORDER_DEFAULT};'
        f'flex-wrap:wrap;">{"".join(cells)}</div>'
    )


def status_dot_html(active: bool) -> str:
    """8px green/red status dot."""
    color = BULL if active else BEAR
    return (
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
        f'background:{color};margin-left:4px;vertical-align:middle;'
        f'box-shadow:0 0 4px {color};"></span>'
    )


def regime_badge_html(regime: str) -> str:
    """Compact colored regime badge."""
    color = REGIME_COLORS.get(regime, TEXT_MUTED)
    label = REGIME_LABELS.get(regime, regime or "-")
    return (
        f'<span style="background:{color};color:white;padding:1px 6px;'
        f'border-radius:8px;font-size:10px;font-weight:500;white-space:nowrap;">'
        f'{label}</span>'
    )


def pnl_colored_html(value: float, fmt: str = "pct") -> str:
    """Green/red P&L text."""
    color = BULL if value >= 0 else BEAR
    if fmt == "pct":
        text = f"{value:+.2f}%"
    elif fmt == "usd":
        text = f"${value:+,.2f}"
    else:
        text = f"{value:+.2f}"
    return f'<span style="color:{color};font-family:monospace;font-size:12px;">{text}</span>'


def watchlist_item_html(
    symbol: str,
    regime: str,
    pnl_pct: float | None,
    has_trade: bool,
    selected: bool,
) -> str:
    """Watchlist single row: coin name + regime dot + P&L."""
    bg = BG_TERTIARY if selected else "transparent"
    border_left = f"3px solid {ACCENT_BLUE}" if selected else "3px solid transparent"

    regime_color = REGIME_COLORS.get(regime, TEXT_MUTED)
    regime_dot = (
        f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;'
        f'background:{regime_color};margin-right:4px;vertical-align:middle;"></span>'
    )

    pnl_html = ""
    if pnl_pct is not None:
        pnl_color = BULL if pnl_pct >= 0 else BEAR
        pnl_html = (
            f'<span style="color:{pnl_color};font-family:monospace;font-size:11px;'
            f'margin-left:auto;">{pnl_pct:+.1f}%</span>'
        )

    trade_dot = ""
    if has_trade:
        trade_dot = (
            f'<span style="display:inline-block;width:5px;height:5px;border-radius:50%;'
            f'background:{ACCENT_YELLOW};margin-left:4px;vertical-align:middle;"'
            f' title="Acik islem"></span>'
        )

    clean_sym = symbol.replace("/USDT:USDT", "")

    return (
        f'<div style="display:flex;align-items:center;padding:4px 8px;'
        f'background:{bg};border-left:{border_left};cursor:pointer;'
        f'font-size:12px;color:{TEXT_PRIMARY};">'
        f'{regime_dot}'
        f'<span style="font-weight:{"600" if selected else "400"};">{clean_sym}</span>'
        f'{trade_dot}{pnl_html}'
        f'</div>'
    )
