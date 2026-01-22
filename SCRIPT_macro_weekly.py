"""
Weekly Macro Market Health Check
==================================

Fetches and analyzes macroeconomic indicators to assess market conditions.

Usage:
    python SCRIPT_macro_weekly.py

Prerequisites:
    pip install tabulate requests

Environment Variables:
    - FMP_API_KEY: Financial Modeling Prep API key
    - ALPHAVANTAGE_API_KEY: AlphaVantage API key

Output:
    - Market Indices: SPY, QQQ, Gold with trend analysis
    - Treasury Rates: 10Y and 2Y yields with trends
    - Economic Indicators: Inflation, Unemployment, Consumer Sentiment

Metrics Calculated:
    - % changes: 1W, 1M, 3M (6M for gold only - SPY/QQQ limited to 100 days)
    - Moving averages: 50-day SMA (200-day for gold only)
    - Treasury yield changes over time
    - Economic indicator trends

Data Sources:
    - AlphaVantage: SPY, QQQ, Gold, Treasury rates, Unemployment
    - FMP: Inflation rate, Consumer sentiment

Note:
    Script includes 12-second delays between AlphaVantage API calls to respect
    rate limits (5 calls per minute). Total runtime: ~2 minutes.
"""

import requests
import os
import sys
import time
from datetime import datetime, timedelta
from tabulate import tabulate

# ============================================================================
# CONSTANTS
# ============================================================================

REQUEST_TIMEOUT = 30  # seconds
API_CALL_DELAY = 12  # seconds between API calls to respect AlphaVantage rate limits (5 calls per minute)
RATE_LIMIT_RETRY_DELAY = 60  # seconds to wait if we hit rate limit
MAX_RATE_LIMIT_RETRIES = 3  # max retries if rate limited
FMP_BASE_URL = "https://financialmodelingprep.com"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# Assets to track
MARKET_ETFS = ['SPY', 'QQQ']
TREASURY_MATURITIES = ['2year', '10year']  # 2Y and 10Y for AlphaVantage

# Economic indicators (from FMP)
FMP_ECONOMIC_INDICATORS = [
    'inflationRate',
    'consumerSentiment'
]

# Lookback periods (in days)
PERIODS = {
    '1W': 7,
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '50D': 50,   # 50-day SMA
    '200D': 200  # 200-day SMA
}

# ============================================================================
# DATE UTILITIES
# ============================================================================

def get_date_n_days_ago(days):
    """Get date N days ago in YYYY-MM-DD format

    Args:
        days: Number of days to look back

    Returns:
        str: Date in YYYY-MM-DD format
    """
    date = datetime.now() - timedelta(days=days)
    return date.strftime('%Y-%m-%d')

def get_today():
    """Get today's date in YYYY-MM-DD format"""
    return datetime.now().strftime('%Y-%m-%d')

# ============================================================================
# API HELPER FUNCTIONS
# ============================================================================

def fetch_with_rate_limit_retry(url, api_name="AlphaVantage"):
    """Fetch data from API with rate limit retry logic

    Args:
        url: Full API URL to fetch
        api_name: Name of API for logging

    Returns:
        dict: JSON response data, or None if failed after retries
    """
    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)

            if response.status_code != 200:
                print(f"    ❌ Error: HTTP {response.status_code}")
                return None

            data = response.json()

            # Check for rate limit messages
            if 'Note' in data or 'Information' in data:
                msg = data.get('Note') or data.get('Information')
                if 'rate limit' in msg.lower() or 'per minute' in msg.lower():
                    if attempt < MAX_RATE_LIMIT_RETRIES - 1:
                        print(f"    ⚠️  Rate limit hit (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})")
                        print(f"    ⏳ Waiting {RATE_LIMIT_RETRY_DELAY}s before retry...")
                        time.sleep(RATE_LIMIT_RETRY_DELAY)
                        continue
                    else:
                        print(f"    ❌ Rate limit exceeded after {MAX_RATE_LIMIT_RETRIES} retries")
                        return None
                else:
                    # Other informational message (not rate limit)
                    print(f"    ⚠️  API Note: {msg[:100]}")
                    return None

            if 'Error Message' in data:
                print(f"    ❌ Error: {data['Error Message']}")
                return None

            return data

        except requests.exceptions.Timeout:
            print(f"    ❌ Request timed out after {REQUEST_TIMEOUT}s")
            return None
        except Exception as e:
            print(f"    ❌ Error: {e}")
            return None

    return None

