import io
import os
import sqlite3
import tempfile
import unittest

import pandas as pd
import requests
from unittest.mock import patch, MagicMock

from transaction_processor import load_from_csv, load_from_api, load_from_database


# ── What these tests check ────────────────────────────────────────────────────
# We can't test real analysis without real data, but we CAN test that each
# loader returns a properly shaped, cleaned DataFrame regardless of source.
# Each test creates a tiny controlled dataset so we know exactly what to expect.


class TestCSVLoader(unittest.TestCase):
    """Tests for load_from_csv()"""

    def test_returns_dataframe(self):
        """Loading the real sample file should return a DataFrame."""
        df = load_from_csv("sample_transactions.csv")
        self.assertIsInstance(df, pd.DataFrame)

    def test_drops_duplicates(self):
        """Duplicate rows in the CSV should be removed."""
        csv_data = (
            "timestamp,ticker,action,quantity,price,trader_id\n"
            "2024-01-15 09:30:00,AAPL,BUY,100,150.00,T001\n"
            "2024-01-15 09:30:00,AAPL,BUY,100,150.00,T001\n"  # exact duplicate
            "2024-01-15 09:31:00,MSFT,SELL,50,300.00,T002\n"
        )
        df = load_from_csv(io.StringIO(csv_data))
        self.assertEqual(len(df), 2)

    def test_fills_missing_trader_id(self):
        """Rows with no trader_id should have it filled with 'Unknown'."""
        csv_data = (
            "timestamp,ticker,action,quantity,price,trader_id\n"
            "2024-01-15 09:30:00,AAPL,BUY,100,150.00,\n"  # blank trader_id
            "2024-01-15 09:31:00,MSFT,SELL,50,300.00,T002\n"
        )
        df = load_from_csv(io.StringIO(csv_data))
        self.assertIn("Unknown", df["trader_id"].values)

    def test_timestamp_is_datetime(self):
        """The timestamp column should be datetime dtype, not string."""
        df = load_from_csv("sample_transactions.csv")
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(df["timestamp"]))


class TestAPILoader(unittest.TestCase):
    """Tests for load_from_api()"""

    @patch("transaction_processor.requests.get")
    def test_returns_dataframe(self, mock_get):
        """
        We never call a real API in tests — we use unittest.mock to fake it.
        mock_get replaces requests.get with a fake that returns our test data.
        """
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"timestamp": "2024-01-15 09:30:00", "ticker": "AAPL",
             "action": "BUY", "quantity": 100, "price": 150.0, "trader_id": "T001"},
            {"timestamp": "2024-01-15 09:31:00", "ticker": "MSFT",
             "action": "SELL", "quantity": 50, "price": 300.0, "trader_id": "T002"},
        ]
        mock_get.return_value = mock_response

        df = load_from_api("https://example.com/transactions")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 2)

    @patch("transaction_processor.requests.get")
    def test_raises_on_bad_status(self, mock_get):
        """A non-200 HTTP response should raise an exception, not silently fail."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            load_from_api("https://example.com/bad-endpoint")


class TestDatabaseLoader(unittest.TestCase):
    """Tests for load_from_database()"""

    def setUp(self):
        """
        setUp() runs before each test method.
        We create a temporary SQLite database file with known test data
        so tests are self-contained and don't depend on any real .db file.
        """
        self.test_rows = [
            ("2024-01-15 09:30:00", "AAPL", "BUY",  100, 150.0, "T001"),
            ("2024-01-15 09:31:00", "MSFT", "SELL",  50, 300.0, "T002"),
            ("2024-01-15 09:32:00", "GOOGL", "BUY", 200, 140.0, "T003"),
        ]
        # tempfile gives us a real file path that load_from_database can open
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = tmp.name
        tmp.close()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE transactions (
                    timestamp TEXT, ticker TEXT, action TEXT,
                    quantity INTEGER, price REAL, trader_id TEXT
                )
            """)
            conn.executemany(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?)",
                self.test_rows
            )

    def tearDown(self):
        """tearDown() runs after each test — clean up the temp file."""
        os.unlink(self.db_path)

    def test_returns_dataframe(self):
        """Querying the test database should return a DataFrame."""
        df = load_from_database(self.db_path, "SELECT * FROM transactions")
        self.assertIsInstance(df, pd.DataFrame)

    def test_correct_row_count(self):
        """The DataFrame should have exactly as many rows as the test data."""
        df = load_from_database(self.db_path, "SELECT * FROM transactions")
        self.assertEqual(len(df), len(self.test_rows))


if __name__ == "__main__":
    unittest.main()
