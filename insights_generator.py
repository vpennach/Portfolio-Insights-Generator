import os
import anthropic
from dotenv import load_dotenv


# Load the ANTHROPIC_API_KEY from the .env file into environment variables.
# This must run before we try to read the key.
load_dotenv()


# ── Prompt Builder ────────────────────────────────────────────────────────────

def build_prompt(
    volume: dict,
    net_positions: dict,
    active_traders: dict,
    time_analysis: dict,
    total_transactions: int,
    buy_sell_ratio: dict,
    trader_concentration: dict,
    trader_pnl: dict,
    best_worst_trades: dict,
    market_pnl: dict
) -> str:
    """
    Format the computed analytics into a text prompt for the LLM.
    We send a compact summary rather than raw CSV data to minimize
    token usage and keep API costs low.

    Args:
        volume:             output of store.get_volume_by_ticker()
        net_positions:      output of store.get_net_position_by_ticker()
        active_traders:     output of store.get_most_active_traders()
        time_analysis:      output of store.get_time_analysis()
        total_transactions: total number of transactions after cleaning

    Returns:
        A formatted string ready to be sent to the Anthropic API.
    """
    date_range = f"{min(time_analysis['by_day'].keys())} to {max(time_analysis['by_day'].keys())}"

    hhi_score = trader_concentration["hhi"]
    if hhi_score < 1500:
        hhi_label = "competitive"
    elif hhi_score < 2500:
        hhi_label = "moderately concentrated"
    else:
        hhi_label = "highly concentrated — potential regulatory concern"

    # ── Market section formatting ─────────────────────────────────────────────
    volume_lines = "\n".join(
        f"  {ticker}: ${vol:,.0f}" for ticker, vol in volume.items()
    )
    net_lines = "\n".join(
        f"  {ticker}: {pos:+,} shares" for ticker, pos in net_positions.items()
    )
    ratio_lines = "\n".join(
        f"  {ticker}: {ratio:.2f} ({'buy-skewed' if ratio > 1 else 'sell-skewed'})"
        for ticker, ratio in buy_sell_ratio.items()
    )
    day_lines = "\n".join(
        f"  {day}: {count} transactions"
        for day, count in time_analysis["by_day"].items()
    )
    hour_lines = "\n".join(
        f"  {hour:02d}:00 — {count} transactions"
        for hour, count in sorted(time_analysis["by_hour"].items())
    )

    # ── Trader section formatting ─────────────────────────────────────────────
    concentration_lines = "\n".join(
        f"  {trader}: {pct}% of all transactions"
        for trader, pct in trader_concentration["by_trader"].items()
    )
    pnl_lines = "\n".join(
        f"  {trader}: realized ${data['realized_pnl']:+,.2f} | "
        f"unrealized ${data['unrealized_pnl']:+,.2f} | "
        f"total ${data['total_pnl']:+,.2f}"
        for trader, data in trader_pnl.items()
    )
    best  = best_worst_trades["best"]
    worst = best_worst_trades["worst"]
    best_line  = (f"  {best['trader_id']} | {best['ticker']} | "
                  f"{best['quantity']} shares | "
                  f"bought @ ${best['buy_price']} → sold @ ${best['sell_price']} | "
                  f"P&L: ${best['pnl']:+,.2f}") if best else "  No matched trades found"
    worst_line = (f"  {worst['trader_id']} | {worst['ticker']} | "
                  f"{worst['quantity']} shares | "
                  f"bought @ ${worst['buy_price']} → sold @ ${worst['sell_price']} | "
                  f"P&L: ${worst['pnl']:+,.2f}") if worst else "  No matched trades found"

    return f"""You are a senior quantitative analyst and compliance officer at a financial firm. \
You are reviewing a summary of recent trading activity across a group of traders who collectively \
operate as a single trading team. Your job is to surface meaningful findings — do not report \
what is unremarkable.

DATASET OVERVIEW
Total transactions (after cleaning): {total_transactions:,}
Date range: {date_range}
Tickers: {', '.join(volume.keys())}
Note: timestamps have no confirmed timezone — treat all time-based findings as preliminary.

════════════════════════════════════════
SECTION 1: MARKET ANALYSIS
════════════════════════════════════════

DOLLAR VOLUME BY TICKER (quantity × price, highest first)
{volume_lines}

NET POSITION BY TICKER (positive = net long, negative = net short)
{net_lines}

BUY/SELL TRANSACTION RATIO BY TICKER (1.0 = balanced, most imbalanced first)
{ratio_lines}

TRANSACTION TIMING
By day:
{day_lines}
By hour (24h clock):
{hour_lines}

════════════════════════════════════════
SECTION 2: TRADER ANALYSIS
════════════════════════════════════════

COLLECTIVE TEAM P&L (all traders combined)
  Realized P&L:   ${market_pnl['total_realized']:+,.2f}
  Unrealized P&L: ${market_pnl['total_unrealized']:+,.2f}
  Total P&L:      ${market_pnl['total_pnl']:+,.2f}
  (Unrealized is estimated using last known transaction price per ticker.
   Only intra-period matched trades are included in realized P&L.)

TRADER CONCENTRATION
HHI Score: {hhi_score} ({hhi_label})
(HHI scale: below 1500 = competitive, 1500–2500 = moderate, above 2500 = high concern)
{concentration_lines}

INDIVIDUAL TRADER P&L (sorted by total P&L, highest first)
{pnl_lines}

BEST SINGLE TRADE (largest realized gain on one matched lot)
{best_line}

WORST SINGLE TRADE (largest realized loss on one matched lot)
{worst_line}

════════════════════════════════════════
INSTRUCTIONS
════════════════════════════════════════
Write a structured compliance and performance report in two parts matching the sections above.
Use markdown headers and bullet points. Include ONLY findings that are genuinely meaningful — \
skip anything unremarkable and never write placeholder text.

Part 1 — Market Analysis: focus on directional bias, volume concentration, and sentiment signals. \
For timing, include only a brief note if transactions cluster outside standard US market hours \
(9:30 AM–4:00 PM ET) — flag it as a likely timezone artifact worth confirming, not as a primary \
finding. Do not lead with timing or treat it as the most significant observation.
Part 2 — Trader Analysis: focus on individual performance, concentration risks, outlier behavior, \
and anything that would warrant further investigation by a compliance or risk team.

Formatting rules:
- Use ## for section headers and - for bullet points only.
- Do NOT use **bold**, *italic*, or ***bold-italic*** anywhere in the response. No asterisks \
of any kind inside sentences or bullets.
- Write all content as plain prose within bullet points.
- Do not use tables, code blocks, or any other special formatting."""


# ── Insights Generator ────────────────────────────────────────────────────────

def generate_insights(prompt: str) -> str:
    """
    Send a prompt to the Anthropic API and return the response as a string.

    Args:
        prompt: the formatted prompt string from build_prompt()

    Returns:
        The LLM's response as a plain string.
    """
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text
