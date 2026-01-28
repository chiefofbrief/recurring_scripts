"""
WSJ Markets RSS Feed Fetcher
=============================

Fetches and displays the most recent market news from The Wall Street Journal's
Markets RSS feed in a clean, readable terminal format.

Installation:
    pip install curl_cffi beautifulsoup4 rich html2text lxml

Usage:
    python SCRIPT_wsj_markets.py                    # Show 50 articles from past 1 day with full content (default)
    python SCRIPT_wsj_markets.py --summary          # Show top 10 headlines from past 1 day
    python SCRIPT_wsj_markets.py --count 3          # Show top 3 articles with full content
    python SCRIPT_wsj_markets.py --summary --count 15  # Show top 15 headlines
    python SCRIPT_wsj_markets.py --days 0           # Filter to today only
    python SCRIPT_wsj_markets.py --days 7           # Filter to articles from past 7 days
    python SCRIPT_wsj_markets.py --days 999         # Show all available articles (no date filtering)

Features:
    - Automatically fetches the latest market news from WSJ RSS feed
    - Bypasses potential restrictions using curl_cffi
    - Beautiful terminal formatting with rich markup
    - Converts HTML descriptions to readable, formatted text
    - Defaults to 50 articles from past 1 day (today + yesterday)
    - Optional --summary flag for headlines only (top 10)
    - Configurable article count with --count flag
    - Date filtering with --days flag (default: 1 day)
    - No authentication or API keys required

Requirements:
    - Python 3.7+
    - curl_cffi (for bypassing potential restrictions)
    - beautifulsoup4 (for XML/HTML parsing)
    - rich (for terminal formatting)
    - html2text (for HTML to Markdown conversion)
    - lxml (for XML parsing)

How it works:
    1. Fetches the RSS feed at https://feeds.content.dowjones.io/public/rss/RSSMarketsMain
    2. Parses XML to extract feed items (title, link, description, pubDate)
    3. Converts HTML descriptions to formatted text
    4. Displays with color, bold, italic, and proper formatting
    5. Shows all articles by default in full mode, or top 10 in summary mode

Output includes:
    - Article title (in colored panel)
    - Publication date (formatted)
    - Article link (clickable in most terminals)
    - Full description/content (or just headline in summary mode)

Note:
    RSS feeds are typically reliable, but if you encounter connection issues,
    simply retry. Some corporate networks may block RSS feeds.
"""

import sys
import argparse
import time
import re
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import html2text
from datetime import datetime

try:
    from curl_cffi import requests
except ImportError:
    print("Error: curl_cffi not installed. Please run: pip install curl_cffi")
    sys.exit(1)

# ============================================================================
# CONSTANTS
# ============================================================================

RSS_FEED_URL = "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"
REQUEST_TIMEOUT = 30  # seconds
DEFAULT_SUMMARY_COUNT = 10  # Number of headlines to show in summary mode
DEFAULT_DAYS = 1  # Default number of days to filter articles (today + yesterday)
DEFAULT_COUNT = 50  # Default number of articles in full mode

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_rss_feed(url):
    """
    Fetch RSS feed content from a URL with browser-like TLS fingerprint.

    Args:
        url (str): URL of the RSS feed

    Returns:
        str: XML content of the RSS feed

    Raises:
        Exception: If the request fails
    """
    try:
        # Use curl_cffi with Chrome impersonation to bypass potential restrictions
        session = requests.Session()

        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            impersonate="chrome120"
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"Failed to fetch RSS feed: {str(e)}")


def parse_rss_feed(xml_content):
    """
    Parse RSS feed XML to extract article items.

    Args:
        xml_content (str): XML content of the RSS feed

    Returns:
        list: List of dictionaries containing article data
              Each dict has: title, link, description, pubDate
    """
    soup = BeautifulSoup(xml_content, 'xml')

    # Find all items in the RSS feed
    items = soup.find_all('item')

    articles = []
    for item in items:
        # Extract basic fields
        title = item.find('title')
        link = item.find('link')
        description = item.find('description')
        pub_date = item.find('pubDate')

        # Also check for content:encoded which might have richer content
        content_encoded = item.find('content:encoded')
        if not content_encoded:
            content_encoded = item.find('encoded')

        # Use content:encoded if available, otherwise use description
        content = content_encoded if content_encoded else description

        article = {
            'title': title.get_text(strip=True) if title else 'No Title',
            'link': link.get_text(strip=True) if link else '',
            'description': content.get_text(strip=True) if content else description.get_text(strip=True) if description else '',
            'pubDate': pub_date.get_text(strip=True) if pub_date else 'Date unknown'
        }

        articles.append(article)

    return articles


