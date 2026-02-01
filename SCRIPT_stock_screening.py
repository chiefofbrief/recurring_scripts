#!/usr/bin/env python3
"""
Preliminary Stock Screening Script
===================================

Quick daily screening for 1-5 stocks before committing to full fundamental
analysis. Fetches data and calculates trend statistics — no AI, just numbers.

Metrics calculated (same stat block for each):
- Price Trend (5yr monthly adjusted data)
- EPS Trend (5yr annual + quarterly)
- Revenue Trend (5yr annual + quarterly)
- Operating Margin Trend (derived from income statement, no extra API call)
- P/E Trend (derived from price + EPS, no extra API call)
- EPS/Revenue Estimates (consensus, range, revisions)
- Price-EPS Correlation (5yr annual data)
- YoY Trend Analysis (quarterly and annual YoY % changes for all metrics)

API Budget: 4 calls per stock
- TIME_SERIES_MONTHLY_ADJUSTED
- EARNINGS
- EARNINGS_ESTIMATES
- INCOME_STATEMENT

Output: screening_YYYY-MM-DD.md (single file, all stocks)

Usage:
    python SCRIPT_screening.py TICKER1 [TICKER2] ... [TICKER5]
    python SCRIPT_screening.py AAPL MSFT GOOGL
"""

import sys
import os
import time
from datetime import datetime
from tabulate import tabulate
from rich.console import Console
from shared_utils import fetch_alpha_vantage

# ============================================================================
# CONFIGURATION
# ============================================================================

API_KEY = os.getenv('ALPHAVANTAGE_API_KEY', 'demo')
API_DELAY = 12  # seconds between API calls (free tier: 5/min)
YEARS_TO_ANALYZE = 5

console = Console()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def safe_float(value, default=None):
    """Convert value to float, return default if None or 'None' string"""
    if value is None or value == 'None' or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_divide(num, denom, default=None):
    """Safely divide, return default if denom is 0 or None"""
    if num is None or denom is None or denom == 0:
        return default
    return num / denom

def pct(num, denom, default=None):
    """Calculate percentage: (num / denom) * 100"""
    result = safe_divide(num, denom, default)
    return round(result * 100, 2) if result is not None else default

def calculate_cagr(values):
    """Calculate Compound Annual Growth Rate"""
    clean = [v for v in values if v is not None]
    if len(clean) < 2 or clean[0] <= 0 or clean[-1] <= 0:
        return None
    years = len(clean) - 1
    return round((((clean[-1] / clean[0]) ** (1 / years)) - 1) * 100, 2)

def calculate_avg(values):
    """Average of non-None values"""
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None

def calculate_cv(values):
    """Coefficient of variation (volatility measure)"""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    avg = sum(clean) / len(clean)
    if avg == 0:
        return None
    variance = sum((x - avg) ** 2 for x in clean) / len(clean)
    return round((variance ** 0.5 / abs(avg)) * 100, 2)

def calculate_slope(values):
    """Calculate linear regression slope for trend direction"""
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 2:
        return None
    n = len(clean)
    sum_x = sum(i for i, _ in clean)
    sum_y = sum(v for _, v in clean)
    sum_xy = sum(i * v for i, v in clean)
    sum_x2 = sum(i * i for i, _ in clean)
    denominator = n * sum_x2 - sum_x * sum_x
    if denominator == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return round(slope, 2)

def calculate_recent_delta(values):
    """Calculate YoY change (most recent vs prior)"""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return {'absolute': None, 'percent': None}
    recent, prior = clean[-1], clean[-2]
    absolute = round(recent - prior, 2)
    percent = round(((recent - prior) / abs(prior) * 100), 2) if prior != 0 else None
    return {'absolute': absolute, 'percent': percent}

def detect_outliers(values):
    """Detect outliers using 2 standard deviations from mean"""
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 3:
        return []
    vals = [v for _, v in clean]
    mean = sum(vals) / len(vals)
    variance = sum((x - mean) ** 2 for x in vals) / len(vals)
    std_dev = variance ** 0.5
    lower, upper = mean - 2 * std_dev, mean + 2 * std_dev
    return [i for i, v in clean if v < lower or v > upper]

def calculate_correlation(values1, values2):
    """Calculate Pearson correlation coefficient between two value lists.

    Returns correlation coefficient (-1 to +1) or None if insufficient data.
    Matches values by index, skipping any pairs where either value is None.
    """
    if not values1 or not values2:
        return None

    # Pair up values, filter out any pairs with None
    paired = [(v1, v2) for v1, v2 in zip(values1, values2) if v1 is not None and v2 is not None]

    if len(paired) < 2:
        return None

    n = len(paired)
    sum_x = sum(x for x, _ in paired)
    sum_y = sum(y for _, y in paired)
    sum_xy = sum(x * y for x, y in paired)
    sum_x2 = sum(x * x for x, _ in paired)
    sum_y2 = sum(y * y for _, y in paired)

    numerator = n * sum_xy - sum_x * sum_y
    denominator = ((n * sum_x2 - sum_x ** 2) * (n * sum_y2 - sum_y ** 2)) ** 0.5

    if denominator == 0:
        return None

    correlation = numerator / denominator
    return round(correlation, 3)


def fmt_val(val, unit='', is_delta=False):
    """Format a value for markdown display"""
    if val is None:
        return "—"
    prefix = "+" if is_delta and val > 0 else ""
    if unit == 'dollars':
        return f"{prefix}${val:,.2f}"
    elif unit == 'dollars_large':
        if abs(val) >= 1e9:
            return f"{prefix}${val / 1e9:,.2f}B"
        elif abs(val) >= 1e6:
            return f"{prefix}${val / 1e6:,.1f}M"
        else:
            return f"{prefix}${val:,.0f}"
    elif unit == 'percent':
        return f"{prefix}{val:.2f}%"
    elif unit == 'ratio':
        return f"{prefix}{val:.2f}"
    else:
        return f"{prefix}{val}"

# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_screening_data(ticker):
    """Fetch all 4 endpoints for a single stock with rate limiting"""
    console.print(f"\n[bold]{'=' * 50}[/bold]")
    console.print(f"  [bold cyan]Fetching data for {ticker}[/bold cyan]")
    console.print(f"[bold]{'=' * 50}[/bold]")

    base_url = "https://www.alphavantage.co/query"

    endpoints = [
        ('price_monthly', 'TIME_SERIES_MONTHLY_ADJUSTED', f'&symbol={ticker}'),
        ('earnings', 'EARNINGS', f'&symbol={ticker}'),
        ('earnings_estimates', 'EARNINGS_ESTIMATES', f'&symbol={ticker}'),
        ('income', 'INCOME_STATEMENT', f'&symbol={ticker}'),
    ]

    data = {}
    for i, (key, function, params) in enumerate(endpoints):
        url = f"{base_url}?function={function}{params}&apikey={API_KEY}"
        console.print(f"  → Fetching {key}...")
        result = fetch_alpha_vantage(url)
        if result:
            data[key] = result
            console.print(f"  [green]✓ {key} received[/green]")

            # Log what keys we got back for debugging
            if isinstance(result, dict):
                top_keys = list(result.keys())[:5]  # First 5 keys
                console.print(f"    Response keys: {', '.join(top_keys)}")

                # If we got an Information key, show the message
                if 'Information' in result:
                    console.print(f"    [yellow]Information message: {result['Information'][:100]}...[/yellow]")
        else:
            console.print(f"  [red]✗ {key} failed (no data returned)[/red]")
            data[key] = None

        # Rate limit delay (skip after last call)
        if i < len(endpoints) - 1:
            console.print(f"  Waiting {API_DELAY}s before next request...")
            time.sleep(API_DELAY)

    return data

