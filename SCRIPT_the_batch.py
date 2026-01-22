"""
The Batch Newsletter Fetcher
=============================

Fetches and displays the most recent issue of The Batch newsletter from DeepLearning.AI
in a clean, readable terminal format.

Installation:
    pip install curl_cffi beautifulsoup4 rich html2text

Usage:
    python SCRIPT_the_batch.py              # Show full article (default)
    python SCRIPT_the_batch.py --summary    # Show brief summary only

Features:
    - Automatically fetches the latest issue of The Batch newsletter
    - Bypasses Cloudflare protection using curl_cffi
    - Beautiful terminal formatting with rich markup
    - Converts HTML to readable, formatted text with bold/italic support
    - Shows full article by default with optional --summary flag
    - Extracts metadata from JSON-LD structured data
    - No authentication or API keys required

Requirements:
    - Python 3.7+
    - curl_cffi (for bypassing Cloudflare/bot protection)
    - beautifulsoup4 (for HTML parsing)
    - rich (for terminal formatting)
    - html2text (for HTML to Markdown conversion)

How it works:
    1. Fetches the archive page at https://www.deeplearning.ai/the-batch/
    2. Parses HTML to find the most recent newsletter entry and its link
    3. Fetches the full newsletter page
    4. Extracts title, publication date from JSON-LD metadata
    5. Extracts article body content
    6. Converts HTML to formatted text with rich markup
    7. Displays with color, bold, italic, and proper bullet points

Output includes:
    - Newsletter title (in colored panel)
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

ARCHIVE_URL = "https://www.deeplearning.ai/the-batch/"
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
    # Try multiple impersonation strategies
    impersonations = ["chrome120", "chrome119", "chrome116", "safari15_5"]

    for impersonate_version in impersonations:
        try:
            # Use provided session or create a new one with chrome impersonation
            if session is None:
                session = requests.Session()

            # curl_cffi automatically mimics browser's TLS fingerprint
            response = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                impersonate=impersonate_version
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            # If this is the last impersonation to try, raise the error
            if impersonate_version == impersonations[-1]:
                raise Exception(f"Failed to fetch {url}: {str(e)}")
            # Otherwise, try the next impersonation
            continue


def find_latest_newsletter_url(archive_html):
    """
    Parse the archive page to find the URL of the most recent newsletter.

    Args:
        archive_html (str): HTML content of the archive page

    Returns:
        str: Full URL of the latest newsletter

    Raises:
        Exception: If no newsletter link is found
    """
    soup = BeautifulSoup(archive_html, 'html.parser')

    # Strategy 1: Look for issue-specific links (most reliable)
    # The Batch uses /issue-XXX/ pattern for actual newsletter issues
    all_links = soup.find_all('a', href=True)

    # First pass: Find issue-XXX links and avoid tag pages
    issue_links = []
    for link in all_links:
        href = link['href']
        # Skip tag pages, navigation, and footer links
        if any(skip in href.lower() for skip in ['/tag/', '#', 'about', 'contact', 'privacy', 'terms', 'login', 'signup', 'search']):
            continue
        # Look for issue-XXX pattern
        if '/issue-' in href.lower():
            issue_links.append(href)

    # If we found issue links, return the first one (most recent)
    if issue_links:
        return construct_full_url(issue_links[0])

    # Strategy 2: Look for article elements or newsletter post cards
    articles = soup.find_all('article')
    if articles:
        # Look for the first article with a link
        for article in articles:
            link = article.find('a', href=True)
            if link and link['href']:
                href = link['href']
                # Skip tag pages
                if '/tag/' not in href:
                    return construct_full_url(href)

    # Strategy 3: Look for any /the-batch/ links that aren't tags or navigation
    for link in all_links:
        href = link['href']
        # Skip tag pages, navigation, and other non-content links
        if any(skip in href.lower() for skip in ['/tag/', '#', 'about', 'contact', 'privacy', 'terms', 'courses']):
            continue
        # Look for newsletter-like patterns
        if '/the-batch/' in href.lower():
            # Make sure it's not just the main page
            if href.strip('/') != 'the-batch':
                return construct_full_url(href)

    raise Exception("Could not find any newsletter links in the archive page")


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
        return f"https://www.deeplearning.ai{href}"
    else:
        return f"https://www.deeplearning.ai/{href}"


def extract_newsletter_content(newsletter_html):
    """
    Extract title, date, and body content from a newsletter's HTML.

    Args:
        newsletter_html (str): HTML content of the newsletter page

    Returns:
        dict: Dictionary containing 'title', 'date', and 'body'
    """
    soup = BeautifulSoup(newsletter_html, 'html.parser')

    # Extract title and date from JSON-LD first (most reliable)
    title = None
    date = None

    json_ld = soup.find('script', type='application/ld+json')
    if json_ld:
        try:
            data = json.loads(json_ld.string)
            # Handle both single object and array of objects
            if isinstance(data, list):
                data = data[0] if data else {}

            if 'headline' in data:
                title = data['headline']
            elif 'name' in data:
                title = data['name']

            if 'datePublished' in data:
                date = data['datePublished']
        except Exception as e:
            pass

    # Fallback to HTML elements if JSON-LD didn't work
    if not title:
        # Try h1 first
        title_tag = soup.find('h1')
        if not title_tag:
            # Try meta tags
            title_meta = soup.find('meta', property='og:title')
            if not title_meta:
                title_meta = soup.find('meta', attrs={'name': 'title'})
            if title_meta and title_meta.get('content'):
                title = title_meta['content']
            else:
                # Last resort: page title
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text().strip()
                else:
                    title = "Unknown Title"
        else:
            title = title_tag.get_text().strip()

    # Extract date if not found in JSON-LD
    if not date:
        # Try time element
        date_element = soup.find('time')
        if date_element:
            # Try datetime attribute first
            if date_element.get('datetime'):
                date = date_element['datetime']
            else:
                date = date_element.get_text().strip()

    # Try meta tags for date
    if not date:
        date_meta = soup.find('meta', property='article:published_time')
        if not date_meta:
            date_meta = soup.find('meta', property='og:published_time')
        if not date_meta:
            date_meta = soup.find('meta', attrs={'name': 'date'})
        if date_meta and date_meta.get('content'):
            date = date_meta['content']

    if not date:
        date = "Date unknown"

    # Extract body content
    body = None

    # Look for article element or main content
    # Try different selectors in order of specificity
    article = soup.find('article')
    if not article:
        article = soup.find('div', class_=lambda c: c and any(
            keyword in c.lower() for keyword in ['content', 'article', 'post', 'body', 'entry', 'newsletter']
        ))
    if not article:
        article = soup.find('main')
    if not article:
        # Try to find a div with id containing content/article
        article = soup.find('div', id=lambda i: i and any(
            keyword in i.lower() for keyword in ['content', 'article', 'post', 'main']
        ))

    if article:
        # Remove unwanted elements
        for tag in article.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        # Remove social sharing buttons, ads, etc.
        for tag in article.find_all(['div', 'section'], class_=lambda c: c and any(
            keyword in c.lower() for keyword in ['share', 'social', 'ad', 'advertisement', 'sidebar', 'related']
        )):
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


def display_newsletter(newsletter_data, summary_only=False, console=None):
    """
    Display the newsletter content in a formatted way using rich.

    Args:
        newsletter_data (dict): Dictionary with 'title', 'date', and 'body'
        summary_only (bool): Whether to show brief summary only
        console (Console): Rich console object
    """
    if console is None:
        console = Console()

    # Format the title
    title_text = Text(newsletter_data['title'], style="bold cyan", justify="center")

    # Format the date
    formatted_date = format_date(newsletter_data['date'])
    date_text = Text(formatted_date, style="dim italic", justify="center")

    # Print header
    console.print("\n")
    console.print(Panel(title_text, border_style="cyan", padding=(1, 2)))
    console.print(date_text)
    console.print("\n" + "─" * console.width + "\n")

    # Process body
    body = newsletter_data['body']

    # Track if we're in summary mode (to add notice later)
    add_summary_notice = False

    if summary_only:
        # Extract key headlines/sections for summary
        lines = body.split('\n')
        summary_lines = []

        for line in lines:
            stripped = line.strip()
            # Capture headers (likely section titles)
            if stripped.startswith('#'):
                summary_lines.append(line)
            # Capture first few bullet points
            elif stripped.startswith('*') or stripped.startswith('-'):
                if len(summary_lines) < 15:  # Limit summary length
                    summary_lines.append(line)

        if summary_lines:
            body = '\n'.join(summary_lines)
            add_summary_notice = True
        else:
            # Fallback to first ~1000 chars if we can't find structure
            body = body[:1000]
            add_summary_notice = True

    # Clean up the markdown before rendering
    # Remove excessive blank lines
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Convert markdown links to just text (terminal-friendly)
    body = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', body)

    # Remove image references
    body = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', body)

    # Escape any remaining square brackets to prevent rich markup interpretation
    body = body.replace('[', '\\[').replace(']', '\\]')

    # Convert markdown formatting to rich markup
    # **bold** -> [bold]bold[/bold]
    # Use a more careful pattern that doesn't cross line boundaries unnecessarily
    body = re.sub(r'\*\*([^\*\n]+?)\*\*', r'[bold]\1[/bold]', body)

    # *italic* -> [italic]italic[/italic] (but not ** patterns)
    # More careful pattern that avoids creating unmatched tags
    body = re.sub(r'(?<!\*)\*([^\*\n]+?)\*(?!\*)', r'[italic]\1[/italic]', body)

    # Headers with color (cyan and bold)
    body = re.sub(r'^###\s+(.+)$', r'\n[bold cyan]### \1[/bold cyan]', body, flags=re.MULTILINE)
    body = re.sub(r'^##\s+(.+)$', r'\n[bold cyan]## \1[/bold cyan]', body, flags=re.MULTILINE)
    body = re.sub(r'^#\s+(.+)$', r'\n[bold cyan]# \1[/bold cyan]', body, flags=re.MULTILINE)

    # Bullet points with proper symbols
    body = re.sub(r'^  \*\s+', '    ◦ ', body, flags=re.MULTILINE)
    body = re.sub(r'^\*\s+', '  • ', body, flags=re.MULTILINE)
    body = re.sub(r'^  -\s+', '    ◦ ', body, flags=re.MULTILINE)
    body = re.sub(r'^-\s+', '  • ', body, flags=re.MULTILINE)

    # Add summary notice if in summary mode (after all conversions)
    if add_summary_notice:
        body += "\n\n[dim][italic](Run without --summary to see full article)[/italic][/dim]"

    # Print with rich markup enabled
    console.print(body, markup=True, highlight=False, soft_wrap=True)
    console.print("\n" + "─" * console.width + "\n")


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """
    Main function to fetch and display the latest The Batch newsletter.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Fetch and display the latest The Batch newsletter from DeepLearning.AI'
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
        console.print("[cyan]Fetching The Batch archive page...[/cyan]")
        archive_html = fetch_html(ARCHIVE_URL, session=session)

        # Step 2: Find latest newsletter URL
        console.print("[cyan]Finding latest newsletter...[/cyan]")
        newsletter_url = find_latest_newsletter_url(archive_html)
        console.print(f"[dim]Newsletter URL: {newsletter_url}[/dim]\n")

        # Add a small delay between requests to appear more human-like
        time.sleep(1.5)

        # Step 3: Fetch newsletter content
        console.print("[cyan]Fetching newsletter content...[/cyan]")
        newsletter_html = fetch_html(newsletter_url, session=session)

        # Step 4: Extract newsletter data
        console.print("[cyan]Parsing content...[/cyan]")
        newsletter_data = extract_newsletter_content(newsletter_html)

        # Step 5: Display the newsletter
        display_newsletter(newsletter_data, summary_only=args.summary, console=console)

        return 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        return 1
    except Exception as e:
        # Use markup=False to avoid interpreting error messages as markup
        console.print("\n[red]Error:[/red]", style="red")
        console.print(str(e), markup=False)
        console.print("[yellow]If you received a 503 error, please try again - Cloudflare protection can be temperamental.[/yellow]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
