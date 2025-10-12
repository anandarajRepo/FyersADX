"""
ADX Strategy Backtesting Engine.

Implements historical backtesting with the same strategy logic used for live trading,
including the mandatory 3:20 PM square-off rule.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from models.trading_models import (
    ADXIndicators, SignalType, ExitReason, StrategyMetrics,
    TradeResult, SymbolCategory
)
from services.analysis_service import ADXTechnicalAnalysisService
from config.settings import ADXStrategyConfig, BacktestConfig
from backtest.data_loader import SQLiteDataLoader

logger = logging.getLogger(__name__)


class BacktestPosition:
    """Simplified position class for backtesting."""

    def __init__(self, symbol: str, signal_type: SignalType, entry_price: float,
                 quantity: int, stop_loss: float, target: float, entry_time: datetime,
                 entry_indicators: ADXIndicators):
        self.symbol = symbol
        self.signal_type = signal_type
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.target = target
        self.entry_time = entry_time
        self.entry_indicators = entry_indicators
        self.current_stop_loss = stop_loss
        self.highest_price = entry_price
        self.lowest_price = entry_price
        self.exit_price: Optional[float] = None
        self.exit_time: Optional[datetime] = None
        self.exit_reason: Optional[ExitReason] = None
        self.pnl: float = 0.0

    def update_price(self, price: float):
        """Update position with new price."""
        self.highest_price = max(self.highest_price, price)
        self.lowest_price = min(self.lowest_price, price)

    def close(self, exit_price: float, exit_time: datetime, exit_reason: ExitReason) -> float:
        """Close position and calculate P&L."""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = exit_reason

        if self.signal_type == SignalType.LONG:
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity

        return self.pnl


class ADXBacktester:
    """
    Historical backtesting engine for ADX DI Crossover strategy.

    Features:
    - Processes historical OHLCV data
    - Calculates DI indicators on historical data
    - Simulates signal generation and position management
    - Enforces 3:20 PM square-off rule
    - Accounts for commission and slippage
    - Generates comprehensive performance reports
    """

    # Market hours (IST)
    MARKET_OPEN = time(9, 15)
    MARKET_CLOSE = time(15, 30)
    SQUARE_OFF_TIME = time(15, 20)  # 3:20 PM mandatory square-off

    def __init__(self, strategy_config: ADXStrategyConfig, backtest_config: BacktestConfig):
        """
        Initialize backtester.

        Args:
            strategy_config: Strategy configuration
            backtest_config: Backtest configuration
        """
        self.strategy_config = strategy_config
        self.backtest_config = backtest_config

        self.analysis_service = ADXTechnicalAnalysisService(strategy_config)
        self.data_loader = SQLiteDataLoader()

        # Backtest state
        self.positions: Dict[str, BacktestPosition] = {}
        self.completed_trades: List[TradeResult] = []
        self.daily_pnl: Dict[str, float] = {}
        self.equity_curve: List[Tuple[datetime, float]] = []

        # Starting capital
        self.capital = backtest_config.initial_capital
        self.initial_capital = backtest_config.initial_capital

        logger.info(f"Initialized ADXBacktester with capital: ₹{self.capital:,.0f}")

    def run_backtest(self, symbols: List[str],
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> StrategyMetrics:
        """
        Run complete backtest on specified symbols.

        Args:
            symbols: List of symbols to backtest
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            StrategyMetrics object with results
        """
        logger.info(f"Starting backtest for {len(symbols)} symbols")

        # Load data for all symbols
        data_dict = self._load_data(symbols, start_date, end_date)

        if not data_dict:
            logger.error("No data loaded for backtesting")
            return self._create_empty_metrics()

        # Run backtest on combined timeline
        self._run_time_based_backtest(data_dict)

        # Generate metrics
        metrics = self._calculate_metrics()

        # Export results if configured
        if self.backtest_config.export_results:
            self._export_results(metrics)

        return metrics

    def _load_data(self, symbols: List[str],
                   start_date: Optional[str],
                   end_date: Optional[str]) -> Dict[str, pd.DataFrame]:
        """
        Load and prepare data for all symbols.

        Args:
            symbols: List of symbols
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Dict mapping symbol to DataFrame with indicators
        """
        data_dict = {}

        for symbol in symbols:
            logger.info(f"Loading data for {symbol}")

            # Load from database
            df = self._load_symbol_data(symbol)

            if df is None or len(df) < self.backtest_config.min_data_points:
                logger.warning(f"Insufficient data for {symbol}")
                continue

            # Filter by date range
            if start_date:
                df = df[df['timestamp'] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df['timestamp'] <= pd.to_datetime(end_date)]

            # Calculate indicators
            df = self.analysis_service.calculate_di_indicators(df, self.strategy_config.di_period)

            # Store
            data_dict[symbol] = df
            logger.info(f"Loaded {len(df)} bars for {symbol}")

        return data_dict

    def _load_symbol_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load data for a single symbol from databases."""
        for db_path in self.backtest_config.data_sources:
            try:
                df = self.data_loader.load_from_database(db_path, symbol)
                if df is not None and len(df) > 0:
                    return df
            except Exception as e:
                logger.debug(f"Could not load {symbol} from {db_path}: {e}")

        return None

    def _run_time_based_backtest(self, data_dict: Dict[str, pd.DataFrame]) -> None:
        """
        Run backtest using time-based simulation.

        Processes all symbols together in chronological order to simulate
        real trading conditions.
        """
        # Combine all timestamps
        all_timestamps = set()
        for df in data_dict.values():
            all_timestamps.update(df['timestamp'].tolist())

        timestamps = sorted(all_timestamps)
        logger.info(f"Processing {len(timestamps)} time points")

        current_date = None

        for timestamp in timestamps:
            # Check if new trading day
            if current_date != timestamp.date():
                # Square off all positions at end of previous day
                if current_date is not None:
                    self._square_off_all_positions(timestamp, ExitReason.TIME_EXIT_3_20PM)

                current_date = timestamp.date()
                logger.debug(f"Trading day: {current_date}")

            # Get current time
            current_time = timestamp.time()

            # Check if within market hours
            if not (self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE):
                continue

            # CRITICAL: Check for 3:20 PM square-off
            if current_time >= self.SQUARE_OFF_TIME:
                self._square_off_all_positions(timestamp, ExitReason.TIME_EXIT_3_20PM)
                continue

            # Process each symbol
            for symbol, df in data_dict.items():
                # Get data for current timestamp
                current_data = df[df['timestamp'] == timestamp]
                if current_data.empty:
                    continue

                row = current_data.iloc[0]

                # Update existing position
                if symbol in self.positions:
                    self._monitor_position(symbol, row, timestamp)

                # Generate new signals (only before signal cutoff time)
                elif (len(self.positions) < self.strategy_config.max_positions and
                      current_time < time(14, 0)):  # Before 2:00 PM
                    self._check_for_signal(symbol, df, timestamp, row)

            # Update equity curve
            self._update_equity_curve(timestamp)

        # Close any remaining positions
        if self.positions:
            last_timestamp = timestamps[-1]
            self._square_off_all_positions(last_timestamp, ExitReason.TIME_EXIT_3_20PM)

    def _check_for_signal(self, symbol: str, df: pd.DataFrame,
                          timestamp: datetime, current_row: pd.Series) -> None:
        """Check for DI crossover signal."""
        # Need previous row for crossover detection
        idx = df[df['timestamp'] == timestamp].index[0]
        if idx == 0:
            return

        prev_row = df.iloc[idx - 1]

        # Create indicator objects
        current_indicators = ADXIndicators(
            symbol=symbol,
            di_plus=current_row['+DI'],
            di_minus=current_row['-DI'],
            adx=current_row['ADX'],
            true_range=current_row['TR'],
            dm_plus=current_row['DM+'],
            dm_minus=current_row['DM-'],
            timestamp=timestamp
        )

        prev_indicators = ADXIndicators(
            symbol=symbol,
            di_plus=prev_row['+DI'],
            di_minus=prev_row['-DI'],
            adx=prev_row['ADX'],
            true_range=prev_row['TR'],
            dm_plus=prev_row['DM+'],
            dm_minus=prev_row['DM-'],
            timestamp=prev_row['timestamp']
        )

        # Detect crossover
        signal_type = self.analysis_service.detect_di_crossover(
            symbol, current_indicators, prev_indicators
        )

        if signal_type:
            # Validate signal (simplified for backtest)
            if self._validate_backtest_signal(current_indicators, current_row):
                self._enter_position(symbol, signal_type, current_row, timestamp, current_indicators)

    def _validate_backtest_signal(self, indicators: ADXIndicators, row: pd.Series) -> bool:
        """Simplified signal validation for backtesting."""
        # Check DI separation
        if indicators.di_separation < self.strategy_config.min_di_separation:
            return False

        # Check ADX strength
        if indicators.adx < self.strategy_config.min_adx_strength:
            return False

        # Volume check (if available)
        if 'volume' in row and self.strategy_config.enable_volume_filter:
            # Simplified: just check if volume > 0
            if row['volume'] <= 0:
                return False

        return True

    def _enter_position(self, symbol: str, signal_type: SignalType,
                        row: pd.Series, timestamp: datetime,
                        indicators: ADXIndicators) -> None:
        """Enter a new position."""
        # Calculate entry parameters
        entry_price = row['close']

        # Apply slippage
        slippage = entry_price * (self.backtest_config.slippage_pct / 100)
        if signal_type == SignalType.LONG:
            entry_price += slippage
        else:
            entry_price -= slippage

        # Calculate stop loss and target
        stop_loss = self._calculate_stop_loss(signal_type, entry_price)
        target = self._calculate_target(signal_type, entry_price, stop_loss)

        # Calculate position size
        quantity = self.strategy_config.calculate_position_size(entry_price, stop_loss)

        # Check if we have enough capital
        required_capital = entry_price * quantity
        if required_capital > self.capital * 0.9:  # Use max 90% of capital
            logger.debug(f"Insufficient capital for {symbol}")
            return

        # Create position
        position = BacktestPosition(
            symbol=symbol,
            signal_type=signal_type,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target=target,
            entry_time=timestamp,
            entry_indicators=indicators
        )

        self.positions[symbol] = position
        logger.info(f"Entered {signal_type.value} position: {symbol} @ ₹{entry_price:.2f}")

    def _monitor_position(self, symbol: str, row: pd.Series, timestamp: datetime) -> None:
        """Monitor existing position for exit conditions."""
        position = self.positions[symbol]
        current_price = row['close']

        # Update position
        position.update_price(current_price)

        # Check stop loss
        if self._is_stop_loss_hit(position, row):
            self._exit_position(symbol, row['low'] if position.signal_type == SignalType.LONG else row['high'],
                                timestamp, ExitReason.STOP_LOSS)
            return

        # Check target
        if self._is_target_hit(position, row):
            self._exit_position(symbol, row['high'] if position.signal_type == SignalType.LONG else row['low'],
                                timestamp, ExitReason.TARGET)
            return

        # Check for opposite crossover (simplified)
        # In full implementation, would check previous indicators

        # Update trailing stop
        if self.strategy_config.enable_trailing_stops:
            new_stop = self.analysis_service.calculate_trailing_stop(
                position.signal_type,
                position.entry_price,
                current_price,
                position.highest_price,
                position.lowest_price,
                self.strategy_config.trailing_stop_pct
            )
            position.current_stop_loss = new_stop

    def _is_stop_loss_hit(self, position: BacktestPosition, row: pd.Series) -> bool:
        """Check if stop loss was hit."""
        if position.signal_type == SignalType.LONG:
            return row['low'] <= position.current_stop_loss
        else:
            return row['high'] >= position.current_stop_loss

    def _is_target_hit(self, position: BacktestPosition, row: pd.Series) -> bool:
        """Check if target was hit."""
        if position.signal_type == SignalType.LONG:
            return row['high'] >= position.target
        else:
            return row['low'] <= position.target

    def _exit_position(self, symbol: str, exit_price: float,
                       exit_time: datetime, exit_reason: ExitReason) -> None:
        """Exit a position."""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        # Apply slippage
        slippage = exit_price * (self.backtest_config.slippage_pct / 100)
        if position.signal_type == SignalType.LONG:
            exit_price -= slippage
        else:
            exit_price += slippage

        # Close position
        pnl = position.close(exit_price, exit_time, exit_reason)

        # Apply commission
        commission = (position.entry_price * position.quantity +
                      exit_price * position.quantity) * (self.backtest_config.commission_pct / 100)
        pnl -= commission

        # Update capital
        self.capital += pnl

        # Record trade
        holding_time = (exit_time - position.entry_time).total_seconds() / 60
        pnl_pct = (pnl / (position.entry_price * position.quantity)) * 100

        trade_result = TradeResult(
            symbol=symbol,
            signal_type=position.signal_type,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            holding_time_minutes=holding_time,
            entry_indicators=position.entry_indicators,
            max_favorable_excursion=position.highest_price if position.signal_type == SignalType.LONG else position.lowest_price,
            max_adverse_excursion=position.lowest_price if position.signal_type == SignalType.LONG else position.highest_price
        )

        self.completed_trades.append(trade_result)
        del self.positions[symbol]

        logger.info(f"Exited {position.signal_type.value}: {symbol} @ ₹{exit_price:.2f} | "
                    f"P&L: ₹{pnl:.2f} [{exit_reason.value}]")

    def _square_off_all_positions(self, timestamp: datetime, exit_reason: ExitReason) -> None:
        """Square off all open positions (3:20 PM rule)."""
        if not self.positions:
            return

        logger.info(f"Squaring off {len(self.positions)} positions at {timestamp.time()}")

        symbols = list(self.positions.keys())
        for symbol in symbols:
            position = self.positions[symbol]
            # Use entry price as approximation (in reality, would use market price)
            self._exit_position(symbol, position.entry_price, timestamp, exit_reason)

    def _calculate_stop_loss(self, signal_type: SignalType, entry_price: float) -> float:
        """Calculate stop loss."""
        stop_pct = self.strategy_config.trailing_stop_pct / 100
        if signal_type == SignalType.LONG:
            return entry_price * (1 - stop_pct)
        else:
            return entry_price * (1 + stop_pct)

    def _calculate_target(self, signal_type: SignalType, entry_price: float, stop_loss: float) -> float:
        """Calculate target (2:1 reward-risk)."""
        risk = abs(entry_price - stop_loss)
        reward = risk * 2
        if signal_type == SignalType.LONG:
            return entry_price + reward
        else:
            return entry_price - reward

    def _update_equity_curve(self, timestamp: datetime) -> None:
        """Update equity curve with current portfolio value."""
        unrealized_pnl = sum(
            (pos.highest_price - pos.entry_price) * pos.quantity
            if pos.signal_type == SignalType.LONG
            else (pos.entry_price - pos.lowest_price) * pos.quantity
            for pos in self.positions.values()
        )

        total_equity = self.capital + unrealized_pnl
        self.equity_curve.append((timestamp, total_equity))

    def _calculate_metrics(self) -> StrategyMetrics:
        """Calculate comprehensive backtest metrics."""
        if not self.completed_trades:
            return self._create_empty_metrics()

        metrics = StrategyMetrics(
            start_date=self.completed_trades[0].entry_time,
            end_date=self.completed_trades[-1].exit_time
        )

        metrics.calculate_from_trades(self.completed_trades)
        metrics.total_return_pct = ((self.capital - self.initial_capital) / self.initial_capital) * 100

        return metrics

    def _create_empty_metrics(self) -> StrategyMetrics:
        """Create empty metrics object."""
        return StrategyMetrics(
            start_date=datetime.now(),
            end_date=datetime.now()
        )

    def _export_results(self, metrics: StrategyMetrics) -> None:
        """Export backtest results to files."""
        output_dir = Path(self.backtest_config.output_directory)
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Export trades
        if self.completed_trades:
            trades_df = pd.DataFrame([
                {
                    'symbol': t.symbol,
                    'signal_type': t.signal_type.value,
                    'entry_time': t.entry_time,
                    'exit_time': t.exit_time,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'quantity': t.quantity,
                    'pnl': t.pnl,
                    'pnl_pct': t.pnl_pct,
                    'exit_reason': t.exit_reason.value,
                    'holding_minutes': t.holding_time_minutes
                }
                for t in self.completed_trades
            ])

            trades_file = output_dir / f"trades_{timestamp}.csv"
            trades_df.to_csv(trades_file, index=False)
            logger.info(f"Exported trades to {trades_file}")

        # Export equity curve
        if self.equity_curve:
            equity_df = pd.DataFrame(self.equity_curve, columns=['timestamp', 'equity'])
            equity_file = output_dir / f"equity_curve_{timestamp}.csv"
            equity_df.to_csv(equity_file, index=False)
            logger.info(f"Exported equity curve to {equity_file}")

        # Export summary
        summary_file = output_dir / f"summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write("ADX BACKTEST SUMMARY\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Period: {metrics.start_date} to {metrics.end_date}\n")
            f.write(f"Total Trades: {metrics.total_trades}\n")
            f.write(f"Win Rate: {metrics.win_rate:.2%}\n")
            f.write(f"Total Return: {metrics.total_return_pct:.2%}\n")
            f.write(f"Profit Factor: {metrics.profit_factor:.2f}\n")

        logger.info(f"Exported summary to {summary_file}")