# ============================================================================
# CALCULATIONS
# ============================================================================

def calculate_price_stats(price_data):
    """Calculate price trend statistics from monthly adjusted data"""
    if not price_data:
        console.print("  [yellow]Warning: No price data provided[/yellow]")
        return None

    time_series = price_data.get('Monthly Adjusted Time Series', {})
    if not time_series:
        console.print(f"  [yellow]Warning: No 'Monthly Adjusted Time Series' key in price data[/yellow]")
        console.print(f"  Available keys: {list(price_data.keys())}")
        return None

    # Extract monthly adjusted closes sorted by date (newest first)
    monthly = []
    for date_str, values in time_series.items():
        close = safe_float(values.get('5. adjusted close'))
        if close is not None:
            monthly.append((date_str, close))

    monthly.sort(key=lambda x: x[0], reverse=True)

    if len(monthly) < 2:
        return None

    # Get up to 60 months (5 years)
    monthly = monthly[:60]
    closes = [close for _, close in monthly]
    dates = [date for date, _ in monthly]

    current = closes[0]

    # 3-month change
    vs_3mo = None
    if len(closes) > 3 and closes[3] != 0:
        vs_3mo = round(((current - closes[3]) / closes[3]) * 100, 2)

    # YoY change
    vs_yoy = None
    if len(closes) > 12 and closes[12] != 0:
        vs_yoy = round(((current - closes[12]) / closes[12]) * 100, 2)

    # 52-week high/low from last 12 months
    last_12 = closes[:min(12, len(closes))]
    high_52w = max(last_12) if last_12 else None
    low_52w = min(last_12) if last_12 else None

    # Chronological order for stats
    closes_chrono = list(reversed(closes))

    # Build annual prices (December close as fiscal year-end proxy)
    annual_prices = {}
    for date_str, close in sorted(monthly, key=lambda x: x[0]):
        year = date_str[:4]
        month = date_str[5:7]
        if month == '12':
            annual_prices[year] = close

    # Also include the most recent month's close as the current year if no Dec yet
    current_year = dates[0][:4]
    if current_year not in annual_prices:
        annual_prices[current_year] = current

    sorted_years = sorted(annual_prices.keys())[-YEARS_TO_ANALYZE:]
    annual_values = [annual_prices[y] for y in sorted_years]

    return {
        'current': current,
        'current_date': dates[0],
        'mean_5yr': calculate_avg(closes_chrono),
        'cagr_5yr': calculate_cagr(closes_chrono),
        'cv': calculate_cv(closes_chrono),
        'slope': calculate_slope(closes_chrono),
        'vs_3mo_pct': vs_3mo,
        'vs_yoy_pct': vs_yoy,
        'high_52w': high_52w,
        'low_52w': low_52w,
        'vs_52w_high_pct': round(((current - high_52w) / high_52w) * 100, 2) if high_52w and high_52w != 0 else None,
        'vs_52w_low_pct': round(((current - low_52w) / low_52w) * 100, 2) if low_52w and low_52w != 0 else None,
        'months_of_data': len(closes),
        'annual_years': sorted_years,
        'annual_values': annual_values,
        'annual_recent_delta': calculate_recent_delta(annual_values),
        'annual_outliers': [sorted_years[i] for i in detect_outliers(annual_values)] if annual_values else []
    }


def calculate_eps_stats(earnings_data):
    """Calculate EPS trend statistics"""
    if not earnings_data:
        return None

    quarterly = earnings_data.get('quarterlyEarnings', [])
    annual = earnings_data.get('annualEarnings', [])

    if not quarterly or len(quarterly) < 2:
        return None

    latest_eps = safe_float(quarterly[0].get('reportedEPS'))
    if latest_eps is None:
        return None

    # Previous quarter
    vs_prev_q = None
    if len(quarterly) > 1:
        prev_eps = safe_float(quarterly[1].get('reportedEPS'))
        if prev_eps is not None and prev_eps != 0:
            vs_prev_q = round(((latest_eps - prev_eps) / abs(prev_eps)) * 100, 2)

    # YoY (same quarter last year = 4 quarters ago)
    vs_yoy = None
    if len(quarterly) > 4:
        yoy_eps = safe_float(quarterly[4].get('reportedEPS'))
        if yoy_eps is not None and yoy_eps != 0:
            vs_yoy = round(((latest_eps - yoy_eps) / abs(yoy_eps)) * 100, 2)

    # TTM EPS (sum of last 4 quarters)
    ttm_eps = None
    if len(quarterly) >= 4:
        ttm_values = [safe_float(q.get('reportedEPS')) for q in quarterly[:4]]
        if all(v is not None for v in ttm_values):
            ttm_eps = round(sum(ttm_values), 2)

    # Annual series for trend
    annual_eps = []
    annual_years = []
    for entry in annual[:YEARS_TO_ANALYZE]:
        eps = safe_float(entry.get('reportedEPS'))
        year = entry.get('fiscalDateEnding', '')[:4]
        if eps is not None and year:
            annual_eps.append(eps)
            annual_years.append(year)

    # Reverse to chronological order
    annual_eps.reverse()
    annual_years.reverse()

    # Beat/miss history (last 4 quarters)
    beat_miss = []
    for q in quarterly[:4]:
        reported = safe_float(q.get('reportedEPS'))
        estimated = safe_float(q.get('estimatedEPS'))
        if reported is not None and estimated is not None:
            surprise = round(reported - estimated, 4)
            surprise_pct = round(((reported - estimated) / abs(estimated)) * 100, 2) if estimated != 0 else None
            beat_miss.append({
                'date': q.get('fiscalDateEnding'),
                'reported': reported,
                'estimated': estimated,
                'surprise': surprise,
                'surprise_pct': surprise_pct
            })

    return {
        'latest': latest_eps,
        'latest_date': quarterly[0].get('fiscalDateEnding'),
        'ttm': ttm_eps,
        'vs_prev_q_pct': vs_prev_q,
        'vs_yoy_pct': vs_yoy,
        'mean_5yr': calculate_avg(annual_eps),
        'cagr_5yr': calculate_cagr(annual_eps),
        'cv': calculate_cv(annual_eps),
        'slope': calculate_slope(annual_eps),
        'recent_delta': calculate_recent_delta(annual_eps),
        'outlier_years': [annual_years[i] for i in detect_outliers(annual_eps)] if annual_eps else [],
        'annual_years': annual_years,
        'annual_values': annual_eps,
        'years_of_data': len(annual_eps),
        'beat_miss_history': beat_miss
    }