# ============================================================================
# API FUNCTIONS - HISTORICAL PRICES
# ============================================================================

def fetch_historical_prices(symbol, api_key, days_back=250):
    """Fetch historical price data for a symbol

    Args:
        symbol: Stock/ETF symbol (e.g., 'SPY')
        api_key: FMP API key
        days_back: How many days of history to fetch

    Returns:
        list: Historical price data (newest first), or empty list if failed
    """
    try:
        print(f"  Fetching {symbol} historical data...")
        url = f"{FMP_BASE_URL}/api/v3/historical-price-full/{symbol}?apikey={api_key}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"    ❌ Error: HTTP {response.status_code}")
            return []

        data = response.json()

        if 'Error Message' in data:
            print(f"    ❌ Error: {data['Error Message']}")
            return []

        historical = data.get('historical', [])

        if not historical:
            print(f"    ❌ No historical data returned")
            return []

        # Limit to days_back
        historical = historical[:days_back]
        print(f"    ✓ Fetched {len(historical)} days")
        return historical

    except requests.exceptions.Timeout:
        print(f"    ❌ Request timed out after {REQUEST_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return []

def fetch_stock_historical_alphavantage(symbol, api_key):
    """Fetch historical stock/ETF prices from AlphaVantage

    Args:
        symbol: Stock/ETF symbol (e.g., 'SPY')
        api_key: AlphaVantage API key

    Returns:
        list: Historical price data (format: {'date': 'YYYY-MM-DD', 'close': float}), or empty list if failed
    """
    print(f"  Fetching {symbol} historical data from AlphaVantage...")
    url = f"{ALPHAVANTAGE_BASE_URL}?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={api_key}"

    data = fetch_with_rate_limit_retry(url)
    if not data:
        return []

    # AlphaVantage returns data in 'Time Series (Daily)' key
    time_series = data.get('Time Series (Daily)', {})

    if not time_series:
        print(f"    ❌ No historical data returned")
        return []

    # Convert to standard format (newest first)
    historical = []
    for date_str, values in time_series.items():
        historical.append({
            'date': date_str,
            'close': float(values['4. close'])
        })

    # Sort by date (newest first)
    historical.sort(key=lambda x: x['date'], reverse=True)

    print(f"    ✓ Fetched {len(historical)} days (compact mode: ~100 days)")
    return historical

def fetch_gold_historical_alphavantage(api_key):
    """Fetch historical gold prices from AlphaVantage

    Args:
        api_key: AlphaVantage API key

    Returns:
        list: Historical price data (format: {'date': 'YYYY-MM-DD', 'close': float}), or empty list if failed
    """
    print(f"  Fetching gold historical data from AlphaVantage...")
    url = f"{ALPHAVANTAGE_BASE_URL}?function=GOLD_SILVER_HISTORY&symbol=GOLD&interval=daily&apikey={api_key}"

    data = fetch_with_rate_limit_retry(url)
    if not data:
        return []

    # AlphaVantage returns data in 'data' key
    time_series = data.get('data', [])

    if not time_series:
        print(f"    ❌ No historical data returned")
        return []

    # Convert to standard format (newest first)
    historical = []
    for item in time_series:
        # AlphaVantage gold API uses 'price' field
        price = item.get('price', item.get('value', 0))
        historical.append({
            'date': item.get('date'),
            'close': float(price)
        })

    # Sort by date (newest first)
    historical.sort(key=lambda x: x['date'], reverse=True)

    print(f"    ✓ Fetched {len(historical)} days")
    return historical[:250]  # Limit to 250 days

# ============================================================================
# API FUNCTIONS - TREASURY RATES (ALPHAVANTAGE)
# ============================================================================

def fetch_treasury_yield_alphavantage(api_key, maturity):
    """Fetch treasury yield historical data from AlphaVantage

    Args:
        api_key: AlphaVantage API key
        maturity: Maturity (e.g., '2year', '10year')

    Returns:
        list: Treasury yield data (format: {'date': 'YYYY-MM-DD', 'value': float}), or empty list if failed
    """
    print(f"  Fetching {maturity} treasury yield from AlphaVantage...")
    url = f"{ALPHAVANTAGE_BASE_URL}?function=TREASURY_YIELD&interval=daily&maturity={maturity}&apikey={api_key}"

    data = fetch_with_rate_limit_retry(url)
    if not data:
        return []

    # AlphaVantage returns data in 'data' key
    time_series = data.get('data', [])

    if not time_series:
        print(f"    ❌ No historical data returned")
        return []

    # Convert to standard format
    historical = []
    for item in time_series:
        value = item.get('value')
        if value and value != '.':  # Skip missing data
            historical.append({
                'date': item.get('date'),
                'value': float(value)
            })

    # Sort by date (newest first)
    historical.sort(key=lambda x: x['date'], reverse=True)

    print(f"    ✓ Fetched {len(historical)} data points")
    return historical[:90]  # Limit to 90 days

# ============================================================================
# API FUNCTIONS - ECONOMIC INDICATORS
# ============================================================================

def fetch_unemployment_alphavantage(api_key):
    """Fetch unemployment rate from AlphaVantage

    Args:
        api_key: AlphaVantage API key

    Returns:
        list: Unemployment data (format: {'date': 'YYYY-MM-DD', 'value': float}), or empty list if failed
    """
    print(f"  Fetching unemployment rate from AlphaVantage...")
    url = f"{ALPHAVANTAGE_BASE_URL}?function=UNEMPLOYMENT&apikey={api_key}"

    data = fetch_with_rate_limit_retry(url)
    if not data:
        return []

    # AlphaVantage returns data in 'data' key
    time_series = data.get('data', [])

    if not time_series:
        print(f"    ❌ No historical data returned")
        return []

    # Convert to standard format
    historical = []
    for item in time_series:
        value = item.get('value')
        if value and value != '.':  # Skip missing data
            historical.append({
                'date': item.get('date'),
                'value': float(value)
            })

    # Sort by date (newest first)
    historical.sort(key=lambda x: x['date'], reverse=True)

    print(f"    ✓ Fetched {len(historical)} data points")
    return historical[:180]  # Limit to ~15 years of monthly data


def fetch_economic_indicator_fmp(indicator_name, api_key, from_date, to_date):
    """Fetch a specific economic indicator from FMP over a date range

    Args:
        indicator_name: Name of indicator (e.g., 'inflationRate')
        api_key: FMP API key
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)

    Returns:
        list: Indicator data, or empty list if failed
    """
    try:
        print(f"  Fetching {indicator_name} from FMP...")
        url = f"{FMP_BASE_URL}/stable/economic-indicators?name={indicator_name}&from={from_date}&to={to_date}&apikey={api_key}"
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        if response.status_code != 200:
            print(f"    ❌ Error: HTTP {response.status_code}")
            return []

        data = response.json()

        if isinstance(data, dict) and 'Error Message' in data:
            print(f"    ❌ Error: {data['Error Message']}")
            return []

        print(f"    ✓ Fetched {len(data)} data points")
        return data

    except requests.exceptions.Timeout:
        print(f"    ❌ Request timed out after {REQUEST_TIMEOUT}s")
        return []
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return []

# ============================================================================
# CALCULATIONS - PRICE ANALYSIS
# ============================================================================

def calculate_price_change(historical, days_ago):
    """Calculate % price change from N days ago to most recent

    Args:
        historical: List of price data (newest first)
        days_ago: Number of days to look back

    Returns:
        float: Percentage change, or None if insufficient data
    """
    if len(historical) < days_ago + 1:
        return None

    current_price = historical[0]['close']
    past_price = historical[days_ago]['close']

    if past_price == 0:
        return None

    return ((current_price - past_price) / past_price) * 100

def calculate_sma(historical, days):
    """Calculate Simple Moving Average

    Args:
        historical: List of price data (newest first)
        days: Number of days for SMA

    Returns:
        float: SMA value, or None if insufficient data
    """
    if len(historical) < days:
        return None

    prices = [day['close'] for day in historical[:days]]
    return sum(prices) / len(prices)

def calculate_price_vs_sma(current_price, sma):
    """Calculate how far current price is from SMA (as %)

    Args:
        current_price: Current price
        sma: SMA value

    Returns:
        float: Percentage difference, or None if invalid
    """
    if sma is None or sma == 0:
        return None

    return ((current_price - sma) / sma) * 100

def analyze_asset(symbol, api_key, historical_data=None):
    """Analyze a single asset (ETF/stock/commodity)

    Args:
        symbol: Asset symbol
        api_key: FMP API key (used only if historical_data not provided)
        historical_data: Pre-fetched historical data (optional)

    Returns:
        dict: Analysis results, or None if failed
    """
    if historical_data is None:
        historical = fetch_historical_prices(symbol, api_key, days_back=250)
    else:
        historical = historical_data

    if not historical:
        return None

    current_price = historical[0]['close']

    # Calculate price changes
    changes = {}
    for period_name, days in [('1W', 7), ('1M', 30), ('3M', 90), ('6M', 180)]:
        changes[period_name] = calculate_price_change(historical, days)

    # Calculate SMAs
    sma_50 = calculate_sma(historical, 50)
    sma_200 = calculate_sma(historical, 200)

    # Calculate distance from SMAs
    sma_50_diff = calculate_price_vs_sma(current_price, sma_50)
    sma_200_diff = calculate_price_vs_sma(current_price, sma_200)

    return {
        'symbol': symbol,
        'price': current_price,
        'changes': changes,
        'sma_50_diff': sma_50_diff,
        'sma_200_diff': sma_200_diff
    }

# ============================================================================
# CALCULATIONS - TREASURY ANALYSIS
# ============================================================================

def analyze_treasury_rates(treasury_data):
    """Analyze treasury rate changes over time (AlphaVantage format)

    Args:
        treasury_data: List of treasury rate data with 'date' and 'value' keys (sorted newest first)

    Returns:
        dict: Analysis results, or None if insufficient data
    """
    if not treasury_data:
        return None

    # Data should already be sorted by date (newest first)
    current = treasury_data[0].get('value')
    current_date = datetime.strptime(treasury_data[0]['date'], '%Y-%m-%d')

    if current is None:
        return None

    # Calculate changes
    changes = {}

    for period_name, days in [('1W', 7), ('1M', 30), ('3M', 90)]:
        # Find the data point closest to N days ago FROM THE CURRENT DATA DATE
        # Skip the first item (current value) when searching for historical data
        past_value = None
        best_match_diff = float('inf')

        for item in treasury_data[1:]:  # Start from index 1 to skip current
            item_date = datetime.strptime(item['date'], '%Y-%m-%d')
            target_date = current_date - timedelta(days=days)  # Look back from current data date, not "now"
            days_diff = abs((item_date - target_date).days)

            # Accept data within 5 days of target (treasury data is daily but may have gaps on weekends)
            # Keep the closest match within the tolerance window
            if days_diff <= 5 and days_diff < best_match_diff:
                past_value = item.get('value')
                best_match_diff = days_diff

        if past_value is not None:
            changes[period_name] = current - past_value
        else:
            changes[period_name] = None

    # Determine trend
    trend = "Stable"
    if changes['1M'] is not None:
        if changes['1M'] > 0.1:
            trend = "Rising"
        elif changes['1M'] < -0.1:
            trend = "Falling"

    return {
        'current': current,
        'changes': changes,
        'trend': trend
    }

# ============================================================================
# CALCULATIONS - ECONOMIC INDICATORS
# ============================================================================

def analyze_economic_indicator(indicator_data):
    """Analyze economic indicator changes over time

    Args:
        indicator_data: List of indicator data points

    Returns:
        dict: Analysis results, or None if insufficient data
    """
    if not indicator_data:
        return None

    # Sort by date (newest first)
    sorted_data = sorted(indicator_data, key=lambda x: x['date'], reverse=True)

    current = sorted_data[0].get('value')
    current_date = datetime.strptime(sorted_data[0]['date'], '%Y-%m-%d')

    if current is None:
        return None

    # Calculate changes
    changes = {}

    for period_name, days in [('1M', 30), ('3M', 90)]:
        # Find the data point closest to N days ago FROM THE CURRENT DATA DATE
        # Skip the first item (current value) when searching for historical data
        past_value = None
        best_match_diff = float('inf')

        for item in sorted_data[1:]:  # Start from index 1 to skip current
            item_date = datetime.strptime(item['date'], '%Y-%m-%d')
            target_date = current_date - timedelta(days=days)  # Look back from current data date, not "now"
            days_diff = abs((item_date - target_date).days)

            # Accept data within 45 days of target (monthly economic data can be irregular)
            # Keep the closest match within the tolerance window
            if days_diff <= 45 and days_diff < best_match_diff:
                past_value = item.get('value')
                best_match_diff = days_diff

        if past_value is not None and past_value != 0:
            # For percentages/rates, show absolute change
            # For indices, show percentage change
            if past_value < 100:  # Likely a percentage/rate
                changes[period_name] = current - past_value
            else:  # Likely an index
                changes[period_name] = ((current - past_value) / past_value) * 100
        else:
            changes[period_name] = None

    return {
        'current': current,
        'changes': changes
    }

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def format_percentage(value, decimals=2):
    """Format a number as a percentage string

    Args:
        value: Numeric value
        decimals: Decimal places

    Returns:
        str: Formatted percentage (e.g., '+3.5%')
    """
    if value is None:
        return 'N/A'

    sign = '+' if value >= 0 else ''
    return f"{sign}{value:.{decimals}f}%"

def format_change(value, decimals=2, is_bps=False):
    """Format a numeric change

    Args:
        value: Numeric value
        decimals: Decimal places
        is_bps: If True, format as basis points

    Returns:
        str: Formatted change (e.g., '+0.15')
    """
    if value is None:
        return 'N/A'

    sign = '+' if value >= 0 else ''
    formatted = f"{sign}{value:.{decimals}f}"

    if is_bps:
        formatted += ' bps'

    return formatted

def display_market_indices(analyses):
    """Display market indices analysis table

    Args:
        analyses: List of analysis results from analyze_asset
    """
    if not analyses:
        print("\n❌ No market indices data available")
        return

    table_data = []

    for analysis in analyses:
        if analysis is None:
            continue

        row = [
            analysis['symbol'],
            f"${analysis['price']:.2f}",
            format_percentage(analysis['changes'].get('1W')),
            format_percentage(analysis['changes'].get('1M')),
            format_percentage(analysis['changes'].get('3M')),
            format_percentage(analysis['changes'].get('6M')),
            format_percentage(analysis['sma_50_diff']),
            format_percentage(analysis['sma_200_diff'])
        ]
        table_data.append(row)

    headers = ['Asset', 'Price', '1W', '1M', '3M', '6M', '50-SMA', '200-SMA']

    print("\nMarket Indices")
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

def display_treasuries(treasury_analyses):
    """Display treasury rates analysis table

    Args:
        treasury_analyses: Dict of maturity -> analysis results
    """
    if not treasury_analyses:
        print("\n❌ No treasury data available")
        return

    table_data = []

    maturity_names = {
        '2year': '2-Year',
        '10year': '10-Year'
    }

    for maturity, analysis in treasury_analyses.items():
        if analysis is None:
            continue

        row = [
            maturity_names.get(maturity, maturity),
            f"{analysis['current']:.2f}%",
            format_change(analysis['changes'].get('1W')),
            format_change(analysis['changes'].get('1M')),
            format_change(analysis['changes'].get('3M')),
            analysis['trend']
        ]
        table_data.append(row)

    headers = ['Maturity', 'Yield', '1W Δ', '1M Δ', '3M Δ', 'Trend']

    print("\nTreasuries")
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

def display_economic_indicators(indicator_analyses):
    """Display economic indicators analysis table

    Args:
        indicator_analyses: Dict of indicator name -> analysis results
    """
    if not indicator_analyses:
        print("\n❌ No economic indicators data available")
        return

    table_data = []

    indicator_labels = {
        'inflationRate': 'Inflation (CPI)',
        'unemploymentRate': 'Unemployment',
        'consumerSentiment': 'Consumer Sentiment'
    }

    for indicator, analysis in indicator_analyses.items():
        if analysis is None:
            continue

        # Format current value based on indicator type
        current_val = analysis['current']
        if indicator in ['inflationRate', 'unemploymentRate']:
            current_str = f"{current_val:.1f}%"
        else:
            current_str = f"{current_val:.1f}"

        row = [
            indicator_labels.get(indicator, indicator),
            current_str,
            format_change(analysis['changes'].get('1M'), decimals=1),
            format_change(analysis['changes'].get('3M'), decimals=1)
        ]
        table_data.append(row)

    headers = ['Indicator', 'Value', '1M Δ', '3M Δ']

    print("\nEconomic Indicators")
    print(tabulate(table_data, headers=headers, tablefmt='simple'))

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution function"""
    print("\n" + "="*80)
    print(f"MACRO MARKET HEALTH CHECK - {get_today()}")
    print("="*80 + "\n")

    # Check for API keys
    fmp_api_key = os.getenv('FMP_API_KEY')
    av_api_key = os.getenv('ALPHAVANTAGE_API_KEY')

    if not fmp_api_key:
        print("❌ Error: FMP_API_KEY environment variable not set")
        print("   Set it with: export FMP_API_KEY='your_key_here'")
        sys.exit(1)

    if not av_api_key:
        print("❌ Error: ALPHAVANTAGE_API_KEY environment variable not set")
        print("   Set it with: export ALPHAVANTAGE_API_KEY='your_key_here'")
        sys.exit(1)

    print("Fetching market data...\n")

    # Analyze market indices
    print("=" * 80)
    print("MARKET INDICES")
    print("=" * 80)

    market_analyses = []

    # Fetch SPY and QQQ from AlphaVantage
    for symbol in MARKET_ETFS:
        stock_historical = fetch_stock_historical_alphavantage(symbol, av_api_key)
        if stock_historical:
            analysis = analyze_asset(symbol, fmp_api_key, historical_data=stock_historical)
            if analysis:
                market_analyses.append(analysis)
        time.sleep(API_CALL_DELAY)  # Rate limit delay

    # Fetch gold historical data from AlphaVantage
    gold_historical = fetch_gold_historical_alphavantage(av_api_key)
    if gold_historical:
        gold_analysis = analyze_asset('Gold', fmp_api_key, historical_data=gold_historical)
        if gold_analysis:
            market_analyses.append(gold_analysis)
    time.sleep(API_CALL_DELAY)  # Rate limit delay

    display_market_indices(market_analyses)

    # Analyze treasury rates from AlphaVantage
    print("\n" + "=" * 80)
    print("TREASURY RATES")
    print("=" * 80)

    treasury_analyses = {}
    for maturity in TREASURY_MATURITIES:
        treasury_data = fetch_treasury_yield_alphavantage(av_api_key, maturity)
        analysis = analyze_treasury_rates(treasury_data)
        if analysis:
            treasury_analyses[maturity] = analysis
        time.sleep(API_CALL_DELAY)  # Rate limit delay

    display_treasuries(treasury_analyses)

    # Analyze economic indicators
    print("\n" + "=" * 80)
    print("ECONOMIC INDICATORS")
    print("=" * 80)

    from_date = get_date_n_days_ago(180)  # Get 6 months of data
    to_date = get_today()
    indicator_analyses = {}

    # Fetch unemployment from AlphaVantage
    unemployment_data = fetch_unemployment_alphavantage(av_api_key)
    unemployment_analysis = analyze_economic_indicator(unemployment_data)
    if unemployment_analysis:
        indicator_analyses['unemploymentRate'] = unemployment_analysis
    time.sleep(API_CALL_DELAY)  # Rate limit delay

    # Fetch other indicators from FMP
    for indicator in FMP_ECONOMIC_INDICATORS:
        indicator_data = fetch_economic_indicator_fmp(indicator, fmp_api_key, from_date, to_date)
        analysis = analyze_economic_indicator(indicator_data)
        if analysis:
            indicator_analyses[indicator] = analysis
        # No delay needed for FMP calls (different API)

    display_economic_indicators(indicator_analyses)

    print("\n" + "="*80)
    print("✓ Analysis complete")
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
