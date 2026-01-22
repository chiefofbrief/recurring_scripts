"""
Market Losers & Most Actives Data Fetcher
==========================================

Fetches biggest stock losers and most actively traded stocks from FMP and AlphaVantage APIs.

Usage:
    python SCRIPT_losers_actives.py

Prerequisites:
    pip install tabulate requests

Environment Variables:
    - FMP_API_KEY: Financial Modeling Prep API key
    - ALPHAVANTAGE_API_KEY: AlphaVantage API key

Output:
    - Table 1: Biggest losers (filtered ≥$1)
      * Symbols marked with * appear in both FMP & AlphaVantage
      * Symbols marked with ► are high-volume (in most actives)
      * Sorted by worst performers (most negative % change)

    - Table 2: Most actively traded stocks (filtered ≥$1)
      * Sorted by volume (highest first)
      * Top 50 from FMP
"""

import requests
import os
import sys
from tabulate import tabulate

# ============================================================================
# CONSTANTS
# ============================================================================

REQUEST_TIMEOUT = 30  # seconds
FMP_LOSERS_URL = "https://financialmodelingprep.com/stable/biggest-losers"
FMP_MOST_ACTIVES_URL = "https://financialmodelingprep.com/stable/most-actives"
ALPHAVANTAGE_LOSERS_URL = "https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS"
MIN_PRICE = 1.00  # Filter stocks below this price

# ============================================================================
# API FUNCTIONS
# ============================================================================

