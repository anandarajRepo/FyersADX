"""
Centralized symbol management for FyersADX Strategy.

Maintains the list of tradeable symbols in a simple format.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)


# Large Cap Stocks (Equity - Top companies by market cap)
LARGE_CAP_SYMBOLS = [
    "NSE:RELIANCE-EQ",      # Reliance Industries
    "NSE:TCS-EQ",           # Tata Consultancy Services
    "NSE:HDFCBANK-EQ",      # HDFC Bank
    "NSE:INFY-EQ",          # Infosys
    "NSE:ICICIBANK-EQ",     # ICICI Bank
    "NSE:HINDUNILVR-EQ",    # Hindustan Unilever
    "NSE:BHARTIARTL-EQ",    # Bharti Airtel
    "NSE:ITC-EQ",           # ITC
    "NSE:SBIN-EQ",          # State Bank of India
    "NSE:KOTAKBANK-EQ",     # Kotak Mahindra Bank
    "NSE:LT-EQ",            # Larsen & Toubro
    "NSE:AXISBANK-EQ",      # Axis Bank
    "NSE:BAJFINANCE-EQ",    # Bajaj Finance
    "NSE:ASIANPAINT-EQ",    # Asian Paints
    "NSE:MARUTI-EQ",        # Maruti Suzuki
    "NSE:HCLTECH-EQ",       # HCL Technologies
    "NSE:WIPRO-EQ",         # Wipro
    "NSE:SUNPHARMA-EQ",     # Sun Pharma
    "NSE:TITAN-EQ",         # Titan Company
    "NSE:TATAMOTORS-EQ",    # Tata Motors
    "NSE:ULTRACEMCO-EQ",    # UltraTech Cement
    "NSE:ADANIENT-EQ",      # Adani Enterprises
    "NSE:ONGC-EQ",          # ONGC
    "NSE:NTPC-EQ",          # NTPC
    "NSE:POWERGRID-EQ",     # Power Grid
]

# Mid Cap Stocks (Equity)
MID_CAP_SYMBOLS = [
    "NSE:DMART-EQ",         # Avenue Supermarts
    "NSE:GODREJCP-EQ",      # Godrej Consumer
    "NSE:PIDILITIND-EQ",    # Pidilite Industries
    "NSE:BERGEPAINT-EQ",    # Berger Paints
    "NSE:HAVELLS-EQ",       # Havells India
    "NSE:DABUR-EQ",         # Dabur India
    "NSE:MARICO-EQ",        # Marico
    "NSE:INDIGO-EQ",        # InterGlobe Aviation
    "NSE:LUPIN-EQ",         # Lupin
    "NSE:TORNTPHARM-EQ",    # Torrent Pharma
    "NSE:MUTHOOTFIN-EQ",    # Muthoot Finance
    "NSE:COLPAL-EQ",        # Colgate-Palmolive
    "NSE:TATACONSUM-EQ",    # Tata Consumer
    "NSE:BANDHANBNK-EQ",    # Bandhan Bank
    "NSE:FEDERALBNK-EQ",    # Federal Bank
]

# Small Cap Stocks (Equity - Use with caution - higher volatility)
SMALL_CAP_SYMBOLS = [
    "NSE:IRCTC-EQ",         # IRCTC
    "NSE:ZOMATO-EQ",        # Zomato
    "NSE:PAYTM-EQ",         # Paytm
    "NSE:POLICYBZR-EQ",     # PB Fintech
    "NSE:NYKAA-EQ",         # Nykaa
]

# Options - Weekly expiry (Example format - Update strike prices as needed)
OPTIONS_SYMBOLS = [
    # Stock Options
    # "NSE:SBILIFE25OCT1860CE",
    # "NSE:SBILIFE25OCT1860PE",
    # "NSE:KOTAKBANK25OCT2200CE",
    # "NSE:KOTAKBANK25OCT2200PE",
    # "NSE:DRREDDY25OCT1260CE",
    # "NSE:DRREDDY25OCT1260PE",
    # "NSE:NTPC25OCT345CE",
    # "NSE:NTPC25OCT345PE",
    # "NSE:COFORGE25OCT1700CE",
    # "NSE:COFORGE25OCT1700PE",

    # Index Options
    "NSE:NIFTY25OCT25850CE",        # NIFTY CALL
    "NSE:NIFTY25OCT25850PE",        # NIFTY PUT
    "NSE:BANKNIFTY25OCT58000CE",    # BANK-NIFTY CALL
    "NSE:BANKNIFTY25OCT58000PE",    # BANK-NIFTY PUT
    "NSE:FINNIFTY25OCT27500CE",     # FIN-NIFTY CALL
    "NSE:FINNIFTY25OCT27500PE",     # FIN-NIFTY PUT
    "NSE:MIDCPNIFTY25OCT13250CE",   # MIDCAP-NIFTY CALL
    "NSE:MIDCPNIFTY25OCT13250PE",   # MIDCAP-NIFTY PUT
]


# All tradeable symbols combined
ALL_SYMBOLS = (
    LARGE_CAP_SYMBOLS +
    MID_CAP_SYMBOLS +
    SMALL_CAP_SYMBOLS +
    OPTIONS_SYMBOLS
)


# Default symbol list for strategy (can be overridden)
# Choose one of: LARGE_CAP_SYMBOLS, MID_CAP_SYMBOLS, OPTIONS_SYMBOLS, ALL_SYMBOLS
DEFAULT_TRADING_SYMBOLS = LARGE_CAP_SYMBOLS


def get_active_symbols() -> List[str]:
    """
    Get all active symbols (default trading symbols).

    Returns:
        List of active symbol identifiers
    """
    return DEFAULT_TRADING_SYMBOLS.copy()


def get_large_cap_symbols() -> List[str]:
    """Get all large cap equity symbols."""
    return LARGE_CAP_SYMBOLS.copy()


def get_mid_cap_symbols() -> List[str]:
    """Get all mid cap equity symbols."""
    return MID_CAP_SYMBOLS.copy()


def get_small_cap_symbols() -> List[str]:
    """Get all small cap equity symbols."""
    return SMALL_CAP_SYMBOLS.copy()


def get_options_symbols() -> List[str]:
    """Get all options symbols."""
    return OPTIONS_SYMBOLS.copy()


def get_all_symbols() -> List[str]:
    """Get all available symbols."""
    return ALL_SYMBOLS.copy()


def validate_symbol_format(symbol: str) -> bool:
    """
    Validate Fyers symbol format.

    Args:
        symbol: Symbol to validate

    Returns:
        bool: True if valid format
    """
    if not symbol.startswith("NSE:"):
        return False
    if "-" not in symbol and not any(x in symbol for x in ["CE", "PE"]):
        return False
    return True


def validate_symbols(symbols: List[str]) -> tuple[List[str], List[str]]:
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
        if validate_symbol_format(symbol):
            valid.append(symbol)
        else:
            invalid.append(symbol)

    if invalid:
        logger.warning(f"Found {len(invalid)} invalid symbols: {invalid}")

    return valid, invalid


def print_summary() -> None:
    """Print symbol universe summary."""
    print("\n" + "=" * 60)
    print("SYMBOL CONFIGURATION SUMMARY")
    print("=" * 60)

    print(f"\nLarge Cap Symbols: {len(LARGE_CAP_SYMBOLS)}")
    print(f"Mid Cap Symbols: {len(MID_CAP_SYMBOLS)}")
    print(f"Small Cap Symbols: {len(SMALL_CAP_SYMBOLS)}")
    print(f"Options Symbols: {len(OPTIONS_SYMBOLS)}")
    print(f"Total Symbols: {len(ALL_SYMBOLS)}")
    print(f"Active/Default Symbols: {len(DEFAULT_TRADING_SYMBOLS)}")

    print("\n" + "=" * 60)


# Optional: Symbol names for display purposes
SYMBOL_NAMES = {
    # Large Cap
    "NSE:RELIANCE-EQ": "Reliance Industries",
    "NSE:TCS-EQ": "Tata Consultancy Services",
    "NSE:HDFCBANK-EQ": "HDFC Bank",
    "NSE:INFY-EQ": "Infosys",
    "NSE:ICICIBANK-EQ": "ICICI Bank",
    "NSE:HINDUNILVR-EQ": "Hindustan Unilever",
    "NSE:BHARTIARTL-EQ": "Bharti Airtel",
    "NSE:ITC-EQ": "ITC",
    "NSE:SBIN-EQ": "State Bank of India",
    "NSE:KOTAKBANK-EQ": "Kotak Mahindra Bank",
    "NSE:LT-EQ": "Larsen & Toubro",
    "NSE:AXISBANK-EQ": "Axis Bank",
    "NSE:BAJFINANCE-EQ": "Bajaj Finance",
    "NSE:ASIANPAINT-EQ": "Asian Paints",
    "NSE:MARUTI-EQ": "Maruti Suzuki",
    "NSE:HCLTECH-EQ": "HCL Technologies",
    "NSE:WIPRO-EQ": "Wipro",
    "NSE:SUNPHARMA-EQ": "Sun Pharma",
    "NSE:TITAN-EQ": "Titan Company",
    "NSE:TATAMOTORS-EQ": "Tata Motors",
    "NSE:ULTRACEMCO-EQ": "UltraTech Cement",
    "NSE:ADANIENT-EQ": "Adani Enterprises",
    "NSE:ONGC-EQ": "ONGC",
    "NSE:NTPC-EQ": "NTPC",
    "NSE:POWERGRID-EQ": "Power Grid",
    # Mid Cap
    "NSE:DMART-EQ": "Avenue Supermarts",
    "NSE:GODREJCP-EQ": "Godrej Consumer",
    "NSE:PIDILITIND-EQ": "Pidilite Industries",
    "NSE:BERGEPAINT-EQ": "Berger Paints",
    "NSE:HAVELLS-EQ": "Havells India",
    "NSE:DABUR-EQ": "Dabur India",
    "NSE:MARICO-EQ": "Marico",
    "NSE:INDIGO-EQ": "InterGlobe Aviation",
    "NSE:LUPIN-EQ": "Lupin",
    "NSE:TORNTPHARM-EQ": "Torrent Pharma",
    "NSE:MUTHOOTFIN-EQ": "Muthoot Finance",
    "NSE:COLPAL-EQ": "Colgate-Palmolive",
    "NSE:TATACONSUM-EQ": "Tata Consumer",
    "NSE:BANDHANBNK-EQ": "Bandhan Bank",
    "NSE:FEDERALBNK-EQ": "Federal Bank",
    # Small Cap
    "NSE:IRCTC-EQ": "IRCTC",
    "NSE:ZOMATO-EQ": "Zomato",
    "NSE:PAYTM-EQ": "Paytm",
    "NSE:POLICYBZR-EQ": "PB Fintech",
    "NSE:NYKAA-EQ": "Nykaa",
}


def get_symbol_name(symbol: str) -> str:
    """
    Get display name for a symbol.

    Args:
        symbol: Symbol identifier

    Returns:
        Display name or the symbol itself if not found
    """
    return SYMBOL_NAMES.get(symbol, symbol)


if __name__ == "__main__":
    # Example usage
    print_summary()

    print("\nDefault Trading Symbols (First 10):")
    for i, symbol in enumerate(DEFAULT_TRADING_SYMBOLS[:10], 1):
        name = get_symbol_name(symbol)
        print(f"  {i}. {name} ({symbol})")

    print("\n" + "=" * 60)