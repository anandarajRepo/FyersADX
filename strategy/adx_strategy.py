"""
Main ADX DI Crossover Strategy Implementation.

This module implements the complete trading strategy including signal generation,
position management, and the critical 3:20 PM square-off logic.
"""

import logging
import asyncio
from datetime import datetime, timedelta
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

        # ADD THIS: Initialize data service for real-time quotes and indicators
        from services.fyers_websocket_service import HybridADXDataService

        self.data_service = None
        if fyers_config and fyers_config.is_authenticated():
            self.data_service = HybridADXDataService(
                fyers_config=fyers_config,
                strategy_config=strategy_config,
                symbols=symbols
            )
            logger.info("Initialized HybridADXDataService for real-time data")
        else:
            logger.warning("No data service initialized - running in limited mode")
        """
        Initialize the ADX strategy.

        Args:
            strategy_config: Strategy configuration
            trading_config: Trading system configuration
            symbols: List of symbols to trade
        """
        self.strategy_config = strategy_config
        self.trading_config = trading_config
        self.symbols = symbols
        self.fyers_config = fyers_config

        # Initialize services
        self.analysis_service = ADXTechnicalAnalysisService(strategy_config)
        self.timing_service = MarketTimingService(
            square_off_time=strategy_config.square_off_time,
            signal_cutoff_time=strategy_config.signal_generation_end_time
        )

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

        # Flags
        self.is_running = False
        self.positions_squared_off_today = False

        logger.info(f"Initialized ADXStrategy with {len(symbols)} symbols")
        logger.info(f"Max positions: {strategy_config.max_positions}")
        logger.info(f"Square-off time: {strategy_config.square_off_time}")

    async def run_strategy_cycle(self) -> None:
        """Main strategy execution cycle."""
        self.is_running = True
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
        logger.info(f"Scanning {len(self.symbols)} symbols for crossovers")

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
        live_quote = self._get_live_quote(symbol)
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
        Execute a trading signal.

        Args:
            signal: ADXSignal to execute

        Returns:
            bool: True if execution successful
        """
        try:
            # Validate entry time
            is_valid, reason = self.timing_service.validate_entry_time()
            if not is_valid:
                logger.warning(f"Entry rejected for {signal.symbol}: {reason}")
                return False

            # Calculate position size
            quantity = self.strategy_config.calculate_position_size(
                signal.entry_price, signal.stop_loss
            )

            if quantity == 0:
                logger.warning(f"Position size calculation returned 0 for {signal.symbol}")
                return False

            # Create position
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

            # In paper trading mode, just track the position
            if self.trading_config.enable_paper_trading:
                self.positions[signal.symbol] = position
                logger.info(f"PAPER TRADE: Entered {signal.signal_type.value} position "
                            f"for {signal.symbol} at ₹{signal.entry_price:.2f}")
                return True

            # In live trading mode, place actual order
            if self.trading_config.enable_order_execution:
                from config.symbols import get_lot_size, is_option_symbol

                logger.info(f"LIVE TRADE: Placing order for {signal.symbol}")

                # Determine order type based on symbol
                order_type = 2  # MARKET order
                product_type = "INTRADAY"

                # For options, verify quantity is in lot multiples
                lot_size = get_lot_size(signal.symbol)
                if is_option_symbol(signal.symbol):
                    if quantity % lot_size != 0:
                        logger.warning(f"Adjusting quantity {quantity} to lot multiple")
                        quantity = (quantity // lot_size) * lot_size
                        if quantity == 0:
                            quantity = lot_size

                # Prepare order data
                order_data = {
                    "symbol": signal.symbol,
                    "qty": quantity,
                    "type": order_type,  # 2 = MARKET, 1 = LIMIT
                    "side": 1 if signal.signal_type == SignalType.LONG else -1,  # 1=BUY, -1=SELL
                    "productType": product_type,
                    "limitPrice": 0,  # 0 for market orders
                    "stopPrice": 0,
                    "validity": "DAY",
                    "disclosedQty": 0,
                    "offlineOrder": False
                }

                # Place order via Fyers API
                try:
                    # Initialize Fyers API if not already done
                    if not hasattr(self, 'fyers_api'):
                        from fyers_apiv3 import fyersModel
                        self.fyers_api = fyersModel.FyersModel(
                            client_id=self.fyers_config.client_id,
                            token=self.fyers_config.access_token,
                            log_path="logs/"
                        )

                    logger.info(f"Placing MARKET order: {order_data}")
                    response = self.fyers_api.place_order(data=order_data)

                    if response and response.get('s') == 'ok':
                        order_id = response.get('id')
                        logger.info(f"✓ Order placed successfully: ID={order_id}, Qty={quantity}")
                        position.order_id = order_id
                    else:
                        error_msg = response.get('message', 'Unknown error') if response else 'No response'
                        logger.error(f"✗ Order placement failed: {error_msg}")
                        return False

                except Exception as e:
                    logger.error(f"✗ Error placing order: {e}", exc_info=True)
                    return False

            self.positions[signal.symbol] = position
            logger.info(f"Entered {signal.signal_type.value} position for {signal.symbol}")

            return True

        except Exception as e:
            logger.error(f"Error executing signal for {signal.symbol}: {e}")
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
            logger.debug(f"No WebSocket indicators for {symbol}, checking history")

        # Fallback to analysis service history
        history = self.analysis_service.get_indicator_history(symbol, 1)
        if history:
            return history[0]

        logger.debug(f"No indicators available for {symbol}")
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

        logger.info(f"Strategy Status: "
                    f"Positions {len(self.positions)}/{self.strategy_config.max_positions} | "
                    f"Daily P&L ₹{self.daily_pnl:.2f} | "
                    f"Trades {self.daily_trades} | "
                    f"Square-off in {time_str}")

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

    def stop_strategy(self) -> None:
        """Stop the strategy gracefully."""
        logger.info("Stopping strategy...")
        self.is_running = False