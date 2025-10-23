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
from config.symbols import get_active_symbols, get_symbol_name, print_summary, validate_symbols, LARGE_CAP_SYMBOLS, MID_CAP_SYMBOLS, SMALL_CAP_SYMBOLS, OPTIONS_SYMBOLS
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


def _update_env_credentials(client_id: str, secret_key: str, redirect_uri: str) -> bool:
    """
    Update .env file with Fyers credentials.

    Args:
        client_id: Fyers Client ID
        secret_key: Fyers Secret Key
        redirect_uri: OAuth redirect URI

    Returns:
        bool: True if updated successfully
    """
    env_file = Path('.env')

    try:
        # Read existing .env or create new
        if env_file.exists():
            with open(env_file, 'r') as f:
                lines = f.readlines()
        else:
            # Copy from template if exists
            template = Path('.env.template')
            if template.exists():
                with open(template, 'r') as f:
                    lines = f.readlines()
            else:
                lines = []

        # Update or add credentials
        updated = {
            'FYERS_CLIENT_ID': False,
            'FYERS_SECRET_KEY': False,
            'FYERS_REDIRECT_URI': False
        }

        new_lines = []
        for line in lines:
            if line.startswith('FYERS_CLIENT_ID='):
                new_lines.append(f'FYERS_CLIENT_ID={client_id}\n')
                updated['FYERS_CLIENT_ID'] = True
            elif line.startswith('FYERS_SECRET_KEY='):
                new_lines.append(f'FYERS_SECRET_KEY={secret_key}\n')
                updated['FYERS_SECRET_KEY'] = True
            elif line.startswith('FYERS_REDIRECT_URI='):
                new_lines.append(f'FYERS_REDIRECT_URI={redirect_uri}\n')
                updated['FYERS_REDIRECT_URI'] = True
            else:
                new_lines.append(line)

        # Add missing entries
        if not updated['FYERS_CLIENT_ID']:
            new_lines.append(f'\nFYERS_CLIENT_ID={client_id}\n')
        if not updated['FYERS_SECRET_KEY']:
            new_lines.append(f'FYERS_SECRET_KEY={secret_key}\n')
        if not updated['FYERS_REDIRECT_URI']:
            new_lines.append(f'FYERS_REDIRECT_URI={redirect_uri}\n')

        # Write back
        with open(env_file, 'w') as f:
            f.writelines(new_lines)

        console.print(f"[green]✓[/green] Credentials saved to .env file")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Error saving credentials: {e}")
        return False


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
        valid, invalid = validate_symbols(trading_symbols)
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
@click.option('--client-id', help='Fyers Client ID')
@click.option('--secret-key', help='Fyers Secret Key')
@click.option('--redirect-uri', help='Redirect URI')
@click.option('--open-browser', is_flag=True, help='Automatically open browser (default: manual copy-paste)')
def auth(client_id, secret_key, redirect_uri, open_browser):
    """
    Setup Fyers API authentication.

    This will guide you through the OAuth flow to obtain access tokens.

    Example:
        python main.py auth
        python main.py auth --client-id YOUR_ID --secret-key YOUR_KEY
        python main.py auth --open-browser # Auto-open browser
    """
    from utils.enhanced_auth_helper import FyersAuthenticationHelper

    console.print("\n[bold cyan] Fyers API Authentication[/bold cyan]\n")

    # Check if credentials are in .env
    env_file = Path('.env')
    has_env = env_file.exists()

    # Get credentials from command line or .env or prompt
    if not client_id:
        if config.fyers.client_id:
            client_id = config.fyers.client_id
            console.print(f"[green]✓[/green] Using Client ID from .env: {client_id[:10]}...")
        else:
            console.print("\n[yellow]Fyers Client ID is required[/yellow]")
            console.print("Get it from: https://myapi.fyers.in/")
            console.print("Format: ABC123-100")
            client_id = input("\nEnter your Fyers Client ID: ").strip()

    if not secret_key:
        if config.fyers.secret_key:
            secret_key = config.fyers.secret_key
            console.print(f"[green]✓[/green] Using Secret Key from .env (hidden)")
        else:
            console.print("\n[yellow]Fyers Secret Key is required[/yellow]")
            import getpass
            secret_key = getpass.getpass("Enter your Fyers Secret Key: ").strip()

    if not client_id or not secret_key:
        console.print("\n[red]✗ Error: Client ID and Secret Key are required[/red]")
        return

    # Update config
    config.fyers.client_id = client_id
    config.fyers.secret_key = secret_key
    config.fyers.redirect_uri = redirect_uri

    # Save to .env if doesn't exist or update
    if not has_env or not config.fyers.client_id:
        _update_env_credentials(client_id, secret_key, redirect_uri)

    # Perform authentication
    console.print("\n[bold cyan]Starting OAuth Flow...[/bold cyan]\n")

    try:
        auth_helper = FyersAuthenticationHelper(config.fyers)

        # Check if already authenticated
        if auth_helper.is_token_valid():
            console.print("[green]✓ Already authenticated![/green]")
            auth_helper.print_token_info()

            refresh = input("\nDo you want to re-authenticate? (y/N): ").strip().lower()
            if refresh != 'y':
                return

        # Set browser opening preference
        auth_helper.auto_open_browser = open_browser

        # Authenticate
        success = auth_helper.authenticate()

        if success:
            console.print("\n[bold green]✓ Authentication Successful![/bold green]")
            auth_helper.print_token_info()
            console.print("\n[green]Tokens have been saved. You can now run the strategy.[/green]")
        else:
            console.print("\n[bold red]✗ Authentication Failed[/bold red]")
            console.print("Please check your credentials and try again.")

    except Exception as e:
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]")
        logging.error(f"Authentication error: {e}", exc_info=True)


