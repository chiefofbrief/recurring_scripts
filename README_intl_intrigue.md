# International Intrigue Newsletter Fetcher

Fetch and display the most recent post from the International Intrigue newsletter in a clean terminal format.

## Installation

```bash
pip install -r requirements_intl_intrigue.txt
```

## Usage

### Show summary (default):
```bash
python SCRIPT_intl_intrigue.py
```

### Show full article:
```bash
python SCRIPT_intl_intrigue.py --full
```

## Features

- Automatically fetches the latest post from International Intrigue
- Bypasses Cloudflare protection using curl_cffi
- Clean, formatted terminal output using rich
- Converts HTML to readable text/Markdown format
- Command-line flag to show full text or summary

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