def format_date(date_str):
    """
    Try to format a date string into a more readable format.

    Args:
        date_str (str): Date string (usually RFC 2822 format from RSS)

    Returns:
        str: Formatted date string
    """
    try:
        # RSS feeds typically use RFC 2822 format
        # Example: "Wed, 22 Jan 2026 10:30:00 GMT"
        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except:
        pass

    try:
        # Try alternative format without timezone
        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except:
        pass

    try:
        # Try parsing with more flexible timezone handling
        # Remove timezone abbreviations and parse
        date_clean = re.sub(r'\s+[A-Z]{3,4}$', '', date_str)
        dt = datetime.strptime(date_clean, '%a, %d %b %Y %H:%M:%S')
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except:
        pass

    # If all parsing fails, return original
    return date_str


def parse_article_date(date_str):
    """
    Parse article date string to datetime object for filtering.

    Args:
        date_str (str): Date string from RSS feed

    Returns:
        datetime: Parsed datetime object, or None if parsing fails
    """
    try:
        # RSS feeds typically use RFC 2822 format
        # Example: "Wed, 22 Jan 2026 10:30:00 GMT"
        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
        return dt
    except:
        pass

    try:
        # Try alternative format without timezone
        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        return dt
    except:
        pass

    try:
        # Try parsing with more flexible timezone handling
        # Remove timezone abbreviations and parse
        date_clean = re.sub(r'\s+[A-Z]{3,4}$', '', date_str)
        dt = datetime.strptime(date_clean, '%a, %d %b %Y %H:%M:%S')
        return dt
    except:
        pass

    # If all parsing fails, return None
    return None


def filter_articles_by_days(articles, days=None):
    """
    Filter articles to only include those from the past N days.

    Args:
        articles (list): List of article dictionaries
        days (int): Number of days to include (None = no filtering)

    Returns:
        list: Filtered list of articles
    """
    if days is None:
        return articles

    # Calculate cutoff date (today minus N days)
    cutoff_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_date = cutoff_date.replace(day=cutoff_date.day - days)

    filtered = []
    for article in articles:
        article_date = parse_article_date(article.get('pubDate', ''))

        # If we can't parse the date, include it (fail-open)
        if article_date is None:
            filtered.append(article)
            continue

        # Remove timezone info for comparison
        article_date_naive = article_date.replace(tzinfo=None)

        # Include if article is newer than cutoff
        if article_date_naive >= cutoff_date:
            filtered.append(article)

    return filtered


