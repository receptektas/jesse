import math

import numpy as np


def _safe(value):
    """Convert to Python float and return None if NaN/Inf, else return the float.

    Using float() ensures numpy scalars (np.float64, np.nan) are converted to
    JSON-serializable Python natives before they reach json.dump.
    """
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _trade_metrics(trades: list, timeframe_seconds=None) -> dict:
    """Compute trade metrics for a given list of to_json trade dicts."""
    total = len(trades)
    if total == 0:
        return {
            'net_pnl': None,
            'gross_profit': None,
            'gross_loss': None,
            'profit_factor': None,
            'commission_paid': None,
            'expected_payoff': None,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'percent_profitable': None,
            'avg_pnl': None,
            'avg_winning_trade': None,
            'avg_losing_trade': None,
            'ratio_avg_win_avg_loss': None,
            'largest_winning_trade': None,
            'largest_winning_trade_pct': None,
            'largest_winner_as_pct_of_gross_profit': None,
            'largest_losing_trade': None,
            'largest_losing_trade_pct': None,
            'largest_loser_as_pct_of_gross_loss': None,
            'avg_bars_in_trades': None,
            'avg_bars_in_winning_trades': None,
            'avg_bars_in_losing_trades': None,
        }

    winners = [t for t in trades if t['PNL'] > 0]
    losers = [t for t in trades if t['PNL'] < 0]

    net_pnl = sum(t['PNL'] for t in trades)
    gross_profit = sum(t['PNL'] for t in winners) if winners else 0.0
    gross_loss = sum(t['PNL'] for t in losers) if losers else 0.0
    commission_paid = sum(t['fee'] for t in trades)
    winning_count = len(winners)
    losing_count = len(losers)

    profit_factor = _safe(abs(gross_profit) / abs(gross_loss)) if gross_loss != 0 else None
    expected_payoff = _safe(net_pnl / total)
    avg_pnl = _safe(net_pnl / total)
    avg_winning_trade = _safe(gross_profit / winning_count) if winning_count else None
    avg_losing_trade = _safe(gross_loss / losing_count) if losing_count else None

    ratio_avg_win_avg_loss = None
    if avg_winning_trade is not None and avg_losing_trade is not None and avg_losing_trade != 0:
        ratio_avg_win_avg_loss = _safe(avg_winning_trade / abs(avg_losing_trade))

    largest_winning_trade = max((t['PNL'] for t in winners), default=None)
    largest_winning_trade_pct = max((t['PNL_percentage'] for t in winners), default=None)
    largest_winner_as_pct_of_gross_profit = None
    if largest_winning_trade is not None and gross_profit != 0:
        largest_winner_as_pct_of_gross_profit = _safe(largest_winning_trade / gross_profit * 100)

    largest_losing_trade = min((t['PNL'] for t in losers), default=None)
    largest_losing_trade_pct = min((t['PNL_percentage'] for t in losers), default=None)
    largest_loser_as_pct_of_gross_loss = None
    if largest_losing_trade is not None and gross_loss != 0:
        largest_loser_as_pct_of_gross_loss = _safe(abs(largest_losing_trade) / abs(gross_loss) * 100)

    avg_bars_in_trades = None
    avg_bars_in_winning_trades = None
    avg_bars_in_losing_trades = None
    if timeframe_seconds and timeframe_seconds > 0:
        holding_periods = [t['holding_period'] for t in trades if t.get('holding_period') is not None]
        if holding_periods:
            avg_bars_in_trades = _safe(np.mean(holding_periods) / timeframe_seconds)
        winning_periods = [t['holding_period'] for t in winners if t.get('holding_period') is not None]
        if winning_periods:
            avg_bars_in_winning_trades = _safe(np.mean(winning_periods) / timeframe_seconds)
        losing_periods = [t['holding_period'] for t in losers if t.get('holding_period') is not None]
        if losing_periods:
            avg_bars_in_losing_trades = _safe(np.mean(losing_periods) / timeframe_seconds)

    return {
        'net_pnl': _safe(net_pnl),
        'gross_profit': _safe(gross_profit),
        'gross_loss': _safe(gross_loss),
        'profit_factor': profit_factor,
        'commission_paid': _safe(commission_paid),
        'expected_payoff': expected_payoff,
        'total_trades': total,
        'winning_trades': winning_count,
        'losing_trades': losing_count,
        'percent_profitable': _safe(winning_count / total * 100),
        'avg_pnl': avg_pnl,
        'avg_winning_trade': avg_winning_trade,
        'avg_losing_trade': avg_losing_trade,
        'ratio_avg_win_avg_loss': ratio_avg_win_avg_loss,
        'largest_winning_trade': _safe(largest_winning_trade),
        'largest_winning_trade_pct': _safe(largest_winning_trade_pct),
        'largest_winner_as_pct_of_gross_profit': largest_winner_as_pct_of_gross_profit,
        'largest_losing_trade': _safe(largest_losing_trade),
        'largest_losing_trade_pct': _safe(largest_losing_trade_pct),
        'largest_loser_as_pct_of_gross_loss': largest_loser_as_pct_of_gross_loss,
        'avg_bars_in_trades': avg_bars_in_trades,
        'avg_bars_in_winning_trades': avg_bars_in_winning_trades,
        'avg_bars_in_losing_trades': avg_bars_in_losing_trades,
    }


