# Commands

## Stock Market Combo

```bash
python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py
```

Save to file (for Cloud Shell scrollback issues):
```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > output.txt
less output.txt
```

Save to file, then Gemini analysis:
```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > output.txt
cat output.txt | gemini -f ANALYSIS_GUIDELINES.md "analyze per guidelines"
```

Archive with date:
```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py && python SCRIPT_wsj_markets.py && python SCRIPT_reddit_top_posts.py) 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > "stockmarket_$(date +%Y-%m-%d).txt"
```

---

## Scripts

### Losers/Actives
```bash
python SCRIPT_losers_actives.py
```
No options. Requires `FMP_API_KEY` and `ALPHAVANTAGE_API_KEY`.

### Barron's News
```bash
python SCRIPT_barrons_news.py
python SCRIPT_barrons_news.py --count 25
python SCRIPT_barrons_news.py --days 3
python SCRIPT_barrons_news.py --all
```
| Option | Description |
|--------|-------------|
| `--count N` | Number of articles (default: 50) |
| `--days N` | Days back to fetch (default: 1) |
| `--all` | Show all available articles |

Requires `PERIGON_API_KEY`.

### WSJ Markets
```bash
python SCRIPT_wsj_markets.py
python SCRIPT_wsj_markets.py --summary
python SCRIPT_wsj_markets.py --count 5
```
| Option | Description |
|--------|-------------|
| `--summary` | Headlines only (default: full content) |
| `--count N` | Number of articles (default: all, or 10 in summary mode) |

### Reddit Top Posts
```bash
python SCRIPT_reddit_top_posts.py
python SCRIPT_reddit_top_posts.py --count 10
python SCRIPT_reddit_top_posts.py --timeframe week
```
| Option | Description |
|--------|-------------|
| `--count N` | Posts per subreddit (default: 15) |
| `--timeframe` | `hour`, `day`, `week`, `month`, `year`, `all` (default: day) |

### Macro Weekly
```bash
python SCRIPT_macro_weekly.py
```
No options. Takes ~2 min due to API rate limits. Requires `FMP_API_KEY` and `ALPHAVANTAGE_API_KEY`.

### International Intrigue
```bash
python SCRIPT_intl_intrigue.py
python SCRIPT_intl_intrigue.py --summary
```
| Option | Description |
|--------|-------------|
| `--summary` | Brief summary only (default: full article) |

### The Batch
```bash
python SCRIPT_the_batch.py
python SCRIPT_the_batch.py --summary
```
| Option | Description |
|--------|-------------|
| `--summary` | Brief summary only (default: full article) |

---

## API Keys

```bash
export PERIGON_API_KEY="..."      # Barron's
export FMP_API_KEY="..."          # Losers, Macro
export ALPHAVANTAGE_API_KEY="..." # Losers, Macro
```
