"""
Symbol Manager for FyersADX - ATM Option Symbol Generation.

Manages the lifecycle of option symbols including:
- Automatic ATM symbol generation
- Daily symbol caching
- Symbol freshness validation
- Integration with ATMSymbolGenerator
"""

import logging
import json
from pathlib import Path
from datetime import datetime, date
from typing import List, Optional, Dict
from utils.symbol_generator import ATMSymbolGenerator

logger = logging.getLogger(__name__)


class SymbolManager:
    """
    High-level manager for option symbol generation and caching.

    Features:
    - Automatic ATM symbol generation using ATMSymbolGenerator
    - Daily symbol caching (symbols are regenerated each trading day)
    - File-based persistence (daily_symbols.json)
    - Symbol freshness validation
    - Fallback to manual symbols if generation fails
    """

    def __init__(self, symbols_file: str = "daily_symbols.json"):
        """
        Initialize Symbol Manager.

        Args:
            symbols_file: Path to JSON file for storing generated symbols
        """
        self.generator: Optional[ATMSymbolGenerator] = None
        self.symbols_file = Path(symbols_file)
        self.cached_symbols: List[str] = []
        self.cache_date: Optional[date] = None

        logger.info(f"Initialized SymbolManager with cache file: {self.symbols_file}")

    def initialize_generator(self, client_id: str, access_token: str) -> bool:
        """
        Initialize the ATM symbol generator.

        Args:
            client_id: Fyers Client ID
            access_token: Valid Fyers access token

        Returns:
            bool: True if initialization successful
        """
        try:
            if not client_id or not access_token:
                logger.error("Client ID or access token missing")
                return False

            logger.info("Initializing ATMSymbolGenerator...")
            self.generator = ATMSymbolGenerator(client_id, access_token)
            logger.info("✓ ATMSymbolGenerator initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ATMSymbolGenerator: {e}")
            return False

    def get_or_generate_symbols(
            self,
            indices: List[str] = None,
            num_strikes_otm: int = 0,
            force_regenerate: bool = False
    ) -> List[str]:
        """
        Get symbols from cache or generate new ones if needed.

        Args:
            indices: List of indices to generate symbols for
            num_strikes_otm: Number of OTM strikes on each side (0 = ATM only)
            force_regenerate: Force regeneration even if cache is fresh

        Returns:
            List of option symbols
        """
        if indices is None:
            indices = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY']

        # Check if we need to regenerate
        need_regenerate = (
                force_regenerate or
                not self._is_cache_fresh() or
                not self.cached_symbols
        )

        if need_regenerate:
            logger.info("Generating new symbols...")
            symbols = self.generate_daily_symbols(indices, num_strikes_otm)
        else:
            logger.info("Using cached symbols from today")
            symbols = self.cached_symbols

        return symbols

    def generate_daily_symbols(
            self,
            indices: List[str] = None,
            num_strikes_otm: int = 0
    ) -> List[str]:
        """
        Generate fresh ATM option symbols for today.

        Args:
            indices: List of indices to generate for
            num_strikes_otm: Number of OTM strikes on each side

        Returns:
            List of generated symbols
        """
        if not self.generator:
            logger.error("Generator not initialized - call initialize_generator() first")
            return []

        try:
            logger.info("=" * 70)
            logger.info("GENERATING ATM OPTION SYMBOLS")
            logger.info("=" * 70)
            logger.info(f"Indices: {indices}")
            logger.info(f"OTM Strikes: {num_strikes_otm} on each side")
            logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %A')}")
            logger.info("=" * 70)

            # Generate symbols using ATMSymbolGenerator
            symbols = self.generator.get_all_atm_symbols_flat(
                indices=indices,
                num_strikes_otm=num_strikes_otm,
                include_spot=False  # Don't include spot symbols
            )

            if symbols:
                logger.info(f"✓ Generated {len(symbols)} symbols")

                # Log sample symbols
                logger.info("\nSample symbols:")
                for sym in symbols[:10]:
                    logger.info(f"  • {sym}")
                if len(symbols) > 10:
                    logger.info(f"  ... and {len(symbols) - 10} more")

                # Cache the symbols
                self.cached_symbols = symbols
                self.cache_date = date.today()

                # Save to file
                self._save_to_file(symbols)

                logger.info("=" * 70)
                return symbols
            else:
                logger.error("✗ No symbols generated")
                return []

        except Exception as e:
            logger.error(f"Error generating symbols: {e}", exc_info=True)
            return []

    def load_symbols_from_file(self) -> List[str]:
        """
        Load symbols from cache file.

        Returns:
            List of symbols if cache is fresh, empty list otherwise
        """
        try:
            if not self.symbols_file.exists():
                logger.debug(f"Cache file not found: {self.symbols_file}")
                return []

            with open(self.symbols_file, 'r') as f:
                data = json.load(f)

            cached_date_str = data.get('date')
            symbols = data.get('symbols', [])

            if not cached_date_str or not symbols:
                logger.debug("Invalid cache file format")
                return []

            # Parse cached date
            cached_date = datetime.strptime(cached_date_str, '%Y-%m-%d').date()

            # Check if cache is from today
            if cached_date != date.today():
                logger.info(f"Cache is stale (from {cached_date}), regeneration needed")
                return []

            logger.info(f"✓ Loaded {len(symbols)} symbols from cache")

            # Update internal cache
            self.cached_symbols = symbols
            self.cache_date = cached_date

            return symbols

        except Exception as e:
            logger.error(f"Error loading symbols from file: {e}")
            return []

    def _save_to_file(self, symbols: List[str]) -> bool:
        """
        Save symbols to cache file.

        Args:
            symbols: List of symbols to save

        Returns:
            bool: True if saved successfully
        """
        try:
            data = {
                'date': date.today().strftime('%Y-%m-%d'),
                'generated_at': datetime.now().isoformat(),
                'count': len(symbols),
                'symbols': symbols
            }

            with open(self.symbols_file, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Symbols saved to {self.symbols_file}")
            return True

        except Exception as e:
            logger.error(f"Error saving symbols to file: {e}")
            return False

    def _is_cache_fresh(self) -> bool:
        """
        Check if cached symbols are from today.

        Returns:
            bool: True if cache is fresh
        """
        if not self.cache_date:
            # Try loading from file
            symbols = self.load_symbols_from_file()
            if symbols:
                return True

        return self.cache_date == date.today() if self.cache_date else False

    def clear_cache(self) -> None:
        """Clear the symbol cache."""
        self.cached_symbols = []
        self.cache_date = None

        if self.symbols_file.exists():
            try:
                self.symbols_file.unlink()
                logger.info("✓ Cache file deleted")
            except Exception as e:
                logger.error(f"Error deleting cache file: {e}")

    def get_cache_info(self) -> Dict:
        """
        Get information about the current cache.

        Returns:
            Dict with cache information
        """
        return {
            'has_cache': bool(self.cached_symbols),
            'cache_date': self.cache_date.isoformat() if self.cache_date else None,
            'is_fresh': self._is_cache_fresh(),
            'symbol_count': len(self.cached_symbols),
            'file_exists': self.symbols_file.exists(),
            'generator_initialized': self.generator is not None
        }

    def print_cache_info(self) -> None:
        """Print formatted cache information."""
        info = self.get_cache_info()

        print("\n" + "=" * 70)
        print("SYMBOL CACHE INFORMATION")
        print("=" * 70)
        print(f"Cache Status: {'✓ Fresh' if info['is_fresh'] else '✗ Stale/Empty'}")
        print(f"Cache Date: {info['cache_date'] or 'None'}")
        print(f"Symbol Count: {info['symbol_count']}")
        print(f"File Exists: {'Yes' if info['file_exists'] else 'No'}")
        print(f"Generator Ready: {'Yes' if info['generator_initialized'] else 'No'}")
        print("=" * 70)


# Convenience function
def get_daily_symbols(
        client_id: str,
        access_token: str,
        indices: List[str] = None,
        num_strikes_otm: int = 0,
        force_regenerate: bool = False
) -> List[str]:
    """
    Convenience function to get daily symbols.

    Args:
        client_id: Fyers Client ID
        access_token: Fyers access token
        indices: List of indices (default: all)
        num_strikes_otm: Number of OTM strikes
        force_regenerate: Force regeneration

    Returns:
        List of option symbols
    """
    manager = SymbolManager()

    if not manager.initialize_generator(client_id, access_token):
        logger.error("Failed to initialize generator")
        return []

    return manager.get_or_generate_symbols(indices, num_strikes_otm, force_regenerate)


if __name__ == "__main__":
    # Example usage
    import os
    from dotenv import load_dotenv

    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    client_id = os.getenv('FYERS_CLIENT_ID')
    access_token = os.getenv('FYERS_ACCESS_TOKEN')

    if client_id and access_token:
        manager = SymbolManager()

        # Initialize
        if manager.initialize_generator(client_id, access_token):
            # Generate symbols
            symbols = manager.get_or_generate_symbols(
                indices=['NIFTY', 'BANKNIFTY'],
                num_strikes_otm=1
            )

            print(f"\nGenerated {len(symbols)} symbols")

            # Print cache info
            manager.print_cache_info()
    else:
        print("Error: Set FYERS_CLIENT_ID and FYERS_ACCESS_TOKEN in .env")