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
        else:
            console.print(f"  [red]✗ {key} failed[/red]")
            data[key] = None

        # Rate limit delay (skip after last call)
        if i < len(endpoints) - 1:
            time.sleep(API_DELAY)

    return data

# ============================================================================
# CALCULATIONS
# ============================================================================

def calculate_price_stats(price_data):
    """Calculate price trend statistics from monthly adjusted data"""
    if not price_data:
        return None

    time_series = price_data.get('Monthly Adjusted Time Series', {})
    if not time_series:
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

        # ==== SUMMARY ====
        lines.append("### Summary")
        lines.append("")

        # Summary table
        summary_headers = ["Metric", "YoY", "3M / Prev Q", "5yr CAGR"]
        summary_rows = []

        if price:
            summary_rows.append([
                "Price",
                fmt_val(price.get('vs_yoy_pct'), 'percent', True),
                fmt_val(price.get('vs_3mo_pct'), 'percent', True),
                fmt_val(price.get('cagr_5yr'), 'percent'),
            ])
        else:
            summary_rows.append(["Price", "—", "—", "—"])

        if eps:
            summary_rows.append([
                "EPS",
                fmt_val(eps.get('vs_yoy_pct'), 'percent', True),
                fmt_val(eps.get('vs_prev_q_pct'), 'percent', True),
                fmt_val(eps.get('cagr_5yr'), 'percent'),
            ])
        else:
            summary_rows.append(["EPS", "—", "—", "—"])

        if revenue:
            summary_rows.append([
                "Revenue",
                fmt_val(revenue.get('vs_yoy_pct'), 'percent', True),
                fmt_val(revenue.get('vs_prev_q_pct'), 'percent', True),
                fmt_val(revenue.get('cagr_5yr'), 'percent'),
            ])
        else:
            summary_rows.append(["Revenue", "—", "—", "—"])

        if margin:
            summary_rows.append([
                "Op. Margin",
                fmt_val(margin.get('vs_yoy_pct'), 'percent', True),
                fmt_val(margin.get('vs_prev_q_pct'), 'percent', True),
                fmt_val(margin.get('cagr_5yr'), 'percent'),
            ])
        else:
            summary_rows.append(["Op. Margin", "—", "—", "—"])

        lines.append(tabulate(summary_rows, headers=summary_headers, tablefmt="pipe"))
        lines.append("")

        # P/E summary line
        if pe:
            pe_parts = [f"Trailing {fmt_val(pe['trailing_pe'], 'ratio')}"]
            pe_parts.append(f"YoY {fmt_val(pe['vs_yoy_pct'], 'percent', True)}")
            pe_parts.append(f"vs 5yr Avg ({fmt_val(pe['mean_5yr'], 'ratio')}): {fmt_val(pe['vs_5yr_avg_pct'], 'percent', True)}")
            lines.append(f"**P/E:** {' | '.join(pe_parts)}")
        else:
            lines.append("**P/E:** —")
        lines.append("")

        # Estimates summary line
        if estimates:
            nq = estimates.get('next_quarter')
            if nq and nq.get('eps_avg') is not None:
                est_parts = [f"Latest actual EPS {fmt_val(estimates['latest_actual_eps'], 'dollars')}"]
                est_parts.append(f"Next Q consensus {fmt_val(nq['eps_avg'], 'dollars')}")
                est_parts.append(f"Delta {fmt_val(estimates['delta_actual_vs_next_q_pct'], 'percent', True)}")
                if nq.get('analyst_count'):
                    est_parts.append(f"{int(nq['analyst_count'])} analysts")
                lines.append(f"**Estimates:** {' | '.join(est_parts)}")
            else:
                lines.append("**Estimates:** —")
        else:
            lines.append("**Estimates:** —")
        lines.append("")

        # ==== PRICE TREND ====
        lines.append("### Price Trend")
        lines.append("")
        if price and price.get('annual_years'):
            # Annual values table
            headers, row = build_annual_table(
                price['annual_years'], price['annual_values'], 'dollars',
                'Current', price['current']
            )
            row = ['Price'] + row
            headers = [''] + headers[1:]  # Remove empty first col, use '' for tabulate
            lines.append(tabulate([row], headers=headers, tablefmt="pipe"))
            lines.append("")

            # Stats table
            stat_headers = ["Current", "5yr Mean", "5yr CAGR", "YoY", "3M", "CV", "Slope", "52w High", "52w Low", "Outliers"]
            stat_row = [
                fmt_val(price['current'], 'dollars'),
                fmt_val(price['mean_5yr'], 'dollars'),
                fmt_val(price['cagr_5yr'], 'percent'),
                fmt_val(price['vs_yoy_pct'], 'percent', True),
                fmt_val(price['vs_3mo_pct'], 'percent', True),
                fmt_val(price['cv'], 'percent'),
                fmt_val(price['slope'], 'ratio'),
                f"{fmt_val(price['high_52w'], 'dollars')} ({fmt_val(price['vs_52w_high_pct'], 'percent', True)})",
                f"{fmt_val(price['low_52w'], 'dollars')} ({fmt_val(price['vs_52w_low_pct'], 'percent', True)})",
                ', '.join(price['annual_outliers']) or 'None'
            ]
            lines.append(tabulate([stat_row], headers=stat_headers, tablefmt="pipe"))
        else:
            lines.append("*No price data available*")
        lines.append("")

        # ==== EPS TREND ====
        lines.append("### EPS Trend")
        lines.append("")
        if eps and eps.get('annual_years'):
            headers, row = build_annual_table(
                eps['annual_years'], eps['annual_values'], 'dollars',
                'TTM', eps['ttm']
            )
            row = ['EPS'] + row
            headers = [''] + headers[1:]
            lines.append(tabulate([row], headers=headers, tablefmt="pipe"))
            lines.append("")

            stat_headers = ["Latest Q", "5yr Mean", "5yr CAGR", "YoY", "Prev Q", "CV", "Slope", "Outliers"]
            stat_row = [
                fmt_val(eps['latest'], 'dollars'),
                fmt_val(eps['mean_5yr'], 'dollars'),
                fmt_val(eps['cagr_5yr'], 'percent'),
                fmt_val(eps['vs_yoy_pct'], 'percent', True),
                fmt_val(eps['vs_prev_q_pct'], 'percent', True),
                fmt_val(eps['cv'], 'percent'),
                fmt_val(eps['slope'], 'ratio'),
                ', '.join(eps['outlier_years']) or 'None'
            ]
            lines.append(tabulate([stat_row], headers=stat_headers, tablefmt="pipe"))
        else:
            lines.append("*No EPS data available*")
        lines.append("")

        # ==== REVENUE TREND ====
        lines.append("### Revenue Trend")
        lines.append("")
        if revenue and revenue.get('annual_years'):
            current_label = None
            current_val = None
            if revenue.get('ytd_annualized'):
                current_label = f"YTD Ann. ({revenue['ytd_num_quarters']}Q)"
                current_val = revenue['ytd_annualized']

            headers, row = build_annual_table(
                revenue['annual_years'], revenue['annual_values'], 'dollars_large',
                current_label, current_val
            )
            row = ['Revenue'] + row
            headers = [''] + headers[1:]
            lines.append(tabulate([row], headers=headers, tablefmt="pipe"))
            lines.append("")

            stat_headers = ["Latest", "5yr Mean", "5yr CAGR", "YoY", "Prev Q", "CV", "Slope", "Outliers"]
            stat_row = [
                fmt_val(revenue['latest'], 'dollars_large'),
                fmt_val(revenue['mean_5yr'], 'dollars_large'),
                fmt_val(revenue['cagr_5yr'], 'percent'),
                fmt_val(revenue['vs_yoy_pct'], 'percent', True),
                fmt_val(revenue['vs_prev_q_pct'], 'percent', True),
                fmt_val(revenue['cv'], 'percent'),
                fmt_val(revenue['slope'], 'ratio'),
                ', '.join(revenue['outlier_years']) or 'None'
            ]
            lines.append(tabulate([stat_row], headers=stat_headers, tablefmt="pipe"))
        else:
            lines.append("*No revenue data available*")
        lines.append("")

        # ==== OPERATING MARGIN TREND ====
        lines.append("### Operating Margin Trend")
        lines.append("")
        if margin and margin.get('annual_years'):
            current_label = None
            current_val = None
            if margin.get('ytd_margin') is not None:
                current_label = f"YTD ({margin['ytd_num_quarters']}Q)"
                current_val = margin['ytd_margin']

            headers, row = build_annual_table(
                margin['annual_years'], margin['annual_values'], 'percent',
                current_label, current_val
            )
            row = ['Op. Margin'] + row
            headers = [''] + headers[1:]
            lines.append(tabulate([row], headers=headers, tablefmt="pipe"))
            lines.append("")

            stat_headers = ["Latest", "5yr Mean", "5yr CAGR", "YoY (pp)", "Prev Q (pp)", "CV", "Slope", "Outliers"]
            stat_row = [
                fmt_val(margin['latest'], 'percent'),
                fmt_val(margin['mean_5yr'], 'percent'),
                fmt_val(margin['cagr_5yr'], 'percent'),
                fmt_val(margin['vs_yoy_pct'], 'percent', True),
                fmt_val(margin['vs_prev_q_pct'], 'percent', True),
                fmt_val(margin['cv'], 'percent'),
                fmt_val(margin['slope'], 'ratio'),
                ', '.join(margin['outlier_years']) or 'None'
            ]
            lines.append(tabulate([stat_row], headers=stat_headers, tablefmt="pipe"))
        else:
            lines.append("*No operating margin data available*")
        lines.append("")

        # ==== P/E TREND ====
        lines.append("### P/E Trend")
        lines.append("")
        if pe and pe.get('annual_years'):
            headers, row = build_annual_table(
                pe['annual_years'], pe['annual_values'], 'ratio',
                'Trailing', pe['trailing_pe']
            )
            row = ['P/E'] + row
            headers = [''] + headers[1:]
            lines.append(tabulate([row], headers=headers, tablefmt="pipe"))
            lines.append("")

            stat_headers = ["Trailing", "5yr Mean", "vs 5yr Avg", "YoY", "CV", "Slope", "Outliers"]
            stat_row = [
                fmt_val(pe['trailing_pe'], 'ratio'),
                fmt_val(pe['mean_5yr'], 'ratio'),
                fmt_val(pe['vs_5yr_avg_pct'], 'percent', True),
                fmt_val(pe['vs_yoy_pct'], 'percent', True),
                fmt_val(pe['cv'], 'percent'),
                fmt_val(pe['slope'], 'ratio'),
                ', '.join(pe['outlier_years']) or 'None'
            ]
            lines.append(tabulate([stat_row], headers=stat_headers, tablefmt="pipe"))
        else:
            lines.append("*No P/E data available (negative or insufficient earnings)*")
        lines.append("")

        # ==== EPS ESTIMATES ====
        lines.append("### EPS Estimates")
        lines.append("")
        if estimates:
            if estimates.get('latest_actual_eps') is not None:
                lines.append(f"**Latest Actual EPS:** {fmt_val(estimates['latest_actual_eps'], 'dollars')}")
                lines.append("")

            # EPS estimates table
            est_headers = ["Horizon", "Consensus", "Low", "High", "Analysts", "30d Revision"]
            est_rows = []
            for est in [estimates.get('next_quarter'), estimates.get('current_fiscal_year'), estimates.get('next_fiscal_year')]:
                if est and est.get('eps_avg') is not None:
                    label = est.get('horizon', '—')
                    date = est.get('date', '')

                    # 30d revision direction
                    rev_30d = "—"
                    if est.get('revision_30d') is not None and est.get('eps_avg') is not None:
                        diff = round(est['eps_avg'] - est['revision_30d'], 4)
                        if diff != 0:
                            rev_30d = fmt_val(diff, 'dollars', True)
                        else:
                            rev_30d = "flat"

                    est_rows.append([
                        f"{label} ({date})",
                        fmt_val(est['eps_avg'], 'dollars'),
                        fmt_val(est['eps_low'], 'dollars'),
                        fmt_val(est['eps_high'], 'dollars'),
                        int(est['analyst_count']) if est.get('analyst_count') else '—',
                        rev_30d
                    ])

            if est_rows:
                lines.append(tabulate(est_rows, headers=est_headers, tablefmt="pipe"))
                lines.append("")

            # Revenue estimates table
            rev_headers = ["Horizon", "Consensus", "Low", "High", "Analysts"]
            rev_rows = []
            for est in [estimates.get('next_quarter'), estimates.get('current_fiscal_year'), estimates.get('next_fiscal_year')]:
                if est and est.get('revenue_avg') is not None:
                    label = est.get('horizon', '—')
                    date = est.get('date', '')
                    rev_rows.append([
                        f"{label} ({date})",
                        fmt_val(est['revenue_avg'], 'dollars_large'),
                        fmt_val(est['revenue_low'], 'dollars_large'),
                        fmt_val(est['revenue_high'], 'dollars_large'),
                        int(est['revenue_analyst_count']) if est.get('revenue_analyst_count') else '—'
                    ])

            if rev_rows:
                lines.append("**Revenue Estimates:**")
                lines.append("")
                lines.append(tabulate(rev_rows, headers=rev_headers, tablefmt="pipe"))
                lines.append("")

            # Beat/miss history
            beat_miss = eps.get('beat_miss_history', []) if eps else []
            if beat_miss:
                lines.append("**Recent Beat/Miss History:**")
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

    for ticker in tickers:
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

        all_results[ticker] = results

    # Generate report
    filename = generate_screening_report(tickers, all_results)

    console.print(f"\n[bold]{'=' * 50}[/bold]")
    console.print(f"  [bold green]✓ Screening complete![/bold green]")
    console.print(f"  Output: [bold]{filename}[/bold]")
    console.print(f"[bold]{'=' * 50}[/bold]\n")


if __name__ == '__main__':
    main()
