# FyersADX Configuration Template
# Copy this file to .env and fill in your actual values

# ============================================================================
# FYERS API CREDENTIALS
# ============================================================================
# Get these from: https://myapi.fyers.in/
FYERS_CLIENT_ID=your_client_id_here
FYERS_SECRET_KEY=your_secret_key_here
FYERS_REDIRECT_URI=http://localhost:8000/callback

# These will be auto-generated after authentication
FYERS_ACCESS_TOKEN=
FYERS_REFRESH_TOKEN=

# Trading PIN (required for order placement)
FYERS_PIN=your_trading_pin_here

# ============================================================================
# PORTFOLIO SETTINGS
# ============================================================================
PORTFOLIO_VALUE=100000
RISK_PER_TRADE=1.0
MAX_POSITIONS=5

# ============================================================================
# ADX/DI PARAMETERS
# ============================================================================
DI_PERIOD=14
VOLUME_THRESHOLD_PERCENTILE=60.0
MIN_VOLUME_RATIO=1.5
TRAILING_STOP_PCT=5.0
ENABLE_TRAILING_STOPS=true

# ============================================================================
# CRITICAL: SQUARE-OFF TIME
# ============================================================================
# Format: HH:MM (24-hour format, IST)
# MANDATORY: All positions will be closed at this time
SQUARE_OFF_TIME=15:20

# ============================================================================
# SIGNAL FILTERING
# ============================================================================
MIN_DI_SEPARATION=2.0
MIN_ADX_STRENGTH=20.0
MIN_CONFIDENCE=0.60
MAX_SIGNAL_AGE_SECONDS=30
ENABLE_VOLUME_FILTER=true
SIGNAL_GENERATION_END_TIME=14:00

# ============================================================================
# TRADING SYSTEM SETTINGS
# ============================================================================
# Paper trading mode (no real orders placed)
ENABLE_PAPER_TRADING=true

# Enable actual order execution (WARNING: Real money!)
ENABLE_ORDER_EXECUTION=false

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Monitoring intervals (seconds)
MONITORING_INTERVAL=10
DATA_UPDATE_INTERVAL=5

# ============================================================================
# RISK MANAGEMENT
# ============================================================================
MAX_DAILY_LOSS_PCT=5.0
MAX_DAILY_TRADES=20

# ============================================================================
# NOTIFICATIONS (Optional)
# ============================================================================
ENABLE_NOTIFICATIONS=false

# Email notifications (if enabled)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_TO=your_email@gmail.com

# SMS notifications (if enabled)
SMS_API_KEY=
SMS_PHONE_NUMBER=

# ============================================================================
# BACKTESTING CONFIGURATION
# ============================================================================
# Comma-separated list of database file paths
BACKTEST_DATA_SOURCES=data/market_data.db

# Date range for backtesting (YYYY-MM-DD format)
BACKTEST_START_DATE=2024-01-01
BACKTEST_END_DATE=2024-12-31

# Backtest parameters
BACKTEST_INITIAL_CAPITAL=100000
BACKTEST_COMMISSION_PCT=0.05
BACKTEST_SLIPPAGE_PCT=0.1
BACKTEST_MIN_DATA_POINTS=100
BACKTEST_EXPORT_RESULTS=true
BACKTEST_OUTPUT_DIR=backtest_results/

# ============================================================================
# ADVANCED SETTINGS
# ============================================================================
# WebSocket reconnection settings
WS_RECONNECT_DELAY=5
WS_MAX_RECONNECT_ATTEMPTS=10

# Data cache settings
ENABLE_DATA_CACHE=true
CACHE_EXPIRY_SECONDS=300

# Performance optimization
ENABLE_PARALLEL_PROCESSING=false
MAX_WORKER_THREADS=4