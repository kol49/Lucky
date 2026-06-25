# ProfitMap

ProfitMap is a Windows desktop application for product-level profitability analysis, break-even planning, pricing, assortment decisions, and AI-assisted business recommendations.

The analytics dashboard also includes profitability coefficients in report format:

- gross profit share = gross profit / net sales
- net profit share = net profit / net sales
- operating expense share = total expenses / net sales
- reimbursements and discounts share = reimbursements and discounts / net sales

## Stack

- Python 3.11+
- PySide6 / Qt
- SQLite
- SQLAlchemy ORM
- PyQtGraph
- Pandas / NumPy
- OpenAI API integration with local rule-based fallback

## Run Locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Run Web Version

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-web.txt
PYTHONPATH=src uvicorn profitmap.web.app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

On a server, the included systemd and nginx configs are in `deploy/`.

On macOS/Linux:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Build EXE

On Windows:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ProfitMap --paths src --hidden-import PySide6.QtSvg --hidden-import pyqtgraph main.py
```

Or use the included Windows workflow in `.github/workflows/build-windows.yml`.

The application stores its SQLite database in the user's home directory as `profitmap.sqlite3` by default.

## AI Recommendations

Create a `.env` file when you want OpenAI-powered recommendations:

```bash
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4.1-mini
```

If the key is missing or the API is unavailable, ProfitMap automatically falls back to local rule-based recommendations.

## Optional Forecasting Engines

The demand forecasting service is designed to use lightweight moving-average and linear-regression models by default. Prophet and XGBoost can be installed later and wired through `src/profitmap/services/demand.py` without changing the UI.
