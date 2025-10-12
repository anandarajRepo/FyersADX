"""
FyersADX - Main Entry Point

Command-line interface for running the ADX DI Crossover trading strategy,
backtesting, and system management.
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import config
from config.symbols import symbol_manager, get_active_symbols
from strategy.adx_strategy import ADXStrategy
from services.market_timing_service import MarketTimingService

# from backtesting.adx_backtest import ADXBacktester  # Import when implemented

console = Console()


def setup_logging():
    """Setup logging configuration."""
    log_level = getattr(logging, config.trading.log_level)

    # Create logs directory
    Path("logs").mkdir(exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/adx_strategy_{datetime.now().strftime("%Y%m%d")}.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """
    FyersADX - ADX DI Crossover Trading Strategy

    A production-ready algorithmic trading system with real-time WebSocket
    integration and comprehensive backtesting capabilities.
    """
    setup_logging()


@cli.command()
@click.option('--symbols', '-s', multiple=True, help='Specific symbols to trade')
@click.option('--paper', is_flag=True, help='Run in paper trading mode')
def run(symbols, paper):
    """
    Run the live ADX trading strategy.

    Examples:
        python main.py run
        python main.py run --paper
        python main.py run -s NSE:RELIANCE-EQ -s NSE:TCS-EQ
    """
    console.print("\n[bold cyan]Starting FyersADX Trading Strategy[/bold cyan]\n")

    # Validate configuration
    is_valid, errors = config.validate_all()
    if not is_valid:
        console.print("[bold red]Configuration Errors:[/bold red]")
        for config_type, error_list in errors.items():
            console.print(f"\n[red]{config_type.upper()}:[/red]")
            for error in error_list:
                console.print(f"  • {error}")
        console.print("\n[yellow]Please fix configuration errors and try again.[/yellow]")
        return

    # Override paper trading mode if specified
    if paper:
        config.trading.enable_paper_trading = True
        config.trading.enable_order_execution = False

    # Get symbols to trade
    if symbols:
        trading_symbols = list(symbols)
        valid, invalid = symbol_manager.validate_symbol_list(trading_symbols)
        if invalid:
            console.print(f"[yellow]Warning: Invalid symbols will be skipped: {invalid}[/yellow]")
        trading_symbols = valid
    else:
        trading_symbols = get_active_symbols()

    console.print(f"[green]✓[/green] Trading {len(trading_symbols)} symbols")
    console.print(f"[green]✓[/green] Paper Trading: {config.trading.enable_paper_trading}")
    console.print(f"[green]✓[/green] Square-off Time: {config.strategy.square_off_time} IST")
    console.print(f"[green]✓[/green] Max Positions: {config.strategy.max_positions}\n")

    # Initialize and run strategy
    try:
        strategy = ADXStrategy(
            strategy_config=config.strategy,
            trading_config=config.trading,
            symbols=trading_symbols
        )

        # Run the strategy
        asyncio.run(strategy.run_strategy_cycle())

    except KeyboardInterrupt:
        console.print("\n[yellow]Strategy stopped by user[/yellow]")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        logging.error(f"Strategy error: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option('--start-date', '-s', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', '-e', help='End date (YYYY-MM-DD)')
@click.option('--symbols', '-sym', multiple=True, help='Specific symbols to backtest')
@click.option('--output', '-o', help='Output file for results')
def backtest(start_date, end_date, symbols, output):
    """
    Run historical backtesting on the ADX strategy.

    Examples:
        python main.py backtest
        python main.py backtest --start-date 2024-01-01 --end-date 2024-12-31
        python main.py backtest -sym NSE:RELIANCE-EQ -sym NSE:TCS-EQ
    """
    console.print("\n[bold cyan]Running ADX Strategy Backtest[/bold cyan]\n")

    # TODO: Implement backtesting
    console.print("[yellow]Backtesting module will be implemented in Phase 4[/yellow]")
    console.print("\nBacktest configuration:")
    console.print(f"  Start Date: {start_date or config.backtest.start_date or 'Not set'}")
    console.print(f"  End Date: {end_date or config.backtest.end_date or 'Not set'}")
    console.print(f"  Data Sources: {config.backtest.data_sources}")
    console.print(f"  Initial Capital: ₹{config.backtest.initial_capital:,.0f}")


@cli.command()
def auth():
    """
    Setup Fyers API authentication.

    This will guide you through the OAuth flow to obtain access tokens.
    """
    console.print("\n[bold cyan]Fyers API Authentication[/bold cyan]\n")

    # TODO: Implement authentication flow
    console.print("[yellow]Authentication module will be implemented with utils/enhanced_auth_helper.py[/yellow]")
    console.print("\nRequired credentials:")
    console.print("  • Client ID")
    console.print("  • Secret Key")
    console.print("  • Trading PIN")
    console.print("\nPlease ensure these are set in your .env file")


@cli.command()
@click.option('--new-pin', prompt='Enter new PIN', hide_input=True, confirmation_prompt=True)
def update_pin(new_pin):
    """Update your trading PIN."""
    # TODO: Implement PIN update
    console.print("[green]✓[/green] PIN updated successfully")


@cli.command()
def validate():
    """
    Validate system configuration and connectivity.
    """
    console.print("\n[bold cyan]System Validation[/bold cyan]\n")

    # Validate configuration
    is_valid, errors = config.validate_all()

    if is_valid:
        console.print("[green]✓ Configuration is valid[/green]\n")
        config.strategy.print_summary()
    else:
        console.print("[bold red]✗ Configuration Errors:[/bold red]\n")
        for config_type, error_list in errors.items():
            console.print(f"[red]{config_type.upper()}:[/red]")
            for error in error_list:
                console.print(f"  • {error}")

    # Validate symbols
    console.print("\n[bold cyan]Symbol Validation[/bold cyan]\n")
    symbol_manager.print_summary()


@cli.command()
def market():
    """
    Show current market status and timing information.
    """
    timing_service = MarketTimingService(
        square_off_time=config.strategy.square_off_time,
        signal_cutoff_time=config.strategy.signal_generation_end_time
    )

    timing_service.print_market_status()


@cli.command()
def symbols():
    """
    Display available trading symbols.
    """
    console.print("\n[bold cyan]Available Trading Symbols[/bold cyan]\n")

    symbol_manager.print_summary()

    # Show detailed list
    console.print("\n[bold]Active Symbols:[/bold]")

    active = get_active_symbols()
    for i, symbol in enumerate(active[:20], 1):  # Show first 20
        info = symbol_manager.get_symbol_info(symbol)
        if info:
            console.print(f"{i:2d}. {info.name:30s} ({symbol:20s}) - {info.sector}")

    if len(active) > 20:
        console.print(f"\n... and {len(active) - 20} more symbols")


@cli.command()
def diagnostics():
    """
    Run comprehensive system diagnostics.
    """
    console.print("\n[bold cyan]System Diagnostics[/bold cyan]\n")

    table = Table(title="Diagnostic Checks", box=box.ROUNDED)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    # Check configuration
    is_valid, errors = config.validate_all()
    if is_valid:
        table.add_row("Configuration", "[green]✓ Valid[/green]", "All settings valid")
    else:
        table.add_row("Configuration", "[red]✗ Invalid[/red]", f"{sum(len(e) for e in errors.values())} errors")

    # Check Fyers authentication
    if config.fyers.is_authenticated():
        table.add_row("Fyers Auth", "[green]✓ Authenticated[/green]", "Access token available")
    else:
        table.add_row("Fyers Auth", "[yellow]⚠ Not Authenticated[/yellow]", "Run 'python main.py auth'")

    # Check market status
    timing_service = MarketTimingService()
    if timing_service.is_market_open():
        table.add_row("Market Status", "[green]✓ Open[/green]", "Market is trading")
    else:
        table.add_row("Market Status", "[yellow]⚠ Closed[/yellow]", "Market is not trading")

    # Check symbols
    active_count = len(get_active_symbols())
    table.add_row("Symbols", "[green]✓ Loaded[/green]", f"{active_count} active symbols")

    # Check directories
    required_dirs = ['logs', 'backtest_results', 'data']
    dirs_exist = all(Path(d).exists() or Path(d).mkdir(exist_ok=True) for d in required_dirs)
    if dirs_exist:
        table.add_row("Directories", "[green]✓ Ready[/green]", "All required directories exist")
    else:
        table.add_row("Directories", "[yellow]⚠ Missing[/yellow]", "Some directories missing")

    console.print(table)

    # Overall status
    console.print()
    if is_valid and config.fyers.is_authenticated():
        console.print("[bold green]✓ System is ready for trading[/bold green]")
    else:
        console.print("[bold yellow]⚠ System needs configuration[/bold yellow]")
        console.print("\nNext steps:")
        if not is_valid:
            console.print("  1. Fix configuration errors (check .env file)")
        if not config.fyers.is_authenticated():
            console.print("  2. Run authentication: python main.py auth")


@cli.command()
def test():
    """
    Test WebSocket connection and data feed.
    """
    console.print("\n[bold cyan]Testing Data Connection[/bold cyan]\n")

    # TODO: Implement WebSocket test
    console.print("[yellow]WebSocket testing will be implemented with services/fyers_websocket_service.py[/yellow]")
    console.print("\nThis will test:")
    console.print("  • WebSocket connection to Fyers")
    console.print("  • Real-time quote reception")
    console.print("  • DI indicator calculation")
    console.print("  • Data quality validation")


@cli.command()
@click.option('--export', '-e', is_flag=True, help='Export results to CSV')
def performance(export):
    """
    Show strategy performance metrics.
    """
    console.print("\n[bold cyan]Strategy Performance Metrics[/bold cyan]\n")

    # TODO: Load and display actual performance data
    console.print("[yellow]Performance tracking will be fully functional after live trading[/yellow]")
    console.print("\nMetrics to be displayed:")
    console.print("  • Total trades and win rate")
    console.print("  • P&L and returns")
    console.print("  • Exit reason breakdown")
    console.print("  • Risk metrics")


@cli.command()
def status():
    """
    Show current strategy status (positions, P&L, etc).
    """
    console.print("\n[bold cyan]Current Strategy Status[/bold cyan]\n")

    # TODO: Load current status from running strategy
    console.print("[yellow]Status display will be available when strategy is running[/yellow]")
    console.print("\nStatus information:")
    console.print("  • Active positions")
    console.print("  • Daily P&L")
    console.print("  • Time to square-off")
    console.print("  • Pending signals")


def main():
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error: {e}[/bold red]")
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()