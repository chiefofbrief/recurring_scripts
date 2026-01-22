"""
International Intrigue Newsletter Fetcher
==========================================

Fetches and displays the most recent post from the International Intrigue newsletter
in a clean, readable terminal format.

Installation:
    pip install curl_cffi beautifulsoup4 rich html2text

Usage:
    python SCRIPT_intl_intrigue.py              # Show full article (default)
    python SCRIPT_intl_intrigue.py --summary    # Show brief summary only

Features:
    - Automatically fetches the latest post from International Intrigue
    - Bypasses Cloudflare protection using curl_cffi
    - Beautiful terminal formatting with rich Markdown rendering
    - Converts HTML to readable, formatted text with bold/italic support
    - Shows full article by default with optional --summary flag
    - No authentication or API keys required

Requirements:
    - Python 3.7+
    - curl_cffi (for bypassing Cloudflare protection)
    - beautifulsoup4 (for HTML parsing)
    - rich (for terminal formatting)
    - html2text (for HTML to Markdown conversion)

How it works:
    1. Fetches the archive page at https://archives.internationalintrigue.io/
    2. Parses HTML to find the newest post link (Beehiiv /p/ pattern)
    3. Fetches the full post content
    4. Extracts title, date (from JSON-LD), and article body
    5. Converts HTML to formatted text with rich markup
    6. Displays with color, bold, italic, and proper bullet points

Output includes:
    - Post title (in colored panel)
    - Publication date (formatted)
    - Full article body with formatting preserved

Note:
    May take a few seconds due to Cloudflare protection. If you get a 503 error,
    simply retry - the bot protection is sometimes temperamental.
"""

import sys
import argparse
import time
import json
import re
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
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

ARCHIVE_URL = "https://archives.internationalintrigue.io/"
REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def fetch_html(url, session=None):
    """
    Fetch HTML content from a URL with browser-like TLS fingerprint.

    Args:
        url (str): URL to fetch
        session: Optional curl_cffi session to reuse

    Returns:
        str: HTML content

    Raises:
        Exception: If the request fails
    """
    try:
        # Use provided session or create a new one with chrome impersonation
        if session is None:
            session = requests.Session()

        # curl_cffi automatically mimics Chrome's TLS fingerprint
        response = session.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            impersonate="chrome120"  # Mimic Chrome 120
        )
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"Failed to fetch {url}: {str(e)}")


def find_latest_post_url(archive_html):
    """
    Parse the archive page to find the URL of the most recent post.

    Args:
        archive_html (str): HTML content of the archive page

    Returns:
        str: Full URL of the latest post

    Raises:
        Exception: If no post link is found
    """
    soup = BeautifulSoup(archive_html, 'html.parser')

    # Beehiiv newsletters use /p/ pattern for posts
    # Find all links with href starting with /p/
    all_links = soup.find_all('a', href=True)

    for link in all_links:
        href = link['href']
        # Look for Beehiiv post pattern: /p/post-slug
        if href.startswith('/p/') and len(href) > 3:
            return construct_full_url(href)

    # Fallback: try other common patterns
    for link in all_links:
        href = link['href']
        # Look for links that contain post-like patterns
        if any(pattern in href.lower() for pattern in ['/p/', '/post/', '/article/']):
            if 'archive' not in href.lower() and 'about' not in href.lower():
                return construct_full_url(href)

    raise Exception("Could not find any post links in the archive page")


def construct_full_url(href):
    """
    Construct a full URL from a potentially relative link.

    Args:
        href (str): Link href attribute

    Returns:
        str: Full URL
    """
    if href.startswith('http'):
        return href
    elif href.startswith('/'):
        return f"https://archives.internationalintrigue.io{href}"
    else:
        return f"https://archives.internationalintrigue.io/{href}"


