"""
__init__.py files for all packages in FyersADX project.

Create these files in the respective directories to make them Python packages.
"""

# ============================================================================
# config/__init__.py
# ============================================================================
"""Configuration package for FyersADX."""

from .settings import (
    ADXStrategyConfig,
    FyersConfig,
    TradingConfig,
    BacktestConfig,
    ConfigManager,
    config
)

__all__ = [
    'ADXStrategyConfig',
    'FyersConfig',
    'TradingConfig',
    'BacktestConfig',
    'ConfigManager',
    'config'
]

# ============================================================================
# models/__init__.py
# ============================================================================
"""Data models package for FyersADX."""

from models.trading_models import (
    SignalType,
    SymbolCategory,
    ExitReason,
    OrderStatus,
    LiveQuote,
    ADXIndicators,
    ADXSignal,
    Position,
    TradeResult,
    StrategyMetrics
)

__all__ = [
    'SignalType',
    'SymbolCategory',
    'ExitReason',
    'OrderStatus',
    'LiveQuote',
    'ADXIndicators',
    'ADXSignal',
    'Position',
    'TradeResult',
    'StrategyMetrics'
]

# ============================================================================
# services/__init__.py
# ============================================================================
"""Services package for FyersADX."""

from  services.analysis_service import ADXTechnicalAnalysisService
from services.market_timing_service import MarketTimingService
from services.fyers_websocket_service import FyersWebSocketService, HybridADXDataService

__all__ = [
    'ADXTechnicalAnalysisService',
    'MarketTimingService',
    'FyersWebSocketService',
    'HybridADXDataService'
]

# ============================================================================
# strategy/__init__.py
# ============================================================================
"""Strategy package for FyersADX."""

from strategy.adx_strategy import ADXStrategy

__all__ = [
    'ADXStrategy'
]

# ============================================================================
# utils/__init__.py
# ============================================================================
"""Utilities package for FyersADX."""

from utils.enhanced_auth_helper import (
    FyersAuthenticationHelper,
    authenticate_fyers,
    ensure_authenticated
)

__all__ = [
    'FyersAuthenticationHelper',
    'authenticate_fyers',
    'ensure_authenticated'
]

# ============================================================================
# backtesting/__init__.py
# ============================================================================
"""Backtesting package for FyersADX."""

from backtest.adx_backtest import ADXBacktester, BacktestPosition
from backtest.data_loader import SQLiteDataLoader, load_data

__all__ = [
    'ADXBacktester',
    'BacktestPosition',
    'SQLiteDataLoader',
    'load_data'
]

# ============================================================================
# INSTALLATION INSTRUCTIONS
# ============================================================================
"""
To set up __init__.py files:

1. Create config/__init__.py and paste the config/__init__.py section above
2. Create models/__init__.py and paste the models/__init__.py section above
3. Create services/__init__.py and paste the services/__init__.py section above
4. Create strategy/__init__.py and paste the strategy/__init__.py section above
5. Create utils/__init__.py and paste the utils/__init__.py section above
6. Create backtesting/__init__.py and paste the backtesting/__init__.py section above

Each section is marked with comments showing which file it belongs to.

Alternatively, run this Python script to create all files automatically:
"""

# ============================================================================
# AUTO-GENERATION SCRIPT
# ============================================================================

if __name__ == "__main__":
    import os
    from pathlib import Path

    # Define __init__ content for each package
    init_contents = {
        'config': '''"""Configuration package for FyersADX."""

from .settings import (
    ADXStrategyConfig,
    FyersConfig,
    TradingConfig,
    BacktestConfig,
    ConfigManager,
    config
)

__all__ = [
    'ADXStrategyConfig',
    'FyersConfig',
    'TradingConfig',
    'BacktestConfig',
    'ConfigManager',
    'config'
]
''',
        'models': '''"""Data models package for FyersADX."""

from .trading_models import (
    SignalType,
    SymbolCategory,
    ExitReason,
    OrderStatus,
    LiveQuote,
    ADXIndicators,
    ADXSignal,
    Position,
    TradeResult,
    StrategyMetrics
)

__all__ = [
    'SignalType',
    'SymbolCategory',
    'ExitReason',
    'OrderStatus',
    'LiveQuote',
    'ADXIndicators',
    'ADXSignal',
    'Position',
    'TradeResult',
    'StrategyMetrics'
]
''',
        'services': '''"""Services package for FyersADX."""

from .analysis_service import ADXTechnicalAnalysisService
from .market_timing_service import MarketTimingService
from .fyers_websocket_service import FyersWebSocketService, HybridADXDataService

__all__ = [
    'ADXTechnicalAnalysisService',
    'MarketTimingService',
    'FyersWebSocketService',
    'HybridADXDataService'
]
''',
        'strategy': '''"""Strategy package for FyersADX."""

from .adx_strategy import ADXStrategy

__all__ = [
    'ADXStrategy'
]
''',
        'utils': '''"""Utilities package for FyersADX."""

from .enhanced_auth_helper import (
    FyersAuthenticationHelper,
    authenticate_fyers,
    ensure_authenticated
)

__all__ = [
    'FyersAuthenticationHelper',
    'authenticate_fyers',
    'ensure_authenticated'
]
''',
        'backtesting': '''"""Backtesting package for FyersADX."""

from .adx_backtest import ADXBacktester, BacktestPosition
from .data_loader import SQLiteDataLoader, load_data

__all__ = [
    'ADXBacktester',
    'BacktestPosition',
    'SQLiteDataLoader',
    'load_data'
]
'''
    }

    print("Creating __init__.py files for all packages...")
    print("=" * 60)

    for package, content in init_contents.items():
        # Create directory if it doesn't exist
        Path(package).mkdir(exist_ok=True)

        # Create __init__.py file
        init_file = Path(package) / '__init__.py'

        with open(init_file, 'w') as f:
            f.write(content)

        print(f"Created {init_file}")

    print("=" * 60)
    print("All __init__.py files created successfully!")
    print("\nYou can now import modules like:")
    print("  from config import config")
    print("  from models import ADXSignal, Position")
    print("  from services import ADXTechnicalAnalysisService")
    print("  from strategy import ADXStrategy")