def _equity_curve_metrics(daily_balance: list, starting_balance: float) -> dict:
    """Compute equity curve metrics from a daily_balance list."""
    null_result = {
        'max_equity_drawdown_close_to_close': None,
        'max_equity_runup_close_to_close': None,
        'max_equity_runup_pct': None,
        'avg_equity_drawdown': None,
        'avg_equity_drawdown_duration_days': None,
        'avg_equity_runup': None,
        'avg_equity_runup_duration_days': None,
        'return_of_max_equity_drawdown': None,
    }

    if not daily_balance or len(daily_balance) < 2:
        return null_result

    balances = [float(b) for b in daily_balance]
    n = len(balances)

    # Max drawdown close-to-close (peak-to-trough)
    peak = balances[0]
    max_dd_dollar = 0.0
    drawdown_phases = []
    dd_peak_idx = 0
    in_drawdown = False

    for i in range(n):
        if balances[i] >= peak:
            if in_drawdown:
                drawdown_phases.append((dd_peak_idx, i - 1))
                in_drawdown = False
            peak = balances[i]
            dd_peak_idx = i
        else:
            if not in_drawdown:
                in_drawdown = True
            dd = peak - balances[i]
            if dd > max_dd_dollar:
                max_dd_dollar = dd

    if in_drawdown:
        drawdown_phases.append((dd_peak_idx, n - 1))

    # Derive runup phases as the gaps between drawdown phases.
    # A runup phase runs from the end of one drawdown to the start of the next.
    # This is symmetric with the drawdown algorithm: drawdown phases go from
    # peak→trough, so runup phases go from trough→peak (the complement).
    runup_phases = []
    prev_end = 0
    for dd_start, dd_end in drawdown_phases:
        if dd_start > prev_end:
            runup_phases.append((prev_end, dd_start))
        prev_end = dd_end
    # Final runup after the last drawdown trough (if equity recovered)
    if prev_end < n - 1:
        runup_phases.append((prev_end, n - 1))

    max_runup_dollar = 0.0
    for start, end in runup_phases:
        ru = max(balances[start:end + 1]) - min(balances[start:end + 1])
        if ru > max_runup_dollar:
            max_runup_dollar = ru

    max_runup_pct = _safe(max_runup_dollar / starting_balance * 100) if starting_balance else None

    avg_dd = None
    avg_dd_duration = None
    if drawdown_phases:
        dd_amounts = []
        dd_durations = []
        for start, end in drawdown_phases:
            phase_peak = max(balances[start:end + 1])
            phase_trough = min(balances[start:end + 1])
            dd_amounts.append(phase_peak - phase_trough)
            dd_durations.append(end - start)
        avg_dd = _safe(float(np.mean(dd_amounts)))
        avg_dd_duration = _safe(float(np.mean(dd_durations)))

    avg_ru = None
    avg_ru_duration = None
    if runup_phases:
        ru_amounts = []
        ru_durations = []
        for start, end in runup_phases:
            phase_trough = min(balances[start:end + 1])
            phase_peak = max(balances[start:end + 1])
            ru_amounts.append(phase_peak - phase_trough)
            ru_durations.append(end - start)
        avg_ru = _safe(float(np.mean(ru_amounts)))
        avg_ru_duration = _safe(float(np.mean(ru_durations)))

    return {
        'max_equity_drawdown_close_to_close': _safe(max_dd_dollar) if max_dd_dollar > 0 else None,
        'max_equity_runup_close_to_close': _safe(max_runup_dollar) if max_runup_dollar > 0 else None,
        'max_equity_runup_pct': max_runup_pct,
        'avg_equity_drawdown': avg_dd,
        'avg_equity_drawdown_duration_days': avg_dd_duration,
        'avg_equity_runup': avg_ru,
        'avg_equity_runup_duration_days': avg_ru_duration,
        'return_of_max_equity_drawdown': None,  # filled in compute()
    }


