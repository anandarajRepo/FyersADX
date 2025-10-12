"""
Configuration settings for FyersADX Trading Strategy.

This module contains all configuration classes for the ADX DI Crossover strategy,
including portfolio settings, indicator parameters, risk management, and API credentials.
"""

import os
from dataclasses import dataclass, field
from datetime import time
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class ADXStrategyConfig:
    """
    Core strategy configuration for ADX DI Crossover trading.

    Attributes:
        portfolio_value: Total portfolio value for position sizing
        risk_per_trade_pct: Risk percentage per trade (1.0 = 1%)
        max_positions: Maximum concurrent positions allowed
        di_period: Period for DI indicator calculation (default 14)
        volume_threshold_percentile: Percentile threshold for volume filter
        min_volume_ratio: Minimum volume ratio vs 20-day average
        trailing_stop_pct: Trailing stop percentage (5.0 = 5%)
        enable_trailing_stops: Enable/disable trailing stop functionality
        square_off_time: Mandatory square-off time (HH:MM format, IST)
        min_di_separation: Minimum gap between +DI and -DI for valid signal
        min_adx_strength: Minimum ADX value for trend strength confirmation
        min_confidence: Minimum confidence score for signal execution (0-1)
        max_signal_age_seconds: Maximum age of signal before rejection
        enable_volume_filter: Enable/disable volume filtering
        signal_generation_end_time: Stop generating new signals after this time
    """
    # Portfolio settings
    portfolio_value: float = float(os.getenv("PORTFOLIO_VALUE", "100000"))
    risk_per_trade_pct: float = float(os.getenv("RISK_PER_TRADE", "1.0"))
    max_positions: int = int(os.getenv("MAX_POSITIONS", "5"))

    # ADX/DI parameters
    di_period: int = int(os.getenv("DI_PERIOD", "14"))
    volume_threshold_percentile: float = float(os.getenv("VOLUME_THRESHOLD_PERCENTILE", "60.0"))
    min_volume_ratio: float = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))

    # Risk management
    trailing_stop_pct: float = float(os.getenv("TRAILING_STOP_PCT", "5.0"))
    enable_trailing_stops: bool = os.getenv("ENABLE_TRAILING_STOPS", "true").lower() == "true"
    square_off_time: str = os.getenv("SQUARE_OFF_TIME", "15:20")  # 3:20 PM IST

    # Signal filtering
    min_di_separation: float = float(os.getenv("MIN_DI_SEPARATION", "2.0"))
    min_adx_strength: float = float(os.getenv("MIN_ADX_STRENGTH", "20.0"))
    min_confidence: float = float(os.getenv("MIN_CONFIDENCE", "0.60"))
    max_signal_age_seconds: int = int(os.getenv("MAX_SIGNAL_AGE_SECONDS", "30"))
    enable_volume_filter: bool = os.getenv("ENABLE_VOLUME_FILTER", "true").lower() == "true"
    signal_generation_end_time: str = os.getenv("SIGNAL_GENERATION_END_TIME", "14:00")  # 2:00 PM IST

    def get_square_off_time(self) -> time:
        """
        Convert square-off time string to time object.

        Returns:
            time: Square-off time as time object
        """
        hour, minute = map(int, self.square_off_time.split(":"))
        return time(hour=hour, minute=minute)

    def get_signal_generation_end_time(self) -> time:
        """
        Convert signal generation end time string to time object.

        Returns:
            time: Signal generation end time as time object
        """
        hour, minute = map(int, self.signal_generation_end_time.split(":"))
        return time(hour=hour, minute=minute)

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Calculate position size based on risk per trade.

        Args:
            entry_price: Entry price for the position
            stop_loss: Stop loss price

        Returns:
            int: Number of shares to trade
        """
        risk_amount = self.portfolio_value * (self.risk_per_trade_pct / 100)
        price_risk = abs(entry_price - stop_loss)

        if price_risk == 0:
            return 0

        quantity = int(risk_amount / price_risk)
        return max(1, quantity)  # Minimum 1 share

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration parameters.

        Returns:
            tuple: (is_valid, list of error messages)
        """
        errors = []

        if self.portfolio_value <= 0:
            errors.append("Portfolio value must be positive")

        if self.risk_per_trade_pct <= 0 or self.risk_per_trade_pct > 100:
            errors.append("Risk per trade must be between 0 and 100")

        if self.max_positions <= 0:
            errors.append("Max positions must be positive")

        if self.di_period < 2:
            errors.append("DI period must be at least 2")

        if self.min_confidence < 0 or self.min_confidence > 1:
            errors.append("Min confidence must be between 0 and 1")

        if self.trailing_stop_pct <= 0:
            errors.append("Trailing stop percentage must be positive")

        return len(errors) == 0, errors


