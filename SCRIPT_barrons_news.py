"""
Barron's News Fetcher (via Perigon API)
========================================

Fetches and displays the most recent news articles from Barron's using the
Perigon API in a clean, readable terminal format.

Installation:
    pip install requests python-dateutil rich

Configuration:
    export PERIGON_API_KEY="your_api_key_here"

Usage:
    python SCRIPT_barrons_news.py                    # Show 50 most recent articles (default)
    python SCRIPT_barrons_news.py --count 25         # Show top 25 articles
    python SCRIPT_barrons_news.py --all              # Show all available articles
    python SCRIPT_barrons_news.py --days 3           # Fetch articles from past 3 days

Features:
    - Fetches latest Barron's news via Perigon API
    - Beautiful terminal formatting with rich markup
    - Sorted by publication date (most recent first)
    - Shows title, description, date, and URL for each article
    - Configurable article count with --count flag
    - Configurable date range with --days flag
    - Default shows 50 most recent articles
    - Use --all to show every available article

Requirements:
    - Python 3.7+
    - requests (for API calls)
    - python-dateutil (for date parsing)
    - rich (for terminal formatting)
    - Valid Perigon API key set as environment variable

How it works:
    1. Fetches articles from Perigon API with source=barrons.com
    2. Filters by date range (default: past 24 hours)
    3. Sorts by publication date (most recent first)
    4. Displays in formatted terminal output
    5. Shows configurable number of articles (default: 50)

Output includes:
    - Article title (in colored panel)
    - Publication date (formatted for readability)
    - Article description/summary
    - Article URL (clickable in most terminals)

Note:
    Requires a valid Perigon API key. Sign up at https://www.goperigon.com/
    to get an API key, then set it as an environment variable.
"""

import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

try:
    import requests
except ImportError:
    print("Error: requests not installed. Please run: pip install requests python-dateutil rich")
    sys.exit(1)

# ============================================================================
# CONSTANTS
# ============================================================================