def compute(
    trades_list: list,
    daily_balance: list,
    starting_balance: float,
    existing_metrics: dict = None,
    timeframe_seconds: int = None,
    first_price: float = None,
    last_price: float = None,
) -> dict:
    """
    Compute a TradingView-compatible strategy report with All/Long/Short breakdowns.

    Args:
        trades_list: list of ClosedTrade.to_json dicts
        daily_balance: equity curve as a list of balance values
        starting_balance: initial account balance
        existing_metrics: dict from metrics.trades() — used for Sharpe, Sortino, CAGR, max_drawdown
        timeframe_seconds: primary timeframe in seconds — for avg_bars calculations
        first_price: close price of the first candle — for buy & hold benchmark
        last_price: close price of the last candle — for buy & hold benchmark
    """
    longs = [t for t in trades_list if t['type'] == 'long']
    shorts = [t for t in trades_list if t['type'] == 'short']

    all_m = _trade_metrics(trades_list, timeframe_seconds)
    long_m = _trade_metrics(longs, timeframe_seconds)
    short_m = _trade_metrics(shorts, timeframe_seconds)

    def tri(key):
        return {'all': all_m[key], 'long': long_m[key], 'short': short_m[key]}

    initial_capital = starting_balance
    open_pnl = existing_metrics.get('open_pl') if existing_metrics else None
    sharpe = existing_metrics.get('sharpe_ratio') if existing_metrics else None
    sortino = existing_metrics.get('sortino_ratio') if existing_metrics else None
    annual_return = existing_metrics.get('annual_return') if existing_metrics else None
    max_drawdown_pct = existing_metrics.get('max_drawdown') if existing_metrics else None
    total_open_trades = existing_metrics.get('total_open_trades', 0) if existing_metrics else 0

    # Buy & hold benchmark
    bh_pct = None
    bh_return = None
    outperformance = None
    if first_price and last_price and starting_balance:
        bh_pct = (last_price - first_price) / first_price * 100
        bh_return = starting_balance * bh_pct / 100
        net_pnl_all = all_m['net_pnl']
        if net_pnl_all is not None:
            outperformance = net_pnl_all - bh_return

    net_pnl_all = all_m['net_pnl']

    # Capital efficiency
    return_on_initial_capital = None
    if net_pnl_all is not None and starting_balance:
        return_on_initial_capital = _safe(net_pnl_all / starting_balance * 100)

    largest_loss_all = all_m['largest_losing_trade']
    net_profit_as_pct_of_largest_loss = None
    if net_pnl_all is not None and largest_loss_all is not None and largest_loss_all != 0:
        net_profit_as_pct_of_largest_loss = _safe(net_pnl_all / abs(largest_loss_all) * 100)

    # Equity curve metrics
    eq_m = _equity_curve_metrics(daily_balance, starting_balance)
    max_dd_dollar = eq_m['max_equity_drawdown_close_to_close']
    if max_dd_dollar and max_dd_dollar != 0 and net_pnl_all is not None:
        eq_m['return_of_max_equity_drawdown'] = _safe(net_pnl_all / max_dd_dollar)

    return {
        'overview': {
            'net_pnl': tri('net_pnl'),
            'max_equity_drawdown_pct': {'all': _safe(max_drawdown_pct)},
            'total_trades': tri('total_trades'),
            'percent_profitable': tri('percent_profitable'),
            'profit_factor': tri('profit_factor'),
        },
        'returns': {
            'initial_capital': initial_capital,
            'open_pnl': _safe(open_pnl),
            'net_pnl': tri('net_pnl'),
            'gross_profit': tri('gross_profit'),
            'gross_loss': tri('gross_loss'),
            'profit_factor': tri('profit_factor'),
            'commission_paid': tri('commission_paid'),
            'expected_payoff': tri('expected_payoff'),
        },
        'benchmark': {
            'buy_and_hold_return': {'all': _safe(bh_return), 'long': None, 'short': None},
            'buy_and_hold_pct': {'all': _safe(bh_pct), 'long': None, 'short': None},
            'strategy_outperformance': {'all': _safe(outperformance), 'long': None, 'short': None},
        },
        'risk_adjusted': {
            'sharpe_ratio': {'all': _safe(sharpe), 'long': None, 'short': None},
            'sortino_ratio': {'all': _safe(sortino), 'long': None, 'short': None},
        },
        'trade_analysis': {
            'total_trades': tri('total_trades'),
            'total_open_trades': total_open_trades,
            'winning_trades': tri('winning_trades'),
            'losing_trades': tri('losing_trades'),
            'percent_profitable': tri('percent_profitable'),
            'avg_pnl': tri('avg_pnl'),
            'avg_winning_trade': tri('avg_winning_trade'),
            'avg_losing_trade': tri('avg_losing_trade'),
            'ratio_avg_win_avg_loss': tri('ratio_avg_win_avg_loss'),
            'largest_winning_trade': tri('largest_winning_trade'),
            'largest_winning_trade_pct': tri('largest_winning_trade_pct'),
            'largest_winner_as_pct_of_gross_profit': tri('largest_winner_as_pct_of_gross_profit'),
            'largest_losing_trade': tri('largest_losing_trade'),
            'largest_losing_trade_pct': tri('largest_losing_trade_pct'),
            'largest_loser_as_pct_of_gross_loss': tri('largest_loser_as_pct_of_gross_loss'),
            'avg_bars_in_trades': tri('avg_bars_in_trades'),
            'avg_bars_in_winning_trades': tri('avg_bars_in_winning_trades'),
            'avg_bars_in_losing_trades': tri('avg_bars_in_losing_trades'),
        },
        'capital_efficiency': {
            'annualized_return_cagr_pct': _safe(annual_return),
            'return_on_initial_capital_pct': return_on_initial_capital,
            'net_profit_as_pct_of_largest_loss': net_profit_as_pct_of_largest_loss,
            'account_size_required': None,
            'return_on_account_size_required': None,
            'avg_margin_used': None,
            'max_margin_used': None,
            'margin_efficiency': None,
            'margin_calls': None,
        },
        'runups_drawdowns': {
            'avg_equity_runup_duration_days': eq_m['avg_equity_runup_duration_days'],
            'avg_equity_runup': eq_m['avg_equity_runup'],
            'max_equity_runup_close_to_close': eq_m['max_equity_runup_close_to_close'],
            'max_equity_runup_intrabar': None,
            'max_equity_runup_pct_intrabar': None,
            'avg_equity_drawdown_duration_days': eq_m['avg_equity_drawdown_duration_days'],
            'avg_equity_drawdown': eq_m['avg_equity_drawdown'],
            'max_equity_drawdown_close_to_close': eq_m['max_equity_drawdown_close_to_close'],
            'max_equity_drawdown_intrabar': None,
            'max_equity_drawdown_pct_intrabar': _safe(max_drawdown_pct),
            'return_of_max_equity_drawdown': eq_m['return_of_max_equity_drawdown'],
        },
    }
