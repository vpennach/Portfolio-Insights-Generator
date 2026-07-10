import pandas as pd      # data loading, cleaning, and analysis
import requests           # making HTTP calls to external APIs
import sqlite3            # connecting to SQLite databases (built into Python)


# ── Loader Functions ─────────────────────────────────────────────────────────
# Each loader handles one data source and always returns a clean DataFrame.
# TransactionStore never cares where the data came from.

def load_from_csv(filepath) -> pd.DataFrame:
    """
    Load and clean transaction data from a CSV file.

    Args:
        filepath: path to the .csv file (e.g. "sample_transactions.csv")

    Returns:
        A cleaned pandas DataFrame ready to be passed into TransactionStore.
    """
    df = pd.read_csv(filepath)
    return _clean(df)


def load_from_api(endpoint: str, params: dict = None) -> pd.DataFrame:
    """
    Load transaction data from a REST API endpoint.

    Args:
        endpoint: the URL to call (e.g. "https://api.example.com/transactions")
        params:   optional query parameters to include in the request
                  (e.g. {"start_date": "2024-01-15"})

    Returns:
        A cleaned pandas DataFrame ready to be passed into TransactionStore.
    """
    response = requests.get(endpoint, params=params)
    response.raise_for_status()

    data = response.json()
    df = pd.DataFrame(data)
    return _clean(df)


def load_from_database(db_path: str, query: str) -> pd.DataFrame:
    """
    Load transaction data from a SQLite database.

    Args:
        db_path: path to the .db file (e.g. "transactions.db")
        query:   SQL SELECT statement to run
                 (e.g. "SELECT * FROM transactions")

    Returns:
        A cleaned pandas DataFrame ready to be passed into TransactionStore.
    """
    with sqlite3.connect(db_path) as connection:
        df = pd.read_sql(query, connection)
    return _clean(df)


