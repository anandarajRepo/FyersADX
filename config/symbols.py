"""
Centralized symbol management for FyersADX Strategy.

Maintains the list of tradeable symbols with categorization and validation.
"""

import logging
from enum import Enum
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

from models.trading_models import SymbolCategory

logger = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    """
    Information about a tradeable symbol.

    Attributes:
        symbol: Fyers format symbol (NSE:SYMBOL-EQ)
        name: Display name
        category: Market cap category
        sector: Industry sector
        is_active: Whether symbol is actively traded
    """
    symbol: str
    name: str
    category: SymbolCategory
    sector: str = "UNKNOWN"
    is_active: bool = True

    def validate_format(self) -> bool:
        """Validate Fyers symbol format."""
        # Expected format: NSE:SYMBOL-EQ or NSE:SYMBOL-XX
        if not self.symbol.startswith("NSE:"):
            return False
        if "-" not in self.symbol:
            return False
        return True


class SymbolManager:
    """
    Centralized manager for all tradeable symbols.

    Provides symbol validation, categorization, and filtering capabilities.
    """

    # Large Cap Stocks (Top companies by market cap)
    LARGE_CAP_SYMBOLS = [
        SymbolInfo("NSE:RELIANCE-EQ", "Reliance Industries", SymbolCategory.LARGE_CAP, "ENERGY"),
        SymbolInfo("NSE:TCS-EQ", "Tata Consultancy Services", SymbolCategory.LARGE_CAP, "IT"),
        SymbolInfo("NSE:HDFCBANK-EQ", "HDFC Bank", SymbolCategory.LARGE_CAP, "BANKING"),
        SymbolInfo("NSE:INFY-EQ", "Infosys", SymbolCategory.LARGE_CAP, "IT"),
        SymbolInfo("NSE:ICICIBANK-EQ", "ICICI Bank", SymbolCategory.LARGE_CAP, "BANKING"),
        SymbolInfo("NSE:HINDUNILVR-EQ", "Hindustan Unilever", SymbolCategory.LARGE_CAP, "FMCG"),
        SymbolInfo("NSE:BHARTIARTL-EQ", "Bharti Airtel", SymbolCategory.LARGE_CAP, "TELECOM"),
        SymbolInfo("NSE:ITC-EQ", "ITC", SymbolCategory.LARGE_CAP, "FMCG"),
        SymbolInfo("NSE:SBIN-EQ", "State Bank of India", SymbolCategory.LARGE_CAP, "BANKING"),
        SymbolInfo("NSE:KOTAKBANK-EQ", "Kotak Mahindra Bank", SymbolCategory.LARGE_CAP, "BANKING"),
        SymbolInfo("NSE:LT-EQ", "Larsen & Toubro", SymbolCategory.LARGE_CAP, "INFRASTRUCTURE"),
        SymbolInfo("NSE:AXISBANK-EQ", "Axis Bank", SymbolCategory.LARGE_CAP, "BANKING"),
        SymbolInfo("NSE:BAJFINANCE-EQ", "Bajaj Finance", SymbolCategory.LARGE_CAP, "FINANCE"),
        SymbolInfo("NSE:ASIANPAINT-EQ", "Asian Paints", SymbolCategory.LARGE_CAP, "PAINT"),
        SymbolInfo("NSE:MARUTI-EQ", "Maruti Suzuki", SymbolCategory.LARGE_CAP, "AUTOMOBILE"),
        SymbolInfo("NSE:HCLTECH-EQ", "HCL Technologies", SymbolCategory.LARGE_CAP, "IT"),
        SymbolInfo("NSE:WIPRO-EQ", "Wipro", SymbolCategory.LARGE_CAP, "IT"),
        SymbolInfo("NSE:SUNPHARMA-EQ", "Sun Pharma", SymbolCategory.LARGE_CAP, "PHARMA"),
        SymbolInfo("NSE:TITAN-EQ", "Titan Company", SymbolCategory.LARGE_CAP, "CONSUMER"),
        SymbolInfo("NSE:TATAMOTORS-EQ", "Tata Motors", SymbolCategory.LARGE_CAP, "AUTOMOBILE"),
        SymbolInfo("NSE:ULTRACEMCO-EQ", "UltraTech Cement", SymbolCategory.LARGE_CAP, "CEMENT"),
        SymbolInfo("NSE:ADANIENT-EQ", "Adani Enterprises", SymbolCategory.LARGE_CAP, "INFRASTRUCTURE"),
        SymbolInfo("NSE:ONGC-EQ", "ONGC", SymbolCategory.LARGE_CAP, "ENERGY"),
        SymbolInfo("NSE:NTPC-EQ", "NTPC", SymbolCategory.LARGE_CAP, "POWER"),
        SymbolInfo("NSE:POWERGRID-EQ", "Power Grid", SymbolCategory.LARGE_CAP, "POWER"),
    ]

    # Mid Cap Stocks
    MID_CAP_SYMBOLS = [
        SymbolInfo("NSE:DMART-EQ", "Avenue Supermarts", SymbolCategory.MID_CAP, "RETAIL"),
        SymbolInfo("NSE:GODREJCP-EQ", "Godrej Consumer", SymbolCategory.MID_CAP, "FMCG"),
        SymbolInfo("NSE:PIDILITIND-EQ", "Pidilite Industries", SymbolCategory.MID_CAP, "CHEMICALS"),
        SymbolInfo("NSE:BERGEPAINT-EQ", "Berger Paints", SymbolCategory.MID_CAP, "PAINT"),
        SymbolInfo("NSE:HAVELLS-EQ", "Havells India", SymbolCategory.MID_CAP, "CONSUMER"),
        SymbolInfo("NSE:DABUR-EQ", "Dabur India", SymbolCategory.MID_CAP, "FMCG"),
        SymbolInfo("NSE:MARICO-EQ", "Marico", SymbolCategory.MID_CAP, "FMCG"),
        SymbolInfo("NSE:INDIGO-EQ", "InterGlobe Aviation", SymbolCategory.MID_CAP, "AVIATION"),
        SymbolInfo("NSE:LUPIN-EQ", "Lupin", SymbolCategory.MID_CAP, "PHARMA"),
        SymbolInfo("NSE:TORNTPHARM-EQ", "Torrent Pharma", SymbolCategory.MID_CAP, "PHARMA"),
        SymbolInfo("NSE:MUTHOOTFIN-EQ", "Muthoot Finance", SymbolCategory.MID_CAP, "FINANCE"),
        SymbolInfo("NSE:COLPAL-EQ", "Colgate-Palmolive", SymbolCategory.MID_CAP, "FMCG"),
        SymbolInfo("NSE:TATACONSUM-EQ", "Tata Consumer", SymbolCategory.MID_CAP, "FMCG"),
        SymbolInfo("NSE:BANDHANBNK-EQ", "Bandhan Bank", SymbolCategory.MID_CAP, "BANKING"),
        SymbolInfo("NSE:FEDERALBNK-EQ", "Federal Bank", SymbolCategory.MID_CAP, "BANKING"),
    ]

    # Small Cap Stocks (Use with caution - higher volatility)
    SMALL_CAP_SYMBOLS = [
        SymbolInfo("NSE:IRCTC-EQ", "IRCTC", SymbolCategory.SMALL_CAP, "TOURISM"),
        SymbolInfo("NSE:ZOMATO-EQ", "Zomato", SymbolCategory.SMALL_CAP, "FOOD_TECH"),
        SymbolInfo("NSE:PAYTM-EQ", "Paytm", SymbolCategory.SMALL_CAP, "FINTECH"),
        SymbolInfo("NSE:POLICYBZR-EQ", "PB Fintech", SymbolCategory.SMALL_CAP, "FINTECH"),
        SymbolInfo("NSE:NYKAA-EQ", "Nykaa", SymbolCategory.SMALL_CAP, "RETAIL"),
    ]

    def __init__(self):
        """Initialize the symbol manager."""
        self.all_symbols: List[SymbolInfo] = []
        self.symbol_map: Dict[str, SymbolInfo] = {}
        self.active_symbols: Set[str] = set()

        self._initialize_symbols()
        logger.info(f"Initialized SymbolManager with {len(self.all_symbols)} symbols")

    def _initialize_symbols(self) -> None:
        """Initialize and validate all symbols."""
        # Combine all symbol lists
        self.all_symbols = (
                self.LARGE_CAP_SYMBOLS +
                self.MID_CAP_SYMBOLS +
                self.SMALL_CAP_SYMBOLS
        )

        # Create symbol map and validate
        for symbol_info in self.all_symbols:
            if not symbol_info.validate_format():
                logger.warning(f"Invalid symbol format: {symbol_info.symbol}")
                continue

            self.symbol_map[symbol_info.symbol] = symbol_info

            if symbol_info.is_active:
                self.active_symbols.add(symbol_info.symbol)

    def get_all_symbols(self, active_only: bool = True) -> List[str]:
        """
        Get list of all symbols.

        Args:
            active_only: Return only active symbols

        Returns:
            List of symbol identifiers
        """
        if active_only:
            return list(self.active_symbols)
        return [s.symbol for s in self.all_symbols]

    def get_symbols_by_category(
            self,
            category: SymbolCategory,
            active_only: bool = True
    ) -> List[str]:
        """
        Get symbols filtered by category.

        Args:
            category: Symbol category to filter by
            active_only: Return only active symbols

        Returns:
            List of symbol identifiers
        """
        symbols = [
            s.symbol for s in self.all_symbols
            if s.category == category and (not active_only or s.is_active)
        ]
        return symbols

    def get_symbols_by_sector(self, sector: str, active_only: bool = True) -> List[str]:
        """
        Get symbols filtered by sector.

        Args:
            sector: Sector to filter by
            active_only: Return only active symbols

        Returns:
            List of symbol identifiers
        """
        symbols = [
            s.symbol for s in self.all_symbols
            if s.sector == sector and (not active_only or s.is_active)
        ]
        return symbols

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """
        Get information about a specific symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            SymbolInfo or None if not found
        """
        return self.symbol_map.get(symbol)

    def is_valid_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is valid and active.

        Args:
            symbol: Symbol identifier

        Returns:
            bool: True if valid and active
        """
        return symbol in self.active_symbols

    def validate_symbol_list(self, symbols: List[str]) -> tuple[List[str], List[str]]:
        """
        Validate a list of symbols.

        Args:
            symbols: List of symbols to validate

        Returns:
            Tuple of (valid_symbols, invalid_symbols)
        """
        valid = []
        invalid = []

        for symbol in symbols:
            if self.is_valid_symbol(symbol):
                valid.append(symbol)
            else:
                invalid.append(symbol)

        return valid, invalid

    def add_custom_symbol(self, symbol_info: SymbolInfo) -> bool:
        """
        Add a custom symbol to the manager.

        Args:
            symbol_info: SymbolInfo object

        Returns:
            bool: True if added successfully
        """
        if not symbol_info.validate_format():
            logger.error(f"Invalid symbol format: {symbol_info.symbol}")
            return False

        if symbol_info.symbol in self.symbol_map:
            logger.warning(f"Symbol already exists: {symbol_info.symbol}")
            return False

        self.all_symbols.append(symbol_info)
        self.symbol_map[symbol_info.symbol] = symbol_info

        if symbol_info.is_active:
            self.active_symbols.add(symbol_info.symbol)

        logger.info(f"Added custom symbol: {symbol_info.symbol}")
        return True

    def deactivate_symbol(self, symbol: str) -> bool:
        """
        Deactivate a symbol.

        Args:
            symbol: Symbol to deactivate

        Returns:
            bool: True if deactivated successfully
        """
        if symbol not in self.symbol_map:
            logger.warning(f"Symbol not found: {symbol}")
            return False

        self.symbol_map[symbol].is_active = False
        self.active_symbols.discard(symbol)

        logger.info(f"Deactivated symbol: {symbol}")
        return True

    def activate_symbol(self, symbol: str) -> bool:
        """
        Activate a symbol.

        Args:
            symbol: Symbol to activate

        Returns:
            bool: True if activated successfully
        """
        if symbol not in self.symbol_map:
            logger.warning(f"Symbol not found: {symbol}")
            return False

        self.symbol_map[symbol].is_active = True
        self.active_symbols.add(symbol)

        logger.info(f"Activated symbol: {symbol}")
        return True

    def get_statistics(self) -> Dict:
        """
        Get statistics about the symbol universe.

        Returns:
            Dict with statistics
        """
        stats = {
            'total_symbols': len(self.all_symbols),
            'active_symbols': len(self.active_symbols),
            'by_category': {},
            'by_sector': {}
        }

        # Count by category
        for category in SymbolCategory:
            count = len([s for s in self.all_symbols if s.category == category])
            stats['by_category'][category.value] = count

        # Count by sector
        sectors = set(s.sector for s in self.all_symbols)
        for sector in sectors:
            count = len([s for s in self.all_symbols if s.sector == sector])
            stats['by_sector'][sector] = count

        return stats

    def print_summary(self) -> None:
        """Print symbol universe summary."""
        stats = self.get_statistics()

        print("\n" + "=" * 60)
        print("SYMBOL UNIVERSE SUMMARY")
        print("=" * 60)

        print(f"\nTotal Symbols: {stats['total_symbols']}")
        print(f"Active Symbols: {stats['active_symbols']}")

        print("\nBy Category:")
        for category, count in stats['by_category'].items():
            print(f"  {category}: {count}")

        print("\nBy Sector:")
        for sector, count in sorted(stats['by_sector'].items()):
            print(f"  {sector}: {count}")

        print("\n" + "=" * 60)


# Global symbol manager instance
symbol_manager = SymbolManager()


# Convenience functions for easy access
def get_active_symbols() -> List[str]:
    """Get all active symbols."""
    return symbol_manager.get_all_symbols(active_only=True)


def get_large_cap_symbols() -> List[str]:
    """Get all large cap symbols."""
    return symbol_manager.get_symbols_by_category(SymbolCategory.LARGE_CAP)


def get_mid_cap_symbols() -> List[str]:
    """Get all mid cap symbols."""
    return symbol_manager.get_symbols_by_category(SymbolCategory.MID_CAP)


def get_small_cap_symbols() -> List[str]:
    """Get all small cap symbols."""
    return symbol_manager.get_symbols_by_category(SymbolCategory.SMALL_CAP)


def validate_symbols(symbols: List[str]) -> tuple[List[str], List[str]]:
    """
    Validate a list of symbols.

    Args:
        symbols: List of symbols to validate

    Returns:
        Tuple of (valid_symbols, invalid_symbols)
    """
    return symbol_manager.validate_symbol_list(symbols)


# Default symbol list for strategy (can be overridden)
DEFAULT_TRADING_SYMBOLS = get_large_cap_symbols()

if __name__ == "__main__":
    # Example usage
    symbol_manager.print_summary()

    print("\n\nActive Trading Symbols:")
    for symbol in DEFAULT_TRADING_SYMBOLS[:10]:
        info = symbol_manager.get_symbol_info(symbol)
        if info:
            print(f"  {info.name} ({symbol}) - {info.sector}")