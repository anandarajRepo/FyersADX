"""
Main ADX DI Crossover Strategy Implementation.

This module implements the complete trading strategy including signal generation,
position management, and the critical 3:20 PM square-off logic.
"""

import json
import logging
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

from models.trading_models import (
    ADXIndicators, ADXSignal, Position, TradeResult, StrategyMetrics,
    LiveQuote, SignalType, SymbolCategory, ExitReason, OrderStatus
)
from services.analysis_service import ADXTechnicalAnalysisService
from services.market_timing_service import MarketTimingService
from config.settings import ADXStrategyConfig, TradingConfig, FyersConfig

logger = logging.getLogger(__name__)


class PaperTradeLogger:
    """
    Logs paper trade orders and closed trades to a daily JSON file.

    File location: logs/paper_trades_YYYYMMDD.json
    Each file is a JSON array of event objects with a 'type' field:
      - "order"  : entry order logged when position is opened
      - "trade"  : closed trade record when position is exited
    """

    def __init__(self):
        Path("logs").mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        self.log_path = Path(f"logs/paper_trades_{date_str}.json")
        self._records: list = []
        # Load existing records if file already exists (e.g., strategy restarted same day)
        if self.log_path.exists():
            try:
                with open(self.log_path, "r") as f:
                    self._records = json.load(f)
            except Exception:
                self._records = []

    def _flush(self):
        try:
            with open(self.log_path, "w") as f:
                json.dump(self._records, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"PaperTradeLogger write error: {e}")

    def log_order(self, signal, quantity: int):
        """Record a paper entry order."""
        record = {
            "type": "order",
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "direction": signal.signal_type.value,
            "quantity": quantity,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "target_price": signal.target_price,
            "risk_reward_ratio": round(signal.risk_reward_ratio, 2),
            "adx": round(signal.adx, 2),
            "di_plus": round(signal.di_plus, 2),
            "di_minus": round(signal.di_minus, 2),
            "confidence": round(signal.confidence, 3),
        }
        self._records.append(record)
        self._flush()
        logger.info(f"[PAPER] Order logged → {self.log_path}")

    def log_trade(self, trade_result):
        """Record a closed paper trade."""
        record = {
            "type": "trade",
            "timestamp": datetime.now().isoformat(),
            "symbol": trade_result.symbol,
            "direction": trade_result.signal_type.value,
            "quantity": trade_result.quantity,
            "entry_price": trade_result.entry_price,
            "exit_price": trade_result.exit_price,
            "entry_time": trade_result.entry_time.isoformat() if trade_result.entry_time else None,
            "exit_time": trade_result.exit_time.isoformat() if trade_result.exit_time else None,
            "holding_minutes": trade_result.holding_time_minutes,
            "pnl": round(trade_result.pnl, 2),
            "pnl_pct": round(trade_result.pnl_pct, 3),
            "exit_reason": trade_result.exit_reason.value,
            "result": "WIN" if trade_result.is_winner else "LOSS",
        }
        self._records.append(record)
        self._flush()
        logger.info(
            f"[PAPER] Trade logged → {trade_result.symbol} "
            f"{'WIN' if trade_result.is_winner else 'LOSS'} "
            f"P&L ₹{trade_result.pnl:.2f} | {self.log_path}"
        )


