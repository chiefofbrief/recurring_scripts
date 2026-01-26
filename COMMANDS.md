# Commands

## Quick Reference

| Script | Command |
|--------|---------|
| Losers/Actives | `python SCRIPT_losers_actives.py` |
| Barron's | `python SCRIPT_barrons_news.py` |
| WSJ Markets | `python SCRIPT_wsj_markets.py` |
| Reddit | `python SCRIPT_reddit_top_posts.py` |
| Macro Weekly | `python SCRIPT_macro_weekly.py` |
| Intl Intrigue | `python SCRIPT_intl_intrigue.py` |
| The Batch | `python SCRIPT_the_batch.py` |

## Multi-Script Commands

### Stock Market (daily check)
```bash
python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py --count 20 && python SCRIPT_wsj_markets.py --count 10 && python SCRIPT_reddit_top_posts.py
```

### Stock Market - Headlines Only (faster)
```bash
python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py --count 10 && python SCRIPT_wsj_markets.py --summary && python SCRIPT_reddit_top_posts.py
```

## Common Options

```bash
# Barron's
--count N    # Limit articles (default 50)
--days N     # Lookback days (default 1)
--all        # Show all articles

# WSJ
--count N    # Limit articles
--summary    # Headlines only

# Intl Intrigue / The Batch
--summary    # Brief summary only
```

## API Keys Required

```bash
export PERIGON_API_KEY="..."      # Barron's
export FMP_API_KEY="..."          # Losers, Macro
export ALPHAVANTAGE_API_KEY="..." # Losers, Macro
```

## Gemini Workflow

Pipe script output directly to Gemini with your guidelines:
```bash
python SCRIPT_losers_actives.py | gemini -f GEMINI.md "analyze per guidelines"
```

Or for the full stock market check:
```bash
(python SCRIPT_losers_actives.py && python SCRIPT_barrons_news.py --count 20 && python SCRIPT_wsj_markets.py --count 10 && python SCRIPT_reddit_top_posts.py) 2>&1 | gemini -f GEMINI.md "analyze per guidelines"
```