def fetch_fmp_losers(api_key):
    """Fetch biggest losers from Financial Modeling Prep API

    Args:
        api_key: FMP API key

    Returns:
        list: List of loser stocks, or empty list if failed
    """
    try:
        print("Fetching data from FMP...")
        url = f"{FMP_LOSERS_URL}?apikey={api_key}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"  ❌ FMP Error: HTTP {response.status_code}")
            return []

        data = response.json()

        if isinstance(data, dict) and 'Error Message' in data:
            print(f"  ❌ FMP Error: {data['Error Message']}")
            return []

        print(f"  ✓ Fetched {len(data)} losers from FMP")
        return data

    except requests.exceptions.Timeout:
        print(f"  ❌ FMP request timed out after {REQUEST_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"  ❌ FMP Error: {e}")
        return []


def fetch_alphavantage_losers(api_key):
    """Fetch biggest losers from AlphaVantage API

    Args:
        api_key: AlphaVantage API key

    Returns:
        list: List of loser stocks, or empty list if failed
    """
    try:
        print("Fetching data from AlphaVantage...")
        url = f"{ALPHAVANTAGE_LOSERS_URL}&apikey={api_key}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"  ❌ AlphaVantage Error: HTTP {response.status_code}")
            return []

        data = response.json()

        if 'Error Message' in data:
            print(f"  ❌ AlphaVantage Error: {data['Error Message']}")
            return []

        if 'Note' in data:
            print(f"  ⚠️  AlphaVantage Note: {data['Note']}")
            return []

        losers = data.get('top_losers', [])
        print(f"  ✓ Fetched {len(losers)} losers from AlphaVantage")
        return losers

    except requests.exceptions.Timeout:
        print(f"  ❌ AlphaVantage request timed out after {REQUEST_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"  ❌ AlphaVantage Error: {e}")
        return []


def fetch_fmp_most_actives(api_key):
    """Fetch most actively traded stocks from Financial Modeling Prep API

    Args:
        api_key: FMP API key

    Returns:
        list: List of most active stocks, or empty list if failed
    """
    try:
        print("Fetching most actives from FMP...")
        url = f"{FMP_MOST_ACTIVES_URL}?apikey={api_key}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"  ❌ FMP Most Actives Error: HTTP {response.status_code}")
            return []

        data = response.json()

        if isinstance(data, dict) and 'Error Message' in data:
            print(f"  ❌ FMP Most Actives Error: {data['Error Message']}")
            return []

        print(f"  ✓ Fetched {len(data)} most actives from FMP")
        return data

    except requests.exceptions.Timeout:
        print(f"  ❌ FMP Most Actives request timed out after {REQUEST_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"  ❌ FMP Most Actives Error: {e}")
        return []


# ============================================================================
# DATA PROCESSING
# ============================================================================

def normalize_losers_data(fmp_data, av_data, most_actives_data):
    """Normalize data from both APIs into common format and find overlaps

    Args:
        fmp_data: List of losers from FMP
        av_data: List of losers from AlphaVantage
        most_actives_data: List of most active stocks from FMP

    Returns:
        tuple: (combined_list, overlap_count, high_volume_count)
    """
    # Create set of most active symbols for fast lookup
    most_active_symbols = {stock.get('symbol', '') for stock in most_actives_data}

    # Normalize FMP data
    fmp_normalized = []
    fmp_symbols = set()

    for stock in fmp_data:
        symbol = stock.get('symbol', '')
        fmp_symbols.add(symbol)
        fmp_normalized.append({
            'symbol': symbol,
            'name': stock.get('name', 'N/A'),
            'price': float(stock.get('price', 0)),
            'change_pct': float(stock.get('changesPercentage', 0)),
            'source': 'FMP'
        })

    # Normalize AlphaVantage data
    av_normalized = []
    av_symbols = set()

    for stock in av_data:
        symbol = stock.get('ticker', '')
        av_symbols.add(symbol)
        # Parse percentage string like "191.7282%" to float
        change_pct_str = stock.get('change_percentage', '0%').rstrip('%')
        av_normalized.append({
            'symbol': symbol,
            'name': 'N/A',  # AlphaVantage doesn't provide company names
            'price': float(stock.get('price', 0)),
            'change_pct': float(change_pct_str),
            'source': 'AlphaVantage'
        })

    # Find overlaps
    overlap_symbols = fmp_symbols & av_symbols
    overlap_count = len(overlap_symbols)

    # Combine and mark overlaps
    all_stocks = []
    seen_symbols = set()

    # Add FMP stocks
    for stock in fmp_normalized:
        if stock['symbol'] not in seen_symbols:
            stock['in_both'] = stock['symbol'] in overlap_symbols
            stock['high_volume'] = stock['symbol'] in most_active_symbols
            all_stocks.append(stock)
            seen_symbols.add(stock['symbol'])

    # Add AlphaVantage stocks (skip if already added from FMP)
    for stock in av_normalized:
        if stock['symbol'] not in seen_symbols:
            stock['in_both'] = stock['symbol'] in overlap_symbols
            stock['high_volume'] = stock['symbol'] in most_active_symbols
            all_stocks.append(stock)
            seen_symbols.add(stock['symbol'])

    # Count high-volume losers
    high_volume_count = sum(1 for s in all_stocks if s['high_volume'])

    # Sort by worst performers (most negative % change)
    all_stocks.sort(key=lambda x: x['change_pct'])

    return all_stocks, overlap_count, high_volume_count


def display_results(stocks, overlap_count, high_volume_count):
    """Display results in formatted terminal table

    Args:
        stocks: List of normalized stock data
        overlap_count: Number of symbols in both sources
        high_volume_count: Number of high-volume losers
    """
    if not stocks:
        print("\n❌ No data to display")
        return

    # Filter stocks by minimum price
    total_count = len(stocks)
    filtered_stocks = [s for s in stocks if s['price'] >= MIN_PRICE]
    filtered_count = total_count - len(filtered_stocks)

    # Prepare table data
    table_data = []
    for stock in filtered_stocks:
        # Build marker string
        markers = ''
        if stock['in_both']:
            markers += '*'
        if stock['high_volume']:
            markers += '►'
        if not markers:
            markers = ' '

        symbol = f"{markers}{stock['symbol']}"
        price = f"${stock['price']:.2f}"
        change = f"{stock['change_pct']:.2f}%"
        name = stock['name'][:40]  # Truncate long names
        source = stock['source']

        table_data.append([symbol, price, change, name, source])

    # Display table
    headers = ['Symbol', 'Price', 'Change %', 'Company Name', 'Source']
    print("\n" + "="*80)
    print("BIGGEST STOCK LOSERS (Price ≥ $1)")
    print("="*80)
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

    # Display summary
    print("\n" + "-"*80)
    print(f"Total stocks: {total_count} | Displayed: {len(filtered_stocks)} | Filtered (<$1): {filtered_count}")
    print(f"In both APIs: {overlap_count} (marked with *)")
    print(f"High volume: {high_volume_count} (marked with ►)")
    print("-"*80 + "\n")


def display_most_actives(most_actives_data):
    """Display most actively traded stocks in formatted terminal table

    Args:
        most_actives_data: List of most active stocks from FMP
    """
    if not most_actives_data:
        print("\n❌ No most actives data to display")
        return

    # Normalize and filter by price
    normalized = []
    for stock in most_actives_data:
        symbol = stock.get('symbol', '')
        price = float(stock.get('price', 0))
        name = stock.get('name', 'N/A')
        change_pct = float(stock.get('changesPercentage', 0))

        # Filter by minimum price
        if price >= MIN_PRICE:
            normalized.append({
                'symbol': symbol,
                'name': name,
                'price': price,
                'change_pct': change_pct
            })

    total_count = len(most_actives_data)
    filtered_count = total_count - len(normalized)

    # Sort by volume would require volume data, but API doesn't return it
    # Keep original order (already sorted by volume from FMP)

    # Prepare table data
    table_data = []
    for stock in normalized:
        symbol = stock['symbol']
        price = f"${stock['price']:.2f}"
        change = f"{stock['change_pct']:.2f}%"
        name = stock['name'][:50]  # Truncate long names

        table_data.append([symbol, price, change, name])

    # Display table
    headers = ['Symbol', 'Price', 'Change %', 'Company Name']
    print("\n" + "="*80)
    print("MOST ACTIVELY TRADED STOCKS (Price ≥ $1)")
    print("="*80)
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

    # Display summary
    print("\n" + "-"*80)
    print(f"Total stocks: {total_count} | Displayed: {len(normalized)} | Filtered (<$1): {filtered_count}")
    print("-"*80 + "\n")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution function"""
    print("\n" + "="*80)
    print("MARKET LOSERS & MOST ACTIVES DATA FETCHER")
    print("="*80 + "\n")

    # Check for API keys
    fmp_key = os.getenv('FMP_API_KEY')
    av_key = os.getenv('ALPHAVANTAGE_API_KEY')

    if not fmp_key:
        print("❌ Error: FMP_API_KEY environment variable not set")
        print("   Set it with: export FMP_API_KEY='your_key_here'")
        sys.exit(1)

    if not av_key:
        print("❌ Error: ALPHAVANTAGE_API_KEY environment variable not set")
        print("   Set it with: export ALPHAVANTAGE_API_KEY='your_key_here'")
        sys.exit(1)

    # Fetch data from APIs
    fmp_losers = fetch_fmp_losers(fmp_key)
    av_losers = fetch_alphavantage_losers(av_key)
    most_actives = fetch_fmp_most_actives(fmp_key)

    if not fmp_losers and not av_losers:
        print("\n❌ Failed to fetch losers data from both APIs")
        sys.exit(1)

    # Process and display losers results
    print("\nProcessing losers data...")
    stocks, overlap_count, high_volume_count = normalize_losers_data(fmp_losers, av_losers, most_actives)
    display_results(stocks, overlap_count, high_volume_count)

    # Display most actives if available
    if most_actives:
        print("\nProcessing most actives data...")
        display_most_actives(most_actives)
    else:
        print("\n⚠️  Most actives data unavailable")


if __name__ == '__main__':
    main()
