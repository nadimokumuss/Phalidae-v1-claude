"""
Phalidae v2 - Charting
Plotly ile interaktif mum grafikleri, Bollinger Bantları, EMA overlay'leri,
equity curve ve P&L timeline.
"""

import pandas as pd
import ta as ta_lib
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    DataFrame'e teknik indikatörleri ekler:
    - EMA 20 / 50 / 200
    - Bollinger Bands (20, 2)
    - RSI 14
    """
    df = df.copy()
    df["ema_20"] = ta_lib.trend.ema_indicator(df["close"], window=20)
    df["ema_50"] = ta_lib.trend.ema_indicator(df["close"], window=50)
    df["ema_200"] = ta_lib.trend.ema_indicator(df["close"], window=200)

    bb = ta_lib.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()

    df["rsi"] = ta_lib.momentum.rsi(df["close"], window=14)
    return df


def plot_interactive_chart(
    df: pd.DataFrame,
    symbol: str = "",
    show_bb: bool = True,
    show_ema: bool = True,
    show_volume: bool = True,
) -> go.Figure:
    """
    Mum grafiği + isteğe bağlı Bollinger Bands, EMA ve hacim alt grafiği.
    """
    df = add_indicators(df)

    row_heights = [0.75, 0.25] if show_volume else [1.0]
    rows = 2 if show_volume else 1

    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # --- Mum Grafiği ---
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        ),
        row=1,
        col=1,
    )

    # --- Bollinger Bands ---
    if show_bb and "bb_upper" in df.columns:
        for col_name, label, color in [
            ("bb_upper", "BB Upper", "rgba(173,216,230,0.4)"),
            ("bb_mid", "BB Mid", "rgba(173,216,230,0.6)"),
            ("bb_lower", "BB Lower", "rgba(173,216,230,0.4)"),
        ]:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df[col_name],
                    name=label,
                    line=dict(width=1, color=color),
                ),
                row=1,
                col=1,
            )

    # --- EMA Çizgileri ---
    if show_ema:
        for col_name, label, color in [
            ("ema_20", "EMA 20", "#ffeb3b"),
            ("ema_50", "EMA 50", "#ff9800"),
            ("ema_200", "EMA 200", "#f44336"),
        ]:
            if col_name in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df["timestamp"],
                        y=df[col_name],
                        name=label,
                        line=dict(width=1.5, color=color),
                    ),
                    row=1,
                    col=1,
                )

    # --- Hacim ---
    if show_volume and "volume" in df.columns:
        colors = [
            "#26a69a" if c >= o else "#ef5350"
            for c, o in zip(df["close"], df["open"])
        ]
        fig.add_trace(
            go.Bar(
                x=df["timestamp"],
                y=df["volume"],
                name="Volume",
                marker_color=colors,
                opacity=0.5,
            ),
            row=2,
            col=1,
        )

    # --- Layout ---
    title = f"{symbol} Chart" if symbol else "Chart"
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=650,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=20, t=60, b=30),
    )
    fig.update_yaxes(title_text="Fiyat", row=1, col=1)
    if show_volume:
        fig.update_yaxes(title_text="Hacim", row=2, col=1)

    return fig


def plot_equity_curve(data: list[dict]) -> go.Figure:
    """
    Plot equity curve from cumulative P&L data.
    data: list of {"date": datetime, "equity": float}
    """
    dates = [d["date"] for d in data]
    equity = [d["equity"] for d in data]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates,
        y=equity,
        mode="lines+markers",
        name="Equity",
        line=dict(width=2, color="#26a69a"),
        marker=dict(size=4),
        fill="tozeroy",
        fillcolor="rgba(38,166,154,0.1)",
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_dash="dot")

    fig.update_layout(
        title="Equity Curve (Paper Trading)",
        template="plotly_dark",
        height=350,
        xaxis_title="Tarih",
        yaxis_title="Kumulatif P&L ($)",
        margin=dict(l=50, r=20, t=60, b=30),
    )
    return fig


def plot_pnl_timeline(snapshots: list[dict], symbol: str = "") -> go.Figure:
    """
    Plot P&L timeline for a single trade from snapshots.
    snapshots: list of {"timestamp": datetime, "pnl": float}
    """
    timestamps = [s["timestamp"] for s in snapshots]
    pnls = [s["pnl"] for s in snapshots]

    colors = ["#26a69a" if p >= 0 else "#ef5350" for p in pnls]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=pnls,
        mode="lines+markers",
        name="P&L",
        line=dict(width=2, color="#2196f3"),
        marker=dict(size=3, color=colors),
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_dash="dot")

    title = f"P&L Timeline - {symbol}" if symbol else "P&L Timeline"
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=300,
        xaxis_title="Zaman",
        yaxis_title="Unrealized P&L ($)",
        margin=dict(l=50, r=20, t=60, b=30),
    )
    return fig