@cli.command()
def setup():
    """
    Interactive setup wizard for first-time configuration.

    Guides you through:
    - Creating .env file from template
    - Setting up Fyers credentials
    - Configuring strategy parameters
    - Authenticating with Fyers API
    """
    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]FyersADX Setup Wizard[/bold cyan]\n\n"
        "This wizard will guide you through the initial setup.",
        border_style="cyan"
    ))

    # Step 1: Check/Create .env file
    console.print("\n[bold]Step 1: Configuration File[/bold]")
    env_file = Path('.env')
    template_file = Path('.env.template')

    if env_file.exists():
        console.print("[green]✓[/green] .env file exists")
        overwrite = input("Do you want to reconfigure? (y/N): ").strip().lower()
        if overwrite != 'y':
            console.print("[yellow]Skipping configuration setup[/yellow]")
        else:
            if template_file.exists():
                import shutil
                shutil.copy(template_file, env_file)
                console.print("[green]✓[/green] Reset .env from template")
    else:
        if template_file.exists():
            import shutil
            shutil.copy(template_file, env_file)
            console.print("[green]✓[/green] Created .env from template")
        else:
            console.print("[red]✗[/red] .env.template not found!")
            console.print("Please ensure .env.template exists in the project root.")
            return

    # Step 2: Fyers Credentials
    console.print("\n[bold]Step 2: Fyers API Credentials[/bold]")
    console.print("Get your credentials from: [cyan]https://myapi.fyers.in/[/cyan]\n")

    client_id = input("Enter your Fyers Client ID (format: ABC123-100): ").strip()

    import getpass
    secret_key = getpass.getpass("Enter your Fyers Secret Key: ").strip()

    redirect_uri = input("Enter Redirect URI [https://trade.fyers.in/api-login/redirect-to-app]: ").strip()
    if not redirect_uri:
        redirect_uri = "https://trade.fyers.in/api-login/redirect-to-app"

    if client_id and secret_key:
        _update_env_credentials(client_id, secret_key, redirect_uri)
    else:
        console.print("[red]✗[/red] Client ID and Secret Key are required")
        return

    # Step 3: Trading PIN
    console.print("\n[bold]Step 3: Trading PIN[/bold]")
    console.print("PIN is required for order placement (live trading only)\n")

    pin = getpass.getpass("Enter your Trading PIN (4-6 digits): ").strip()

    if pin and pin.isdigit() and 4 <= len(pin) <= 6:
        # Update PIN in .env
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()

            pin_updated = False
            new_lines = []
            for line in lines:
                if line.startswith('FYERS_PIN='):
                    new_lines.append(f'FYERS_PIN={pin}\n')
                    pin_updated = True
                else:
                    new_lines.append(line)

            if not pin_updated:
                new_lines.append(f'FYERS_PIN={pin}\n')

            with open(env_file, 'w') as f:
                f.writelines(new_lines)

            console.print("[green]✓[/green] PIN saved")
        except Exception as e:
            console.print(f"[red]✗[/red] Error saving PIN: {e}")
    else:
        console.print("[yellow]⚠[/yellow] Invalid PIN format. You can set it later with: python main.py update-pin")

    # Step 4: Strategy Parameters
    console.print("\n[bold]Step 4: Strategy Parameters[/bold]")
    console.print("Configure basic strategy settings (you can change these later in .env)\n")

    portfolio = input("Portfolio Value [100000]: ").strip()
    if portfolio and portfolio.isdigit():
        _update_env_setting('PORTFOLIO_VALUE', portfolio)

    risk = input("Risk Per Trade % [1.0]: ").strip()
    if risk:
        _update_env_setting('RISK_PER_TRADE', risk)

    max_pos = input("Max Positions [5]: ").strip()
    if max_pos and max_pos.isdigit():
        _update_env_setting('MAX_POSITIONS', max_pos)

    console.print("[green]✓[/green] Configuration saved")

    # Step 5: Authentication
    console.print("\n[bold]Step 5: Fyers Authentication[/bold]")
    console.print("Now we'll authenticate with Fyers to get access tokens.\n")

    proceed = input("Proceed with authentication? (Y/n): ").strip().lower()
    if proceed != 'n':
        # Reload config to pick up new values
        from importlib import reload
        from config import settings
        reload(settings)

        # Run auth command
        console.print("\n" + "="*60)
        from utils.enhanced_auth_helper import FyersAuthenticationHelper
        auth_helper = FyersAuthenticationHelper(settings.config.fyers)

        if auth_helper.authenticate():
            console.print("\n[bold green]✓ Setup Complete![/bold green]")
            console.print("\nYou can now:")
            console.print("  • Run diagnostics: [cyan]python main.py diagnostics[/cyan]")
            console.print("  • Check market: [cyan]python main.py market[/cyan]")
            console.print("  • Start paper trading: [cyan]python main.py run --paper[/cyan]")
        else:
            console.print("\n[yellow]⚠ Authentication failed[/yellow]")
            console.print("You can retry later with: [cyan]python main.py auth[/cyan]")
    else:
        console.print("\n[yellow]Authentication skipped.[/yellow]")
        console.print("Run [cyan]python main.py auth[/cyan] when ready.")

    console.print("\n" + "="*60)