def calculate_revenue_stats(income_data):
    """Calculate revenue trend statistics from income statement data"""
    if not income_data:
        return None

    annual_reports = income_data.get('annualReports', [])
    quarterly_reports = income_data.get('quarterlyReports', [])

    if not annual_reports:
        return None

    # Annual revenue
    annual_rev = []
    annual_years = []
    for r in annual_reports[:YEARS_TO_ANALYZE]:
        rev = safe_float(r.get('totalRevenue'))
        year = r.get('fiscalDateEnding', '')[:4]
        if rev is not None and year:
            annual_rev.append(rev)
            annual_years.append(year)

    # Reverse to chronological
    annual_rev.reverse()
    annual_years.reverse()

    if len(annual_rev) < 2:
        return None

    latest = annual_rev[-1]

    # YoY
    vs_yoy = None
    if len(annual_rev) >= 2 and annual_rev[-2] != 0:
        vs_yoy = round(((annual_rev[-1] - annual_rev[-2]) / abs(annual_rev[-2])) * 100, 2)

    # Previous quarter comparison
    vs_prev_q = None
    if len(quarterly_reports) >= 2:
        q_latest = safe_float(quarterly_reports[0].get('totalRevenue'))
        q_prev = safe_float(quarterly_reports[1].get('totalRevenue'))
        if q_latest and q_prev and q_prev != 0:
            vs_prev_q = round(((q_latest - q_prev) / abs(q_prev)) * 100, 2)

    # YTD annualized
    current_year = str(datetime.now().year)
    ytd_quarters = [r for r in quarterly_reports if r.get('fiscalDateEnding', '').startswith(current_year)]
    ytd_annualized = None
    ytd_num_quarters = 0
    if ytd_quarters:
        ytd_num_quarters = len(ytd_quarters)
        ytd_sum = sum(safe_float(r.get('totalRevenue', 0)) or 0 for r in ytd_quarters)
        ytd_annualized = ytd_sum * (4 / ytd_num_quarters)

    return {
        'latest': latest,
        'latest_year': annual_years[-1] if annual_years else None,
        'vs_yoy_pct': vs_yoy,
        'vs_prev_q_pct': vs_prev_q,
        'mean_5yr': calculate_avg(annual_rev),
        'cagr_5yr': calculate_cagr(annual_rev),
        'cv': calculate_cv(annual_rev),
        'slope': calculate_slope(annual_rev),
        'recent_delta': calculate_recent_delta(annual_rev),
        'outlier_years': [annual_years[i] for i in detect_outliers(annual_rev)] if annual_rev else [],
        'annual_years': annual_years,
        'annual_values': annual_rev,
        'years_of_data': len(annual_rev),
        'ytd_annualized': ytd_annualized,
        'ytd_num_quarters': ytd_num_quarters,
        'quarterly_latest': safe_float(quarterly_reports[0].get('totalRevenue')) if quarterly_reports else None,
        'quarterly_latest_date': quarterly_reports[0].get('fiscalDateEnding') if quarterly_reports else None
    }


def calculate_margin_stats(income_data):
    """Calculate operating margin trend statistics from income statement data"""
    if not income_data:
        return None

    annual_reports = income_data.get('annualReports', [])
    quarterly_reports = income_data.get('quarterlyReports', [])

    if not annual_reports:
        return None

    # Annual operating margin
    annual_margins = []
    annual_years = []
    for r in annual_reports[:YEARS_TO_ANALYZE]:
        oi = safe_float(r.get('operatingIncome'))
        rev = safe_float(r.get('totalRevenue'))
        year = r.get('fiscalDateEnding', '')[:4]
        margin = pct(oi, rev)
        if margin is not None and year:
            annual_margins.append(margin)
            annual_years.append(year)

    # Reverse to chronological
    annual_margins.reverse()
    annual_years.reverse()

    if len(annual_margins) < 2:
        return None

    latest = annual_margins[-1]

    # YoY (absolute percentage point change)
    vs_yoy = None
    if len(annual_margins) >= 2:
        vs_yoy = round(annual_margins[-1] - annual_margins[-2], 2)

    # Previous quarter comparison
    vs_prev_q = None
    if len(quarterly_reports) >= 2:
        q_latest_oi = safe_float(quarterly_reports[0].get('operatingIncome'))
        q_latest_rev = safe_float(quarterly_reports[0].get('totalRevenue'))
        q_prev_oi = safe_float(quarterly_reports[1].get('operatingIncome'))
        q_prev_rev = safe_float(quarterly_reports[1].get('totalRevenue'))
        q_latest_margin = pct(q_latest_oi, q_latest_rev)
        q_prev_margin = pct(q_prev_oi, q_prev_rev)
        if q_latest_margin is not None and q_prev_margin is not None:
            vs_prev_q = round(q_latest_margin - q_prev_margin, 2)

    # YTD margin
    current_year = str(datetime.now().year)
    ytd_quarters = [r for r in quarterly_reports if r.get('fiscalDateEnding', '').startswith(current_year)]
    ytd_margin = None
    ytd_num_quarters = 0
    if ytd_quarters:
        ytd_num_quarters = len(ytd_quarters)
        ytd_oi = sum(safe_float(r.get('operatingIncome', 0)) or 0 for r in ytd_quarters)
        ytd_rev = sum(safe_float(r.get('totalRevenue', 0)) or 0 for r in ytd_quarters)
        ytd_margin = pct(ytd_oi, ytd_rev)

    return {
        'latest': latest,
        'latest_year': annual_years[-1] if annual_years else None,
        'vs_yoy_pct': vs_yoy,
        'vs_prev_q_pct': vs_prev_q,
        'mean_5yr': calculate_avg(annual_margins),
        'cagr_5yr': calculate_cagr(annual_margins),
        'cv': calculate_cv(annual_margins),
        'slope': calculate_slope(annual_margins),
        'recent_delta': calculate_recent_delta(annual_margins),
        'outlier_years': [annual_years[i] for i in detect_outliers(annual_margins)] if annual_margins else [],
        'annual_years': annual_years,
        'annual_values': annual_margins,
        'years_of_data': len(annual_margins),
        'ytd_margin': ytd_margin,
        'ytd_num_quarters': ytd_num_quarters
    }