@dataclass
class FyersConfig:
    """
    Fyers API configuration and credentials.

    Attributes:
        client_id: Fyers client ID
        secret_key: Fyers secret key
        redirect_uri: OAuth redirect URI
        access_token: Current access token (auto-generated)
        refresh_token: Refresh token for token renewal
        pin: Trading PIN for order placement
        base_url: Fyers API base URL
        ws_url: WebSocket URL for real-time data
    """
    client_id: str = os.getenv("FYERS_CLIENT_ID", "")
    secret_key: str = os.getenv("FYERS_SECRET_KEY", "")
    redirect_uri: str = os.getenv("FYERS_REDIRECT_URI", "http://localhost:8000/callback")
    access_token: Optional[str] = os.getenv("FYERS_ACCESS_TOKEN")
    refresh_token: Optional[str] = os.getenv("FYERS_REFRESH_TOKEN")
    pin: str = os.getenv("FYERS_PIN", "")

    # API endpoints
    base_url: str = "https://api-t1.fyers.in/api/v3"
    ws_url: str = "wss://api-t1.fyers.in/socket/v3"

    def is_authenticated(self) -> bool:
        """Check if valid access token exists."""
        return bool(self.access_token and len(self.access_token) > 0)

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate Fyers configuration.

        Returns:
            tuple: (is_valid, list of error messages)
        """
        errors = []

        if not self.client_id:
            errors.append("Fyers Client ID is required")

        if not self.secret_key:
            errors.append("Fyers Secret Key is required")

        if not self.pin:
            errors.append("Trading PIN is required")

        if not self.is_authenticated():
            errors.append("Access token is missing (run 'python main.py auth')")

        return len(errors) == 0, errors


@dataclass
class TradingConfig:
    """
    General trading system configuration.

    Attributes:
        enable_paper_trading: Enable paper trading mode (no real orders)
        enable_order_execution: Enable actual order placement
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        monitoring_interval: Interval for monitoring loop (seconds)
        data_update_interval: Interval for data updates (seconds)
        enable_notifications: Enable notifications (email/SMS)
        max_daily_loss_pct: Maximum daily loss before stopping (percentage)
        max_daily_trades: Maximum trades per day
        backtest_mode: Running in backtest mode
    """
    enable_paper_trading: bool = os.getenv("ENABLE_PAPER_TRADING", "true").lower() == "true"
    enable_order_execution: bool = os.getenv("ENABLE_ORDER_EXECUTION", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    monitoring_interval: int = int(os.getenv("MONITORING_INTERVAL", "10"))
    data_update_interval: int = int(os.getenv("DATA_UPDATE_INTERVAL", "5"))
    enable_notifications: bool = os.getenv("ENABLE_NOTIFICATIONS", "false").lower() == "true"
    max_daily_loss_pct: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
    max_daily_trades: int = int(os.getenv("MAX_DAILY_TRADES", "20"))
    backtest_mode: bool = False

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate trading configuration.

        Returns:
            tuple: (is_valid, list of error messages)
        """
        errors = []

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_log_levels:
            errors.append(f"Log level must be one of {valid_log_levels}")

        if self.monitoring_interval <= 0:
            errors.append("Monitoring interval must be positive")

        if self.max_daily_loss_pct <= 0:
            errors.append("Max daily loss percentage must be positive")

        if self.max_daily_trades <= 0:
            errors.append("Max daily trades must be positive")

        return len(errors) == 0, errors


