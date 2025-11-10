"""
Fyers WebSocket Service for Real-Time Market Data.

Handles WebSocket connections to Fyers for real-time quotes and calculates
ADX/DI indicators on-the-fly.
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Set
from collections import deque

try:
    from fyers_apiv3 import fyersModel
    from fyers_apiv3.FyersWebsocket import data_ws
    FYERS_AVAILABLE = True
except ImportError:
    FYERS_AVAILABLE = False
    logging.warning("Fyers API not available - install with: pip install fyers-apiv3")

from models.trading_models import LiveQuote, ADXIndicators
from services.analysis_service import ADXTechnicalAnalysisService
from config.settings import FyersConfig, ADXStrategyConfig

logger = logging.getLogger(__name__)


class FyersWebSocketService:
    """
    Real-time market data service using Fyers WebSocket.

    Features:
    - Real-time quote streaming
    - On-the-fly ADX/DI calculation
    - Automatic reconnection
    - REST API fallback
    - Quote buffering and validation
    """

    def __init__(
        self,
        fyers_config: FyersConfig,
        strategy_config: ADXStrategyConfig,
        symbols: List[str]
    ):
        """
        Initialize WebSocket service.

        Args:
            fyers_config: Fyers API configuration
            strategy_config: Strategy configuration
            symbols: List of symbols to subscribe
        """
        self.fyers_config = fyers_config
        self.strategy_config = strategy_config
        self.symbols = symbols

        # Analysis service for indicators
        self.analysis_service = ADXTechnicalAnalysisService(strategy_config)

        # WebSocket instance
        self.ws_instance = None
        self.is_connected = False
        self.is_running = False

        # Data storage
        self.latest_quotes: Dict[str, LiveQuote] = {}
        self.latest_indicators: Dict[str, ADXIndicators] = {}
        self.quote_buffer: Dict[str, deque] = {}

        # Callbacks
        self.quote_callbacks: List[Callable] = []
        self.indicator_callbacks: List[Callable] = []
        self.error_callbacks: List[Callable] = []

        # Connection state
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5

        # Subscribed symbols
        self.subscribed_symbols: Set[str] = set()

        logger.info(f"Initialized FyersWebSocketService for {len(symbols)} symbols")

    async def connect(self) -> bool:
        """
        Connect to Fyers WebSocket.

        Returns:
            bool: True if connection successful
        """
        if not FYERS_AVAILABLE:
            logger.error("Fyers API not available")
            return False

        if not self.fyers_config.is_authenticated():
            logger.error("Not authenticated with Fyers")
            return False

        try:
            logger.info("Connecting to Fyers WebSocket...")

            # Create WebSocket instance with proper data type
            self.ws_instance = data_ws.FyersDataSocket(
                access_token=self.fyers_config.access_token,
                log_path="logs/",
                litemode=False,
                write_to_file=False,
                reconnect=True,
                reconnect_retry=self.max_reconnect_attempts,
                on_connect=self._on_connect,
                on_close=self._on_close,
                on_error=self._on_error,
                on_message=self._on_message
            )

            # Connect (non-blocking)
            self.ws_instance.connect()
            self.is_running = True

            # Wait for connection with timeout
            max_wait = 10  # seconds
            wait_interval = 0.5
            elapsed = 0

            while elapsed < max_wait:
                if self.is_connected:
                    logger.info("WebSocket connected successfully")
                    return True
                await asyncio.sleep(wait_interval)
                elapsed += wait_interval

            logger.error("WebSocket connection timeout")
            return False

        except Exception as e:
            logger.error(f"Error connecting to WebSocket: {e}", exc_info=True)
            return False

    async def subscribe_symbols(self, symbols: Optional[List[str]] = None) -> bool:
        """
        Subscribe to symbols for real-time data.

        Args:
            symbols: List of symbols (uses self.symbols if None)

        Returns:
            bool: True if subscription successful
        """
        if not self.is_connected:
            logger.error("Not connected to WebSocket")
            return False

        if symbols is None:
            symbols = self.symbols

        try:
            # Format symbols for Fyers WebSocket
            symbol_list = [self._format_symbol_for_ws(s) for s in symbols]

            logger.info(f"Subscribing to symbols: {symbol_list[:5]}..." if len(symbol_list) > 5 else f"Subscribing to symbols: {symbol_list}")

            # Try different subscription approaches based on Fyers API version
            try:
                # Method 1: Direct list subscription
                self.ws_instance.subscribe(symbol_list)
            except TypeError as e:
                logger.warning(f"Direct subscription failed: {e}, trying alternate method...")
                # Method 2: Individual symbol subscription
                for sym in symbol_list:
                    try:
                        self.ws_instance.subscribe([sym])
                    except Exception as sym_error:
                        logger.error(f"Failed to subscribe to {sym}: {sym_error}")

            self.subscribed_symbols.update(symbols)

            # Initialize buffers
            for symbol in symbols:
                if symbol not in self.quote_buffer:
                    self.quote_buffer[symbol] = deque(maxlen=100)

            logger.info(f"Subscribed to {len(symbols)} symbols")
            return True

        except Exception as e:
            logger.error(f"Error subscribing to symbols: {e}", exc_info=True)
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    async def unsubscribe_symbols(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from symbols.

        Args:
            symbols: List of symbols to unsubscribe

        Returns:
            bool: True if successful
        """
        if not self.is_connected:
            return False

        try:
            symbol_list = [self._format_symbol_for_ws(s) for s in symbols]

            # Unsubscribe - Fyers API expects just the symbol list
            self.ws_instance.unsubscribe(symbol_list)

            self.subscribed_symbols.difference_update(symbols)

            logger.info(f"✓ Unsubscribed from {len(symbols)} symbols")
            return True

        except Exception as e:
            logger.error(f"Error unsubscribing: {e}", exc_info=True)
            return False

    def _on_connect(self, *args, **kwargs):
        """WebSocket connection callback."""
        self.is_connected = True
        self.reconnect_attempts = 0
        message = args[0] if args else kwargs.get('message', 'Connected')
        logger.info(f"WebSocket connected: {message}")

    def _on_close(self, *args, **kwargs):
        """WebSocket close callback."""
        self.is_connected = False
        message = args[0] if args else kwargs.get('message', 'Connection closed')
        logger.warning(f"WebSocket closed: {message}")

        # Attempt reconnection
        if self.is_running and self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            logger.info(f"Attempting reconnection {self.reconnect_attempts}/{self.max_reconnect_attempts}")
            asyncio.create_task(self._reconnect())

    def _on_error(self, *args, **kwargs):
        """WebSocket error callback."""
        message = args[0] if args else kwargs.get('message', 'Unknown error')
        logger.error(f"WebSocket error: {message}")

        # Notify error callbacks
        for callback in self.error_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    def _on_message(self, *args, **kwargs):
        """
        WebSocket message callback.

        Processes incoming quotes and calculates indicators.
        """
        try:
            # Get message from args or kwargs
            message = args[0] if args else kwargs.get('message')

            if not message:
                logger.info("Received empty message")
                return

            # Parse message
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message

            # Extract quote data
            symbol = self._extract_symbol(data)
            if not symbol or symbol not in self.subscribed_symbols:
                return

            # Create LiveQuote object
            quote = self._parse_quote(data)
            if not quote:
                return

            # Store latest quote
            self.latest_quotes[symbol] = quote

            # Buffer quote for indicator calculation
            self.quote_buffer[symbol].append(quote)

            # Calculate indicators if enough data
            if len(self.quote_buffer[symbol]) >= self.strategy_config.di_period + 1:
                self._calculate_and_update_indicators(symbol)

            # Notify quote callbacks
            for callback in self.quote_callbacks:
                try:
                    callback(quote)
                except Exception as e:
                    logger.error(f"Error in quote callback: {e}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    def _parse_quote(self, data: Dict) -> Optional[LiveQuote]:
        """Parse WebSocket data into LiveQuote object."""
        try:
            # Fyers WebSocket data structure
            # Adjust field names based on actual Fyers API response
            quote = LiveQuote(
                symbol=data.get('symbol', ''),
                timestamp=datetime.now(),
                ltp=float(data.get('ltp', 0) or data.get('last_price', 0)),
                open=float(data.get('open_price', 0) or data.get('open', 0)),
                high=float(data.get('high_price', 0) or data.get('high', 0)),
                low=float(data.get('low_price', 0) or data.get('low', 0)),
                close=float(data.get('prev_close_price', 0) or data.get('close', 0)),
                volume=int(data.get('volume', 0) or 0),
                bid=float(data.get('bid', 0) or 0),
                ask=float(data.get('ask', 0) or 0),
                bid_size=int(data.get('bid_size', 0) or 0),
                ask_size=int(data.get('ask_size', 0) or 0)
            )

            return quote

        except Exception as e:
            logger.error(f"Error parsing quote: {e}")
            return None

    def _calculate_and_update_indicators(self, symbol: str) -> None:
        """Calculate ADX indicators for a symbol."""
        try:
            # Get latest quote
            latest_quote = self.latest_quotes.get(symbol)
            if not latest_quote:
                return

            # Calculate indicators using analysis service
            indicators = self.analysis_service.calculate_single_indicator(
                symbol=symbol,
                high=latest_quote.high,
                low=latest_quote.low,
                close=latest_quote.ltp,
                timestamp=latest_quote.timestamp
            )

            if indicators:
                # Store latest indicators
                self.latest_indicators[symbol] = indicators

                # Notify indicator callbacks
                for callback in self.indicator_callbacks:
                    try:
                        callback(indicators)
                    except Exception as e:
                        logger.error(f"Error in indicator callback: {e}")

        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")

    def _extract_symbol(self, data: Dict) -> Optional[str]:
        """Extract symbol from WebSocket data."""
        symbol = data.get('symbol', data.get('fytoken', ''))
        return symbol if symbol else None

    def _format_symbol_for_ws(self, symbol: str) -> str:
        """
        Format symbol for Fyers WebSocket subscription.

        Args:
            symbol: Symbol in format NSE:RELIANCE-EQ or NSE:NIFTY25NOV24000CE

        Returns:
            Formatted symbol string
        """
        # Fyers WebSocket expects symbols in the format: NSE:RELIANCE-EQ
        # This is already our standard format, so just return as-is
        return symbol

    async def _reconnect(self) -> None:
        """Attempt to reconnect to WebSocket."""
        await asyncio.sleep(self.reconnect_delay)

        if await self.connect():
            # Re-subscribe to symbols
            if self.subscribed_symbols:
                await self.subscribe_symbols(list(self.subscribed_symbols))

    def register_quote_callback(self, callback: Callable[[LiveQuote], None]) -> None:
        """
        Register callback for quote updates.

        Args:
            callback: Function to call with LiveQuote
        """
        self.quote_callbacks.append(callback)

    def register_indicator_callback(self, callback: Callable[[ADXIndicators], None]) -> None:
        """
        Register callback for indicator updates.

        Args:
            callback: Function to call with ADXIndicators
        """
        self.indicator_callbacks.append(callback)

    def register_error_callback(self, callback: Callable) -> None:
        """
        Register callback for errors.

        Args:
            callback: Function to call on error
        """
        self.error_callbacks.append(callback)

    def get_latest_quote(self, symbol: str) -> Optional[LiveQuote]:
        """
        Get latest quote for a symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            Latest LiveQuote or None
        """
        return self.latest_quotes.get(symbol)

    def get_latest_indicators(self, symbol: str) -> Optional[ADXIndicators]:
        """
        Get latest indicators for a symbol.

        Args:
            symbol: Symbol identifier

        Returns:
            Latest ADXIndicators or None
        """
        return self.latest_indicators.get(symbol)

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self.is_running = False

        if self.ws_instance and self.is_connected:
            try:
                self.ws_instance.close()
                logger.info("WebSocket disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

        self.is_connected = False

    def get_connection_status(self) -> Dict:
        """
        Get connection status information.

        Returns:
            Dict with connection details
        """
        return {
            'is_connected': self.is_connected,
            'is_running': self.is_running,
            'subscribed_symbols': len(self.subscribed_symbols),
            'reconnect_attempts': self.reconnect_attempts,
            'latest_quotes': len(self.latest_quotes),
            'latest_indicators': len(self.latest_indicators)
        }


class HybridADXDataService:
    """
    Hybrid data service combining WebSocket and REST API.

    Uses WebSocket for real-time data with REST API fallback.
    """

    def __init__(
        self,
        fyers_config: FyersConfig,
        strategy_config: ADXStrategyConfig,
        symbols: List[str]
    ):
        """Initialize hybrid service."""
        self.fyers_config = fyers_config
        self.strategy_config = strategy_config
        self.symbols = symbols

        # WebSocket service
        self.ws_service = FyersWebSocketService(
            fyers_config, strategy_config, symbols
        )

        # REST API instance (for fallback)
        if FYERS_AVAILABLE:
            self.fyers_api = fyersModel.FyersModel(
                client_id=fyers_config.client_id,
                token=fyers_config.access_token,
                log_path="logs/"
            )
        else:
            self.fyers_api = None

        self.use_websocket = True
        self.rest_fallback_count = 0

        logger.info("Initialized HybridADXDataService")

    async def start(self) -> bool:
        """Start the data service."""
        try:
            # Try WebSocket first
            logger.info("Attempting WebSocket connection...")
            if await self.ws_service.connect():
                await self.ws_service.subscribe_symbols()
                self.use_websocket = True
                logger.info("Using WebSocket for real-time data")
                return True
        except Exception as e:
            logger.error(f"WebSocket initialization failed: {e}")

        # Fallback to REST
        logger.warning("⚠ WebSocket failed, using REST API fallback")
        self.use_websocket = False

        if self.fyers_api is None:
            logger.error("✗ REST API also not available - no data source")
            return False

        logger.info("✓ Using REST API for data (polling mode)")
        return True

    async def get_quote(self, symbol: str) -> Optional[LiveQuote]:
        """
        Get quote with WebSocket or REST fallback.

        Args:
            symbol: Symbol identifier

        Returns:
            LiveQuote or None
        """
        if self.use_websocket:
            quote = self.ws_service.get_latest_quote(symbol)
            if quote:
                return quote

        # REST API fallback
        return await self._get_quote_from_rest(symbol)

    async def _get_quote_from_rest(self, symbol: str) -> Optional[LiveQuote]:
        """Get quote from REST API."""
        if not self.fyers_api:
            logger.debug("REST API not available")
            return None

        try:
            self.rest_fallback_count += 1

            # Fyers REST API call
            data = {
                "symbols": symbol
            }

            response = self.fyers_api.quotes(data)

            if response and response.get('s') == 'ok':
                # Handle response - Fyers returns data in 'd' key
                if 'd' not in response or not response['d']:
                    logger.debug(f"No data in response for {symbol}")
                    return None

                quote_data = response['d'][0]['v']  # 'v' contains the quote values

                quote = LiveQuote(
                    symbol=symbol,
                    timestamp=datetime.now(),
                    ltp=float(quote_data.get('lp', 0)),
                    open=float(quote_data.get('open_price', 0)),
                    high=float(quote_data.get('high_price', 0)),
                    low=float(quote_data.get('low_price', 0)),
                    close=float(quote_data.get('prev_close_price', 0)),
                    volume=int(quote_data.get('volume', 0))
                )

                return quote
            else:
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                logger.debug(f"REST API error for {symbol}: {error_msg}")
                return None

        except Exception as e:
            logger.error(f"Error getting quote from REST for {symbol}: {e}")
            return None


# Example usage
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    # Example configuration
    fyers_config = FyersConfig()
    strategy_config = ADXStrategyConfig()
    symbols = ["NSE:RELIANCE-EQ", "NSE:TCS-EQ"]

    # Create service
    service = FyersWebSocketService(fyers_config, strategy_config, symbols)

    # Example callbacks
    def on_quote(quote: LiveQuote):
        print(f"Quote: {quote.symbol} @ {quote.ltp}")

    def on_indicator(indicator: ADXIndicators):
        print(f"Indicator: {indicator}")

    service.register_quote_callback(on_quote)
    service.register_indicator_callback(on_indicator)

    # Run example
    async def example():
        if await service.connect():
            await service.subscribe_symbols()
            await asyncio.sleep(60)  # Run for 60 seconds
            await service.disconnect()

    # asyncio.run(example())
    print("WebSocket service example ready")