def calculate_pe_stats(price_stats, eps_stats):
    """Calculate P/E trend statistics (derived from already-computed price + EPS stats)"""
    if not price_stats or not eps_stats:
        return None

    # Current trailing P/E
    current_price = price_stats.get('current')
    ttm_eps = eps_stats.get('ttm')
    trailing_pe = round(current_price / ttm_eps, 2) if current_price and ttm_eps and ttm_eps > 0 else None

    # Historical annual P/E: year-end price / annual EPS
    price_annual = dict(zip(price_stats.get('annual_years', []), price_stats.get('annual_values', [])))
    eps_annual = dict(zip(eps_stats.get('annual_years', []), eps_stats.get('annual_values', [])))

    common_years = sorted(set(price_annual.keys()) & set(eps_annual.keys()))

    pe_values = []
    pe_years = []
    for year in common_years:
        price = price_annual[year]
        eps = eps_annual[year]
        if price is not None and eps is not None and eps > 0:
            pe_values.append(round(price / eps, 2))
            pe_years.append(year)

    mean_5yr = calculate_avg(pe_values) if pe_values else None

    # Current vs 5yr avg
    vs_5yr_avg_pct = None
    if trailing_pe and mean_5yr and mean_5yr != 0:
        vs_5yr_avg_pct = round(((trailing_pe - mean_5yr) / mean_5yr) * 100, 2)

    # YoY P/E change
    vs_yoy_pct = None
    if len(pe_values) >= 2 and pe_values[-2] != 0:
        vs_yoy_pct = round(((pe_values[-1] - pe_values[-2]) / pe_values[-2]) * 100, 2)

    return {
        'trailing_pe': trailing_pe,
        'current_price': current_price,
        'ttm_eps': ttm_eps,
        'mean_5yr': mean_5yr,
        'cagr_5yr': calculate_cagr(pe_values),
        'cv': calculate_cv(pe_values),
        'slope': calculate_slope(pe_values),
        'vs_yoy_pct': vs_yoy_pct,
        'vs_5yr_avg_pct': vs_5yr_avg_pct,
        'recent_delta': calculate_recent_delta(pe_values),
        'outlier_years': [pe_years[i] for i in detect_outliers(pe_values)] if pe_values else [],
        'annual_years': pe_years,
        'annual_values': pe_values,
        'years_of_data': len(pe_values)
    }


def calculate_estimates_stats(estimates_data, earnings_data):
    """Calculate EPS estimates statistics"""
    if not estimates_data:
        return None

    estimates = estimates_data.get('estimates', [])
    if not estimates:
        return None

    # Get latest actual EPS for delta calculation
    latest_actual = None
    if earnings_data:
        quarterly = earnings_data.get('quarterlyEarnings', [])
        if quarterly:
            latest_actual = safe_float(quarterly[0].get('reportedEPS'))

    # Parse all estimate horizons
    parsed = []
    for est in estimates:
        parsed.append({
            'date': est.get('date'),
            'horizon': est.get('horizon'),
            'eps_avg': safe_float(est.get('eps_estimate_average')),
            'eps_high': safe_float(est.get('eps_estimate_high')),
            'eps_low': safe_float(est.get('eps_estimate_low')),
            'analyst_count': safe_float(est.get('eps_estimate_analyst_count')),
            'revision_7d': safe_float(est.get('eps_estimate_average_7_days_ago')),
            'revision_30d': safe_float(est.get('eps_estimate_average_30_days_ago')),
            'revision_60d': safe_float(est.get('eps_estimate_average_60_days_ago')),
            'revision_90d': safe_float(est.get('eps_estimate_average_90_days_ago')),
            'rev_up_7d': safe_float(est.get('eps_estimate_revision_up_trailing_7_days')),
            'rev_down_7d': safe_float(est.get('eps_estimate_revision_down_trailing_7_days')),
            'rev_up_30d': safe_float(est.get('eps_estimate_revision_up_trailing_30_days')),
            'rev_down_30d': safe_float(est.get('eps_estimate_revision_down_trailing_30_days')),
            'revenue_avg': safe_float(est.get('revenue_estimate_average')),
            'revenue_high': safe_float(est.get('revenue_estimate_high')),
            'revenue_low': safe_float(est.get('revenue_estimate_low')),
            'revenue_analyst_count': safe_float(est.get('revenue_estimate_analyst_count')),
        })

    # Find key horizons
    next_quarter = None
    next_fiscal_year = None
    current_fiscal_year = None
    for p in parsed:
        horizon = (p.get('horizon') or '').strip().lower()
        if 'next quarter' in horizon and next_quarter is None:
            next_quarter = p
        elif 'next fiscal year' in horizon and next_fiscal_year is None:
            next_fiscal_year = p
        elif 'current fiscal year' in horizon and current_fiscal_year is None:
            current_fiscal_year = p

    # Delta: latest actual EPS vs next quarter consensus
    delta_vs_consensus = None
    delta_vs_consensus_pct = None
    if latest_actual is not None and next_quarter and next_quarter['eps_avg']:
        delta_vs_consensus = round(latest_actual - next_quarter['eps_avg'], 4)
        if next_quarter['eps_avg'] != 0:
            delta_vs_consensus_pct = round(
                ((latest_actual - next_quarter['eps_avg']) / abs(next_quarter['eps_avg'])) * 100, 2
            )

    return {
        'latest_actual_eps': latest_actual,
        'next_quarter': next_quarter,
        'current_fiscal_year': current_fiscal_year,
        'next_fiscal_year': next_fiscal_year,
        'delta_actual_vs_next_q': delta_vs_consensus,
        'delta_actual_vs_next_q_pct': delta_vs_consensus_pct,
        'all_estimates': parsed
    }