def html_to_formatted_text(html_content):
    """
    Convert HTML content to formatted text with rich markup.

    Args:
        html_content (str): HTML content

    Returns:
        str: Formatted text with rich markup
    """
    if not html_content or html_content == 'No description':
        return html_content

    # Convert HTML to markdown
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True  # Images don't display well in terminal
    h.ignore_emphasis = False  # Keep bold/italic
    h.body_width = 0  # No wrapping - let rich handle it
    h.unicode_snob = True  # Use unicode characters
    h.wrap_links = False
    h.skip_internal_links = False
    h.inline_links = True
    h.protect_links = True
    h.mark_code = True

    text = h.handle(html_content)

    # Clean up the markdown
    # Remove excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Convert markdown links to just text (terminal-friendly)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove image references
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)

    # Escape square brackets to prevent rich markup interpretation
    text = text.replace('[', '\\[').replace(']', '\\]')

    # Convert markdown formatting to rich markup
    # **bold** -> [bold]bold[/bold]
    text = re.sub(r'\*\*([^\*\n]+?)\*\*', r'[bold]\1[/bold]', text)

    # *italic* -> [italic]italic[/italic]
    text = re.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', r'[italic]\1[/italic]', text)

    # Headers with color
    text = re.sub(r'^###\s+(.+)$', r'\n[bold cyan]### \1[/bold cyan]', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s+(.+)$', r'\n[bold cyan]## \1[/bold cyan]', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s+(.+)$', r'\n[bold cyan]# \1[/bold cyan]', text, flags=re.MULTILINE)

    # Bullet points
    text = re.sub(r'^  \*\s+', '    ◦ ', text, flags=re.MULTILINE)
    text = re.sub(r'^\*\s+', '  • ', text, flags=re.MULTILINE)
    text = re.sub(r'^  -\s+', '    ◦ ', text, flags=re.MULTILINE)
    text = re.sub(r'^-\s+', '  • ', text, flags=re.MULTILINE)

    return text.strip()


def display_articles(articles, summary_only=False, count=None, console=None):
    """
    Display articles in a formatted way using rich.

    Args:
        articles (list): List of article dictionaries
        summary_only (bool): Whether to show brief headlines only
        count (int): Number of articles to display
        console (Console): Rich console object
    """
    if console is None:
        console = Console()

    # Determine how many articles to show
    if count is None:
        if summary_only:
            count = DEFAULT_SUMMARY_COUNT
            articles_to_show = articles[:count]
        else:
            # Show all articles in full mode by default
            articles_to_show = articles
    else:
        # Limit to requested count
        articles_to_show = articles[:count]

    if not articles_to_show:
        console.print("[yellow]No articles found in the RSS feed.[/yellow]")
        return

    # Print feed header
    console.print("\n")
    header_text = Text("WSJ Markets News", style="bold white", justify="center")
    console.print(Panel(header_text, border_style="blue", padding=(1, 2)))
    console.print(f"[dim]Showing {len(articles_to_show)} of {len(articles)} articles[/dim]", justify="center")
    console.print("\n" + "═" * console.width + "\n")

    # Display each article
    for i, article in enumerate(articles_to_show, 1):
        # Format title
        title_text = Text(f"{i}. {article['title']}", style="bold cyan")
        console.print(title_text)

        # Format date
        formatted_date = format_date(article['pubDate'])
        console.print(f"[dim]{formatted_date}[/dim]")

        # Show link
        if article['link']:
            console.print(f"[blue underline]{article['link']}[/blue underline]")

        # Show description in full mode
        if not summary_only and article['description']:
            formatted_desc = html_to_formatted_text(article['description'])
            console.print()
            console.print(formatted_desc, markup=True, highlight=False, soft_wrap=True)

        # Separator between articles
        if i < len(articles_to_show):
            console.print("\n" + "─" * console.width + "\n")

    # Footer
    console.print("\n" + "═" * console.width + "\n")

    if summary_only:
        console.print("[dim italic](Run without --summary to see full article content)[/dim italic]", justify="center")
    console.print()


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to fetch and display WSJ Markets RSS feed.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Fetch and display the latest WSJ Markets news from RSS feed'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show brief headlines only (default: show full content)'
    )
    parser.add_argument(
        '--count',
        type=int,
        default=DEFAULT_COUNT,
        help=f'Number of articles to display (default: {DEFAULT_COUNT} for full mode, {DEFAULT_SUMMARY_COUNT} for summary)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS,
        help=f'Filter articles to only include those from the past N days (default: {DEFAULT_DAYS} for today + yesterday)'
    )
    args = parser.parse_args()

    console = Console()

    try:
        # Step 1: Fetch RSS feed
        console.print("[cyan]Fetching WSJ Markets RSS feed...[/cyan]")
        rss_xml = fetch_rss_feed(RSS_FEED_URL)

        # Step 2: Parse RSS feed
        console.print("[cyan]Parsing feed content...[/cyan]")
        articles = parse_rss_feed(rss_xml)

        if not articles:
            console.print("[yellow]No articles found in the feed.[/yellow]")
            return 1

        # Step 3: Filter articles by date if requested
        if args.days is not None:
            articles = filter_articles_by_days(articles, args.days)
            if not articles:
                console.print(f"[yellow]No articles found from the past {args.days} day(s).[/yellow]")
                return 1

        # Step 4: Display articles
        display_articles(articles, summary_only=args.summary, count=args.count, console=console)

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]", markup=False)
        console.print("[yellow]If you encountered a connection error, please check your internet connection and try again.[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