PERIGON_BASE_URL = "https://api.goperigon.com/v1"
BARRONS_DOMAIN = "barrons.com"
REQUEST_TIMEOUT = 30  # seconds
DEFAULT_ARTICLE_COUNT = 50  # Show top 50 by default
DEFAULT_DAYS_BACK = 1  # Fetch from past 1 day by default
MAX_RETRIES = 3  # Max retries for rate limiting
RETRY_DELAY = 5  # Initial delay in seconds for exponential backoff

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_barrons_articles(api_key, days_back=DEFAULT_DAYS_BACK):
    """
    Fetch Barron's articles from Perigon API with retry logic.

    Args:
        api_key (str): Perigon API key
        days_back (int): Number of days back to fetch articles

    Returns:
        dict: API response with articles

    Raises:
        Exception: If the request fails after all retries
    """
    # Calculate date range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_back)

    # Format dates for API (YYYY-MM-DD)
    from_date = start_time.strftime("%Y-%m-%d")
    to_date = end_time.strftime("%Y-%m-%d")

    # Build API request
    endpoint = f"{PERIGON_BASE_URL}/all"
    params = {
        "apiKey": api_key,
        "source": BARRONS_DOMAIN,
        "from": from_date,
        "to": to_date,
        "sortBy": "date",  # Most recent first
        "showNumResults": "true",
        "showReprints": "false",
        "size": 100  # Request up to 100 articles per call
    }

    # Retry logic with exponential backoff
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(endpoint, params=params, timeout=REQUEST_TIMEOUT)

            # Handle rate limiting (503) with retry
            if response.status_code == 503:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff: 5s, 10s, 20s
                    print(f"  ⚠️  Rate limit hit (attempt {attempt + 1}/{MAX_RETRIES})")
                    print(f"  ⏳ Waiting {delay}s before retry...")
                    time.sleep(delay)
                    continue
                else:
                    raise Exception(f"API rate limit exceeded after {MAX_RETRIES} retries. Please try again later.")

            # Raise for other HTTP errors
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise Exception("Authentication failed. Please check your PERIGON_API_KEY.")
            elif response.status_code == 403:
                raise Exception("Access forbidden. Your API key may not have access to this endpoint.")
            elif response.status_code == 503:
                # Already handled above, but catch it here too
                continue
            else:
                raise Exception(f"API request failed with status {response.status_code}: {str(e)}")
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                print(f"  ⚠️  Request timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                print(f"  ⏳ Retrying in {delay}s...")
                time.sleep(delay)
                continue
            raise Exception("API request timed out after multiple retries. Please try again.")
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")

    # If we exhausted all retries
    raise Exception(f"API request failed after {MAX_RETRIES} retries.")


def format_date(date_str):
    """
    Format a date string into a more readable format.

    Args:
        date_str (str): ISO 8601 date string from API

    Returns:
        str: Formatted date string
    """
    try:
        dt = date_parser.parse(date_str)
        # Convert to local time if needed
        return dt.strftime('%B %d, %Y at %I:%M %p')
    except:
        # If parsing fails, return original
        return date_str


def display_articles(articles, count=None, show_all=False, days_back=DEFAULT_DAYS_BACK, console=None):
    """
    Display articles in a formatted way using rich.

    Args:
        articles (list): List of article dictionaries from API
        count (int): Number of articles to display (None = default)
        show_all (bool): Whether to show all available articles
        days_back (int): Number of days articles were fetched from
        console (Console): Rich console object
    """
    if console is None:
        console = Console()

    total_articles = len(articles)

    if not articles:
        console.print("[yellow]No articles found from Barron's in the specified time range.[/yellow]")
        return

    # Determine how many articles to show
    if show_all:
        articles_to_show = articles
    elif count is not None:
        articles_to_show = articles[:count]
    else:
        # Default behavior: show DEFAULT_ARTICLE_COUNT
        articles_to_show = articles[:DEFAULT_ARTICLE_COUNT]

    num_showing = len(articles_to_show)

    # Print feed header
    console.print("\n")
    header_text = Text("Barron's News", style="bold white", justify="center")
    console.print(Panel(header_text, border_style="blue", padding=(1, 2)))

    # Show article count and date range
    day_text = "day" if days_back == 1 else f"{days_back} days"
    console.print(
        f"[dim]Showing {num_showing} of {total_articles} articles from past {day_text}[/dim]",
        justify="center"
    )
    console.print("\n" + "═" * console.width + "\n")

    # Display each article
    for i, article in enumerate(articles_to_show, 1):
        # Extract article data
        title = article.get('title', 'No title')
        description = article.get('description', '')
        url = article.get('url', '')
        pub_date = article.get('pubDate', '')

        # Format title
        title_text = Text(f"{i}. {title}", style="bold cyan")
        console.print(title_text)

        # Format and show date
        if pub_date:
            formatted_date = format_date(pub_date)
            console.print(f"[dim]{formatted_date}[/dim]")

        # Show URL
        if url:
            console.print(f"[blue underline]{url}[/blue underline]")

        # Show description
        if description:
            console.print()
            # Clean up description and limit length if too long
            clean_desc = description.strip()
            console.print(f"{clean_desc}")

        # Separator between articles
        if i < num_showing:
            console.print("\n" + "─" * console.width + "\n")

    # Footer
    console.print("\n" + "═" * console.width + "\n")

    # Show hint if not showing all
    if not show_all and total_articles > num_showing:
        remaining = total_articles - num_showing
        console.print(
            f"[dim italic]({remaining} more articles available - use --all to see everything)[/dim italic]",
            justify="center"
        )
    console.print()


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to fetch and display Barron's news articles.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Fetch and display the latest Barron\'s news via Perigon API'
    )
    parser.add_argument(
        '--count',
        type=int,
        help=f'Number of articles to display (default: {DEFAULT_ARTICLE_COUNT})'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all available articles'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS_BACK,
        help=f'Number of days back to fetch articles (default: {DEFAULT_DAYS_BACK})'
    )
    args = parser.parse_args()

    console = Console()

    # Get API key from environment
    api_key = os.environ.get('PERIGON_API_KEY')
    if not api_key:
        console.print("[red]Error: PERIGON_API_KEY environment variable not set[/red]")
        console.print("\n[yellow]Please set your API key:[/yellow]")
        console.print("  export PERIGON_API_KEY='your_api_key_here'")
        console.print("\n[dim]Get an API key at: https://www.goperigon.com/[/dim]")
        return 1

    try:
        # Step 1: Fetch articles from API
        day_text = "day" if args.days == 1 else f"{args.days} days"
        console.print(f"[cyan]Fetching Barron's articles from past {day_text}...[/cyan]")
        data = fetch_barrons_articles(api_key, days_back=args.days)

        # Step 2: Extract articles
        articles = data.get('articles', [])
        num_results = data.get('numResults', len(articles))

        if num_results == 0:
            console.print(f"[yellow]No articles found from Barron's in the past {day_text}.[/yellow]")
            return 0

        # Step 3: Display articles
        display_articles(
            articles,
            count=args.count,
            show_all=args.all,
            days_back=args.days,
            console=console
        )

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        console.print("[yellow]If you encountered an API error, please check your API key and try again.[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