def build_yoy_trend_data(price_data, earnings_data, income_data):
    """Build YoY % change trend data for Price, EPS, Revenue, and Operating Margin.

    Combines both quarterly and annual data points for comprehensive trend view.
    Returns list of data points sorted chronologically, each containing:
    - date: fiscal date
    - period_type: 'Q' or 'A' (quarterly or annual)
    - price_yoy: YoY % change in price
    - eps_yoy: YoY % change in EPS
    - revenue_yoy: YoY % change in revenue
    - margin_yoy: YoY percentage point change in operating margin
    """
    trend_points = []

    if not earnings_data or not income_data:
        return trend_points

    # Get quarterly data
    quarterly_earnings = earnings_data.get('quarterlyEarnings', [])
    quarterly_income = income_data.get('quarterlyReports', [])

    # Get monthly price data
    price_monthly = {}
    if price_data:
        time_series = price_data.get('Monthly Adjusted Time Series', {})
        for date_str, values in time_series.items():
            close = safe_float(values.get('5. adjusted close'))
            if close is not None:
                price_monthly[date_str] = close

    # Build quarterly trend points (YoY = compare to 4 quarters ago)
    for i in range(len(quarterly_earnings) - 4):
        current_q = quarterly_earnings[i]
        yoy_q = quarterly_earnings[i + 4]

        date = current_q.get('fiscalDateEnding')
        if not date:
            continue

        point = {
            'date': date,
            'period_type': 'Q',
            'price_yoy': None,
            'eps_yoy': None,
            'revenue_yoy': None,
            'margin_yoy': None
        }

        # EPS YoY
        current_eps = safe_float(current_q.get('reportedEPS'))
        yoy_eps = safe_float(yoy_q.get('reportedEPS'))
        if current_eps is not None and yoy_eps is not None and yoy_eps != 0:
            point['eps_yoy'] = round(((current_eps - yoy_eps) / abs(yoy_eps)) * 100, 2)

        # Find matching quarterly income report
        current_income = None
        yoy_income = None
        for j, inc in enumerate(quarterly_income):
            if inc.get('fiscalDateEnding') == date:
                current_income = inc
                # YoY income is 4 quarters later
                if j + 4 < len(quarterly_income):
                    yoy_income = quarterly_income[j + 4]
                break

        if current_income and yoy_income:
            # Revenue YoY
            current_rev = safe_float(current_income.get('totalRevenue'))
            yoy_rev = safe_float(yoy_income.get('totalRevenue'))
            if current_rev is not None and yoy_rev is not None and yoy_rev != 0:
                point['revenue_yoy'] = round(((current_rev - yoy_rev) / abs(yoy_rev)) * 100, 2)

            # Operating Margin YoY (percentage point change)
            current_margin = pct(
                safe_float(current_income.get('operatingIncome')),
                current_rev
            )
            yoy_margin = pct(
                safe_float(yoy_income.get('operatingIncome')),
                yoy_rev
            )
            if current_margin is not None and yoy_margin is not None:
                point['margin_yoy'] = round(current_margin - yoy_margin, 2)

        # Price YoY - find price closest to fiscal date
        # Try exact match first, then month match
        price_current = None
        price_yoy = None

        # Extract year-month from fiscal date
        year_month = date[:7]  # YYYY-MM
        year = int(date[:4])
        yoy_year_month = f"{year - 1}{date[4:7]}"

        # Try to find prices
        if year_month in price_monthly:
            price_current = price_monthly[year_month]
        if yoy_year_month in price_monthly:
            price_yoy = price_monthly[yoy_year_month]

        # If exact month not found, try nearby months
        if price_current is None:
            for offset in ['-01', '-02', '-03']:
                test_date = year_month + offset
                if test_date in price_monthly:
                    price_current = price_monthly[test_date]
                    break

        if price_yoy is None:
            for offset in ['-01', '-02', '-03']:
                test_date = yoy_year_month + offset
                if test_date in price_monthly:
                    price_yoy = price_monthly[test_date]
                    break

        if price_current is not None and price_yoy is not None and price_yoy != 0:
            point['price_yoy'] = round(((price_current - price_yoy) / abs(price_yoy)) * 100, 2)

        trend_points.append(point)

    # Build annual trend points
    annual_earnings = earnings_data.get('annualEarnings', [])
    annual_income = income_data.get('annualReports', [])

    for i in range(len(annual_earnings) - 1):
        current_a = annual_earnings[i]
        yoy_a = annual_earnings[i + 1]

        date = current_a.get('fiscalDateEnding')
        if not date:
            continue

        point = {
            'date': date,
            'period_type': 'A',
            'price_yoy': None,
            'eps_yoy': None,
            'revenue_yoy': None,
            'margin_yoy': None
        }

        # EPS YoY
        current_eps = safe_float(current_a.get('reportedEPS'))
        yoy_eps = safe_float(yoy_a.get('reportedEPS'))
        if current_eps is not None and yoy_eps is not None and yoy_eps != 0:
            point['eps_yoy'] = round(((current_eps - yoy_eps) / abs(yoy_eps)) * 100, 2)

        # Find matching annual income report
        current_income = None
        yoy_income = None
        for j, inc in enumerate(annual_income):
            if inc.get('fiscalDateEnding') == date:
                current_income = inc
                if j + 1 < len(annual_income):
                    yoy_income = annual_income[j + 1]
                break

        if current_income and yoy_income:
            # Revenue YoY
            current_rev = safe_float(current_income.get('totalRevenue'))
            yoy_rev = safe_float(yoy_income.get('totalRevenue'))
            if current_rev is not None and yoy_rev is not None and yoy_rev != 0:
                point['revenue_yoy'] = round(((current_rev - yoy_rev) / abs(yoy_rev)) * 100, 2)

            # Operating Margin YoY
            current_margin = pct(
                safe_float(current_income.get('operatingIncome')),
                current_rev
            )
            yoy_margin = pct(
                safe_float(yoy_income.get('operatingIncome')),
                yoy_rev
            )
            if current_margin is not None and yoy_margin is not None:
                point['margin_yoy'] = round(current_margin - yoy_margin, 2)

        # Price YoY - use December close for annual
        year = date[:4]
        yoy_year = str(int(year) - 1)
        dec_current = f"{year}-12"
        dec_yoy = f"{yoy_year}-12"

        price_current = price_monthly.get(dec_current)
        price_yoy = price_monthly.get(dec_yoy)

        if price_current is not None and price_yoy is not None and price_yoy != 0:
            point['price_yoy'] = round(((price_current - price_yoy) / abs(price_yoy)) * 100, 2)

        trend_points.append(point)

    # Sort chronologically (oldest first)
    trend_points.sort(key=lambda x: x['date'])

    return trend_points

# ============================================================================
# REPORT GENERATION
# ============================================================================

def build_stat_table(stats, unit, include_yoy=True, include_secondary=True):
    """Build the standard stat block table rows (tabulate format).

    Returns a list of [header_list, row_list] for use with tabulate.
    """
    headers = ["Current", "5yr Mean", "5yr CAGR", "YoY"]
    row = [
        fmt_val(stats.get('current') or stats.get('latest') or stats.get('trailing_pe'), unit),
        fmt_val(stats.get('mean_5yr'), unit),
        fmt_val(stats.get('cagr_5yr'), 'percent'),
        fmt_val(stats.get('vs_yoy_pct'), 'percent', True),
    ]

    # Second change column (3M for price, Prev Q for EPS/Revenue)
    secondary_label = stats.get('_secondary_label', '3M / Prev Q')
    secondary_val = stats.get('vs_3mo_pct') or stats.get('vs_prev_q_pct')
    if include_secondary:
        headers.append(secondary_label)
        row.append(fmt_val(secondary_val, 'percent', True))

    headers.extend(["CV", "Slope", "Outliers"])
    row.extend([
        fmt_val(stats.get('cv'), 'percent'),
        fmt_val(stats.get('slope'), 'ratio'),
        ', '.join(stats.get('outlier_years', stats.get('annual_outliers', []))) or 'None'
    ])

    return headers, row


def build_annual_table(years, values, unit, current_label=None, current_val=None):
    """Build the annual historical values table."""
    headers = [''] + list(years)
    row_vals = [fmt_val(v, unit) for v in values]

    if current_label and current_val is not None:
        headers.append(current_label)
        row_vals.append(fmt_val(current_val, unit))

    return headers, row_vals


