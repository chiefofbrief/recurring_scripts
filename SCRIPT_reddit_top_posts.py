#!/usr/bin/env python3
"""
Reddit Top Posts Fetcher (via SociaVault API)
==============================================

Fetches and displays the top 15 upvoted posts from selected investment subreddits
from the past day using the SociaVault API in a clean, readable terminal format.

SUBREDDITS COVERED:
    - r/ValueInvesting (value investing strategies and discussions)
    - r/stocks (stock market discussions and analysis)
    - r/options (options trading strategies and education)

INSTALLATION:
    pip install requests rich

CONFIGURATION:
    export SOCIAVAULT_API_KEY="your_api_key_here"

BASIC USAGE:
    python SCRIPT_reddit_top_posts.py                    # Default: top 15 from past day
    python SCRIPT_reddit_top_posts.py --count 10         # Show top 10 per subreddit
    python SCRIPT_reddit_top_posts.py --timeframe week   # Show from past week

PARAMETERS:
    --count      Number of posts per subreddit (default: 15)
    --timeframe  Time period: hour, day, week, month, year, all (default: day)

OUTPUT FORMAT:
    - Post title (bold, cyan)
    - Upvotes (green) and comments (blue)
    - Upvote ratio percentage
    - Author username
    - Clickable URL
    - Post body text (first 300 chars if available)

API COST:
    - Credit check: 0 credits (runs automatically)
    - Per subreddit: 1 credit
    - Total per run: 3 credits

FEATURES:
    - Smart retry logic with exponential backoff
    - Rate limiting protection (handles 429 errors)
    - Timeout handling with retries
    - Beautiful terminal formatting
    - Automatic credit checking

REQUIREMENTS:
    - Python 3.7+
    - requests (for API calls)
    - rich (for terminal formatting)
    - Valid SociaVault API key

TROUBLESHOOTING:
    - "API key not set": Export SOCIAVAULT_API_KEY environment variable
    - "Insufficient credits": Check your SociaVault account
    - Connection timeout: Script retries up to 3 times with exponential backoff
"""

import os
import sys
import time
import argparse
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

try:
    import requests
except ImportError:
    print("Error: requests not installed. Please run: pip install requests rich")
    sys.exit(1)

# ============================================================================
# CONSTANTS
# ============================================================================

SOCIAVAULT_BASE_URL = "https://api.sociavault.com/v1"
DEFAULT_POST_COUNT = 15  # Show top 15 posts per subreddit
DEFAULT_TIMEFRAME = "day"  # Fetch from past day
SUBREDDITS = ["ValueInvesting", "stocks", "options"]
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3  # Max retries for rate limiting/timeouts
RETRY_DELAY = 2  # Initial delay in seconds for exponential backoff

# ============================================================================
# API CLIENT
# ============================================================================

