# Commands

## Setup

```bash
pip install tabulate requests rich curl_cffi beautifulsoup4 html2text lxml python-dateutil
```

---

## Stock Market

Runs losers, Barron's, WSJ, and Reddit. Saves to timestamped file.

```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > "stockmarket_$(date +%Y-%m-%d).txt"
```

With Gemini analysis:
```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | tee "stockmarket_$(date +%Y-%m-%d).txt" | gemini -f ANALYSIS_GUIDELINES.md "analyze per guidelines"
```

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
python SCRIPT_wsj_markets.py [--summary] [--count N]
```
- `--summary` — Headlines only
- `--count N` — Limit articles

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