def build_inline_delta_table(years, values, unit, current_label=None, current_val=None, metric_name='Value'):
    """Build inline delta table with Year | Value | Δ% | Year | Value | Δ% format

    Args:
        years: List of year strings
        values: List of values corresponding to years
        unit: Unit for formatting ('dollars', 'percent', etc.)
        current_label: Optional label for current/TTM value
        current_val: Optional current/TTM value
        metric_name: Name of the metric for the first column

    Returns:
        Markdown table string with inline deltas
    """
    if not years or not values:
        return "*No data available*"

    # Build header row
    headers = ['Year']
    row = [metric_name]

    for i, (year, val) in enumerate(zip(years, values)):
        # Add year/value
        headers.extend([year, 'Δ%'])
        row.append(fmt_val(val, unit))

        # Calculate delta from previous year
        if i > 0 and values[i-1] is not None and val is not None and values[i-1] != 0:
            delta_pct = round(((val - values[i-1]) / abs(values[i-1])) * 100, 2)
            row.append(fmt_val(delta_pct, 'percent', is_delta=True))
        else:
            row.append('—')

    # Add current/TTM column if provided
    if current_label and current_val is not None:
        headers.extend([current_label + '*', 'Δ%*'])
        row.append(fmt_val(current_val, unit))

        # Delta vs most recent year
        if values and values[-1] is not None and values[-1] != 0:
            delta_pct = round(((current_val - values[-1]) / abs(values[-1])) * 100, 2)
            row.append(fmt_val(delta_pct, 'percent', is_delta=True))
        else:
            row.append('—')

    # Remove the last Δ% column header (doesn't make sense for final value)
    if headers[-1] == 'Δ%' or headers[-1] == 'Δ%*':
        headers = headers[:-1]
        row = row[:-1]

    return tabulate([row], headers=headers, tablefmt="pipe")


def generate_yoy_trend_chart(trend_points):
    """Generate a markdown table showing YoY % change trends for all metrics.

    Args:
        trend_points: List of trend data points from build_yoy_trend_data

    Returns:
        String containing markdown-formatted table
    """
    if not trend_points:
        return "*Insufficient data for YoY trend chart*"

    # Limit to most recent data points (last 12 for readability)
    display_points = trend_points[-12:] if len(trend_points) > 12 else trend_points

    headers = ["Period", "Date", "Price YoY %", "EPS YoY %", "Revenue YoY %", "Op Margin YoY pp"]
    rows = []

    for point in display_points:
        rows.append([
            point['period_type'],
            point['date'],
            fmt_val(point.get('price_yoy'), 'percent', True),
            fmt_val(point.get('eps_yoy'), 'percent', True),
            fmt_val(point.get('revenue_yoy'), 'percent', True),
            fmt_val(point.get('margin_yoy'), 'percent', True)
        ])

    return tabulate(rows, headers=headers, tablefmt="pipe")