class SociaVaultClient:
    """Client for interacting with SociaVault Reddit API."""

    def __init__(self, api_key: str):
        """Initialize client with API key."""
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def check_credits(self):
        """Check available API credits (costs 0 credits)."""
        response = requests.get(
            f"{SOCIAVAULT_BASE_URL}/credits",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    def fetch_subreddit_posts(self, subreddit: str, timeframe: str = "day", sort: str = "top"):
        """
        Fetch posts from a subreddit with retry logic.

        Args:
            subreddit: Subreddit name (without r/ prefix)
            timeframe: Time period (hour, day, week, month, year, all)
            sort: Sort method (top, new, hot, rising, controversial)

        Returns:
            API response as dictionary (typically ~25 posts per page)

        Raises:
            Exception: If the request fails after all retries
        """
        params = {
            "subreddit": subreddit,
            "timeframe": timeframe,
            "sort": sort,
            "trim": False
        }

        # Retry logic with exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    f"{SOCIAVAULT_BASE_URL}/scrape/reddit/subreddit",
                    headers=self.headers,
                    params=params,
                    timeout=REQUEST_TIMEOUT
                )

                # Handle rate limiting (429) with retry
                if response.status_code == 429:
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                        print(f"  ⚠️  Rate limit hit for r/{subreddit} (attempt {attempt + 1}/{MAX_RETRIES})")
                        print(f"  ⏳ Waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        raise Exception(f"API rate limit exceeded for r/{subreddit} after {MAX_RETRIES} retries.")

                # Raise for other HTTP errors
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise Exception("Authentication failed. Please check your SOCIAVAULT_API_KEY.")
                elif response.status_code == 402:
                    raise Exception("Insufficient credits. Please check your SociaVault account.")
                elif response.status_code == 403:
                    raise Exception("Access forbidden. Your API key may not have access to this endpoint.")
                elif response.status_code == 429:
                    # Already handled above, but catch it here too
                    continue
                else:
                    raise Exception(f"API request failed with status {response.status_code}: {str(e)}")
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2 ** attempt)
                    print(f"  ⚠️  Request timeout for r/{subreddit} (attempt {attempt + 1}/{MAX_RETRIES})")
                    print(f"  ⏳ Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                raise Exception(f"API request timed out for r/{subreddit} after multiple retries.")
            except requests.exceptions.RequestException as e:
                raise Exception(f"API request failed for r/{subreddit}: {str(e)}")

        # If we exhausted all retries
        raise Exception(f"API request failed for r/{subreddit} after {MAX_RETRIES} retries.")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_all_subreddit_posts(client, subreddits, timeframe, console):
    """
    Fetch posts from all specified subreddits.

    Args:
        client: SociaVaultClient instance
        subreddits: List of subreddit names
        timeframe: Time period to fetch from
        console: Rich console object

    Returns:
        Dictionary mapping subreddit names to lists of posts
    """
    all_posts = {}

    for subreddit in subreddits:
        try:
            console.print(f"[cyan]  Fetching r/{subreddit}...[/cyan]")
            data = client.fetch_subreddit_posts(subreddit, timeframe=timeframe, sort="top")

            # Extract posts from nested structure
            posts_dict = data.get('data', {}).get('posts', {})
            if isinstance(posts_dict, dict):
                posts = list(posts_dict.values())
            else:
                posts = []

            # Sort by score (upvotes) in descending order
            posts.sort(key=lambda p: p.get('score', 0), reverse=True)

            all_posts[subreddit] = posts
            console.print(f"[green]  ✓ Found {len(posts)} posts from r/{subreddit}[/green]")

        except Exception as e:
            console.print(f"[yellow]  ⚠ Error fetching r/{subreddit}: {str(e)}[/yellow]")
            all_posts[subreddit] = []

    return all_posts


def display_posts(all_posts, count, timeframe, console):
    """
    Display posts in a formatted way using rich.

    Args:
        all_posts: Dictionary mapping subreddit names to lists of posts
        count: Number of posts to display per subreddit
        timeframe: Time period posts were fetched from
        console: Rich console object
    """
    total_posts = sum(len(posts) for posts in all_posts.values())

    if total_posts == 0:
        console.print("[yellow]No posts found from any subreddit.[/yellow]")
        return

    # Print feed header
    console.print("\n")
    header_text = Text("Reddit Top Posts - Investment Subreddits", style="bold white", justify="center")
    console.print(Panel(header_text, border_style="blue", padding=(1, 2)))

    # Show summary
    time_desc = {
        "hour": "past hour",
        "day": "past day",
        "week": "past week",
        "month": "past month",
        "year": "past year",
        "all": "all time"
    }
    console.print(
        f"[dim]Top {count} posts from {time_desc.get(timeframe, timeframe)} • r/{', r/'.join(all_posts.keys())}[/dim]",
        justify="center"
    )
    console.print("\n" + "═" * console.width + "\n")

    # Display posts for each subreddit
    for subreddit_idx, (subreddit, posts) in enumerate(all_posts.items()):
        if not posts:
            continue

        # Subreddit header
        subreddit_header = Text(f"r/{subreddit}", style="bold yellow")
        console.print(subreddit_header)
        console.print(f"[dim]Showing top {min(count, len(posts))} of {len(posts)} posts[/dim]\n")

        # Display top N posts
        posts_to_show = posts[:count]

        for i, post in enumerate(posts_to_show, 1):
            # Extract post data
            title = post.get('title', 'No title')
            score = post.get('score', 0)
            num_comments = post.get('num_comments', 0)
            url = post.get('url', '')
            selftext = post.get('selftext', '')
            author = post.get('author', 'unknown')
            upvote_ratio = post.get('upvote_ratio', 0)

            # Format title with number
            title_text = Text(f"{i}. {title}", style="bold cyan")
            console.print(title_text)

            # Stats line
            stats = f"[green]↑ {score:,}[/green] upvotes  •  [blue]{num_comments:,}[/blue] comments"
            if upvote_ratio:
                stats += f"  •  [dim]{int(upvote_ratio * 100)}% upvoted[/dim]"
            stats += f"  •  [dim]u/{author}[/dim]"
            console.print(stats)

            # Show URL
            if url:
                console.print(f"[blue underline]{url}[/blue underline]")

            # Show post body if it's a text post
            if selftext:
                console.print()
                # Truncate long posts
                max_length = 300
                clean_text = selftext.strip()
                if len(clean_text) > max_length:
                    clean_text = clean_text[:max_length] + "..."

                console.print(f"[dim]{clean_text}[/dim]")

            # Separator between posts
            if i < len(posts_to_show):
                console.print("\n" + "─" * console.width + "\n")

        # Separator between subreddits
        if subreddit_idx < len(all_posts) - 1:
            console.print("\n" + "═" * console.width + "\n")

    # Footer
    console.print("\n" + "═" * console.width + "\n")
    console.print()


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to fetch and display Reddit top posts.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Fetch and display top Reddit posts from investment subreddits'
    )
    parser.add_argument(
        '--count',
        type=int,
        default=DEFAULT_POST_COUNT,
        help=f'Number of posts to display per subreddit (default: {DEFAULT_POST_COUNT})'
    )
    parser.add_argument(
        '--timeframe',
        default=DEFAULT_TIMEFRAME,
        choices=["hour", "day", "week", "month", "year", "all"],
        help=f'Time period to fetch posts from (default: {DEFAULT_TIMEFRAME})'
    )
    args = parser.parse_args()

    console = Console()

    # Get API key from environment
    api_key = os.environ.get('SOCIAVAULT_API_KEY')
    if not api_key:
        console.print("[red]Error: SOCIAVAULT_API_KEY environment variable not set[/red]")
        console.print("\n[yellow]Please set your API key:[/yellow]")
        console.print("  export SOCIAVAULT_API_KEY='your_api_key_here'")
        return 1

    try:
        # Initialize client
        client = SociaVaultClient(api_key)

        # Check credits (0 cost)
        console.print("[cyan]Checking API credits...[/cyan]")
        credits_info = client.check_credits()
        available_credits = credits_info.get('credits', 'unknown')
        console.print(f"[green]✓ Available credits: {available_credits}[/green]\n")

        # Warn if low on credits
        if isinstance(available_credits, (int, float)) and available_credits < len(SUBREDDITS):
            console.print(f"[yellow]⚠ Warning: Low credits. This operation requires {len(SUBREDDITS)} credits.[/yellow]\n")

        # Fetch posts from all subreddits
        console.print(f"[cyan]Fetching top posts from {len(SUBREDDITS)} subreddits...[/cyan]")
        all_posts = fetch_all_subreddit_posts(client, SUBREDDITS, args.timeframe, console)

        # Display results
        console.print(f"\n[green]✓ Successfully fetched posts (cost: {len(SUBREDDITS)} API credits)[/green]")
        display_posts(all_posts, args.count, args.timeframe, console)

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except requests.exceptions.HTTPError as e:
        console.print(f"\n[red]HTTP Error: {str(e)}[/red]")
        if hasattr(e, 'response') and e.response.status_code == 402:
            console.print("[yellow]Insufficient credits. Please check your SociaVault account.[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
