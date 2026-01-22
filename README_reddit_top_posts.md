# Reddit Top Posts Script

Fetches and displays the top 15 upvoted posts from investment-focused subreddits using the SociaVault API.

## Subreddits Covered

- **r/ValueInvesting** - Value investing strategies and discussions
- **r/stocks** - Stock market discussions and analysis
- **r/options** - Options trading strategies and education

## Installation

1. Install required dependencies:
   ```bash
   pip install requests rich
   ```

2. Set your SociaVault API key as an environment variable:
   ```bash
   export SOCIAVAULT_API_KEY="your-api-key-here"
   ```

## Usage

### Basic Usage

Fetch top 15 posts from past day (default):
```bash
python SCRIPT_reddit_top_posts.py
```

### Custom Options

Fetch top 10 posts per subreddit:
```bash
python SCRIPT_reddit_top_posts.py --count 10
```

Fetch from past week instead of past day:
```bash
python SCRIPT_reddit_top_posts.py --timeframe week
```

Combine options:
```bash
python SCRIPT_reddit_top_posts.py --count 20 --timeframe month
```

## Parameters

- `--count`: Number of posts to display per subreddit (default: 15)
- `--timeframe`: Time period to fetch from (default: day)
  - Options: `hour`, `day`, `week`, `month`, `year`, `all`

## Output Format

The script displays posts in a beautifully formatted terminal output with:

- **Post title** - Clear, bold heading
- **Upvotes** - Number of upvotes with green highlighting
- **Comments** - Number of comments
- **Upvote ratio** - Percentage of upvotes
- **Author** - Reddit username
- **URL** - Clickable link to the post
- **Body text** - First 300 characters of text posts (if applicable)

## API Cost

- **Credit check**: 0 credits (runs automatically)
- **Per subreddit**: 1 credit
- **Total per run**: 3 credits (one for each subreddit)

The script automatically checks your available credits before fetching and warns if credits are low.

## Example Output

```
╭────────────────────────────────────────────────────╮
│  Reddit Top Posts - Investment Subreddits          │
╰────────────────────────────────────────────────────╯

Top 15 posts from past day • r/ValueInvesting, r/stocks, r/options

════════════════════════════════════════════════════

r/ValueInvesting
Showing top 15 of 25 posts

1. Analysis of Current Market Valuations
↑ 1,234 upvotes  •  156 comments  •  95% upvoted  •  u/investor123
https://reddit.com/...

Looking at historical P/E ratios and how they compare...

────────────────────────────────────────────────────

2. Deep Dive: Undervalued Tech Stocks
↑ 987 upvotes  •  89 comments  •  92% upvoted  •  u/valueseeker
...
```

## Features

- Fetches from multiple subreddits in one run
- Sorts by upvotes (highest first)
- Clean, readable terminal formatting
- Configurable post count and timeframe
- Automatic credit checking
- Handles long post text gracefully with truncation
- Shows key metrics (upvotes, comments, upvote ratio)

## Requirements

- Python 3.7+
- `requests` library (for API calls)
- `rich` library (for terminal formatting)
- Valid SociaVault API key

## Troubleshooting

**Error: SOCIAVAULT_API_KEY environment variable not set**
- Make sure you've exported your API key: `export SOCIAVAULT_API_KEY="your_key"`

**HTTP Error 402: Insufficient credits**
- Check your SociaVault account credits at https://sociavault.com

**Connection timeout**
- Check your internet connection
- The script will timeout after 30 seconds per request