def _update_env_setting(key: str, value: str) -> bool:
    """Update a single setting in .env file."""
    env_file = Path('.env')
    if not env_file.exists():
        return False

    try:
        with open(env_file, 'r') as f:
            lines = f.readlines()

        updated = False
        new_lines = []
        for line in lines:
            if line.startswith(f'{key}='):
                new_lines.append(f'{key}={value}\n')
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f'{key}={value}\n')

        with open(env_file, 'w') as f:
            f.writelines(new_lines)

        return True
    except Exception:
        return False


@cli.command()
@click.option('--new-pin', help='New trading PIN (4-6 digits)')
def update_pin(new_pin):
    """
    Update your trading PIN.

    Example:
        python main.py update-pin
        python main.py update-pin --new-pin 1234
    """
    from utils.enhanced_auth_helper import FyersAuthenticationHelper

    console.print("\n[bold cyan] Update Trading PIN[/bold cyan]\n")

    if not new_pin:
        console.print("[yellow]Trading PIN is used for order placement[/yellow]")
        console.print("PIN should be 4-6 digits\n")

        import getpass
        new_pin = getpass.getpass("Enter new PIN: ").strip()
        confirm_pin = getpass.getpass("Confirm new PIN: ").strip()

        if new_pin != confirm_pin:
            console.print("[red]✗ PINs do not match[/red]")
            return

    # Validate PIN
    if not new_pin.isdigit() or len(new_pin) < 4 or len(new_pin) > 6:
        console.print("[red]✗ Invalid PIN format. Must be 4-6 digits.[/red]")
        return

    try:
        auth_helper = FyersAuthenticationHelper(config.fyers)

        if auth_helper.update_pin(new_pin):
            console.print("[green]✓ PIN updated successfully[/green]")
            console.print("\n[dim]PIN has been saved to .env file[/dim]")
        else:
            console.print("[red]✗ Failed to update PIN[/red]")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]")


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
    print_summary()


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

    print_summary()

    # Show detailed list
    console.print("\n[bold]Active Symbols:[/bold]")

    active = get_active_symbols()
    for i, symbol in enumerate(active[:20], 1):
        name = get_symbol_name(symbol)
        console.print(f"  {i}. {name} ({symbol})")

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