def extract_post_content(post_html):
    """
    Extract title, date, and body content from a post's HTML.

    Args:
        post_html (str): HTML content of the post page

    Returns:
        dict: Dictionary containing 'title', 'date', and 'body'
    """
    soup = BeautifulSoup(post_html, 'html.parser')

    # Extract title
    title = None
    # Try JSON-LD structured data first (most reliable for Beehiiv)
    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            if 'headline' in data:
                title = data['headline']
        except:
            pass

    if not title:
        title_tag = soup.find('h1')
        if not title_tag:
            title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text().strip()
        else:
            title = "Unknown Title"

    # Extract date
    date = None
    # Try JSON-LD first
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            if 'datePublished' in data:
                date = data['datePublished']
        except:
            pass

    # Try time element
    if not date:
        date_element = soup.find('time')
        if date_element:
            date = date_element.get_text().strip()
            # Also try datetime attribute
            if not date and date_element.get('datetime'):
                date = date_element['datetime']

    # Try meta tags for date
    if not date:
        date_meta = soup.find('meta', property='article:published_time')
        if not date_meta:
            date_meta = soup.find('meta', attrs={'name': 'date'})
        if date_meta and date_meta.get('content'):
            date = date_meta['content']

    if not date:
        date = "Date unknown"

    # Extract body content
    body = None

    # Look for article element or main content
    article = soup.find('article')
    if not article:
        article = soup.find('div', class_=lambda c: c and any(
            keyword in c.lower() for keyword in ['content', 'article', 'post', 'body', 'entry']
        ))
    if not article:
        article = soup.find('main')

    if article:
        # Remove script, style, nav, header, and footer tags
        for tag in article.find_all(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()

        # Get HTML content and convert to text
        body_html = str(article)

        # Convert HTML to markdown-style text
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
        body = h.handle(body_html)
    else:
        body = "Could not extract article body"

    return {
        'title': title,
        'date': date,
        'body': body
    }


def format_date(date_str):
    """
    Try to format a date string into a more readable format.

    Args:
        date_str (str): Date string in various formats

    Returns:
        str: Formatted date string
    """
    try:
        # Try parsing ISO format
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%B %d, %Y')
    except:
        pass

    return date_str


def display_post(post_data, summary_only=False, console=None):
    """
    Display the post content in a formatted way using rich.

    Args:
        post_data (dict): Dictionary with 'title', 'date', and 'body'
        summary_only (bool): Whether to show brief summary only
        console (Console): Rich console object
    """
    if console is None:
        console = Console()

    # Format the title
    title_text = Text(post_data['title'], style="bold cyan", justify="center")

    # Format the date
    formatted_date = format_date(post_data['date'])
    date_text = Text(formatted_date, style="dim italic", justify="center")

    # Print header
    console.print("\n")
    console.print(Panel(title_text, border_style="cyan", padding=(1, 2)))
    console.print(date_text)
    console.print("\n" + "─" * console.width + "\n")

    # Process body
    body = post_data['body']

    if summary_only:
        # Extract just the key headlines/bullet points for summary
        lines = body.split('\n')
        summary_lines = []
        in_briefing = False

        for line in lines:
            stripped = line.strip()
            # Look for the "Today's briefing" section or main bullet points
            if 'today' in stripped.lower() and 'briefing' in stripped.lower():
                in_briefing = True
                summary_lines.append(line)
                continue
            if in_briefing:
                # Capture bullet points
                if stripped.startswith('—') or stripped.startswith('-') or stripped.startswith('*'):
                    summary_lines.append(line)
                elif stripped and not stripped.startswith('#') and len(summary_lines) > 3:
                    # Stop after we have some bullets and hit a non-bullet line
                    break
            # Also capture main headers
            elif stripped.startswith('###') or stripped.startswith('##'):
                summary_lines.append(line)

        if summary_lines:
            body = '\n'.join(summary_lines)
            body += "\n\n[dim italic](Run without --summary to see full article)[/dim italic]"
        else:
            # Fallback to first ~1000 chars if we can't find structure
            body = body[:1000] + "\n\n[dim italic]...(Run without --summary to see full article)[/dim italic]"

    # Clean up the markdown before rendering
    # Remove excessive blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Simplify: Convert markdown links to just text
    body = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', body)

    # Remove images
    body = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', body)

    # Convert markdown formatting to rich markup
    # **bold** -> [bold]bold[/bold]
    body = re.sub(r'\*\*([^\*]+)\*\*', r'[bold]\1[/bold]', body)

    # *italic* -> [italic]italic[/italic] (but not ** patterns)
    body = re.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', r'[italic]\1[/italic]', body)

    # Headers with color
    body = re.sub(r'^###\s+(.+)$', r'\n[bold cyan]### \1[/bold cyan]', body, flags=re.MULTILINE)
    body = re.sub(r'^##\s+(.+)$', r'\n[bold cyan]## \1[/bold cyan]', body, flags=re.MULTILINE)
    body = re.sub(r'^#\s+(.+)$', r'\n[bold cyan]# \1[/bold cyan]', body, flags=re.MULTILINE)

    # Bullet points
    body = re.sub(r'^  \*\s+', '    ◦ ', body, flags=re.MULTILINE)
    body = re.sub(r'^\*\s+', '  • ', body, flags=re.MULTILINE)
    body = re.sub(r'^  -\s+', '    ◦ ', body, flags=re.MULTILINE)
    body = re.sub(r'^-\s+', '  • ', body, flags=re.MULTILINE)
    body = re.sub(r'^—\s+', '  — ', body, flags=re.MULTILINE)

    # Print with rich markup enabled
    console.print(body, markup=True, highlight=False, soft_wrap=True)
    console.print("\n" + "─" * console.width + "\n")


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to fetch and display the latest International Intrigue post.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Fetch and display the latest International Intrigue newsletter post'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show brief summary only (default: show full article)'
    )
    args = parser.parse_args()

    console = Console()

    try:
        # Create a single curl_cffi session to reuse across requests
        session = requests.Session()

        # Step 1: Fetch archive page
        console.print("[cyan]Fetching archive page...[/cyan]")
        archive_html = fetch_html(ARCHIVE_URL, session=session)

        # Step 2: Find latest post URL
        console.print("[cyan]Finding latest post...[/cyan]")
        post_url = find_latest_post_url(archive_html)
        console.print(f"[dim]Post URL: {post_url}[/dim]\n")

        # Add a small delay between requests to appear more human-like
        time.sleep(1)

        # Step 3: Fetch post content
        console.print("[cyan]Fetching post content...[/cyan]")
        post_html = fetch_html(post_url, session=session)

        # Step 4: Extract post data
        console.print("[cyan]Parsing content...[/cyan]")
        post_data = extract_post_content(post_html)

        # Step 5: Display the post
        display_post(post_data, summary_only=args.summary, console=console)

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except Exception as e:
        console.print(f"\n[red]Error: {str(e)}[/red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
