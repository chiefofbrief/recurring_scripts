# Commands

## Setup

```bash
pip install tabulate requests rich curl_cffi beautifulsoup4 html2text lxml python-dateutil
```

---

## Quick Workflow

### 1. Collect Stock Market News

Runs losers, Barron's, WSJ, and Reddit. Saves to timestamped file.

```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py --days 1 && python SCRIPT_wsj_markets.py --days 1 && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > "stockmarket_$(date +%Y-%m-%d).txt"
```

### 2. Analyze News (Claude/Gemini Prompt)

```
Review all headlines and posts in @stockmarket_YYYY-MM-DD.txt. Analyze using @ANALYSIS_GUIDELINES.md, providing a comprehensive but concise analysis.

At the end of your analysis, include a "Screening Candidates" section listing stocks (ticker symbols) that warrant deeper fundamental analysis. Provide brief rationale for each. You may suggest more than 5 candidates, but note that only 1-5 will be selected for screening.

Format:
**Screening Candidates:**
- TICKER: rationale
- TICKER: rationale

Append the analysis to the top of @stockmarket_YYYY-MM-DD.txt
```

### 3. Run Stock Screening

Based on the candidates identified, run fundamental screening (select 1-5 tickers):

```bash
python SCRIPT_stock_screening.py TICKER1 TICKER2 TICKER3 TICKER4 TICKER5
```

Output: `screening_YYYY-MM-DD.md` with 5yr trends, correlation analysis, and YoY charts.

---

## Individual Scripts

### SCRIPT_losers_actives.py
Biggest stock losers and most active stocks.
```bash
python SCRIPT_losers_actives.py
```
Requires: `FMP_API_KEY`, `ALPHAVANTAGE_API_KEY`

### SCRIPT_barrons_news.py
Latest Barron's articles via Perigon API.
```bash
python SCRIPT_barrons_news.py [--count N] [--days N] [--all]
```
- `--count N` — Number of articles (default: 50)
- `--days N` — Days back (default: 1)
- `--all` — Show all articles

Requires: `PERIGON_API_KEY`

### SCRIPT_wsj_markets.py
WSJ Markets news via RSS.
```bash
python SCRIPT_wsj_markets.py [--summary] [--count N] [--days N]
```
- `--summary` — Headlines only
- `--count N` — Limit articles
- `--days N` — Filter to articles from past N days (e.g., `--days 1` for today + yesterday)

### SCRIPT_reddit_top_posts.py
Top posts from finance subreddits.
```bash
python SCRIPT_reddit_top_posts.py [--count N] [--timeframe T]
```
- `--count N` — Posts per subreddit (default: 15)
- `--timeframe` — hour, day, week, month, year, all (default: day)

### SCRIPT_macro_weekly.py
Macro indicators: ETFs, Treasury rates, inflation, unemployment.
```bash
python SCRIPT_macro_weekly.py
```
Takes ~2 min (API rate limits). Requires: `FMP_API_KEY`, `ALPHAVANTAGE_API_KEY`

### SCRIPT_intl_intrigue.py
International Intrigue newsletter.
```bash
python SCRIPT_intl_intrigue.py [--summary]
```

### SCRIPT_the_batch.py
The Batch (DeepLearning.AI newsletter).
```bash
python SCRIPT_the_batch.py [--summary]
```

### SCRIPT_stock_screening.py
Fundamental screening for 1-5 stocks. 5-year trend analysis with correlation and YoY charts.
```bash
python SCRIPT_stock_screening.py TICKER1 [TICKER2] ... [TICKER5]
```

Metrics calculated:
- Price, EPS, Revenue, Operating Margin trends (5yr annual + quarterly)
- P/E trend (derived, no extra API call)
- EPS/Revenue estimates (consensus, range, revisions)
- Price-EPS correlation (5yr annual data)
- YoY trend chart (quarterly and annual % changes for all metrics)

API Budget: 4 calls per stock (TIME_SERIES_MONTHLY_ADJUSTED, EARNINGS, EARNINGS_ESTIMATES, INCOME_STATEMENT)

Output: `screening_YYYY-MM-DD.md`

Requires: `ALPHAVANTAGE_API_KEY`
