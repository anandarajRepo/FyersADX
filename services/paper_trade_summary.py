"""
Paper Trade Daily Summary.

Reads the daily paper-trade log written by PaperTradeLogger
(logs/paper_trades_YYYYMMDD.json) and produces an end-of-day summary:
how many trades happened, each trade's details, and the profit/loss
breakdown for the day.

Can be used in two ways:
  1. Programmatically at end of a trading session (auto-printed when the
     strategy squares off / stops in paper mode).
  2. On-demand after market hours via:  python main.py summary
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

logger = logging.getLogger(__name__)


def get_log_path(date_str: Optional[str] = None) -> Path:
    """Return the paper-trade log path for the given date (default: today)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    return Path(f"logs/paper_trades_{date_str}.json")


def load_records(date_str: Optional[str] = None) -> List[dict]:
    """Load the raw event records from the daily paper-trade log."""
    log_path = get_log_path(date_str)
    if not log_path.exists():
        return []
    try:
        with open(log_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read paper trade log {log_path}: {e}")
        return []


def build_summary(records: List[dict]) -> Dict:
    """
    Build an aggregate summary from raw paper-trade event records.

    Returns a dict with order/trade lists and P&L statistics.
    """
    orders = [r for r in records if r.get("type") == "order"]
    trades = [r for r in records if r.get("type") == "trade"]

    total_pnl = sum(t.get("pnl", 0.0) for t in trades)
    wins = [t for t in trades if t.get("pnl", 0.0) > 0]
    losses = [t for t in trades if t.get("pnl", 0.0) <= 0]

    gross_profit = sum(t.get("pnl", 0.0) for t in wins)
    gross_loss = sum(t.get("pnl", 0.0) for t in losses)

    win_rate = (len(wins) / len(trades)) if trades else 0.0
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss != 0 else 0.0

    best_trade = max(trades, key=lambda t: t.get("pnl", 0.0)) if trades else None
    worst_trade = min(trades, key=lambda t: t.get("pnl", 0.0)) if trades else None

    # Exit reason breakdown
    exit_breakdown: Dict[str, int] = {}
    for t in trades:
        reason = t.get("exit_reason", "UNKNOWN")
        exit_breakdown[reason] = exit_breakdown.get(reason, 0) + 1

    return {
        "orders": orders,
        "trades": trades,
        "orders_count": len(orders),
        "closed_trades_count": len(trades),
        "open_positions_count": max(len(orders) - len(trades), 0),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "exit_breakdown": exit_breakdown,
    }


def _fmt_time(iso_str: Optional[str]) -> str:
    """Format an ISO timestamp to HH:MM:SS, gracefully handling None."""
    if not iso_str:
        return "-"
    try:
        return datetime.fromisoformat(iso_str).strftime("%H:%M:%S")
    except Exception:
        return str(iso_str)


def print_summary(date_str: Optional[str] = None,
                  console: Optional[Console] = None) -> Dict:
    """
    Print a formatted end-of-day paper-trading summary and return the
    summary dict. Safe to call after market hours.
    """
    console = console or Console()
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    display_date = datetime.strptime(date_str, "%Y%m%d").strftime("%d %b %Y")

    records = load_records(date_str)

    if not records:
        console.print(Panel.fit(
            f"No paper trades recorded for {display_date}.\n"
            f"Expected log file: {get_log_path(date_str)}",
            title="📋 Paper Trading Summary",
            border_style="yellow",
        ))
        return build_summary([])

    summary = build_summary(records)

    console.print(Panel.fit(
        f"[bold]Paper Trading Summary — {display_date}[/bold]",
        border_style="cyan",
    ))

    # ── Per-trade details ──────────────────────────────────────────────
    if summary["trades"]:
        table = Table(title="Closed Trades", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Symbol")
        table.add_column("Dir")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Exit", justify="right")
        table.add_column("In", justify="center")
        table.add_column("Out", justify="center")
        table.add_column("Hold (m)", justify="right")
        table.add_column("Exit Reason")
        table.add_column("P&L ₹", justify="right")
        table.add_column("P&L %", justify="right")
        table.add_column("Result")

        for i, t in enumerate(summary["trades"], 1):
            pnl = t.get("pnl", 0.0)
            is_win = pnl > 0
            pnl_style = "green" if is_win else "red"
            result = "[green]WIN[/green]" if is_win else "[red]LOSS[/red]"
            hold = t.get("holding_minutes")
            hold_str = f"{hold:.0f}" if isinstance(hold, (int, float)) else "-"

            table.add_row(
                str(i),
                t.get("symbol", "-"),
                t.get("direction", "-"),
                str(t.get("quantity", "-")),
                f"{t.get('entry_price', 0):.2f}",
                f"{t.get('exit_price', 0):.2f}",
                _fmt_time(t.get("entry_time")),
                _fmt_time(t.get("exit_time")),
                hold_str,
                t.get("exit_reason", "-"),
                f"[{pnl_style}]{pnl:,.2f}[/{pnl_style}]",
                f"[{pnl_style}]{t.get('pnl_pct', 0):.2f}[/{pnl_style}]",
                result,
            )

        console.print(table)
    else:
        console.print("[yellow]No positions were closed today.[/yellow]")

    # ── Open positions not closed (orders without a matching trade) ─────
    if summary["open_positions_count"] > 0:
        console.print(
            f"[yellow]⚠ {summary['open_positions_count']} order(s) had no "
            f"recorded exit (still open or not squared off).[/yellow]"
        )

    # ── Aggregate statistics ───────────────────────────────────────────
    total_pnl = summary["total_pnl"]
    pnl_style = "green" if total_pnl >= 0 else "red"

    stats = Table(title="Day Statistics", box=box.SIMPLE, show_header=False)
    stats.add_column("Metric", style="cyan")
    stats.add_column("Value", justify="right")

    stats.add_row("Orders Placed", str(summary["orders_count"]))
    stats.add_row("Trades Closed", str(summary["closed_trades_count"]))
    stats.add_row("Winners", str(summary["wins"]))
    stats.add_row("Losers", str(summary["losses"]))
    stats.add_row("Win Rate", f"{summary['win_rate']:.1%}")
    stats.add_row("Gross Profit", f"₹{summary['gross_profit']:,.2f}")
    stats.add_row("Gross Loss", f"₹{summary['gross_loss']:,.2f}")
    stats.add_row("Profit Factor",
                  f"{summary['profit_factor']:.2f}" if summary['profit_factor'] else "N/A")
    if summary["best_trade"]:
        bt = summary["best_trade"]
        stats.add_row("Best Trade", f"{bt.get('symbol')} (₹{bt.get('pnl', 0):,.2f})")
    if summary["worst_trade"]:
        wt = summary["worst_trade"]
        stats.add_row("Worst Trade", f"{wt.get('symbol')} (₹{wt.get('pnl', 0):,.2f})")
    stats.add_row("[bold]Net P&L[/bold]",
                  f"[bold {pnl_style}]₹{total_pnl:,.2f}[/bold {pnl_style}]")

    console.print(stats)

    # ── Exit reason breakdown ──────────────────────────────────────────
    if summary["exit_breakdown"]:
        breakdown = Table(title="Exit Reason Breakdown", box=box.SIMPLE,
                          header_style="bold cyan")
        breakdown.add_column("Exit Reason")
        breakdown.add_column("Count", justify="right")
        for reason, count in summary["exit_breakdown"].items():
            breakdown.add_row(reason, str(count))
        console.print(breakdown)

    return summary


def log_summary(date_str: Optional[str] = None) -> Dict:
    """
    Emit a plain-text end-of-day summary to the logger (for cron/log files
    where rich formatting is not desired). Returns the summary dict.
    """
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    records = load_records(date_str)
    summary = build_summary(records)

    logger.info("=" * 70)
    logger.info(f"PAPER TRADING DAILY SUMMARY — {date_str}")
    logger.info("=" * 70)

    if not records:
        logger.info("No paper trades recorded today.")
        logger.info("=" * 70)
        return summary

    for i, t in enumerate(summary["trades"], 1):
        result = "WIN" if t.get("pnl", 0.0) > 0 else "LOSS"
        logger.info(
            f"  {i}. {t.get('symbol')} {t.get('direction')} x{t.get('quantity')} | "
            f"Entry ₹{t.get('entry_price', 0):.2f} → Exit ₹{t.get('exit_price', 0):.2f} | "
            f"{t.get('exit_reason')} | P&L ₹{t.get('pnl', 0):,.2f} "
            f"({t.get('pnl_pct', 0):.2f}%) [{result}]"
        )

    logger.info("-" * 70)
    logger.info(f"  Orders Placed : {summary['orders_count']}")
    logger.info(f"  Trades Closed : {summary['closed_trades_count']}")
    logger.info(f"  Winners/Losers: {summary['wins']}/{summary['losses']} "
                f"(Win Rate {summary['win_rate']:.1%})")
    logger.info(f"  Net P&L       : ₹{summary['total_pnl']:,.2f}")
    logger.info("=" * 70)

    return summary
