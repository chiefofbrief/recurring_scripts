# International Intrigue Newsletter Fetcher

Fetch and display the most recent post from the International Intrigue newsletter in a clean terminal format.

## Installation

```bash
pip install -r requirements_intl_intrigue.txt
```

## Usage

### Show full article (default):
```bash
python SCRIPT_intl_intrigue.py
```

### Show brief summary only:
```bash
python SCRIPT_intl_intrigue.py --summary
```

## Features

- Automatically fetches the latest post from International Intrigue
- Bypasses Cloudflare protection using curl_cffi
- Beautiful terminal formatting with rich Markdown rendering
- Converts HTML to readable, formatted text
- Shows full article by default with optional --summary flag

## Requirements

- Python 3.7+
- beautifulsoup4
- rich
- html2text
- curl_cffi

## Notes

- No authentication or API keys required
- Directly parses public web pages
- May take a few seconds to bypass bot protection