def generate_screening_report(tickers, all_results):
    """Generate the screening markdown report"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"screening_{date_str}.md"

    lines = []
    lines.append(f"# Stock Screening — {date_str}")
    lines.append("")
    lines.append(f"**Tickers:** {', '.join(tickers)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for ticker in tickers:
        results = all_results.get(ticker)
        if not results:
            lines.append(f"## {ticker}")
            lines.append("")
            lines.append("Data unavailable.")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        price = results.get('price')
        eps = results.get('eps')
        revenue = results.get('revenue')
        margin = results.get('margin')
        pe = results.get('pe')
        estimates = results.get('estimates')

        lines.append(f"## {ticker}")
        lines.append("")

        # ==== HEADER BLOCK ====
        # Build header line with key metrics
        header_parts = []

        if price:
            header_parts.append(f"**Current Price:** {fmt_val(price['current'], 'dollars')} (as of {price['current_date']})")
        else:
            header_parts.append("**Current Price:** —")

        if eps and eps.get('ttm') is not None:
            header_parts.append(f"**TTM EPS:** {fmt_val(eps['ttm'], 'dollars')}")
        else:
            header_parts.append("**TTM EPS:** —")

        if pe and pe.get('trailing_pe') is not None:
            header_parts.append(f"**Trailing P/E:** {fmt_val(pe['trailing_pe'], 'ratio')}")
        else:
            header_parts.append("**Trailing P/E:** —")

        lines.append(' | '.join(header_parts))
        lines.append("")

        # Price-EPS Correlation on second line
        price_eps_corr = results.get('price_eps_correlation')
        if price_eps_corr is not None:
            # Interpret correlation
            if price_eps_corr >= 0.7:
                interp = "Strong positive"
            elif price_eps_corr >= 0.3:
                interp = "Moderate positive"
            elif price_eps_corr >= -0.3:
                interp = "Weak"
            elif price_eps_corr >= -0.7:
                interp = "Moderate negative"
            else:
                interp = "Strong negative"
            lines.append(f"**Price-EPS Correlation (5yr):** {price_eps_corr} ({interp})")
        else:
            lines.append("**Price-EPS Correlation (5yr):** —")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== SUMMARY TABLE ====
        lines.append("### Summary")
        lines.append("")

        # Enhanced summary table with more columns
        summary_headers = ["Metric", "Current", "5-Yr Avg", "CAGR", "YoY Δ%", "3M/QoQ Δ%", "CV", "Slope"]
        summary_rows = []

        if price:
            summary_rows.append([
                "Price",
                fmt_val(price.get('current'), 'dollars'),
                fmt_val(price.get('mean_5yr'), 'dollars'),
                fmt_val(price.get('cagr_5yr'), 'percent'),
                fmt_val(price.get('vs_yoy_pct'), 'percent', True),
                fmt_val(price.get('vs_3mo_pct'), 'percent', True),
                fmt_val(price.get('cv'), 'percent'),
                fmt_val(price.get('slope'), 'ratio'),
            ])
        else:
            summary_rows.append(["Price", "—", "—", "—", "—", "—", "—", "—"])

        if eps:
            summary_rows.append([
                "EPS",
                fmt_val(eps.get('ttm'), 'dollars'),
                fmt_val(eps.get('mean_5yr'), 'dollars'),
                fmt_val(eps.get('cagr_5yr'), 'percent'),
                fmt_val(eps.get('vs_yoy_pct'), 'percent', True),
                fmt_val(eps.get('vs_prev_q_pct'), 'percent', True),
                fmt_val(eps.get('cv'), 'percent'),
                fmt_val(eps.get('slope'), 'ratio'),
            ])
        else:
            summary_rows.append(["EPS", "—", "—", "—", "—", "—", "—", "—"])

        if revenue:
            summary_rows.append([
                "Revenue",
                fmt_val(revenue.get('latest'), 'dollars_large'),
                fmt_val(revenue.get('mean_5yr'), 'dollars_large'),
                fmt_val(revenue.get('cagr_5yr'), 'percent'),
                fmt_val(revenue.get('vs_yoy_pct'), 'percent', True),
                fmt_val(revenue.get('vs_prev_q_pct'), 'percent', True),
                fmt_val(revenue.get('cv'), 'percent'),
                fmt_val(revenue.get('slope'), 'ratio'),
            ])
        else:
            summary_rows.append(["Revenue", "—", "—", "—", "—", "—", "—", "—"])

        if margin:
            summary_rows.append([
                "Op. Margin",
                fmt_val(margin.get('latest'), 'percent'),
                fmt_val(margin.get('mean_5yr'), 'percent'),
                fmt_val(margin.get('cagr_5yr'), 'percent'),
                fmt_val(margin.get('vs_yoy_pct'), 'percent', True) + 'pp' if margin.get('vs_yoy_pct') is not None else "—",
                fmt_val(margin.get('vs_prev_q_pct'), 'percent', True) + 'pp' if margin.get('vs_prev_q_pct') is not None else "—",
                fmt_val(margin.get('cv'), 'percent'),
                fmt_val(margin.get('slope'), 'ratio'),
            ])
        else:
            summary_rows.append(["Op. Margin", "—", "—", "—", "—", "—", "—", "—"])

        lines.append(tabulate(summary_rows, headers=summary_headers, tablefmt="pipe"))
        lines.append("")
        lines.append("---")
        lines.append("")

        # YoY Trend Chart
        yoy_trend = results.get('yoy_trend', [])
        if yoy_trend:
            lines.append("### YoY Trend Analysis")
            lines.append("")
            lines.append("*Year-over-year % changes (last 12 periods). Shows how metrics move together and diverge.*")
            lines.append("")
            lines.append(generate_yoy_trend_chart(yoy_trend))
            lines.append("")
            lines.append("---")
            lines.append("")

        # ==== PRICE TREND ====
        lines.append("### Price Trend")
        lines.append("")
        if price and price.get('annual_years'):
            # Inline delta table
            lines.append(build_inline_delta_table(
                price['annual_years'], price['annual_values'], 'dollars',
                'Current', price['current'], 'Price'
            ))
            lines.append("")
            lines.append(f"*Current as of {price['current_date']}*")
            lines.append("")

            # Stats summary line
            stats_parts = [
                f"5-Yr Avg {fmt_val(price['mean_5yr'], 'dollars')}",
                f"CAGR {fmt_val(price['cagr_5yr'], 'percent')}",
                f"CV {fmt_val(price['cv'], 'percent')}",
                f"Slope {fmt_val(price['slope'], 'ratio')}",
                f"52w High {fmt_val(price['high_52w'], 'dollars')} ({fmt_val(price['vs_52w_high_pct'], 'percent', True)})",
                f"52w Low {fmt_val(price['low_52w'], 'dollars')} ({fmt_val(price['vs_52w_low_pct'], 'percent', True)})",
            ]
            outliers = ', '.join(price['annual_outliers']) or 'None'
            stats_parts.append(f"Outliers: {outliers}")
            lines.append("**Stats:** " + ' | '.join(stats_parts))
        else:
            lines.append("*No price data available*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== EPS TREND ====
        lines.append("### EPS Trend")
        lines.append("")
        if eps and eps.get('annual_years'):
            # Inline delta table
            lines.append(build_inline_delta_table(
                eps['annual_years'], eps['annual_values'], 'dollars',
                'TTM', eps['ttm'], 'EPS'
            ))
            lines.append("")
            lines.append(f"*TTM through {eps['latest_date']}*")
            lines.append("")

            # Stats summary line
            stats_parts = [
                f"Latest Q {fmt_val(eps['latest'], 'dollars')}",
                f"5-Yr Avg {fmt_val(eps['mean_5yr'], 'dollars')}",
                f"CAGR {fmt_val(eps['cagr_5yr'], 'percent')}",
                f"CV {fmt_val(eps['cv'], 'percent')}",
                f"Slope {fmt_val(eps['slope'], 'ratio')}",
            ]
            outliers = ', '.join(eps['outlier_years']) or 'None'
            stats_parts.append(f"Outliers: {outliers}")
            lines.append("**Stats:** " + ' | '.join(stats_parts))
        else:
            lines.append("*No EPS data available*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== REVENUE TREND ====
        lines.append("### Revenue Trend")
        lines.append("")
        if revenue and revenue.get('annual_years'):
            # Determine current label and value
            current_label = None
            current_val = None
            if revenue.get('ytd_annualized'):
                current_label = f"YTD Ann. ({revenue['ytd_num_quarters']}Q)"
                current_val = revenue['ytd_annualized']

            # Inline delta table
            lines.append(build_inline_delta_table(
                revenue['annual_years'], revenue['annual_values'], 'dollars_large',
                current_label, current_val, 'Revenue'
            ))
            lines.append("")
            if current_label:
                lines.append(f"*{current_label} annualized based on YTD data*")
                lines.append("")

            # Stats summary line
            stats_parts = [
                f"Latest {fmt_val(revenue['latest'], 'dollars_large')}",
                f"5-Yr Avg {fmt_val(revenue['mean_5yr'], 'dollars_large')}",
                f"CAGR {fmt_val(revenue['cagr_5yr'], 'percent')}",
                f"CV {fmt_val(revenue['cv'], 'percent')}",
                f"Slope {fmt_val(revenue['slope'], 'ratio')}",
            ]
            outliers = ', '.join(revenue['outlier_years']) or 'None'
            stats_parts.append(f"Outliers: {outliers}")
            lines.append("**Stats:** " + ' | '.join(stats_parts))
        else:
            lines.append("*No revenue data available*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== OPERATING MARGIN TREND ====
        lines.append("### Operating Margin Trend")
        lines.append("")
        if margin and margin.get('annual_years'):
            # Determine current label and value
            current_label = None
            current_val = None
            if margin.get('ytd_margin') is not None:
                current_label = f"YTD ({margin['ytd_num_quarters']}Q)"
                current_val = margin['ytd_margin']

            # Inline delta table
            lines.append(build_inline_delta_table(
                margin['annual_years'], margin['annual_values'], 'percent',
                current_label, current_val, 'Op. Margin'
            ))
            lines.append("")
            if current_label:
                lines.append(f"*{current_label} based on YTD data. Δ% shows percentage point changes.*")
                lines.append("")

            # Stats summary line
            stats_parts = [
                f"Latest {fmt_val(margin['latest'], 'percent')}",
                f"5-Yr Avg {fmt_val(margin['mean_5yr'], 'percent')}",
                f"CAGR {fmt_val(margin['cagr_5yr'], 'percent')}",
                f"CV {fmt_val(margin['cv'], 'percent')}",
                f"Slope {fmt_val(margin['slope'], 'ratio')}",
            ]
            outliers = ', '.join(margin['outlier_years']) or 'None'
            stats_parts.append(f"Outliers: {outliers}")
            lines.append("**Stats:** " + ' | '.join(stats_parts))
        else:
            lines.append("*No operating margin data available*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== P/E TREND ====
        lines.append("### P/E Trend")
        lines.append("")
        if pe and pe.get('annual_years'):
            # Inline delta table
            lines.append(build_inline_delta_table(
                pe['annual_years'], pe['annual_values'], 'ratio',
                'Trailing', pe['trailing_pe'], 'P/E'
            ))
            lines.append("")
            lines.append(f"*Trailing P/E based on current price ({fmt_val(pe['current_price'], 'dollars')}) and TTM EPS ({fmt_val(pe['ttm_eps'], 'dollars')})*")
            lines.append("")

            # Stats summary line
            stats_parts = [
                f"Trailing {fmt_val(pe['trailing_pe'], 'ratio')}",
                f"5-Yr Avg {fmt_val(pe['mean_5yr'], 'ratio')}",
                f"vs 5yr Avg {fmt_val(pe['vs_5yr_avg_pct'], 'percent', True)}",
                f"CV {fmt_val(pe['cv'], 'percent')}",
                f"Slope {fmt_val(pe['slope'], 'ratio')}",
            ]
            outliers = ', '.join(pe['outlier_years']) or 'None'
            stats_parts.append(f"Outliers: {outliers}")
            lines.append("**Stats:** " + ' | '.join(stats_parts))
        else:
            lines.append("*No P/E data available (negative or insufficient earnings)*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ==== ESTIMATES & CONSENSUS ====
        lines.append("### Estimates & Consensus")
        lines.append("")
        if estimates:
            if estimates.get('latest_actual_eps') is not None:
                lines.append(f"**Latest Actual EPS:** {fmt_val(estimates['latest_actual_eps'], 'dollars')}")
                lines.append("")

            # Combined EPS and Revenue estimates table
            est_headers = ["Horizon", "EPS Consensus", "Range (Low-High)", "Analysts", "30d Rev", "Revenue Consensus", "Revenue Range"]
            est_rows = []
            for est in [estimates.get('next_quarter'), estimates.get('current_fiscal_year'), estimates.get('next_fiscal_year')]:
                if est and (est.get('eps_avg') is not None or est.get('revenue_avg') is not None):
                    label = est.get('horizon', '—')
                    date = est.get('date', '')

                    # EPS data
                    eps_consensus = fmt_val(est.get('eps_avg'), 'dollars')
                    eps_range = "—"
                    if est.get('eps_low') is not None and est.get('eps_high') is not None:
                        eps_range = f"{fmt_val(est['eps_low'], 'dollars')} - {fmt_val(est['eps_high'], 'dollars')}"

                    analysts = int(est['analyst_count']) if est.get('analyst_count') else '—'

                    # 30d revision
                    rev_30d = "—"
                    if est.get('revision_30d') is not None and est.get('eps_avg') is not None:
                        diff = round(est['eps_avg'] - est['revision_30d'], 4)
                        if diff != 0:
                            rev_30d = fmt_val(diff, 'dollars', True)
                        else:
                            rev_30d = "flat"

                    # Revenue data
                    rev_consensus = fmt_val(est.get('revenue_avg'), 'dollars_large')
                    rev_range = "—"
                    if est.get('revenue_low') is not None and est.get('revenue_high') is not None:
                        rev_range = f"{fmt_val(est['revenue_low'], 'dollars_large')} - {fmt_val(est['revenue_high'], 'dollars_large')}"

                    est_rows.append([
                        f"{label} ({date})",
                        eps_consensus,
                        eps_range,
                        analysts,
                        rev_30d,
                        rev_consensus,
                        rev_range
                    ])

            if est_rows:
                lines.append(tabulate(est_rows, headers=est_headers, tablefmt="pipe"))
                lines.append("")

            # Beat/miss history
            beat_miss = eps.get('beat_miss_history', []) if eps else []
            if beat_miss:
                lines.append("**Beat/Miss History (Last 4 Quarters):**")
                lines.append("")
                bm_headers = ["Quarter", "Reported", "Estimated", "Surprise", "Surprise %"]
                bm_rows = []
                for bm in beat_miss:
                    bm_rows.append([
                        bm['date'],
                        fmt_val(bm['reported'], 'dollars'),
                        fmt_val(bm['estimated'], 'dollars'),
                        fmt_val(bm['surprise'], 'dollars', True),
                        fmt_val(bm['surprise_pct'], 'percent', True)
                    ])
                lines.append(tabulate(bm_rows, headers=bm_headers, tablefmt="pipe"))
                lines.append("")
        else:
            lines.append("*No estimates data available*")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Write file
    report = "\n".join(lines)
    with open(filename, 'w') as f:
        f.write(report)

    return filename

# ============================================================================
# MAIN
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python SCRIPT_screening.py TICKER1 [TICKER2] ... [TICKER5]")
        print("Example: python SCRIPT_screening.py AAPL MSFT GOOGL")
        sys.exit(1)

    tickers = [t.upper() for t in sys.argv[1:]]
    if len(tickers) > 5:
        console.print("[yellow]Warning: Maximum 5 tickers. Using first 5.[/yellow]")
        tickers = tickers[:5]

    api_calls_needed = len(tickers) * 4

    console.print(f"\n[bold]{'=' * 50}[/bold]")
    console.print(f"  [bold cyan]Preliminary Stock Screening[/bold cyan]")
    console.print(f"[bold]{'=' * 50}[/bold]")
    console.print(f"  Tickers: {', '.join(tickers)}")
    console.print(f"  API calls needed: {api_calls_needed} ({len(tickers)} x 4 endpoints)")
    console.print(f"[bold]{'=' * 50}[/bold]\n")

    all_results = {}

    for i, ticker in enumerate(tickers):
        data = fetch_screening_data(ticker)

        results = {}
        results['price'] = calculate_price_stats(data.get('price_monthly'))
        results['eps'] = calculate_eps_stats(data.get('earnings'))
        results['revenue'] = calculate_revenue_stats(data.get('income'))
        results['margin'] = calculate_margin_stats(data.get('income'))
        results['pe'] = calculate_pe_stats(results['price'], results['eps'])
        results['estimates'] = calculate_estimates_stats(
            data.get('earnings_estimates'), data.get('earnings')
        )

        # Calculate EPS-Price correlation
        price_corr = None
        if results['price'] and results['eps']:
            price_annual = results['price'].get('annual_values', [])
            eps_annual = results['eps'].get('annual_values', [])
            if price_annual and eps_annual:
                price_corr = calculate_correlation(price_annual, eps_annual)
        results['price_eps_correlation'] = price_corr

        # Build YoY trend data
        results['yoy_trend'] = build_yoy_trend_data(
            data.get('price_monthly'),
            data.get('earnings'),
            data.get('income')
        )

        all_results[ticker] = results

        # Rate limit delay between tickers (skip after last ticker)
        # Alpha Vantage free tier: 5 calls/minute
        # Each ticker = 4 calls, so we need to ensure we don't exceed 5 calls in 60s
        # With 12s delay between endpoints: 4 calls take ~36s
        # We need to wait at least 24s before starting the next ticker to ensure
        # the next ticker's 1st call is >=60s after this ticker's 1st call
        if i < len(tickers) - 1:
            console.print(f"\n  [cyan]Waiting 24s before fetching next ticker (rate limit protection)...[/cyan]\n")
            time.sleep(24)

    # Generate report
    filename = generate_screening_report(tickers, all_results)

    console.print(f"\n[bold]{'=' * 50}[/bold]")
    console.print(f"  [bold green]✓ Screening complete![/bold green]")
    console.print(f"  Output: [bold]{filename}[/bold]")
    console.print(f"[bold]{'=' * 50}[/bold]\n")


if __name__ == '__main__':
    main()
