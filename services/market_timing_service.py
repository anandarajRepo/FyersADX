"""
Market Timing Service for FyersADX Strategy.

Handles market hours, trading windows, and the critical 3:20 PM square-off logic.
All times are in IST (Indian Standard Time).
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Tuple, Dict
import pytz

logger = logging.getLogger(__name__)

# Indian Standard Time timezone
IST = pytz.timezone('Asia/Kolkata')


class MarketTimingService:
    """
    Service for managing market timing and trading windows.

    Critical Features:
    - Market hours validation (9:15 AM - 3:30 PM IST)
    - Signal generation window (9:15 AM - 2:00 PM IST)
    - Mandatory 3:20 PM square-off enforcement
    - Market holiday detection
    """

    # Market timings (IST)
    MARKET_OPEN = time(9, 15)  # 9:15 AM
    MARKET_CLOSE = time(15, 30)  # 3:30 PM
    SQUARE_OFF_TIME = time(15, 20)  # 3:20 PM - MANDATORY EXIT TIME
    SIGNAL_CUTOFF_TIME = time(14, 30)  # 2:30 PM - Stop generating new signals

    # Pre-market and post-market timings
    PRE_MARKET_OPEN = time(9, 0)  # 9:00 AM
    POST_MARKET_CLOSE = time(15, 45)  # 3:45 PM

    def __init__(self, square_off_time: Optional[str] = None,
                 signal_cutoff_time: Optional[str] = None):
        """
        Initialize market timing service.

        Args:
            square_off_time: Custom square-off time (HH:MM format), default 15:20
            signal_cutoff_time: Custom signal cutoff time (HH:MM format), default 14:00
        """
        if square_off_time:
            hour, minute = map(int, square_off_time.split(':'))
            self.SQUARE_OFF_TIME = time(hour, minute)

        if signal_cutoff_time:
            hour, minute = map(int, signal_cutoff_time.split(':'))
            self.SIGNAL_CUTOFF_TIME = time(hour, minute)

        logger.info(f"Initialized MarketTimingService:")
        logger.info(f"  Market Hours: {self.MARKET_OPEN} - {self.MARKET_CLOSE}")
        logger.info(f"  Square-off Time: {self.SQUARE_OFF_TIME}")
        logger.info(f"  Signal Cutoff: {self.SIGNAL_CUTOFF_TIME}")

    def get_current_time_ist(self) -> datetime:
        """
        Get current time in IST timezone.

        Returns:
            datetime: Current time in IST
        """
        return datetime.now(IST)

    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open.

        Args:
            check_time: Time to check (default: current time)

        Returns:
            bool: True if market is open
        """
        if check_time is None:
            check_time = self.get_current_time_ist()

        # Check if weekend
        if check_time.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check if within market hours
        current_time = check_time.time()
        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE

    def should_square_off_positions(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if it's time to square off all positions (3:20 PM or later).

        This is the CRITICAL function that enforces mandatory position closure.

        Args:
            check_time: Time to check (default: current time)

        Returns:
            bool: True if should square off NOW
        """
        if check_time is None:
            check_time = self.get_current_time_ist()

        current_time = check_time.time()

        # Square off at or after 3:20 PM
        should_exit = current_time >= self.SQUARE_OFF_TIME

        if should_exit:
            logger.warning(f"MANDATORY SQUARE-OFF TIME REACHED: {current_time}")

        return should_exit

    def time_until_square_off(self, check_time: Optional[datetime] = None) -> Optional[timedelta]:
        """
        Calculate time remaining until square-off.

        Args:
            check_time: Time to check (default: current time)

        Returns:
            timedelta: Time remaining, or None if already past square-off time
        """
        if check_time is None:
            check_time = self.get_current_time_ist()

        # Create square-off datetime for today
        square_off_dt = check_time.replace(
            hour=self.SQUARE_OFF_TIME.hour,
            minute=self.SQUARE_OFF_TIME.minute,
            second=0,
            microsecond=0
        )

        if check_time >= square_off_dt:
            return None  # Already past square-off time

        return square_off_dt - check_time

    def is_signal_generation_time(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if it's appropriate time to generate new signals.

        Signals should only be generated between market open and signal cutoff time
        (default 2:00 PM) to avoid late entries that would immediately be squared off.

        Args:
            check_time: Time to check (default: current time)

        Returns:
            bool: True if signals should be generated
        """
        if check_time is None:
            check_time = self.get_current_time_ist()

        if not self.is_market_open(check_time):
            return False

        current_time = check_time.time()

        # Generate signals only between market open and cutoff time
        can_generate = self.MARKET_OPEN <= current_time < self.SIGNAL_CUTOFF_TIME

        if not can_generate and current_time < self.MARKET_CLOSE:
            logger.debug(f"Signal generation stopped: Past cutoff time {self.SIGNAL_CUTOFF_TIME}")

        return can_generate

    def get_square_off_time(self, for_date: Optional[datetime] = None) -> datetime:
        """
        Get the square-off datetime for a given date.

        Args:
            for_date: Date to get square-off time for (default: today)

        Returns:
            datetime: Square-off datetime in IST
        """
        if for_date is None:
            for_date = self.get_current_time_ist()

        square_off_dt = for_date.replace(
            hour=self.SQUARE_OFF_TIME.hour,
            minute=self.SQUARE_OFF_TIME.minute,
            second=0,
            microsecond=0
        )

        return square_off_dt

    def get_market_status(self) -> Dict[str, any]:
        """
        Get comprehensive market status information.

        Returns:
            Dict with market status details
        """
        current_time = self.get_current_time_ist()

        status = {
            'current_time': current_time,
            'current_time_str': current_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'is_market_open': self.is_market_open(current_time),
            'is_weekend': current_time.weekday() >= 5,
            'should_square_off': self.should_square_off_positions(current_time),
            'can_generate_signals': self.is_signal_generation_time(current_time),
            'square_off_time': self.SQUARE_OFF_TIME.strftime('%H:%M'),
            'signal_cutoff_time': self.SIGNAL_CUTOFF_TIME.strftime('%H:%M'),
            'time_until_square_off': None,
            'time_until_square_off_str': None
        }

        # Calculate time until square-off
        time_remaining = self.time_until_square_off(current_time)
        if time_remaining:
            status['time_until_square_off'] = time_remaining
            total_seconds = int(time_remaining.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            status['time_until_square_off_str'] = f"{hours}h {minutes}m"
        else:
            status['time_until_square_off_str'] = "Past square-off time"

        return status

    def print_market_status(self) -> None:
        """Print formatted market status."""
        status = self.get_market_status()

        print("\n" + "=" * 60)
        print("MARKET STATUS")
        print("=" * 60)
        print(f"\nCurrent Time: {status['current_time_str']}")
        print(f"\nMarket Status:")
        print(f"  Market Open: {'Yes' if status['is_market_open'] else 'No'}")
        print(f"  Weekend: {'Yes' if status['is_weekend'] else 'No'}")

        print(f"\nTrading Windows:")
        print(f"  Can Generate Signals: {'Yes' if status['can_generate_signals'] else 'No'}")
        print(f"  Signal Cutoff Time: {status['signal_cutoff_time']}")
        print(f"  Square-off Time: {status['square_off_time']}")

        print(f"\nSquare-off Status:")
        if status['should_square_off']:
            print(f"  Should Square Off: YES - IMMEDIATE ACTION REQUIRED")
        else:
            print(f"  Should Square Off: No")
            if status['time_until_square_off_str'] != "Past square-off time":
                print(f"  Time Until Square-off: {status['time_until_square_off_str']}")

        print("\n" + "=" * 60)

    def is_market_holiday(self, check_date: Optional[datetime] = None) -> bool:
        """
        Check if given date is a market holiday.

        Note: This is a placeholder. In production, integrate with a holiday calendar API
        or maintain a list of NSE holidays.

        Args:
            check_date: Date to check (default: today)

        Returns:
            bool: True if market holiday
        """
        if check_date is None:
            check_date = self.get_current_time_ist()

        # Weekend check
        if check_date.weekday() >= 5:
            return True

        # TODO: Add NSE holiday calendar integration
        # For now, just check weekends

        return False

    def get_next_trading_day(self, from_date: Optional[datetime] = None) -> datetime:
        """
        Get the next trading day.

        Args:
            from_date: Start date (default: today)

        Returns:
            datetime: Next trading day
        """
        if from_date is None:
            from_date = self.get_current_time_ist()

        next_day = from_date + timedelta(days=1)

        # Skip weekends and holidays
        while self.is_market_holiday(next_day):
            next_day += timedelta(days=1)

        return next_day

    def calculate_holding_time(self, entry_time: datetime,
                               exit_time: Optional[datetime] = None) -> float:
        """
        Calculate holding time in minutes.

        Args:
            entry_time: Position entry time
            exit_time: Position exit time (default: current time)

        Returns:
            float: Holding time in minutes
        """
        if exit_time is None:
            exit_time = self.get_current_time_ist()

        delta = exit_time - entry_time
        return delta.total_seconds() / 60.0

    def validate_entry_time(self, check_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Validate if it's appropriate to enter a new position.

        Args:
            check_time: Time to validate (default: current time)

        Returns:
            Tuple of (is_valid, reason_message)
        """
        if check_time is None:
            check_time = self.get_current_time_ist()

        # Check if market is open
        if not self.is_market_open(check_time):
            return False, "Market is closed"

        # Check if weekend
        if check_time.weekday() >= 5:
            return False, "Weekend - market closed"

        # Check if past signal generation cutoff
        if not self.is_signal_generation_time(check_time):
            return False, f"Past signal cutoff time ({self.SIGNAL_CUTOFF_TIME})"

        # Check if too close to square-off time (need at least 30 minutes)
        time_remaining = self.time_until_square_off(check_time)
        if time_remaining and time_remaining < timedelta(minutes=30):
            return False, f"Too close to square-off time (less than 30 minutes)"

        return True, "Valid entry time"

    def format_time_remaining(self, time_remaining: timedelta) -> str:
        """
        Format time remaining as human-readable string.

        Args:
            time_remaining: Time delta to format

        Returns:
            str: Formatted time string (e.g., "2h 15m")
        """
        if time_remaining.total_seconds() < 0:
            return "Expired"

        total_seconds = int(time_remaining.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize service
    timing_service = MarketTimingService()

    # Print market status
    timing_service.print_market_status()

    # Test various checks
    print("\nTesting time validations:")
    print(f"Is market open? {timing_service.is_market_open()}")
    print(f"Should square off? {timing_service.should_square_off_positions()}")
    print(f"Can generate signals? {timing_service.is_signal_generation_time()}")

    # Test entry validation
    is_valid, reason = timing_service.validate_entry_time()
    print(f"\nEntry validation: {is_valid} - {reason}")

    # Calculate time until square-off
    time_remaining = timing_service.time_until_square_off()
    if time_remaining:
        print(f"\nTime until square-off: {timing_service.format_time_remaining(time_remaining)}")