class ADXStrategy:
    """
    Complete ADX DI Crossover Trading Strategy.

    Features:
    - Real-time DI crossover detection
    - Volume-filtered signal generation
    - Dynamic trailing stops
    - Position management
    - Mandatory 3:20 PM square-off
    - Comprehensive performance tracking
    """

    def __init__(
            self,
            strategy_config: ADXStrategyConfig,
            trading_config: TradingConfig,
            symbols: List[str],
            fyers_config: Optional[FyersConfig] = None
    ):

        self.strategy_config = strategy_config
        self.trading_config = trading_config
        self.symbols = symbols
        self.fyers_config = fyers_config

        # Initialize services — analysis_service must be created first so it
        # can be shared with the WebSocket service (fixes the split-instance bug
        # that caused "No previous indicators available" on every scan cycle).
        self.analysis_service = ADXTechnicalAnalysisService(strategy_config)
        self.timing_service = MarketTimingService(
            square_off_time=strategy_config.square_off_time,
            signal_cutoff_time=strategy_config.signal_generation_end_time
        )

        # Initialize data service, sharing the same analysis_service instance
        from services.fyers_websocket_service import HybridADXDataService

        self.data_service = None
        if fyers_config and fyers_config.is_authenticated():
            self.data_service = HybridADXDataService(
                fyers_config=fyers_config,
                strategy_config=strategy_config,
                symbols=symbols,
                analysis_service=self.analysis_service
            )
            logger.info("Initialized HybridADXDataService for real-time data")
        else:
            logger.warning("No data service initialized - running in limited mode")

        # State management
        self.positions: Dict[str, Position] = {}
        self.pending_signals: List[ADXSignal] = []
        self.completed_trades: List[TradeResult] = []
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0

        # Performance tracking
        self.metrics = StrategyMetrics(
            start_date=datetime.now(),
            end_date=datetime.now()
        )

        # Resolve live trading mode: LIVE_TRADING env flag takes precedence
        # over the legacy enable_paper_trading / enable_order_execution flags.
        if hasattr(trading_config, 'live_trading'):
            self.live_trading = trading_config.live_trading
        else:
            # Backward-compat: derive from legacy flags
            self.live_trading = (
                trading_config.enable_order_execution and
                not trading_config.enable_paper_trading
            )

        # Paper trade logger (used when not live)
        self.paper_logger = PaperTradeLogger() if not self.live_trading else None

        # Flags
        self.is_running = False
        self.positions_squared_off_today = False

        mode = "LIVE" if self.live_trading else "PAPER"
        logger.info(f"Initialized ADXStrategy with {len(symbols)} symbols — mode: {mode}")
        logger.info(f"Max positions: {strategy_config.max_positions}")
        logger.info(f"Square-off time: {strategy_config.square_off_time}")

    async def run_strategy_cycle(self) -> None:
        """Main strategy execution cycle."""
        self.is_running = True
        self._last_df_snapshot_time: datetime = datetime.min
        logger.info("Starting ADX strategy cycle")

        try:
            # START DATA SERVICE
            if self.data_service:
                logger.info("Starting data service...")
                service_started = await self.data_service.start()
                if not service_started:
                    logger.error("Failed to start data service")
                    return
                logger.info("Data service started successfully")

                # Setup callbacks for real-time updates
                self._setup_data_callbacks()
            else:
                logger.warning("Running without data service - limited functionality")

            while self.is_running:
                # Check if market is open
                if not self.timing_service.is_market_open():
                    logger.info("Market closed, waiting...")
                    await asyncio.sleep(60)
                    continue

                # CRITICAL: Check for mandatory 3:20 PM square-off
                if self.timing_service.should_square_off_positions():
                    await self._square_off_all_positions(ExitReason.TIME_EXIT_3_20PM)
                    self.positions_squared_off_today = True
                    logger.warning("All positions squared off at 3:20 PM - NO MORE TRADING TODAY")
                    self.is_running = False
                    break

                # Update market state
                await self._update_market_state()

                # Monitor existing positions
                await self._monitor_positions()

                # Scan for new signals
                if (self.timing_service.is_signal_generation_time() and
                        not self.positions_squared_off_today and
                        len(self.positions) < self.strategy_config.max_positions):
                    await self._scan_for_di_crossovers()

                # Execute pending signals
                await self._process_pending_signals()

                # Update performance metrics
                self._update_metrics()

                # Log status periodically
                if self.daily_trades % 10 == 0:
                    self._log_strategy_status()

                # Log dataframe snapshot every 15 minutes
                now = datetime.now()
                if (now - self._last_df_snapshot_time).total_seconds() >= 900:
                    self.analysis_service.log_dataframe_snapshot()
                    self._last_df_snapshot_time = now

                # Sleep before next cycle
                await asyncio.sleep(self.trading_config.monitoring_interval)

        except Exception as e:
            logger.error(f"Error in strategy cycle: {e}", exc_info=True)
            raise
        finally:
            # CLEANUP: Stop data service
            if self.data_service:
                logger.info("Stopping data service...")
                await self.data_service.stop()

            self.is_running = False
            logger.info("Strategy cycle stopped")

            # End-of-day paper trading summary (after market hours / on stop)
            if not self.live_trading:
                self._print_end_of_day_summary()

    def _setup_data_callbacks(self) -> None:
        """Setup callbacks for real-time data updates."""
        if not self.data_service:
            return

        def on_quote_update(quote: LiveQuote):
            """Handle real-time quote updates."""
            logger.debug(f"Quote update: {quote.symbol} @ {quote.ltp}")

            # Update position if exists
            if quote.symbol in self.positions:
                self.positions[quote.symbol].update_price(quote.ltp)

        def on_indicator_update(indicators: ADXIndicators):
            """Handle real-time indicator updates."""
            logger.debug(f"Indicator update: {indicators.symbol} - "
                         f"+DI: {indicators.di_plus:.2f}, -DI: {indicators.di_minus:.2f}, "
                         f"ADX: {indicators.adx:.2f}")

        def on_error(error_message):
            """Handle data service errors."""
            logger.error(f"Data service error: {error_message}")

        # Register callbacks
        self.data_service.ws_service.register_quote_callback(on_quote_update)
        self.data_service.ws_service.register_indicator_callback(on_indicator_update)
        self.data_service.ws_service.register_error_callback(on_error)

        logger.info("Data callbacks registered")

    async def _update_market_state(self) -> None:
        """Update market data for all symbols."""
        if not self.data_service:
            logger.warning("No data service available")
            return

        # Data is automatically updated via WebSocket callbacks
        # This method can be used for any additional state management
        logger.debug("Market state updated via WebSocket")

    async def _scan_for_di_crossovers(self) -> None:
        """
        Scan all symbols for DI crossovers and generate signals.
        """
        self.analysis_service.print_df_tail()

        for symbol in self.symbols:
            try:
                # Skip if already have position
                if symbol in self.positions:
                    continue

                # Get current indicators (would come from your data service)
                # This is a placeholder - integrate with your WebSocket service
                current_indicators = self._get_current_indicators(symbol)
                if not current_indicators:
                    continue

                # Detect crossover
                signal_type = self.analysis_service.detect_di_crossover(
                    symbol, current_indicators
                )

                if signal_type:
                    # Generate signal
                    signal = await self._generate_signal(
                        symbol, signal_type, current_indicators
                    )

                    if signal:
                        self.pending_signals.append(signal)
                        logger.info(f"Generated {signal_type.value} signal for {symbol}")

            except Exception as e:
                logger.error(f"Error scanning {symbol}: {e}")

    async def _generate_signal(
            self,
            symbol: str,
            signal_type: SignalType,
            indicators: ADXIndicators
    ) -> Optional[ADXSignal]:
        """
        Generate and validate a trading signal.

        Args:
            symbol: Symbol identifier
            signal_type: LONG or SHORT
            indicators: Current ADX indicators

        Returns:
            ADXSignal or None if validation fails
        """
        # Get current quote (placeholder - integrate with your data service)
        live_quote = await self._get_live_quote(symbol)
        if not live_quote:
            return None

        # Calculate entry parameters
        entry_price = live_quote.ltp
        stop_loss = self._calculate_stop_loss(signal_type, entry_price)
        target_price = self._calculate_target_price(signal_type, entry_price, stop_loss)

        # Calculate risk/reward
        risk_amount = abs(entry_price - stop_loss)
        reward_amount = abs(target_price - entry_price)
        risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

        # Create signal
        signal = ADXSignal(
            symbol=symbol,
            category=SymbolCategory.UNKNOWN,  # Would be determined from symbol list
            signal_type=signal_type,
            di_plus=indicators.di_plus,
            di_minus=indicators.di_minus,
            adx=indicators.adx,
            di_separation=indicators.di_separation,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            confidence=0.0,  # Will be calculated in validation
            volume_ratio=0.0,  # Will be calculated in validation
            signal_volume=live_quote.volume,
            timestamp=datetime.now(),
            square_off_time=self.timing_service.get_square_off_time(),
            risk_amount=risk_amount,
            reward_amount=reward_amount,
            risk_reward_ratio=risk_reward_ratio
        )

        # Validate signal
        is_valid, confidence, quality_scores = self.analysis_service.validate_adx_signal(
            symbol, signal, live_quote
        )

        if not is_valid:
            logger.debug(f"Signal rejected for {symbol}: Low confidence")
            return None

        # Update signal with validation results
        signal.confidence = confidence
        signal.quality_scores = quality_scores
        signal.volume_ratio = quality_scores.get('volume_ratio', 1.0)

        return signal

    async def _process_pending_signals(self) -> None:
        """Process and execute pending signals."""
        if not self.pending_signals:
            return

        # Sort by confidence (highest first)
        self.pending_signals.sort(key=lambda s: s.confidence, reverse=True)

        executed = []
        for signal in self.pending_signals:
            # Check if we can still enter positions
            if len(self.positions) >= self.strategy_config.max_positions:
                logger.info("Max positions reached, skipping remaining signals")
                break

            # Check daily trade limit
            if self.daily_trades >= self.trading_config.max_daily_trades:
                logger.warning("Daily trade limit reached")
                break

            # Execute signal
            success = await self._execute_signal(signal)
            if success:
                executed.append(signal)
                self.daily_trades += 1

        # Remove executed signals
        for signal in executed:
            self.pending_signals.remove(signal)

    async def _execute_signal(self, signal: ADXSignal) -> bool:
        """
        Execute a trading signal with comprehensive logging and error handling.

        Args:
            signal: ADXSignal to execute

        Returns:
            bool: True if execution successful
        """
        try:
            # ═══════════════════════════════════════════════════════
            # VALIDATE ENTRY CONDITIONS
            # ═══════════════════════════════════════════════════════
            is_valid, reason = self.timing_service.validate_entry_time()
            if not is_valid:
                logger.warning(f"Entry rejected for {signal.symbol}: {reason}")
                return False

            # Calculate position size
            quantity = self.strategy_config.calculate_position_size(
                signal.entry_price, signal.stop_loss, signal.symbol
            )

            if quantity == 0:
                logger.warning(f"Position size calculation returned 0 for {signal.symbol}")
                return False

            logger.info(f"Position calculated: {signal.symbol} x {quantity}")

            # ═══════════════════════════════════════════════════════
            # CREATE POSITION OBJECT
            # ═══════════════════════════════════════════════════════
            position = Position(
                symbol=signal.symbol,
                category=signal.category,
                signal_type=signal.signal_type,
                entry_price=signal.entry_price,
                quantity=quantity,
                stop_loss=signal.stop_loss,
                target_price=signal.target_price,
                entry_di_plus=signal.di_plus,
                entry_di_minus=signal.di_minus,
                entry_adx=signal.adx,
                entry_time=datetime.now(),
                must_square_off_at=signal.square_off_time
            )

            # ═══════════════════════════════════════════════════════
            # PAPER TRADING MODE (LIVE_TRADING=false)
            # ═══════════════════════════════════════════════════════
            if not self.live_trading:
                self.positions[signal.symbol] = position
                logger.info("=" * 70)
                logger.info("PAPER TRADE EXECUTED (LIVE_TRADING=false)")
                logger.info("=" * 70)
                logger.info(f"   Type: {signal.signal_type.value}")
                logger.info(f"   Symbol: {signal.symbol}")
                logger.info(f"   Entry: ₹{signal.entry_price:.2f}")
                logger.info(f"   Quantity: {quantity}")
                logger.info(f"   Stop Loss: ₹{signal.stop_loss:.2f}")
                logger.info(f"   Target: ₹{signal.target_price:.2f}")
                logger.info("=" * 70)
                if self.paper_logger:
                    self.paper_logger.log_order(signal, quantity)
                return True

            # ═══════════════════════════════════════════════════════
            # LIVE TRADING MODE - PLACE REAL ORDER (LIVE_TRADING=true)
            # ═══════════════════════════════════════════════════════
            if self.live_trading:
                logger.info("=" * 70)
                logger.info("LIVE TRADING MODE - PLACING REAL ORDER")
                logger.info("=" * 70)

                # Validate Fyers authentication
                if not self.fyers_config or not self.fyers_config.is_authenticated():
                    logger.error("FATAL ERROR: Fyers not authenticated!")
                    logger.error("   Run: python main.py auth")
                    logger.error("=" * 70)
                    return False

                from config.symbols import get_lot_size, is_option_symbol

                # Adjust quantity for options (must be in lot multiples)
                lot_size = get_lot_size(signal.symbol)
                original_qty = quantity

                if is_option_symbol(signal.symbol):
                    if quantity % lot_size != 0:
                        quantity = (quantity // lot_size) * lot_size
                        if quantity == 0:
                            quantity = lot_size
                        logger.info(f"Lot size adjustment: {original_qty} → {quantity} (Lot: {lot_size})")

                # Update position with adjusted quantity
                position.quantity = quantity

                # Prepare order data for Fyers API
                order_data = {
                    "symbol": signal.symbol,
                    "qty": quantity,
                    "type": 2,  # 2 = MARKET ORDER
                    "side": 1 if signal.signal_type == SignalType.LONG else -1,  # 1=BUY, -1=SELL
                    "productType": "INTRADAY",
                    "limitPrice": 0,
                    "stopPrice": 0,
                    "validity": "DAY",
                    "disclosedQty": 0,
                    "offlineOrder": False
                }

                logger.info(f"   ORDER REQUEST:")
                logger.info(f"   Symbol: {signal.symbol}")
                logger.info(f"   Direction: {signal.signal_type.value}")
                logger.info(f"   Quantity: {quantity}")
                logger.info(f"   Order Type: MARKET")
                logger.info(f"   Price (est): ₹{signal.entry_price:.2f}")
                logger.info(f"   Product Type: INTRADAY")
                logger.info(f"   Side Code: {'BUY (1)' if order_data['side'] == 1 else 'SELL (-1)'}")

                try:
                    # Initialize Fyers API client if not already done
                    if not hasattr(self, 'fyers_api'):
                        from fyers_apiv3 import fyersModel

                        logger.info("🔧 Initializing Fyers API client...")
                        self.fyers_api = fyersModel.FyersModel(
                            client_id=self.fyers_config.client_id,
                            token=self.fyers_config.access_token,
                            log_path="logs/"
                        )
                        logger.info(" Fyers API client initialized")

                    # Place the order
                    logger.info(" Sending order to Fyers API...")
                    logger.info(f"   Full order payload: {order_data}")

                    response = self.fyers_api.place_order(data=order_data)

                    logger.info(f" Received response from Fyers:")
                    logger.info(f"   {response}")

                    # Check if order was successful
                    if response and response.get('s') == 'ok':
                        order_id = response.get('id')

                        logger.info("=" * 70)
                        logger.info(" ORDER PLACED SUCCESSFULLY!  ")
                        logger.info("=" * 70)
                        logger.info(f"   Order ID: {order_id}")
                        logger.info(f"   Symbol: {signal.symbol}")
                        logger.info(f"   Direction: {signal.signal_type.value}")
                        logger.info(f"   Quantity: {quantity}")
                        logger.info(f"   Entry Price: ₹{signal.entry_price:.2f}")
                        logger.info(f"   Stop Loss: ₹{signal.stop_loss:.2f}")
                        logger.info(f"   Target: ₹{signal.target_price:.2f}")
                        logger.info(f"   Risk: ₹{abs(signal.entry_price - signal.stop_loss) * quantity:.2f}")
                        logger.info(f"   Reward: ₹{abs(signal.target_price - signal.entry_price) * quantity:.2f}")
                        logger.info("=" * 70)

                        # Add position to active positions dictionary
                        self.positions[signal.symbol] = position
                        return True

                    else:
                        # Order placement failed
                        error_msg = response.get('message', 'Unknown error') if response else 'No response received'
                        error_code = response.get('code', 'N/A') if response else 'N/A'

                        logger.error("=" * 70)
                        logger.error("  ORDER PLACEMENT FAILED ")
                        logger.error("=" * 70)
                        logger.error(f"   Error Message: {error_msg}")
                        logger.error(f"   Error Code: {error_code}")
                        logger.error(f"   Full Response: {response}")
                        logger.error(f"   Symbol: {signal.symbol}")
                        logger.error(f"   Quantity: {quantity}")
                        logger.error("=" * 70)
                        logger.error("")
                        logger.error("POSSIBLE CAUSES:")
                        logger.error("  • Insufficient funds in trading account")
                        logger.error("  • Symbol not available for trading")
                        logger.error("  • Market hours restriction")
                        logger.error("  • Quantity not in proper lot multiples")
                        logger.error("  • Invalid symbol format")
                        logger.error("  • API rate limit exceeded")
                        logger.error("=" * 70)

                        return False

                except Exception as e:
                    logger.error("=" * 70)
                    logger.error(" EXCEPTION DURING ORDER PLACEMENT ")
                    logger.error("=" * 70)
                    logger.error(f"   Exception Type: {type(e).__name__}")
                    logger.error(f"   Exception Message: {str(e)}")
                    logger.error(f"   Symbol: {signal.symbol}")
                    logger.error("=" * 70)
                    logger.exception("Full exception traceback:")
                    logger.error("=" * 70)
                    return False

            # Should never reach here — both branches above are exhaustive
            logger.error("Unexpected execution path in _execute_signal — check live_trading flag")
            return False

        except Exception as e:
            logger.error("=" * 70)
            logger.error(f" FATAL ERROR in _execute_signal: {e}")
            logger.error("=" * 70)
            logger.exception("Full traceback:")
            logger.error("=" * 70)
            return False

    async def _monitor_positions(self) -> None:
        """Monitor all open positions for exit conditions."""
        if not self.positions:
            return

        positions_to_close = []

        for symbol, position in self.positions.items():
            try:
                # Update position with current price
                live_quote = self._get_live_quote(symbol)
                if not live_quote:
                    continue

                position.update_price(live_quote.ltp)

                # Check for exit conditions
                exit_reason = await self._check_exit_conditions(position)

                if exit_reason:
                    positions_to_close.append((symbol, exit_reason))

            except Exception as e:
                logger.error(f"Error monitoring position for {symbol}: {e}")

        # Close positions
        for symbol, exit_reason in positions_to_close:
            await self._close_position(symbol, exit_reason)

    async def _check_exit_conditions(self, position: Position) -> Optional[ExitReason]:
        """
        Check if position should be exited.

        Args:
            position: Position to check

        Returns:
            ExitReason or None
        """
        # 1. CRITICAL: Check mandatory 3:20 PM square-off
        if self.timing_service.should_square_off_positions():
            return ExitReason.TIME_EXIT_3_20PM

        # 2. Check stop loss
        if position.is_stop_loss_hit():
            logger.info(f"Stop loss hit for {position.symbol}")
            return ExitReason.STOP_LOSS

        # 3. Check target
        if position.is_target_hit():
            logger.info(f"Target reached for {position.symbol}")
            return ExitReason.TARGET

        # 4. Check opposite DI crossover
        current_indicators = self._get_current_indicators(position.symbol)
        if current_indicators:
            history = self.analysis_service.get_indicator_history(position.symbol, 2)
            if len(history) >= 2:
                should_exit = self.analysis_service.should_exit_on_opposite_crossover(
                    position.signal_type, history[0], history[1]
                )
                if should_exit:
                    return ExitReason.SIGNAL_EXIT

        # 5. Update trailing stop
        if self.strategy_config.enable_trailing_stops:
            new_stop = self.analysis_service.calculate_trailing_stop(
                position.signal_type,
                position.entry_price,
                position.current_price,
                position.highest_price,
                position.lowest_price,
                self.strategy_config.trailing_stop_pct
            )
            position.update_trailing_stop(new_stop)

            # Check if trailing stop hit
            if position.is_stop_loss_hit():
                logger.info(f"Trailing stop hit for {position.symbol}")
                return ExitReason.TRAILING_STOP

        return None

    async def _close_position(self, symbol: str, exit_reason: ExitReason) -> None:
        """
        Close a position and record the trade.

        Args:
            symbol: Symbol to close
            exit_reason: Reason for exit
        """
        if symbol not in self.positions:
            return

        position = self.positions[symbol]
        exit_time = datetime.now()
        exit_price = position.current_price

        # Close position
        realized_pnl = position.close_position(exit_price, exit_reason, exit_time)

        # Update daily P&L
        self.daily_pnl += realized_pnl

        # Create trade result
        holding_time = self.timing_service.calculate_holding_time(
            position.entry_time, exit_time
        )

        pnl_pct = (realized_pnl / (position.entry_price * position.quantity)) * 100

        trade_result = TradeResult(
            symbol=symbol,
            signal_type=position.signal_type,
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=realized_pnl,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            holding_time_minutes=holding_time,
            entry_indicators=ADXIndicators(
                symbol=symbol,
                di_plus=position.entry_di_plus,
                di_minus=position.entry_di_minus,
                adx=position.entry_adx,
                true_range=0,
                dm_plus=0,
                dm_minus=0,
                timestamp=position.entry_time
            ),
            max_favorable_excursion=position.highest_price if position.signal_type == SignalType.LONG else position.lowest_price,
            max_adverse_excursion=position.lowest_price if position.signal_type == SignalType.LONG else position.highest_price
        )

        self.completed_trades.append(trade_result)

        # Remove from active positions
        del self.positions[symbol]

        result_str = "WIN" if trade_result.is_winner else "LOSS"
        logger.info(f"CLOSED {position.signal_type.value} position for {symbol}: "
                    f"P&L ₹{realized_pnl:.2f} ({pnl_pct:.2f}%) - {result_str} "
                    f"[{exit_reason.value}]")

        # Log closed trade to paper trade file when not live
        if not self.live_trading and self.paper_logger:
            self.paper_logger.log_trade(trade_result)

    async def _square_off_all_positions(self, exit_reason: ExitReason) -> None:
        """
        Square off all positions immediately.

        Args:
            exit_reason: Reason for square-off (typically TIME_EXIT_3_20PM)
        """
        if not self.positions:
            logger.info("No positions to square off")
            return

        logger.warning(f"SQUARING OFF ALL {len(self.positions)} POSITIONS: {exit_reason.value}")

        symbols_to_close = list(self.positions.keys())
        for symbol in symbols_to_close:
            await self._close_position(symbol, exit_reason)

        logger.info(f"All positions squared off. Daily P&L: ₹{self.daily_pnl:.2f}")

    def _calculate_stop_loss(self, signal_type: SignalType, entry_price: float) -> float:
        """Calculate initial stop loss."""
        stop_pct = self.strategy_config.trailing_stop_pct / 100.0

        if signal_type == SignalType.LONG:
            return entry_price * (1 - stop_pct)
        else:  # SHORT
            return entry_price * (1 + stop_pct)

    def _calculate_target_price(
            self,
            signal_type: SignalType,
            entry_price: float,
            stop_loss: float
    ) -> float:
        """Calculate target price (2:1 reward-risk ratio)."""
        risk = abs(entry_price - stop_loss)
        reward = risk * 2.0  # 2:1 ratio

        if signal_type == SignalType.LONG:
            return entry_price + reward
        else:  # SHORT
            return entry_price - reward

    def _get_current_indicators(self, symbol: str) -> Optional[ADXIndicators]:
        """
        Get current ADX indicators for a symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            Latest ADXIndicators or None if not available
        """
        if self.data_service:
            # Try to get from WebSocket service
            indicators = self.data_service.ws_service.get_latest_indicators(symbol)
            if indicators:
                return indicators

            # Fallback: Try from analysis service history
            logger.info(f"No WebSocket indicators for {symbol}, checking history")

        # Fallback to analysis service history
        history = self.analysis_service.get_indicator_history(symbol, 1)
        if history:
            return history[0]

        logger.info(f"No indicators available for {symbol}")
        return None

    async def _get_live_quote(self, symbol: str) -> Optional[LiveQuote]:
        """
        Get live quote for a symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            Latest LiveQuote or None if not available
        """
        if not self.data_service:
            logger.warning(f"No data service available for {symbol}")
            return None

        try:
            # Get quote from hybrid data service (WebSocket or REST fallback)
            quote = await self.data_service.get_quote(symbol)

            if quote:
                return quote
            else:
                logger.debug(f"No quote available for {symbol}")
                return None

        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return None

    def _update_metrics(self) -> None:
        """Update strategy performance metrics."""
        if self.completed_trades:
            self.metrics.calculate_from_trades(self.completed_trades)
            self.metrics.end_date = datetime.now()

    def _log_strategy_status(self) -> None:
        """Log current strategy status."""
        time_remaining = self.timing_service.time_until_square_off()
        time_str = self.timing_service.format_time_remaining(time_remaining) if time_remaining else "Past square-off"

        self.analysis_service.print_df_tail()

    def get_status_summary(self) -> Dict:
        """Get comprehensive strategy status."""
        return {
            'current_time': self.timing_service.get_current_time_ist(),
            'is_running': self.is_running,
            'positions_count': len(self.positions),
            'max_positions': self.strategy_config.max_positions,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'completed_trades': len(self.completed_trades),
            'pending_signals': len(self.pending_signals),
            'market_status': self.timing_service.get_market_status(),
            'positions': {symbol: {
                'signal_type': pos.signal_type.value,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'unrealized_pnl': pos.unrealized_pnl,
                'quantity': pos.quantity
            } for symbol, pos in self.positions.items()}
        }

    def _print_end_of_day_summary(self) -> None:
        """
        Print and log the end-of-day paper-trading summary.

        Reads today's paper-trade log (the on-disk source of truth) so the
        same summary is available both here and via `python main.py summary`.
        """
        try:
            from services.paper_trade_summary import print_summary, log_summary
            from rich.console import Console

            date_str = datetime.now().strftime("%Y%m%d")
            # Plain-text version goes to the log file (cron-friendly)
            log_summary(date_str)
            # Rich version goes to the console
            print_summary(date_str, console=Console())
            # Append the full ADX/DI + signal dataframe for all symbols
            self._print_full_dataframe(date_str)
        except Exception as e:
            logger.error(f"Failed to generate end-of-day paper summary: {e}")

    def _print_full_dataframe(self, date_str: str) -> None:
        """Concatenate and emit the entire price-history dataframe (all symbols)
        with ADX/DI values and crossover signals, alongside the trade summary.

        The combined frame is printed to the console, written to the log file and
        persisted to ``logs/adx_signals_<date>.csv`` for later inspection.
        """
        try:
            full_df = self.analysis_service.build_full_dataframe()
        except Exception as e:
            logger.error(f"Failed to build full ADX/signal dataframe: {e}")
            return

        if full_df.empty:
            logger.info("No ADX/signal dataframe available to append to summary.")
            return

        # Persist to CSV for downstream analysis.
        try:
            os.makedirs("logs", exist_ok=True)
            csv_path = f"logs/adx_signals_{date_str}.csv"
            full_df.to_csv(csv_path, index=False)
            logger.info(f"Saved full ADX/signal dataframe to {csv_path}")
        except Exception as e:
            logger.warning(f"Failed to save ADX/signal dataframe CSV: {e}")

        # Emit to log file (plain text) and console.
        logger.info(
            f"===== Full ADX/DI + Signal DataFrame ({len(full_df)} rows) =====\n"
            f"{full_df.to_string(index=False)}"
        )
        try:
            Console().print(full_df.to_string(index=False))
        except Exception:
            pass

    def stop_strategy(self) -> None:
        """Stop the strategy gracefully."""
        logger.info("Stopping strategy...")
        self.is_running = False