"""
Technical Analysis Service for ADX/DI calculations and signal validation.

This service handles all indicator calculations, crossover detection, and signal
quality validation for the ADX DI Crossover strategy.
"""

import json
import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List

from models.trading_models import (
    ADXIndicators, ADXSignal, LiveQuote, SignalType, SymbolCategory, ExitReason
)
from config.settings import ADXStrategyConfig

logger = logging.getLogger(__name__)


class ADXTechnicalAnalysisService:
    """
    Service for calculating ADX/DI indicators and validating trading signals.

    Implements Wilder's smoothing method for accurate ADX calculation and provides
    comprehensive signal validation including volume, trend strength, and quality checks.
    """

    def __init__(self, config: ADXStrategyConfig):
        """
        Initialize the analysis service.

        Args:
            config: Strategy configuration object
        """
        self.config = config
        self.indicator_history: Dict[str, List[ADXIndicators]] = {}
        self.volume_history: Dict[str, List[int]] = {}
        self.price_history: Dict[str, pd.DataFrame] = {}
        # Tracks the bucket start time of the candle currently being built per
        # symbol, so we know when to update the in-progress candle vs. start a new one.
        self._current_candle_bucket: Dict[str, datetime] = {}
        self._history_cache_path = os.path.join("cache", "indicator_history.json")

        self._load_indicator_history()
        logger.info(f"Initialized ADXTechnicalAnalysisService with DI period: {config.di_period}")

    def calculate_di_indicators(
            self,
            df: pd.DataFrame,
            period: int = 14
    ) -> pd.DataFrame:
        """
        Calculate +DI, -DI, and ADX indicators using Wilder's smoothing method.

        Args:
            df: DataFrame with columns: high, low, close
            period: Period for DI calculation (default 14)

        Returns:
            DataFrame with additional columns: +DI, -DI, ADX, TR, DM+, DM-
        """
        df = df.copy()

        # Ensure numeric dtypes — an empty DataFrame created with only `columns=`
        # carries object dtype, which breaks the masked DM assignments below on
        # newer pandas versions.
        for col in ('high', 'low', 'close'):
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Calculate True Range (TR)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['TR'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)

        # Calculate Directional Movements (DM+ and DM-)
        df['high_diff'] = df['high'] - df['high'].shift(1)
        df['low_diff'] = df['low'].shift(1) - df['low']

        # DM+ and DM- rules
        df['DM+'] = 0.0
        df['DM-'] = 0.0

        # DM+ when high_diff > low_diff and high_diff > 0
        mask_dm_plus = (df['high_diff'] > df['low_diff']) & (df['high_diff'] > 0)
        df.loc[mask_dm_plus, 'DM+'] = df.loc[mask_dm_plus, 'high_diff']

        # DM- when low_diff > high_diff and low_diff > 0
        mask_dm_minus = (df['low_diff'] > df['high_diff']) & (df['low_diff'] > 0)
        df.loc[mask_dm_minus, 'DM-'] = df.loc[mask_dm_minus, 'low_diff']

        # Apply Wilder's smoothing (EMA with alpha = 1/period)
        alpha = 1.0 / period

        # Smoothed TR, DM+, DM-
        df['TR_smoothed'] = df['TR'].ewm(alpha=alpha, adjust=False).mean()
        df['DM+_smoothed'] = df['DM+'].ewm(alpha=alpha, adjust=False).mean()
        df['DM-_smoothed'] = df['DM-'].ewm(alpha=alpha, adjust=False).mean()

        # Calculate +DI and -DI
        df['+DI'] = 100 * (df['DM+_smoothed'] / df['TR_smoothed'])
        df['-DI'] = 100 * (df['DM-_smoothed'] / df['TR_smoothed'])

        # Calculate DX and ADX
        df['DI_diff'] = abs(df['+DI'] - df['-DI'])
        df['DI_sum'] = df['+DI'] + df['-DI']
        df['DX'] = 100 * (df['DI_diff'] / df['DI_sum'])

        # ADX is smoothed DX
        df['ADX'] = df['DX'].ewm(alpha=alpha, adjust=False).mean()

        # Handle NaN values
        df['+DI'].fillna(0, inplace=True)
        df['-DI'].fillna(0, inplace=True)
        df['ADX'].fillna(0, inplace=True)

        logger.debug(f"Calculated DI indicators for {len(df)} data points")

        return df

    def calculate_single_indicator(
            self,
            symbol: str,
            high: float,
            low: float,
            close: float,
            timestamp: datetime
    ) -> Optional[ADXIndicators]:
        """
        Calculate ADX indicators for a single price update.

        Args:
            symbol: Symbol identifier
            high: Current high price
            low: Current low price
            close: Current close price
            timestamp: Price timestamp

        Returns:
            ADXIndicators object or None if insufficient data
        """
        # Store price data
        if symbol not in self.price_history:
            self.price_history[symbol] = pd.DataFrame(
                columns=['timestamp', 'high', 'low', 'close']
            )

        # Append new price data
        new_row = pd.DataFrame([{
            'timestamp': timestamp,
            'high': high,
            'low': low,
            'close': close
        }])

        self.price_history[symbol] = pd.concat(
            [self.price_history[symbol], new_row],
            ignore_index=True
        )

        # Keep only necessary history (period * 3 for stable calculation)
        max_rows = self.config.di_period * 3
        if len(self.price_history[symbol]) > max_rows:
            self.price_history[symbol] = self.price_history[symbol].iloc[-max_rows:]

        # Need at least period + 1 data points
        if len(self.price_history[symbol]) < self.config.di_period + 1:
            logger.debug(f"Insufficient data for {symbol}: {len(self.price_history[symbol])} points")
            return None

        # Calculate indicators
        df_with_indicators = self.calculate_di_indicators(
            self.price_history[symbol],
            self.config.di_period
        )

        # Get latest values
        latest = df_with_indicators.iloc[-1]

        indicator = ADXIndicators(
            symbol=symbol,
            di_plus=float(latest['+DI']),
            di_minus=float(latest['-DI']),
            adx=float(latest['ADX']),
            true_range=float(latest['TR']),
            dm_plus=float(latest['DM+']),
            dm_minus=float(latest['DM-']),
            timestamp=timestamp,
            period=self.config.di_period
        )

        # Store in history
        if symbol not in self.indicator_history:
            self.indicator_history[symbol] = []

        self.indicator_history[symbol].append(indicator)

        # Keep limited history
        if len(self.indicator_history[symbol]) > 100:
            self.indicator_history[symbol] = self.indicator_history[symbol][-100:]

        self._save_indicator_history()
        return indicator

    def update_with_tick(
            self,
            symbol: str,
            ltp: float,
            timestamp: datetime
    ) -> Optional[ADXIndicators]:
        """
        Aggregate a single LTP tick into a time-based OHLC candle and recompute
        indicators on the resulting candle series.

        Incoming quotes only carry the day's static high/low, which makes
        directional movement (and therefore +DI/-DI/ADX) always zero. Building
        candles from the moving LTP gives the DI/ADX calculation real bar-to-bar
        range to work with.

        Args:
            symbol: Symbol identifier
            ltp: Last traded price for this tick
            timestamp: Tick timestamp

        Returns:
            ADXIndicators object or None if insufficient data
        """
        interval = max(int(self.config.candle_interval_seconds), 1)

        # Floor the timestamp to the start of its candle bucket.
        epoch = int(timestamp.timestamp())
        bucket = datetime.fromtimestamp(epoch - (epoch % interval))

        if symbol not in self.price_history:
            self.price_history[symbol] = pd.DataFrame(
                columns=['timestamp', 'high', 'low', 'close']
            )

        df = self.price_history[symbol]
        current_bucket = self._current_candle_bucket.get(symbol)

        if current_bucket is None or bucket > current_bucket or df.empty:
            # Start a new candle (open=high=low=close=ltp).
            new_row = pd.DataFrame([{
                'timestamp': bucket,
                'high': ltp,
                'low': ltp,
                'close': ltp
            }])
            self.price_history[symbol] = pd.concat([df, new_row], ignore_index=True)
            self._current_candle_bucket[symbol] = bucket
        else:
            # Update the in-progress candle for the current bucket.
            idx = df.index[-1]
            df.at[idx, 'high'] = max(df.at[idx, 'high'], ltp)
            df.at[idx, 'low'] = min(df.at[idx, 'low'], ltp)
            df.at[idx, 'close'] = ltp

        # Keep only necessary history (period * 3 for stable calculation).
        max_rows = self.config.di_period * 3
        if len(self.price_history[symbol]) > max_rows:
            self.price_history[symbol] = self.price_history[symbol].iloc[-max_rows:]

        # Need at least period + 1 candles for a stable calculation.
        if len(self.price_history[symbol]) < self.config.di_period + 1:
            logger.debug(
                f"Insufficient candles for {symbol}: "
                f"{len(self.price_history[symbol])} (need {self.config.di_period + 1})"
            )
            return None

        return self._compute_and_store_indicators(symbol, timestamp)

    def _compute_and_store_indicators(
            self,
            symbol: str,
            timestamp: datetime
    ) -> Optional[ADXIndicators]:
        """Compute DI/ADX from the symbol's candle series and persist the latest value."""
        df_with_indicators = self.calculate_di_indicators(
            self.price_history[symbol],
            self.config.di_period
        )

        latest = df_with_indicators.iloc[-1]

        indicator = ADXIndicators(
            symbol=symbol,
            di_plus=float(latest['+DI']),
            di_minus=float(latest['-DI']),
            adx=float(latest['ADX']),
            true_range=float(latest['TR']),
            dm_plus=float(latest['DM+']),
            dm_minus=float(latest['DM-']),
            timestamp=timestamp,
            period=self.config.di_period
        )

        if symbol not in self.indicator_history:
            self.indicator_history[symbol] = []

        self.indicator_history[symbol].append(indicator)

        if len(self.indicator_history[symbol]) > 100:
            self.indicator_history[symbol] = self.indicator_history[symbol][-100:]

        self._save_indicator_history()
        return indicator

    def detect_di_crossover(
            self,
            symbol: str,
            current_indicators: ADXIndicators,
            previous_indicators: Optional[ADXIndicators] = None
    ) -> Optional[SignalType]:
        """
        Detect DI crossover signals.

        Args:
            symbol: Symbol identifier
            current_indicators: Current ADX indicators
            previous_indicators: Previous ADX indicators (optional)

        Returns:
            SignalType (LONG or SHORT) or None if no crossover
        """
        if previous_indicators is None:
            # Try to get from history
            if symbol in self.indicator_history and len(self.indicator_history[symbol]) >= 2:
                previous_indicators = self.indicator_history[symbol][-2]
            else:
                self.print_df_tail(symbol)
                return None

        # Check for +DI crossing above -DI (LONG signal)
        if (previous_indicators.di_plus <= previous_indicators.di_minus and
                current_indicators.di_plus > current_indicators.di_minus):
            logger.info(f"LONG crossover detected for {symbol}: "
                        f"+DI {current_indicators.di_plus:.2f} > -DI {current_indicators.di_minus:.2f}")
            return SignalType.LONG

        # Check for -DI crossing above +DI (SHORT signal)
        if (previous_indicators.di_minus <= previous_indicators.di_plus and
                current_indicators.di_minus > current_indicators.di_plus):
            logger.info(f"SHORT crossover detected for {symbol}: "
                        f"-DI {current_indicators.di_minus:.2f} > +DI {current_indicators.di_plus:.2f}")
            return SignalType.SHORT

        return None

    def validate_adx_signal(
            self,
            symbol: str,
            signal: ADXSignal,
            live_quote: LiveQuote
    ) -> Tuple[bool, float, Dict[str, float]]:
        """
        Validate signal quality with comprehensive checks.

        Args:
            symbol: Symbol identifier
            signal: ADXSignal to validate
            live_quote: Current market quote

        Returns:
            Tuple of (is_valid, confidence_score, quality_scores_dict)
        """
        quality_scores = {}

        # 1. Volume validation
        if self.config.enable_volume_filter:
            volume_ratio = self.calculate_volume_ratio(symbol, live_quote.volume)
            quality_scores['volume_ratio'] = volume_ratio

            if volume_ratio < self.config.min_volume_ratio:
                logger.debug(f"Signal rejected for {symbol}: Low volume ratio {volume_ratio:.2f}")
                return False, 0.0, quality_scores

        # 2. DI separation check
        di_separation = signal.di_separation
        quality_scores['di_separation'] = di_separation

        if di_separation < self.config.min_di_separation:
            logger.debug(f"Signal rejected for {symbol}: Insufficient DI separation {di_separation:.2f}")
            return False, 0.0, quality_scores

        # 3. ADX strength check
        quality_scores['adx_strength'] = signal.adx

        if signal.adx < self.config.min_adx_strength:
            logger.debug(f"Signal rejected for {symbol}: Weak ADX {signal.adx:.2f}")
            return False, 0.0, quality_scores

        # 4. Trend consistency check
        trend_score = self._calculate_trend_consistency(signal)
        quality_scores['trend_consistency'] = trend_score

        # 5. Calculate overall confidence
        confidence = self._calculate_confidence_score(quality_scores)

        is_valid = confidence >= self.config.min_confidence

        if is_valid:
            logger.info(f"Signal validated for {symbol}: Confidence {confidence:.2%}")
        else:
            logger.debug(f"Signal rejected for {symbol}: Low confidence {confidence:.2%}")

        return is_valid, confidence, quality_scores

    def calculate_volume_ratio(self, symbol: str, current_volume: int) -> float:
        """
        Calculate current volume ratio vs historical average.

        Args:
            symbol: Symbol identifier
            current_volume: Current volume

        Returns:
            float: Volume ratio (current / average)
        """
        if symbol not in self.volume_history:
            self.volume_history[symbol] = []

        # Store volume
        self.volume_history[symbol].append(current_volume)

        # Keep last 20 days
        if len(self.volume_history[symbol]) > 20:
            self.volume_history[symbol] = self.volume_history[symbol][-20:]

        # Need at least 5 data points for meaningful average
        if len(self.volume_history[symbol]) < 5:
            return 1.0  # Neutral ratio if insufficient data

        avg_volume = np.mean(self.volume_history[symbol])
        ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        return ratio

    def calculate_trailing_stop(
            self,
            signal_type: SignalType,
            entry_price: float,
            current_price: float,
            highest_price: float,
            lowest_price: float,
            trailing_pct: float
    ) -> float:
        """
        Calculate dynamic trailing stop loss.

        Args:
            signal_type: LONG or SHORT position
            entry_price: Original entry price
            current_price: Current market price
            highest_price: Highest price since entry
            lowest_price: Lowest price since entry
            trailing_pct: Trailing percentage (5.0 = 5%)

        Returns:
            float: New trailing stop price
        """
        trailing_multiplier = trailing_pct / 100.0

        if signal_type == SignalType.LONG:
            # For LONG: trail below the highest price
            initial_stop = entry_price * (1 - trailing_multiplier)
            trailing_stop = highest_price * (1 - trailing_multiplier)

            # Use the higher of initial or trailing stop
            return max(initial_stop, trailing_stop)

        else:  # SHORT
            # For SHORT: trail above the lowest price
            initial_stop = entry_price * (1 + trailing_multiplier)
            trailing_stop = lowest_price * (1 + trailing_multiplier)

            # Use the lower of initial or trailing stop
            return min(initial_stop, trailing_stop)

    def _calculate_trend_consistency(self, signal: ADXSignal) -> float:
        """
        Calculate trend consistency score based on DI relationship.

        Args:
            signal: ADXSignal object

        Returns:
            float: Trend consistency score (0-1)
        """
        # Higher score when DI separation is larger
        di_score = min(signal.di_separation / 20.0, 1.0)

        # Higher score when ADX is stronger
        adx_score = min(signal.adx / 50.0, 1.0)

        # Combined score
        trend_score = (di_score * 0.6) + (adx_score * 0.4)

        return trend_score

    def _calculate_confidence_score(self, quality_scores: Dict[str, float]) -> float:
        """
        Calculate overall confidence score from quality metrics.

        Args:
            quality_scores: Dictionary of quality metrics

        Returns:
            float: Confidence score (0-1)
        """
        weights = {
            'volume_ratio': 0.25,
            'di_separation': 0.30,
            'adx_strength': 0.25,
            'trend_consistency': 0.20
        }

        confidence = 0.0

        # Volume ratio contribution
        if 'volume_ratio' in quality_scores:
            vol_ratio = quality_scores['volume_ratio']
            vol_score = min(vol_ratio / 2.0, 1.0)  # Normalize to 0-1
            confidence += vol_score * weights['volume_ratio']

        # DI separation contribution
        if 'di_separation' in quality_scores:
            di_sep = quality_scores['di_separation']
            di_score = min(di_sep / 10.0, 1.0)  # Normalize to 0-1
            confidence += di_score * weights['di_separation']

        # ADX strength contribution
        if 'adx_strength' in quality_scores:
            adx = quality_scores['adx_strength']
            adx_score = min(adx / 50.0, 1.0)  # Normalize to 0-1
            confidence += adx_score * weights['adx_strength']

        # Trend consistency contribution
        if 'trend_consistency' in quality_scores:
            trend_score = quality_scores['trend_consistency']
            confidence += trend_score * weights['trend_consistency']

        return confidence

    def should_exit_on_opposite_crossover(
            self,
            position_signal_type: SignalType,
            current_indicators: ADXIndicators,
            previous_indicators: ADXIndicators
    ) -> bool:
        """
        Check if opposite DI crossover occurred (exit signal).

        Args:
            position_signal_type: Current position type (LONG or SHORT)
            current_indicators: Current ADX indicators
            previous_indicators: Previous ADX indicators

        Returns:
            bool: True if should exit
        """
        # For LONG positions, exit on -DI crossing above +DI
        if position_signal_type == SignalType.LONG:
            if (previous_indicators.di_minus <= previous_indicators.di_plus and
                    current_indicators.di_minus > current_indicators.di_plus):
                logger.info(f"Exit signal for LONG: -DI crossed above +DI")
                return True

        # For SHORT positions, exit on +DI crossing above -DI
        if position_signal_type == SignalType.SHORT:
            if (previous_indicators.di_plus <= previous_indicators.di_minus and
                    current_indicators.di_plus > current_indicators.di_minus):
                logger.info(f"Exit signal for SHORT: +DI crossed above -DI")
                return True

        return False

    def get_indicator_history(self, symbol: str, bars: int = 10) -> List[ADXIndicators]:
        """
        Get recent indicator history for a symbol.

        Args:
            symbol: Symbol identifier
            bars: Number of historical bars to return

        Returns:
            List of ADXIndicators (most recent first)
        """
        if symbol not in self.indicator_history:
            return []

        history = self.indicator_history[symbol][-bars:]
        return list(reversed(history))  # Most recent first

    def clear_history(self, symbol: Optional[str] = None) -> None:
        """
        Clear indicator and volume history.

        Args:
            symbol: Specific symbol to clear, or None for all
        """
        if symbol:
            self.indicator_history.pop(symbol, None)
            self.volume_history.pop(symbol, None)
            self.price_history.pop(symbol, None)
            logger.info(f"Cleared history for {symbol}")
        else:
            self.indicator_history.clear()
            self.volume_history.clear()
            self.price_history.clear()
            logger.info("Cleared all historical data")
        self._save_indicator_history()

    def _save_indicator_history(self) -> None:
        """Persist indicator_history to disk so it survives restarts."""
        try:
            os.makedirs(os.path.dirname(self._history_cache_path), exist_ok=True)
            data: Dict[str, list] = {}
            for symbol, entries in self.indicator_history.items():
                data[symbol] = [
                    {
                        "symbol": e.symbol,
                        "di_plus": e.di_plus,
                        "di_minus": e.di_minus,
                        "adx": e.adx,
                        "true_range": e.true_range,
                        "dm_plus": e.dm_plus,
                        "dm_minus": e.dm_minus,
                        "timestamp": e.timestamp.isoformat(),
                        "period": e.period,
                    }
                    for e in entries
                ]
            with open(self._history_cache_path, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save indicator history: {e}")

    def print_df_tail(self, symbol: str = None, n: int = 5) -> None:
        """Print the last n rows of price_history for one or all symbols.

        Only prints when new data has arrived since the previous call for that
        symbol. If the latest timestamp is unchanged (feed frozen / no new
        ticks), a single staleness warning is emitted instead of re-printing
        the same dataframe on every scan iteration.
        """
        targets = {symbol: self.price_history[symbol]} if symbol and symbol in self.price_history else dict(self.price_history)
        if not targets:
            logger.info("No price history available yet.")
            return

        # Lazily initialise the per-symbol marker that tracks the last printed tick.
        if not hasattr(self, "_last_printed_ts"):
            self._last_printed_ts: Dict[str, object] = {}

        for sym, df in targets.items():
            if df.empty:
                continue

            latest_ts = df['timestamp'].iloc[-1]

            if self._last_printed_ts.get(sym) == latest_ts:
                # No new data since last print — surface the freeze once, not every scan.
                if not self._last_printed_ts.get(f"{sym}__stale_warned"):
                    logger.warning(
                        f"[{sym}] No new price data since {latest_ts} "
                        f"(feed may be stale or disconnected)."
                    )
                    self._last_printed_ts[f"{sym}__stale_warned"] = True
                continue

            self._last_printed_ts[sym] = latest_ts
            self._last_printed_ts[f"{sym}__stale_warned"] = False

            display_df = self._build_display_df(df)
            logger.info(
                f"[{sym}] last {min(n, len(display_df))} rows:\n"
                f"{display_df.tail(n).to_string()}"
            )

    def _build_display_df(self, df: 'pd.DataFrame') -> 'pd.DataFrame':
        """Return a reference dataframe with price + ADX/DI values and crossover signals.

        Augments the raw OHLC frame (timestamp/high/low/close) with the computed
        +DI, -DI and ADX columns, plus a 'signal' column flagging DI crossovers
        (LONG when +DI crosses above -DI, SHORT when -DI crosses above +DI).
        This is purely informational for log inspection; it does not affect
        signal generation.
        """
        base_cols = ['timestamp', 'high', 'low', 'close']

        # Not enough data to compute indicators — return raw prices as-is.
        if len(df) < self.config.di_period + 1:
            return df[[c for c in base_cols if c in df.columns]].copy()

        enriched = self.calculate_di_indicators(df, self.config.di_period)

        # Round indicator columns for readable log output.
        for col in ['+DI', '-DI', 'ADX']:
            if col in enriched.columns:
                enriched[col] = enriched[col].round(2)

        # Derive a crossover signal column by comparing each row to the previous.
        prev_plus = enriched['+DI'].shift(1)
        prev_minus = enriched['-DI'].shift(1)
        long_cross = (prev_plus <= prev_minus) & (enriched['+DI'] > enriched['-DI'])
        short_cross = (prev_minus <= prev_plus) & (enriched['-DI'] > enriched['+DI'])

        enriched['signal'] = ''
        enriched.loc[long_cross, 'signal'] = 'LONG'
        enriched.loc[short_cross, 'signal'] = 'SHORT'

        display_cols = base_cols + ['+DI', '-DI', 'ADX', 'signal']
        return enriched[[c for c in display_cols if c in enriched.columns]].copy()

    def log_dataframe_snapshot(self) -> None:
        """Log the latest computed ADX/DI values for all symbols with available price history."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"===== DataFrame Snapshot @ {now} =====")

        if not self.price_history:
            logger.info("No price history available yet.")
            logger.info("=" * 50)
            return

        for symbol, df in dict(self.price_history).items():
            if df.empty or len(df) < self.config.di_period + 1:
                logger.info(f"[{symbol}] Insufficient data ({len(df)} rows, need {self.config.di_period + 1})")
                continue

            try:
                df_calc = self.calculate_di_indicators(df, self.config.di_period)
                latest = df_calc.iloc[-1]
                logger.info(
                    f"[{symbol}] rows={len(df)} | "
                    f"+DI={latest['+DI']:.4f} | -DI={latest['-DI']:.4f} | "
                    f"ADX={latest['ADX']:.4f} | TR={latest['TR']:.4f} | "
                    f"DM+={latest['DM+']:.4f} | DM-={latest['DM-']:.4f} | "
                    f"last_close={latest['close']:.4f}"
                )
            except Exception as e:
                logger.error(f"[{symbol}] Snapshot calculation error: {e}")

        logger.info("=" * 50)

    def _load_indicator_history(self) -> None:
        """Load persisted indicator_history from disk on startup."""
        if not os.path.exists(self._history_cache_path):
            return
        try:
            with open(self._history_cache_path, "r") as f:
                data = json.load(f)
            for symbol, entries in data.items():
                self.indicator_history[symbol] = [
                    ADXIndicators(
                        symbol=e["symbol"],
                        di_plus=e["di_plus"],
                        di_minus=e["di_minus"],
                        adx=e["adx"],
                        true_range=e["true_range"],
                        dm_plus=e["dm_plus"],
                        dm_minus=e["dm_minus"],
                        timestamp=datetime.fromisoformat(e["timestamp"]),
                        period=e["period"],
                    )
                    for e in entries
                ]
            total = sum(len(v) for v in self.indicator_history.values())
            logger.info(f"Loaded indicator history: {len(self.indicator_history)} symbols, {total} entries")
        except Exception as e:
            logger.warning(f"Failed to load indicator history: {e}")