@dataclass
class BacktestConfig:
    """
    Configuration for backtesting engine.

    Attributes:
        data_sources: List of SQLite database paths
        start_date: Backtest start date (YYYY-MM-DD)
        end_date: Backtest end date (YYYY-MM-DD)
        initial_capital: Initial capital for backtesting
        commission_pct: Commission percentage per trade
        slippage_pct: Slippage percentage
        min_data_points: Minimum data points required per symbol
        export_results: Export results to CSV
        output_directory: Directory for backtest results
    """
    data_sources: list[str] = field(default_factory=lambda:
    os.getenv("BACKTEST_DATA_SOURCES", "data/").split(","))
    start_date: Optional[str] = os.getenv("BACKTEST_START_DATE")
    end_date: Optional[str] = os.getenv("BACKTEST_END_DATE")
    initial_capital: float = float(os.getenv("BACKTEST_INITIAL_CAPITAL", "100000"))
    commission_pct: float = float(os.getenv("BACKTEST_COMMISSION_PCT", "0.05"))
    slippage_pct: float = float(os.getenv("BACKTEST_SLIPPAGE_PCT", "0.1"))
    min_data_points: int = int(os.getenv("BACKTEST_MIN_DATA_POINTS", "100"))
    export_results: bool = os.getenv("BACKTEST_EXPORT_RESULTS", "true").lower() == "true"
    output_directory: str = os.getenv("BACKTEST_OUTPUT_DIR", "backtest_results/")


class ConfigManager:
    """
    Centralized configuration manager for all settings.

    Manages loading, validation, and access to all configuration objects.
    """

    def __init__(self):
        """Initialize all configuration objects."""
        self.strategy = ADXStrategyConfig()
        self.fyers = FyersConfig()
        self.trading = TradingConfig()
        self.backtest = BacktestConfig()

    def validate_all(self) -> tuple[bool, dict[str, list[str]]]:
        """
        Validate all configurations.

        Returns:
            tuple: (all_valid, dict of errors by config type)
        """
        all_errors = {}

        is_valid, errors = self.strategy.validate()
        if not is_valid:
            all_errors["strategy"] = errors

        is_valid, errors = self.fyers.validate()
        if not is_valid:
            all_errors["fyers"] = errors

        is_valid, errors = self.trading.validate()
        if not is_valid:
            all_errors["trading"] = errors

        return len(all_errors) == 0, all_errors

    def print_summary(self) -> None:
        """Print configuration summary."""
        print("=" * 60)
        print("FyersADX Configuration Summary")
        print("=" * 60)

        print("\n📊 Strategy Configuration:")
        print(f"  Portfolio Value: ₹{self.strategy.portfolio_value:,.0f}")
        print(f"  Risk per Trade: {self.strategy.risk_per_trade_pct}%")
        print(f"  Max Positions: {self.strategy.max_positions}")
        print(f"  DI Period: {self.strategy.di_period}")
        print(f"  Square-off Time: {self.strategy.square_off_time} IST")

        print("\n🔧 Trading Configuration:")
        print(f"  Paper Trading: {'Enabled' if self.trading.enable_paper_trading else 'Disabled'}")
        print(f"  Order Execution: {'Enabled' if self.trading.enable_order_execution else 'Disabled'}")
        print(f"  Log Level: {self.trading.log_level}")
        print(f"  Monitoring Interval: {self.trading.monitoring_interval}s")

        print("\n🔑 Fyers Configuration:")
        print(f"  Client ID: {self.fyers.client_id[:10]}..." if self.fyers.client_id else "  Client ID: Not set")
        print(f"  Authenticated: {'Yes' if self.fyers.is_authenticated() else 'No'}")

        print("\n" + "=" * 60)


# Global configuration instance
config = ConfigManager()