"""
Trading data models for FyersADX Strategy.

This module contains all data classes used throughout the trading system,
including quotes, indicators, signals, positions, and performance metrics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List


class SignalType(Enum):
    """Trading signal types."""
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    HOLD = "HOLD"


class SymbolCategory(Enum):
    """Symbol categories for classification."""
    LARGE_CAP = "LARGE_CAP"
    MID_CAP = "MID_CAP"
    SMALL_CAP = "SMALL_CAP"
    UNKNOWN = "UNKNOWN"


class ExitReason(Enum):
    """Reasons for position exit."""
    SIGNAL_EXIT = "SIGNAL_EXIT"  # Opposite DI crossover
    TRAILING_STOP = "TRAILING_STOP"  # Trailing stop hit
    TIME_EXIT_3_20PM = "TIME_EXIT_3:20PM"  # Mandatory square-off
    STOP_LOSS = "STOP_LOSS"  # Stop loss hit
    TARGET = "TARGET"  # Target reached
    MANUAL = "MANUAL"  # Manual exit


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class LiveQuote:
    """
    Real-time market quote data.

    Attributes:
        symbol: Symbol identifier (NSE:RELIANCE-EQ format)
        timestamp: Quote timestamp
        ltp: Last traded price
        open: Opening price
        high: Day high
        low: Day low
        close: Previous close
        volume: Current volume
        bid: Best bid price
        ask: Best ask price
        bid_size: Bid quantity
        ask_size: Ask quantity
    """
    symbol: str
    timestamp: datetime
    ltp: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    bid: float = 0.0
    ask: float = 0.0
    bid_size: int = 0
    ask_size: int = 0

    def __post_init__(self):
        """Validate quote data."""
        if self.ltp <= 0:
            raise ValueError(f"Invalid LTP for {self.symbol}: {self.ltp}")


@dataclass
class ADXIndicators:
    """
    ADX and Directional Indicator values.

    Attributes:
        symbol: Symbol identifier
        di_plus: +DI (Positive Directional Indicator)
        di_minus: -DI (Negative Directional Indicator)
        adx: ADX (Average Directional Index)
        true_range: True Range value
        dm_plus: +DM (Positive Directional Movement)
        dm_minus: -DM (Negative Directional Movement)
        timestamp: Calculation timestamp
        period: Period used for calculation
    """
    symbol: str
    di_plus: float
    di_minus: float
    adx: float
    true_range: float
    dm_plus: float
    dm_minus: float
    timestamp: datetime
    period: int = 14

    @property
    def di_separation(self) -> float:
        """Calculate separation between +DI and -DI."""
        return abs(self.di_plus - self.di_minus)

    @property
    def is_bullish(self) -> bool:
        """Check if +DI is above -DI."""
        return self.di_plus > self.di_minus

    @property
    def is_bearish(self) -> bool:
        """Check if -DI is above +DI."""
        return self.di_minus > self.di_plus

    def __repr__(self) -> str:
        return (f"ADXIndicators({self.symbol}: +DI={self.di_plus:.2f}, "
                f"-DI={self.di_minus:.2f}, ADX={self.adx:.2f})")


@dataclass
class ADXSignal:
    """
    ADX DI Crossover trading signal.

    Attributes:
        symbol: Symbol identifier
        category: Symbol category (LARGE_CAP, MID_CAP, etc.)
        signal_type: LONG or SHORT signal
        di_plus: +DI value at signal
        di_minus: -DI value at signal
        adx: ADX value at signal
        di_separation: Absolute difference between +DI and -DI
        entry_price: Suggested entry price
        stop_loss: Initial stop loss price
        target_price: Target price
        confidence: Signal confidence score (0-1)
        volume_ratio: Current volume / average volume ratio
        signal_volume: Volume at signal generation
        timestamp: Signal generation time
        square_off_time: Mandatory square-off time (3:20 PM)
        risk_amount: Risk amount in currency
        reward_amount: Reward amount in currency
        risk_reward_ratio: Reward/Risk ratio
        quality_scores: Dict of quality metrics
    """
    symbol: str
    category: SymbolCategory
    signal_type: SignalType

    # DI values at signal
    di_plus: float
    di_minus: float
    adx: float
    di_separation: float

    # Entry parameters
    entry_price: float
    stop_loss: float
    target_price: float

    # Signal quality
    confidence: float
    volume_ratio: float
    signal_volume: int

    # Timing
    timestamp: datetime
    square_off_time: datetime

    # Risk metrics
    risk_amount: float
    reward_amount: float
    risk_reward_ratio: float

    # Additional quality metrics
    quality_scores: Dict[str, float] = field(default_factory=dict)

    def is_valid(self, min_confidence: float = 0.6) -> bool:
        """Check if signal meets minimum confidence threshold."""
        return self.confidence >= min_confidence

    def __repr__(self) -> str:
        return (f"ADXSignal({self.symbol} {self.signal_type.value}: "
                f"Entry={self.entry_price:.2f}, Confidence={self.confidence:.2%})")


@dataclass
class Position:
    """
    Active trading position.

    Attributes:
        symbol: Symbol identifier
        category: Symbol category
        signal_type: LONG or SHORT
        entry_price: Entry price
        quantity: Number of shares
        stop_loss: Current stop loss price
        target_price: Target price
        highest_price: Highest price since entry (for trailing stops)
        lowest_price: Lowest price since entry (for trailing stops)
        current_stop_loss: Current trailing stop loss
        entry_di_plus: +DI at entry
        entry_di_minus: -DI at entry
        entry_adx: ADX at entry
        entry_time: Entry timestamp
        must_square_off_at: Mandatory square-off time (3:20 PM)
        unrealized_pnl: Current unrealized P&L
        realized_pnl: Realized P&L if closed
        current_price: Latest price
        exit_time: Exit timestamp (if closed)
        exit_reason: Reason for exit
        is_closed: Position closed flag
    """
    symbol: str
    category: SymbolCategory
    signal_type: SignalType

    entry_price: float
    quantity: int
    stop_loss: float
    target_price: float

    # Tracking for trailing stops
    highest_price: float = 0.0
    lowest_price: float = 0.0
    current_stop_loss: float = 0.0

    # ADX specific
    entry_di_plus: float = 0.0
    entry_di_minus: float = 0.0
    entry_adx: float = 0.0

    # Timing
    entry_time: datetime = field(default_factory=datetime.now)
    must_square_off_at: datetime = field(default_factory=datetime.now)

    # Performance tracking
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    current_price: float = 0.0

    # Exit tracking
    exit_time: Optional[datetime] = None
    exit_reason: Optional[ExitReason] = None
    is_closed: bool = False

    def __post_init__(self):
        """Initialize tracking values."""
        self.highest_price = self.entry_price
        self.lowest_price = self.entry_price
        self.current_stop_loss = self.stop_loss
        self.current_price = self.entry_price

    def update_price(self, new_price: float) -> None:
        """
        Update position with new price.

        Args:
            new_price: Latest market price
        """
        self.current_price = new_price
        self.highest_price = max(self.highest_price, new_price)
        self.lowest_price = min(self.lowest_price, new_price)
        self.calculate_unrealized_pnl()

    def calculate_unrealized_pnl(self) -> float:
        """
        Calculate unrealized P&L.

        Returns:
            float: Unrealized P&L amount
        """
        if self.signal_type == SignalType.LONG:
            self.unrealized_pnl = (self.current_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - self.current_price) * self.quantity

        return self.unrealized_pnl

    def update_trailing_stop(self, new_stop: float) -> None:
        """
        Update trailing stop loss.

        Args:
            new_stop: New stop loss price
        """
        self.current_stop_loss = new_stop

    def close_position(self, exit_price: float, exit_reason: ExitReason,
                       exit_time: datetime) -> float:
        """
        Close the position.

        Args:
            exit_price: Exit price
            exit_reason: Reason for exit
            exit_time: Exit timestamp

        Returns:
            float: Realized P&L
        """
        self.current_price = exit_price
        self.is_closed = True
        self.exit_time = exit_time
        self.exit_reason = exit_reason

        if self.signal_type == SignalType.LONG:
            self.realized_pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.realized_pnl = (self.entry_price - exit_price) * self.quantity

        return self.realized_pnl

    def is_stop_loss_hit(self) -> bool:
        """Check if stop loss has been hit."""
        if self.signal_type == SignalType.LONG:
            return self.current_price <= self.current_stop_loss
        else:  # SHORT
            return self.current_price >= self.current_stop_loss

    def is_target_hit(self) -> bool:
        """Check if target has been reached."""
        if self.signal_type == SignalType.LONG:
            return self.current_price >= self.target_price
        else:  # SHORT
            return self.current_price <= self.target_price

    def __repr__(self) -> str:
        status = "CLOSED" if self.is_closed else "OPEN"
        pnl = self.realized_pnl if self.is_closed else self.unrealized_pnl
        return (f"Position({self.symbol} {self.signal_type.value} {status}: "
                f"Entry={self.entry_price:.2f}, Current={self.current_price:.2f}, "
                f"P&L={pnl:.2f})")


@dataclass
class TradeResult:
    """
    Completed trade result for performance tracking.

    Attributes:
        symbol: Symbol traded
        signal_type: LONG or SHORT
        entry_time: Entry timestamp
        exit_time: Exit timestamp
        entry_price: Entry price
        exit_price: Exit price
        quantity: Quantity traded
        pnl: Profit/Loss
        pnl_pct: P&L percentage
        exit_reason: Reason for exit
        holding_time_minutes: Time held in minutes
        entry_indicators: ADX indicators at entry
        max_favorable_excursion: Best price reached
        max_adverse_excursion: Worst price reached
    """
    symbol: str
    signal_type: SignalType
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    exit_reason: ExitReason
    holding_time_minutes: float
    entry_indicators: ADXIndicators
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0

    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0

    def __repr__(self) -> str:
        result = "WIN" if self.is_winner else "LOSS"
        return (f"TradeResult({self.symbol} {result}: "
                f"P&L={self.pnl:.2f} ({self.pnl_pct:.2%}), "
                f"Exit={self.exit_reason.value})")


@dataclass
class StrategyMetrics:
    """
    Comprehensive strategy performance metrics.

    Attributes:
        start_date: Strategy start date
        end_date: Strategy end date (or current date)
        total_trades: Total number of trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate: Win rate percentage
        total_pnl: Total profit/loss
        total_return_pct: Total return percentage
        average_win: Average winning trade amount
        average_loss: Average losing trade amount
        largest_win: Largest winning trade
        largest_loss: Largest losing trade
        profit_factor: Total wins / Total losses
        max_drawdown: Maximum drawdown percentage
        max_drawdown_duration_days: Max drawdown duration
        sharpe_ratio: Sharpe ratio (if applicable)
        sortino_ratio: Sortino ratio (if applicable)
        exit_reason_breakdown: Count of trades by exit reason
        time_based_exits_count: Number of 3:20 PM exits
        time_based_exits_pct: Percentage of time-based exits
        avg_holding_time_minutes: Average holding time
        total_commission: Total commission paid
    """
    start_date: datetime
    end_date: datetime

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # P&L metrics
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None

    # Exit analysis
    exit_reason_breakdown: Dict[str, int] = field(default_factory=dict)
    time_based_exits_count: int = 0
    time_based_exits_pct: float = 0.0

    # Timing
    avg_holding_time_minutes: float = 0.0

    # Costs
    total_commission: float = 0.0

    def calculate_from_trades(self, trades: List[TradeResult]) -> None:
        """
        Calculate metrics from list of completed trades.

        Args:
            trades: List of TradeResult objects
        """
        if not trades:
            return

        self.total_trades = len(trades)
        self.winning_trades = sum(1 for t in trades if t.is_winner)
        self.losing_trades = self.total_trades - self.winning_trades
        self.win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0

        # P&L calculations
        self.total_pnl = sum(t.pnl for t in trades)
        wins = [t.pnl for t in trades if t.is_winner]
        losses = [t.pnl for t in trades if not t.is_winner]

        self.average_win = sum(wins) / len(wins) if wins else 0
        self.average_loss = sum(losses) / len(losses) if losses else 0
        self.largest_win = max(wins) if wins else 0
        self.largest_loss = min(losses) if losses else 0

        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        self.profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Exit reason breakdown
        for trade in trades:
            reason = trade.exit_reason.value
            self.exit_reason_breakdown[reason] = self.exit_reason_breakdown.get(reason, 0) + 1

        self.time_based_exits_count = self.exit_reason_breakdown.get(
            ExitReason.TIME_EXIT_3_20PM.value, 0
        )
        self.time_based_exits_pct = (
            self.time_based_exits_count / self.total_trades if self.total_trades > 0 else 0
        )

        # Timing
        self.avg_holding_time_minutes = (
            sum(t.holding_time_minutes for t in trades) / self.total_trades
            if self.total_trades > 0 else 0
        )

    def print_summary(self) -> None:
        """Print formatted metrics summary."""
        print("\n" + "=" * 70)
        print("STRATEGY PERFORMANCE METRICS")
        print("=" * 70)

        print(f"\n📊 Overall Performance:")
        print(f"  Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"  Total Trades: {self.total_trades}")
        print(f"  Win Rate: {self.win_rate:.2%}")
        print(f"  Total P&L: ₹{self.total_pnl:,.2f}")
        print(f"  Total Return: {self.total_return_pct:.2%}")

        print(f"\n💰 P&L Analysis:")
        print(f"  Winning Trades: {self.winning_trades}")
        print(f"  Losing Trades: {self.losing_trades}")
        print(f"  Average Win: ₹{self.average_win:,.2f}")
        print(f"  Average Loss: ₹{self.average_loss:,.2f}")
        print(f"  Largest Win: ₹{self.largest_win:,.2f}")
        print(f"  Largest Loss: ₹{self.largest_loss:,.2f}")
        print(f"  Profit Factor: {self.profit_factor:.2f}")

        print(f"\n⚠️ Risk Metrics:")
        print(f"  Max Drawdown: {self.max_drawdown:.2%}")
        if self.sharpe_ratio:
            print(f"  Sharpe Ratio: {self.sharpe_ratio:.2f}")

        print(f"\n🚪 Exit Analysis:")
        for reason, count in self.exit_reason_breakdown.items():
            pct = count / self.total_trades if self.total_trades > 0 else 0
            print(f"  {reason}: {count} ({pct:.1%})")

        print(f"\n⏱️ Timing:")
        print(f"  Avg Holding Time: {self.avg_holding_time_minutes:.1f} minutes")

        print("\n" + "=" * 70)