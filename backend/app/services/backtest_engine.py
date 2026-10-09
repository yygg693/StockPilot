"""Professional backtesting engine with trading costs, slippage, and risk metrics."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# A-share trading cost parameters (configurable)
DEFAULT_COMMISSION_RATE = 0.00025    # Broker commission: 0.025% (min 5 yuan)
DEFAULT_STAMP_DUTY_RATE = 0.001      # Stamp duty: 0.1% (sell only)
DEFAULT_TRANSFER_FEE_RATE = 0.00002  # Transfer fee: 0.002%
DEFAULT_SLIPPAGE = 0.001             # Slippage: 0.1%
MIN_COMMISSION = 5.0                 # Minimum commission per trade: 5 yuan


@dataclass
class TradeCost:
    """Trading cost configuration."""
    commission_rate: float = DEFAULT_COMMISSION_RATE
    stamp_duty_rate: float = DEFAULT_STAMP_DUTY_RATE
    transfer_fee_rate: float = DEFAULT_TRANSFER_FEE_RATE
    slippage: float = DEFAULT_SLIPPAGE
    min_commission: float = MIN_COMMISSION


@dataclass
class TradeRecord:
    """Single trade record."""
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    qty: int
    gross_pnl: float = 0.0
    total_cost: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0


@dataclass
class BacktestResult:
    """Complete backtest result with professional metrics."""
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def calc_buy_cost(price: float, qty: int, config: TradeCost) -> tuple[float, float]:
    """Calculate total cost for a buy order.

    Returns (actual_fill_price, total_cost) where total_cost includes commission + transfer fee.
    """
    fill_price = price * (1 + config.slippage)
    amount = fill_price * qty
    commission = max(amount * config.commission_rate, config.min_commission)
    transfer = amount * config.transfer_fee_rate
    total_cost = amount + commission + transfer
    return fill_price, total_cost


def calc_sell_proceeds(price: float, qty: int, config: TradeCost) -> tuple[float, float]:
    """Calculate net proceeds for a sell order.

    Returns (actual_fill_price, net_proceeds) where net_proceeds deducts commission + stamp duty + transfer.
    """
    fill_price = price * (1 - config.slippage)
    amount = fill_price * qty
    commission = max(amount * config.commission_rate, config.min_commission)
    stamp_duty = amount * config.stamp_duty_rate
    transfer = amount * config.transfer_fee_rate
    net_proceeds = amount - commission - stamp_duty - transfer
    return fill_price, net_proceeds


def calc_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    initial_capital: float,
    benchmark_return: float = 0.0,
) -> dict:
    """Calculate professional performance metrics.

    Metrics:
    - Total return, annualized return
    - Sharpe ratio (assuming risk-free rate = 2%)
    - Max drawdown, Calmar ratio
    - Win rate, profit factor
    - Average win/loss, max single win/loss
    - Total trades, average holding days
    """
    if not equity_curve or not trades:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "calmar_ratio": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_single_win": 0.0,
            "max_single_loss": 0.0,
            "avg_hold_days": 0.0,
            "benchmark_return": round(benchmark_return, 2),
            "excess_return": 0.0,
        }

    # --- Returns ---
    final_equity = equity_curve[-1]
    total_return = (final_equity - initial_capital) / initial_capital * 100

    # Annualized return (assume 250 trading days per year)
    n_days = len(equity_curve)
    if n_days > 1:
        annualized = ((final_equity / initial_capital) ** (250 / n_days) - 1) * 100
    else:
        annualized = 0.0

    # --- Sharpe Ratio ---
    # Calculate daily returns from equity curve
    daily_returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i - 1] > 0:
            daily_returns.append(equity_curve[i] / equity_curve[i - 1] - 1)

    if len(daily_returns) > 1:
        mean_return = sum(daily_returns) / len(daily_returns)
        std_return = (sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
        # Risk-free rate: 2% annual -> daily
        rf_daily = 0.02 / 250
        if std_return > 0:
            sharpe = (mean_return - rf_daily) / std_return * math.sqrt(250)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # --- Max Drawdown ---
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # Calmar ratio
    calmar = annualized / max_dd if max_dd > 0 else 0.0

    # --- Trade Statistics ---
    total_trades = len(trades)
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    win_rate = len(wins) / total_trades * 100 if total_trades else 0.0

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

    avg_win = gross_profit / len(wins) if wins else 0.0
    avg_loss = -gross_loss / len(losses) if losses else 0.0
    max_single_win = max((t.pnl_pct for t in trades), default=0.0)
    max_single_loss = min((t.pnl_pct for t in trades), default=0.0)
    avg_hold_days = sum(t.hold_days for t in trades) / total_trades if total_trades else 0.0

    excess = total_return - benchmark_return

    return {
        "total_return": round(total_return, 2),
        "annualized_return": round(annualized, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 99.99,
        "total_trades": total_trades,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_single_win": round(max_single_win, 2),
        "max_single_loss": round(max_single_loss, 2),
        "avg_hold_days": round(avg_hold_days, 1),
        "benchmark_return": round(benchmark_return, 2),
        "excess_return": round(excess, 2),
        "final_equity": round(final_equity, 2),
        "total_cost": round(sum(t.total_cost for t in trades), 2),
    }


def run_backtest(
    klines: list[dict],
    strategy: str = "ma_cross",
    initial_capital: float = 1_000_000,
    cost_config: TradeCost | None = None,
    position_pct: float = 0.95,
) -> BacktestResult:
    """Run a full backtest with trading costs and professional metrics.

    Args:
        klines: List of {date, open, close, high, low, volume}
        strategy: ma_cross / bollinger / momentum
        initial_capital: Starting capital
        cost_config: Trading cost configuration
        position_pct: Max position size as fraction of equity

    Returns:
        BacktestResult with trades, equity curve, and summary metrics.
    """
    if cost_config is None:
        cost_config = TradeCost()

    if len(klines) < 30:
        return BacktestResult(summary={"error": "Insufficient data for backtest"})

    closes = [k["close"] for k in klines]
    dates = [k["date"] for k in klines]
    n = len(closes)

    # Generate buy/sell signals based on strategy
    signals = _generate_signals(closes, strategy)

    # Simulate trades with costs
    trades: list[TradeRecord] = []
    equity_curve: list[float] = []
    cash = initial_capital
    position = False
    entry_price = 0.0
    entry_date = ""
    entry_day = 0
    entry_qty = 0
    entry_cost = 0.0

    for i in range(n):
        # Check for exit signal first (if in position)
        if position and signals[i] == -1:
            fill_price, proceeds = calc_sell_proceeds(closes[i], entry_qty, cost_config)
            gross_pnl = (fill_price - entry_price) * entry_qty
            net_pnl = proceeds - entry_cost
            pnl_pct = net_pnl / entry_cost * 100
            hold_days = i - entry_day

            trades.append(TradeRecord(
                entry_date=entry_date,
                exit_date=dates[i],
                entry_price=round(entry_price, 2),
                exit_price=round(fill_price, 2),
                qty=entry_qty,
                gross_pnl=round(gross_pnl, 2),
                total_cost=round(entry_cost + (fill_price * entry_qty - proceeds), 2),
                net_pnl=round(net_pnl, 2),
                pnl_pct=round(pnl_pct, 2),
                hold_days=hold_days,
            ))

            cash += proceeds
            position = False

        # Check for entry signal (if not in position)
        if not position and signals[i] == 1:
            available = cash * position_pct
            # Calculate qty (round to 100 shares)
            raw_qty = available / (closes[i] * (1 + cost_config.slippage))
            qty = int(raw_qty / 100) * 100
            if qty < 100:
                equity_curve.append(cash)
                continue

            fill_price, total_cost = calc_buy_cost(closes[i], qty, cost_config)
            if total_cost > cash:
                equity_curve.append(cash)
                continue

            cash -= total_cost
            position = True
            entry_price = fill_price
            entry_date = dates[i]
            entry_day = i
            entry_qty = qty
            entry_cost = total_cost

        # Track equity curve
        if position:
            equity = cash + closes[i] * entry_qty
        else:
            equity = cash
        equity_curve.append(equity)

    # Close any open position at the end
    if position:
        fill_price, proceeds = calc_sell_proceeds(closes[-1], entry_qty, cost_config)
        net_pnl = proceeds - entry_cost
        pnl_pct = net_pnl / entry_cost * 100
        hold_days = n - 1 - entry_day
        trades.append(TradeRecord(
            entry_date=entry_date,
            exit_date=dates[-1],
            entry_price=round(entry_price, 2),
            exit_price=round(fill_price, 2),
            qty=entry_qty,
            gross_pnl=round((fill_price - entry_price) * entry_qty, 2),
            total_cost=round(entry_cost + (fill_price * entry_qty - proceeds), 2),
            net_pnl=round(net_pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            hold_days=hold_days,
        ))
        cash += proceeds
        equity_curve[-1] = cash

    # Buy & hold benchmark
    bh_qty = int(initial_capital / closes[0] / 100) * 100
    bh_cost = bh_qty * closes[0]
    bh_final = bh_qty * closes[-1]
    benchmark_return = (bh_final - bh_cost) / bh_cost * 100 if bh_cost > 0 else 0.0

    # Calculate metrics
    metrics = calc_metrics(trades, equity_curve, initial_capital, benchmark_return)

    # Build trade list for output (last 30 trades)
    trade_list = [
        {
            "entry_date": t.entry_date,
            "exit_date": t.exit_date,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "qty": t.qty,
            "net_pnl": t.net_pnl,
            "pnl_pct": t.pnl_pct,
            "hold_days": t.hold_days,
            "cost": t.total_cost,
        }
        for t in trades[-30:]
    ]

    # Build equity curve for output (sample to max 120 points)
    eq_out = []
    step = max(1, len(equity_curve) // 120)
    for i in range(0, len(equity_curve), step):
        eq_out.append({"date": dates[i], "equity": round(equity_curve[i], 2)})

    return BacktestResult(
        trades=trade_list,
        equity_curve=eq_out,
        summary=metrics,
    )


def _generate_signals(closes: list[float], strategy: str) -> list[int]:
    """Generate trading signals: 1=buy, -1=sell, 0=hold."""
    n = len(closes)
    signals = [0] * n

    if strategy == "ma_cross":
        for i in range(20, n):
            ma5 = sum(closes[i-4:i+1]) / 5
            ma20 = sum(closes[i-19:i+1]) / 20
            prev_ma5 = sum(closes[i-5:i]) / 5
            prev_ma20 = sum(closes[i-20:i]) / 20
            if prev_ma5 <= prev_ma20 and ma5 > ma20:
                signals[i] = 1
            elif prev_ma5 >= prev_ma20 and ma5 < ma20:
                signals[i] = -1

    elif strategy == "bollinger":
        w = 20
        for i in range(w, n):
            window = closes[i-w+1:i+1]
            ma = sum(window) / w
            std = (sum((x - ma) ** 2 for x in window) / w) ** 0.5
            lower = ma - 2 * std
            if closes[i] < lower:
                signals[i] = 1
            elif closes[i] > ma:
                signals[i] = -1

    elif strategy == "momentum":
        for i in range(20, n):
            momentum = (closes[i] - closes[i-20]) / closes[i-20] * 100
            if momentum > 10:
                signals[i] = 1
            elif momentum < 0:
                signals[i] = -1

    return signals
