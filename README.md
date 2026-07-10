# Portfolio Insights Generator

A Python application that processes financial transaction data, computes analytics, and uses the Anthropic API (Claude) to generate natural language compliance and performance insights.

## Requirements

- Python 3.10 or higher
- An Anthropic API key ([get one here](https://console.anthropic.com/))

## Setup

**1. Clone or download the project.**

**2. Create and activate a virtual environment:**

```bash
python3 -m venv venv
source venv/bin/activate       # macOS / Linux
venv\Scripts\activate          # Windows
```

**3. Install dependencies:**

```bash
pip install -r requirements.txt
```

**4. Add your API key:**

Copy `.env.example` to `.env` and replace the placeholder with your real key:

```bash
cp .env.example .env
```

Open `.env` and set:

```
ANTHROPIC_API_KEY=your-actual-key-here
```

**5. Run the dashboard:**

```bash
streamlit run dashboard.py
```

The app will open in your browser at `http://localhost:8501`.

## Running Tests

```bash
python -m unittest test_loaders.py -v
```

## File Overview

| File | Purpose |
|---|---|
| `transaction_processor.py` | Data loading, cleaning, and all analytics (`TransactionStore`) |
| `insights_generator.py` | Prompt builder and Anthropic API call |
| `dashboard.py` | Streamlit dashboard wiring everything together |
| `test_loaders.py` | Unit tests for all three data loaders |
| `sample_transactions.csv` | Sample dataset (1,030 raw rows, 1,000 after cleaning) |
| `.env.example` | API key template — copy to `.env` and fill in your key |

## Data Sources

The dashboard supports three data sources, switchable at runtime via the sidebar:

- **CSV Upload** — upload any CSV matching the required schema
- **REST API** — enter an endpoint URL and optional JSON query parameters
- **Database** — enter a SQLite file path and SQL query

Required columns: `timestamp`, `ticker`, `action`, `quantity`, `price`, `trader_id`
