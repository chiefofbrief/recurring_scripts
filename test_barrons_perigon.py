"""
Test Perigon API for Barron's News from Past Day
=================================================

This script tests whether the Perigon API can fetch news articles from
Barron's (barrons.com) from the past 24 hours.

Requirements:
    pip install requests python-dateutil

Usage:
    export PERIGON_API_KEY="your_api_key_here"
    python test_barrons_perigon.py

"""

import os
import sys
import json
from datetime import datetime, timedelta
from dateutil import parser as date_parser

try:
    import requests
except ImportError:
    print("Error: requests not installed. Please run: pip install requests")
    sys.exit(1)

# Perigon API Configuration
PERIGON_BASE_URL = "https://api.goperigon.com/v1"
API_KEY = os.environ.get("PERIGON_API_KEY")

def test_barrons_api():
    """
    Test fetching Barron's articles from the past day using Perigon API.
    """
    if not API_KEY:
        print("ERROR: PERIGON_API_KEY environment variable not set")
        print("\nPlease set your API key:")
        print("  export PERIGON_API_KEY='your_api_key_here'")
        return False

    # Calculate date range (past 24 hours)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)

    # Format dates for API (ISO 8601 format)
    from_date = start_time.strftime("%Y-%m-%d")
    to_date = end_time.strftime("%Y-%m-%d")

    print("=" * 70)
    print("Testing Perigon API for Barron's News")
    print("=" * 70)
    print(f"Source: barrons.com")
    print(f"Date Range: {from_date} to {to_date} (past 24 hours)")
    print(f"API Key: {'*' * (len(API_KEY) - 4) + API_KEY[-4:] if len(API_KEY) > 4 else '****'}")
    print("=" * 70)
    print()

    # Build API request
    endpoint = f"{PERIGON_BASE_URL}/all"
    params = {
        "apiKey": API_KEY,
        "source": "barrons.com",  # Only Barron's
        "from": from_date,
        "to": to_date,
        "sortBy": "date",  # Most recent first
        "showNumResults": "true",
        "showReprints": "false"
    }

    try:
        print("Making API request...")
        print(f"Endpoint: {endpoint}")
        print(f"Parameters: {json.dumps({k: v for k, v in params.items() if k != 'apiKey'}, indent=2)}")
        print()

        response = requests.get(endpoint, params=params, timeout=30)

        print(f"Response Status: {response.status_code}")
        print()

        if response.status_code == 200:
            data = response.json()

            # Check if articles were returned
            num_results = data.get("numResults", 0)
            articles = data.get("articles", [])

            print("✓ API Request Successful!")
            print(f"✓ Number of Results: {num_results}")
            print()

            if num_results > 0:
                print(f"✓ Found {len(articles)} Barron's articles from the past day")
                print()
                print("Sample Articles:")
                print("-" * 70)

                # Show first 5 articles
                for i, article in enumerate(articles[:5], 1):
                    title = article.get("title", "No title")
                    url = article.get("url", "No URL")
                    pub_date = article.get("pubDate", "")
                    source = article.get("source", {}).get("domain", "Unknown")

                    # Parse and format date
                    try:
                        dt = date_parser.parse(pub_date)
                        formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        formatted_date = pub_date

                    print(f"\n{i}. {title}")
                    print(f"   Source: {source}")
                    print(f"   Published: {formatted_date}")
                    print(f"   URL: {url}")

                print()
                print("-" * 70)
                print()
                print("✓ RESULT: YES, we CAN fetch Barron's news from the past day!")
                print()

                # Show full response structure for first article
                if articles:
                    print("Sample Article Structure (first article):")
                    print(json.dumps(articles[0], indent=2))

                return True
            else:
                print("⚠ No articles found from Barron's in the past day")
                print()
                print("Possible reasons:")
                print("  - Barron's may not have published articles in the past 24 hours")
                print("  - Perigon may not index Barron's in real-time")
                print("  - The source domain might be different (e.g., www.barrons.com)")
                print()
                print("Let's try with www.barrons.com as well...")

                # Try with www subdomain
                params["source"] = "www.barrons.com"
                response2 = requests.get(endpoint, params=params, timeout=30)

                if response2.status_code == 200:
                    data2 = response2.json()
                    num_results2 = data2.get("numResults", 0)

                    if num_results2 > 0:
                        print(f"✓ Found {num_results2} articles with www.barrons.com!")
                        return True
                    else:
                        print("⚠ Still no results with www.barrons.com")

                return False

        elif response.status_code == 401:
            print("✗ Authentication Failed (401)")
            print("  Your API key may be invalid or expired")
            print()
            return False

        elif response.status_code == 403:
            print("✗ Forbidden (403)")
            print("  Your API key may not have access to this endpoint or source")
            print()
            return False

        else:
            print(f"✗ API Request Failed with status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            print()
            return False

    except requests.exceptions.Timeout:
        print("✗ Request timed out")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ Request error: {str(e)}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print()
    success = test_barrons_api()
    print()

    if success:
        print("=" * 70)
        print("CONCLUSION: Perigon API works for fetching Barron's news!")
        print("=" * 70)
        sys.exit(0)
    else:
        print("=" * 70)
        print("CONCLUSION: Unable to verify - need valid API key or no data available")
        print("=" * 70)
        sys.exit(1)
