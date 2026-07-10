import json
import re
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import streamlit as st
from transaction_processor import (
    load_from_csv,
    load_from_api,
    load_from_database,
    TransactionStore,
)
from insights_generator import build_prompt, generate_insights


# ── Page Configuration ────────────────────────────────────────────────────────

def configure_page():
    st.set_page_config(
        page_title="Portfolio Insights Generator",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    # Green Generate Insights button + suppress anchor links on headers
    st.markdown("""
        <style>
            button[kind="primary"] {
                background-color: #28a745 !important;
                border-color: #28a745 !important;
            }
            button[kind="primary"]:hover {
                background-color: #218838 !important;
                border-color: #1e7e34 !important;
            }
            h1 a, h2 a, h3 a { display: none !important; }
        </style>
    """, unsafe_allow_html=True)


# ── Chart Helper ─────────────────────────────────────────────────────────────

def _bar_chart(data: dict, fmt_pct: bool = False, wide: bool = False) -> plt.Figure:
    """Return a static matplotlib Figure — no hover interactivity."""
    fig, ax = plt.subplots(figsize=(12 if wide else 8, 3.5))
    labels = list(data.keys())
    values = list(data.values())
    colors = ["#d9534f" if v < 0 else "#4c78a8" for v in values]
    ax.bar(labels, values, color=colors, width=0.6)
    if any(v < 0 for v in values):
        ax.axhline(0, color="black", linewidth=0.6)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    if fmt_pct:
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    return fig


# ── Session State Initialization ──────────────────────────────────────────────

def init_session_state():
    if "df" not in st.session_state:
        st.session_state.df           = load_from_csv("sample_transactions.csv")
        st.session_state.source_label = "sample_transactions.csv (default)"
        st.session_state.insights     = None


# ── Data Source Switcher ──────────────────────────────────────────────────────

def render_data_source_switcher():
    with st.sidebar:
        st.header("Data Source")
        csv_tab, api_tab, db_tab = st.tabs(["CSV", "API", "Database"])

        with csv_tab:
            uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
            if st.button("Load CSV", key="load_csv"):
                if uploaded is None:
                    st.warning("Please upload a CSV file first.")
                else:
                    try:
                        st.session_state.df           = load_from_csv(uploaded)
                        st.session_state.source_label = uploaded.name
                        st.session_state.insights     = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load CSV: {e}")

        with api_tab:
            endpoint = st.text_input(
                "API Endpoint URL",
                placeholder="https://api.example.com/transactions"
            )
            params_input = st.text_input(
                "Query parameters (JSON, optional)",
                placeholder='{"start_date": "2024-01-15"}'
            )
            if st.button("Load from API", key="load_api"):
                if not endpoint:
                    st.warning("Please enter an API endpoint URL.")
                else:
                    try:
                        params = json.loads(params_input) if params_input else None
                        st.session_state.df           = load_from_api(endpoint, params)
                        st.session_state.source_label = f"API: {endpoint}"
                        st.session_state.insights     = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load from API: {e}")

        with db_tab:
            db_path = st.text_input(
                "Database file path",
                placeholder="transactions.db"
            )
            query = st.text_area("SQL Query", value="SELECT * FROM transactions")
            if st.button("Load from Database", key="load_db"):
                if not db_path:
                    st.warning("Please enter a database file path.")
                else:
                    try:
                        st.session_state.df           = load_from_database(db_path, query)
                        st.session_state.source_label = f"Database: {db_path}"
                        st.session_state.insights     = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load from database: {e}")


# ── Key Metrics Row ───────────────────────────────────────────────────────────

def render_metrics(store: TransactionStore):
    st.title("Portfolio Insights Generator")
    st.caption(f"Data source: {st.session_state.source_label}")
    st.divider()

    market_pnl = store.get_market_pnl()
    dates      = store.df["timestamp"].dt.date

    # Shortened date format to fit the metric card
    date_str = (
        f"{dates.min().strftime('%b %d')} → {dates.max().strftime('%b %d, %Y')}"
    )

    col1, col2, col3, col4, col5 = st.columns([1.5, 0.8, 0.8, 1.8, 1.8])

    with col1:
        st.metric("Total Transactions", f"{len(store.df):,}")
    with col2:
        st.metric("Tickers", store.df["ticker"].nunique())
    with col3:
        st.metric("Traders", store.df["trader_id"].nunique())
    with col4:
        st.metric("Date Range", date_str)
    with col5:
        st.metric(
            "Team Total P&L",
            f"${market_pnl['total_pnl']:+,.2f}",
            delta=f"Realized: ${market_pnl['total_realized']:+,.2f}"
        )

    st.markdown(
        '<a href="#ai-insights" style="display:inline-block; padding:8px 18px; '
        'background-color:#4c78a8; color:white; text-decoration:none; '
        'border-radius:6px; font-size:14px; font-weight:600;">↓ Jump to AI Insights</a>',
        unsafe_allow_html=True
    )
    st.divider()


# ── Raw Data Table ────────────────────────────────────────────────────────────

def render_data_table(store: TransactionStore):
    st.header("Transaction Data", anchor=False)

    tickers  = ["All"] + sorted(store.df["ticker"].unique().tolist())
    selected = st.selectbox("Filter by ticker", tickers)

    if selected == "All":
        display_df = store.df
    else:
        display_df = store.get_transactions_by_ticker(selected)
        if display_df.empty:
            st.warning(f"No transactions found for {selected}.")
            return

    st.caption(f"Showing {len(display_df):,} transactions")
    st.dataframe(display_df, use_container_width=True)
    st.divider()


# ── Analytics Charts ──────────────────────────────────────────────────────────

def render_analytics(store: TransactionStore):
    trader_pnl = store.get_trader_pnl()
    best_worst = store.get_best_and_worst_trades()
    time_data  = store.get_time_analysis()

    # ── Market Analysis ───────────────────────────────────────────────────────
    st.header("Market Analysis", anchor=False)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Dollar Volume by Ticker", anchor=False)
        st.pyplot(_bar_chart(store.get_volume_by_ticker()), use_container_width=True)

    with col2:
        st.subheader("Net Position by Ticker (shares)", anchor=False)
        st.pyplot(_bar_chart(store.get_net_position_by_ticker()), use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Buy/Sell Imbalance by Ticker", anchor=False)
        st.caption("Deviation from 1.0 — positive = more buys, negative = more sells")
        raw_ratio = store.get_buy_sell_ratio()
        deviation = {ticker: round(r - 1.0, 2) for ticker, r in raw_ratio.items()}
        st.pyplot(_bar_chart(deviation), use_container_width=True)

    with col4:
        st.subheader("Transaction Activity by Day", anchor=False)
        day_data = {str(k): v for k, v in time_data["by_day"].items()}
        st.pyplot(_bar_chart(day_data), use_container_width=True)

    st.subheader("Transaction Activity by Hour (24h)", anchor=False)
    st.caption("Hours with no bar had zero transactions recorded")
    all_hours = {f"{h:02d}:00": time_data["by_hour"].get(h, 0) for h in range(24)}
    st.pyplot(_bar_chart(all_hours, wide=True), use_container_width=True)

    st.divider()

    # ── Trader Analysis ───────────────────────────────────────────────────────
    st.header("Trader Analysis", anchor=False)

    st.subheader("Trader Concentration", anchor=False)
    conc = store.get_trader_concentration()
    hhi  = conc["hhi"]
    hhi_label = (
        "competitive"            if hhi < 1500 else
        "moderately concentrated" if hhi < 2500 else
        "highly concentrated"
    )
    delta = "above 2500 = high concern" if hhi >= 1500 else None
    st.metric("HHI Score", f"{hhi} ({hhi_label})", delta=delta)
    st.pyplot(_bar_chart(conc["by_trader"], fmt_pct=True), use_container_width=True)

    st.subheader("Trader P&L Breakdown", anchor=False)
    pnl_rows = [
        {
            "Trader":     trader,
            "Realized":   f"${data['realized_pnl']:+,.2f}",
            "Unrealized": f"${data['unrealized_pnl']:+,.2f}",
            "Total P&L":  f"${data['total_pnl']:+,.2f}",
        }
        for trader, data in trader_pnl.items()
    ]
    st.dataframe(pd.DataFrame(pnl_rows), use_container_width=True, hide_index=True)

    st.subheader("Total P&L by Trader", anchor=False)
    pnl_chart = {trader: data["total_pnl"] for trader, data in trader_pnl.items()}
    st.pyplot(_bar_chart(pnl_chart), use_container_width=True)

    col7, col8 = st.columns(2)

    with col7:
        st.subheader("Best Single Trade", anchor=False)
        if best_worst["best"]:
            b = best_worst["best"]
            st.success(
                f"**{b['trader_id']} — {b['ticker']}**  \n"
                f"{b['quantity']} shares  \n"
                f"Bought @ ${b['buy_price']} → Sold @ ${b['sell_price']}  \n"
                f"P&L: +${b['pnl']:,.2f}"
            )
        else:
            st.info("No matched trades found.")

    with col8:
        st.subheader("Worst Single Trade", anchor=False)
        if best_worst["worst"]:
            w = best_worst["worst"]
            st.error(
                f"**{w['trader_id']} — {w['ticker']}**  \n"
                f"{w['quantity']} shares  \n"
                f"Bought @ ${w['buy_price']} → Sold @ ${w['sell_price']}  \n"
                f"P&L: -${abs(w['pnl']):,.2f}"
            )
        else:
            st.info("No matched trades found.")

    st.divider()


# ── AI Insights ───────────────────────────────────────────────────────────────

def clean_insights_text(text: str) -> str:
    # Remove diff-style code fences that cause red/green line coloring
    text = re.sub(r"```diff\n(.*?)```", r"\1", text, flags=re.DOTALL)
    # Move sign outside dollar sign: $+1,234 → +$1,234  and  $-1,234 → -$1,234
    text = re.sub(r"\$\+(\d)", r"+$\1", text)
    text = re.sub(r"\$-(\d)",  r"-$\1", text)
    # Escape every remaining $digit so Streamlit doesn't open a LaTeX math block.
    # e.g. $456.35 → \$456.35  which renders as a literal $ sign.
    text = re.sub(r"\$(\d)", r"\\$\1", text)
    # Strip inline italic (*text*) — Streamlit renders it inconsistently,
    # sometimes showing literal asterisks or collapsing spaces in the output
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    return text


def render_insights(store: TransactionStore):
    st.header("AI Insights", anchor="ai-insights")
    st.caption("Powered by Claude — analyzes market patterns, trader behavior, and compliance flags")

    if st.button("Generate Insights", type="primary"):
        with st.spinner("Analyzing trading patterns... this may take up to 60 seconds."):
            try:
                prompt = build_prompt(
                    volume               = store.get_volume_by_ticker(),
                    net_positions        = store.get_net_position_by_ticker(),
                    active_traders       = store.get_most_active_traders(),
                    time_analysis        = store.get_time_analysis(),
                    total_transactions   = len(store.df),
                    buy_sell_ratio       = store.get_buy_sell_ratio(),
                    trader_concentration = store.get_trader_concentration(),
                    trader_pnl           = store.get_trader_pnl(),
                    best_worst_trades    = store.get_best_and_worst_trades(),
                    market_pnl           = store.get_market_pnl()
                )
                st.session_state.insights = generate_insights(prompt)
            except Exception as e:
                st.error(f"Failed to generate insights: {e}")

    if st.session_state.insights:
        st.markdown(clean_insights_text(st.session_state.insights))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    configure_page()
    init_session_state()

    store = TransactionStore(st.session_state.df)

    render_data_source_switcher()
    render_metrics(store)
    render_data_table(store)
    render_analytics(store)
    render_insights(store)


if __name__ == "__main__":
    main()