# ── Shared Cleaning Helper ────────────────────────────────────────────────────
# All three loaders funnel through this so cleaning logic lives in one place.

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all data cleaning steps to a raw DataFrame.
    Called internally by every loader — not meant to be used directly.

    Cleaning steps (documented here for SOLUTION.md):
      1. Copy the DataFrame so we never mutate the caller's original
      2. Drop exact duplicate rows
      3. Fill missing trader_id with "Unknown"
      4. Parse timestamp column from string to datetime
      5. Sort by timestamp and reset the index
    """
    REQUIRED_COLUMNS = ["timestamp", "ticker", "action", "quantity", "price", "trader_id"]

    if not set(REQUIRED_COLUMNS).issubset(set(df.columns)):
        missing = set(REQUIRED_COLUMNS) - set(df.columns)
        raise ValueError(f"Data is missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()

    df = df.drop_duplicates()

    df["trader_id"] = df["trader_id"].fillna("Unknown")

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df = df.sort_values("timestamp").reset_index(drop=True)

    return df


# ── TransactionStore Class ────────────────────────────────────────────────────

class TransactionStore:
    """
    Holds cleaned transaction data and provides methods for analysis.
    Accepts any pandas DataFrame — does not care how the data was loaded.
    """

    def __init__(self, df: pd.DataFrame):
        """
        Store the DataFrame and build a ticker index for fast lookups.

        The ticker index is a dict: { "AAPL": [0, 3, 7, ...], "GOOGL": [...] }
        Mapping each ticker to the list of row positions where it appears.
        This lets get_transactions_by_ticker() find rows in O(1) instead of
        scanning every row every time.
        """
        self.df = df

        self.ticker_index = {
            ticker: df.index[df["ticker"] == ticker].tolist()
            for ticker in df["ticker"].unique()
        }

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def get_transactions_by_ticker(self, ticker: str) -> pd.DataFrame:
        """
        Return all transactions for a given ticker symbol.

        Uses the ticker index (dict) to find rows instantly rather than
        filtering the whole DataFrame every time.

        Args:
            ticker: stock symbol, e.g. "AAPL"

        Returns:
            DataFrame containing only rows for that ticker,
            or an empty DataFrame if the ticker is not found.
        """
        if ticker not in self.ticker_index:
            return pd.DataFrame(columns=self.df.columns)

        row_positions = self.ticker_index[ticker]
        return self.df.iloc[row_positions]

    # ── Analytics ─────────────────────────────────────────────────────────────

    def get_volume_by_ticker(self) -> dict:
        """
        Calculate total dollar volume traded per ticker.
        Dollar volume = quantity * price, summed across all transactions.

        Returns:
            { "AAPL": 4520000.0, "GOOGL": 1823000.0, ... } sorted highest to lowest
        """
        df = self.df.copy()
        df["dollar_volume"] = df["quantity"] * df["price"]
        result = df.groupby("ticker")["dollar_volume"].sum()
        return result.sort_values(ascending=False).to_dict()

    def get_net_position_by_ticker(self) -> dict:
        """
        Calculate net share position per ticker.
        Net position = total shares bought - total shares sold.
        Positive = net long (more bought than sold).
        Negative = net short (more sold than bought).

        Returns:
            { "AAPL": 350, "GOOGL": -200, ... } sorted by absolute value, largest first
        """
        import numpy as np

        df = self.df.copy()
        df["signed_quantity"] = np.where(
            df["action"] == "BUY",
            df["quantity"],
            -df["quantity"]
        )
        result = df.groupby("ticker")["signed_quantity"].sum()
        return result.reindex(result.abs().sort_values(ascending=False).index).to_dict()

    def get_most_active_traders(self, top_n: int = 5) -> dict:
        """
        Return the traders with the most transactions.

        Args:
            top_n: how many traders to return (default 5)

        Returns:
            { "T001": 87, "T008": 74, ... } sorted highest to lowest
        """
        result = self.df["trader_id"].value_counts()
        return result.head(top_n).to_dict()

    def get_buy_sell_ratio(self) -> dict:
        """
        Calculate the ratio of BUY transactions to SELL transactions per ticker.
        A ratio below 1.0 means more sells than buys — bearish signal.
        A ratio above 1.0 means more buys than sells — bullish signal.

        Returns:
            { "AAPL": 0.82, "MSFT": 1.3, ... } sorted by most imbalanced first
        """
        import numpy as np

        counts = self.df.groupby(["ticker", "action"]).size().unstack(fill_value=0)

        ratio = (counts["BUY"] / counts["SELL"]).round(2)

        imbalance = ratio.apply(lambda x: abs(np.log(x)))
        return ratio.reindex(imbalance.sort_values(ascending=False).index).to_dict()

    def _match_trades_fifo(self) -> tuple:
        """
        Private helper that walks every trader+ticker combination chronologically
        and matches each SELL against the oldest available BUY using FIFO.

        Returns:
            matched_trades: list of dicts — every completed buy/sell pairing with P&L
            open_positions: list of dicts — unmatched lots (long or short exposure)
        """
        from collections import deque

        matched_trades = []
        open_positions = []

        # Last known price per ticker — used to estimate unrealized P&L
        last_prices = self.df.groupby("ticker")["price"].last().to_dict()

        # Process each unique trader+ticker combination
        for (trader_id, ticker), group in self.df.groupby(["trader_id", "ticker"]):
            buy_queue = deque()

            for _, row in group.iterrows():

                if row["action"] == "BUY":
                    # Store as a mutable list so we can reduce quantity on partial fills
                    buy_queue.append([row["price"], row["quantity"]])

                elif row["action"] == "SELL":
                    remaining_qty = row["quantity"]

                    while remaining_qty > 0:
                        if not buy_queue:
                            # No buy to match — this is a short position
                            last_price = last_prices.get(ticker, row["price"])
                            open_positions.append({
                                "trader_id":      trader_id,
                                "ticker":         ticker,
                                "quantity":       remaining_qty,
                                "side":           "short",
                                "avg_price":      round(row["price"], 2),
                                "last_price":     round(last_price, 2),
                                "unrealized_pnl": round((row["price"] - last_price) * remaining_qty, 2)
                            })
                            remaining_qty = 0

                        else:
                            buy_price, buy_qty = buy_queue[0]
                            matched_qty = min(remaining_qty, buy_qty)

                            matched_trades.append({
                                "trader_id":  trader_id,
                                "ticker":     ticker,
                                "quantity":   matched_qty,
                                "buy_price":  round(buy_price, 2),
                                "sell_price": round(row["price"], 2),
                                "pnl":        round((row["price"] - buy_price) * matched_qty, 2),
                                "sell_time":  row["timestamp"]
                            })

                            remaining_qty      -= matched_qty
                            buy_queue[0][1]    -= matched_qty

                            if buy_queue[0][1] == 0:
                                buy_queue.popleft()

            # Anything still in the queue is an open long position
            for buy_price, buy_qty in buy_queue:
                if buy_qty > 0:
                    last_price = last_prices.get(ticker, buy_price)
                    open_positions.append({
                        "trader_id":      trader_id,
                        "ticker":         ticker,
                        "quantity":       buy_qty,
                        "side":           "long",
                        "avg_price":      round(buy_price, 2),
                        "last_price":     round(last_price, 2),
                        "unrealized_pnl": round((last_price - buy_price) * buy_qty, 2)
                    })

        return matched_trades, open_positions

    def get_trader_pnl(self) -> dict:
        """
        Calculate realized and unrealized P&L per trader across all tickers.
        Uses _match_trades_fifo() internally.

        Returns:
            {
              "T001": {
                "realized_pnl": 1250.00,
                "unrealized_pnl": -340.00,
                "total_pnl": 910.00
              }, ...
            } sorted by total_pnl descending
        """
        matched_trades, open_positions = self._match_trades_fifo()

        # Realized P&L — sum matched trade P&L per trader
        if matched_trades:
            matched_df = pd.DataFrame(matched_trades)
            realized = matched_df.groupby("trader_id")["pnl"].sum()
        else:
            realized = pd.Series(dtype=float)

        # Unrealized P&L — sum open position estimates per trader
        if open_positions:
            open_df = pd.DataFrame(open_positions)
            unrealized = open_df.groupby("trader_id")["unrealized_pnl"].sum()
        else:
            unrealized = pd.Series(dtype=float)

        # Combine — use all known trader IDs as the index
        all_traders = self.df["trader_id"].unique()
        result = {}
        for trader in all_traders:
            r = round(realized.get(trader, 0.0), 2)
            u = round(unrealized.get(trader, 0.0), 2)
            result[trader] = {
                "realized_pnl":   r,
                "unrealized_pnl": u,
                "total_pnl":      round(r + u, 2)
            }

        return dict(sorted(result.items(), key=lambda x: x[1]["total_pnl"], reverse=True))

    def get_best_and_worst_trades(self) -> dict:
        """
        Find the single most profitable and most unprofitable matched trade
        across all traders and tickers.
        Uses _match_trades_fifo() internally.

        Returns:
            {
              "best":  { "trader_id": "T001", "ticker": "AAPL", "pnl": 820.00, ... },
              "worst": { "trader_id": "T009", "ticker": "META", "pnl": -540.00, ... }
            }
        """
        matched_trades, _ = self._match_trades_fifo()

        if not matched_trades:
            return {"best": None, "worst": None}

        best  = max(matched_trades, key=lambda t: t["pnl"])
        worst = min(matched_trades, key=lambda t: t["pnl"])

        return {"best": best, "worst": worst}

    def get_market_pnl(self) -> dict:
        """
        Aggregate P&L across all traders — treating the entire trading group
        as a single team trying to generate collective returns.

        Returns:
            {
              "total_realized":   1250.00,
              "total_unrealized": 8430.00,
              "total_pnl":        9680.00
            }
        """
        trader_pnl = self.get_trader_pnl()
        total_realized   = sum(v["realized_pnl"]   for v in trader_pnl.values())
        total_unrealized = sum(v["unrealized_pnl"] for v in trader_pnl.values())
        return {
            "total_realized":   round(total_realized, 2),
            "total_unrealized": round(total_unrealized, 2),
            "total_pnl":        round(total_realized + total_unrealized, 2)
        }

    # After-hours activity analysis was considered but not implemented.
    # The timestamps in the dataset carry no timezone information, making it
    # impossible to reliably determine whether a transaction occurred during
    # US market hours (9:30am–4:00pm ET) without an unverifiable assumption.
    # This should be revisited once the timezone of the data source is confirmed.

    def get_trader_concentration(self) -> dict:
        """
        Calculate each trader's share of total transaction activity as a percentage.
        Also computes the Herfindahl-Hirschman Index (HHI) — a standard regulatory
        metric for market concentration. HHI above 2500 indicates high concentration.

        Returns:
            {
              "by_trader": { "T001": 33.0, "T002": 5.2, ... },
              "hhi": 1823
            }
        """
        proportions = self.df["trader_id"].value_counts(normalize=True) * 100

        hhi = int((proportions ** 2).sum())

        return {
            "by_trader": proportions.round(1).to_dict(),
            "hhi": hhi
        }

    def get_time_analysis(self) -> dict:
        """
        Break down transaction activity by time.
        Returns counts grouped by hour and by day so we can spot
        when trading is most active.

        Returns:
            {
              "by_hour": { 9: 45, 10: 112, ... },
              "by_day":  { "2024-01-15": 310, "2024-01-16": 287, ... }
            }
        """
        by_hour = self.df["timestamp"].dt.hour.value_counts().sort_index()

        by_day = self.df["timestamp"].dt.date.value_counts().sort_index()

        return {
            "by_hour": by_hour.to_dict(),
            "by_day":  {str(k): v for k, v in by_day.to_dict().items()}
        }
