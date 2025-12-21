# FyersADX - ADX DI Crossover Trading Strategy

A production-ready Python algorithmic trading system implementing the ADX DI Crossover strategy with real-time WebSocket integration and comprehensive backtesting capabilities.

## 🎯 Strategy Overview

The ADX DI Crossover Strategy identifies trend reversals using Directional Indicator (+DI and -DI) crossovers:

- **LONG Signal**: +DI crosses above -DI with volume confirmation
- **SHORT Signal**: -DI crosses above +DI with volume confirmation
- **Exit**: Opposite crossover, trailing stop, or mandatory 3:20 PM square-off

### Key Features

✅ Real-time DI crossover detection via WebSocket  
✅ Volume-filtered signal generation  
✅ Dynamic trailing stop loss  
✅ **Mandatory 3:20 PM square-off (no overnight positions)**  
✅ Multi-symbol support (50+ symbols)  
✅ Historical backtesting with SQLite databases  
✅ Comprehensive performance metrics  
✅ Auto-authentication with token refresh  

## 📁 Project Structure

```
FyersADX/
├── config/
│   ├── settings.py              # Strategy & trading configuration
│   ├── symbols.py               # Centralized symbol management
│   └── websocket_config.py      # WebSocket configuration
├── models/
│   └── trading_models.py        # Data models (ADXSignal, Position, etc.)
├── services/
│   ├── fyers_websocket_service.py   # Real-time data service
│   ├── analysis_service.py          # ADX/DI calculations
│   └── market_timing_service.py     # Market hours & square-off logic
├── strategy/
│   └── adx_strategy.py          # Main strategy implementation
├── utils/
│   └── enhanced_auth_helper.py  # Fyers authentication
├── backtesting/
│   ├── adx_backtest.py          # Historical backtesting
│   └── data_loader.py           # SQLite data loader
├── main.py                      # CLI entry point
├── requirements.txt
├── .env.template
└── README.md
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd FyersADX

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.template .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

Required credentials:
- Fyers Client ID
- Fyers Secret Key
- Trading PIN

### 3. Authentication

```bash
# Setup Fyers authentication
python main.py auth

# Update trading PIN if needed
python main.py update-pin
```

### 4. Validate Setup

```bash
# Run system diagnostics
python main.py diagnostics

# Test WebSocket connection
python main.py test

# Check market status
python main.py market
```

## 📊 Usage

### Live Trading

```bash
# Run live ADX strategy
python main.py run

# Run with custom config
python main.py run --config custom_config.env
```

### Backtesting

```bash
# Run historical backtest
python main.py backtest

# Backtest specific symbols
python main.py backtest --symbols RELIANCE TCS HDFCBANK

# Backtest with date range
python main.py backtest --start 2024-01-01 --end 2024-12-31
```

### Validation

```bash
# Validate configuration
python main.py validate

# Check symbol list
python main.py symbols
```

## ⚙️ Configuration

### Strategy Parameters

Edit `.env` file:

```bash
# Portfolio Settings
PORTFOLIO_VALUE=100000
RISK_PER_TRADE=1.0
MAX_POSITIONS=5

# ADX/DI Parameters
DI_PERIOD=14
VOLUME_THRESHOLD_PERCENTILE=60
MIN_VOLUME_RATIO=1.5
TRAILING_STOP_PCT=5.0

# Critical: Square-off time
SQUARE_OFF_TIME=15:20  # 3:20 PM IST

# Signal Filtering
MIN_DI_SEPARATION=2.0
MIN_ADX_STRENGTH=20.0
MIN_CONFIDENCE=0.60
```

### Symbol Management

Edit `config/symbols.py`:

```python
ACTIVE_SYMBOLS = [
    "NSE:RELIANCE-EQ",
    "NSE:TCS-EQ",
    "NSE:HDFCBANK-EQ",
    # Add more symbols...
]
```

## 📈 Strategy Logic

### Entry Conditions

1. **DI Crossover Detection**:
   - LONG: +DI crosses above -DI
   - SHORT: -DI crosses above +DI

2. **Volume Filter**:
   - Current volume > 60th percentile
   - Volume ratio vs 20-day average > 1.5x

3. **Quality Checks**:
   - Minimum DI separation (2.0 points)
   - Minimum ADX strength (20.0)
   - Confidence score > 60%

### Exit Conditions

1. **Signal-Based**: Opposite DI crossover
2. **Risk Management**: Trailing stop loss (5% from high/low)
3. **Time-Based**: **MANDATORY 3:20 PM square-off** (all positions)

### Risk Management

- Position sizing: 1% risk per trade
- Maximum positions: 5 concurrent
- Trailing stops: Dynamic 5% from high/low
- No overnight positions (3:20 PM exit)

## 🔬 Indicator Calculations

### +DI and -DI (Directional Indicators)

```
True Range (TR) = max(high - low, |high - prev_close|, |low - prev_close|)
DM+ = current_high - prev_high (if positive, else 0)
DM- = prev_low - current_low (if positive, else 0)

Smoothed TR = Wilder's EMA(TR, 14)
Smoothed DM+ = Wilder's EMA(DM+, 14)
Smoothed DM- = Wilder's EMA(DM-, 14)

+DI = 100 * (Smoothed DM+ / Smoothed TR)
-DI = 100 * (Smoothed DM- / Smoothed TR)
```

### ADX (Average Directional Index)

```
DX = 100 * |+DI - -DI| / |+DI + -DI|
ADX = Wilder's EMA(DX, 14)
```

## 📊 Output Examples

### Live Trading Status

```
ADX Strategy Status:
  Time: 2025-01-15 14:30:00 IST
  Positions: 3/5 (Long: 2, Short: 1)
  Daily P&L: ₹2,450.50
  Unrealized P&L: ₹1,230.00
  
Signals Today: 5
  - Executed: 3
  - Filtered: 2
  
Time to Square-Off: 50 minutes (3:20 PM IST)

Active Positions:
  RELIANCE (LONG): Entry ₹2,450 | Current ₹2,465 | P&L: +₹750
    DI+: 28.5 | DI-: 18.3 | ADX: 32.1 | Stop: ₹2,327.50
```

### Backtest Report

```
ADX DI CROSSOVER BACKTEST SUMMARY
=====================================
Period: 2024-01-01 to 2024-12-31
Symbols Analyzed: 45

Overall Performance:
  Total Return: +15.8%
  Total Trades: 287
  Win Rate: 62.4%
  Profit Factor: 2.15
  Max Drawdown: -3.2%

Exit Breakdown:
  3:20 PM Square-offs: 189 (65.9%)
  Signal Exits: 64 (22.3%)
  Trailing Stops: 34 (11.8%)
```

## 🧪 Testing

```bash
# Run unit tests
pytest tests/

# Run with coverage
pytest --cov=. tests/

# Run specific test module
pytest tests/test_analysis_service.py
```

## 📝 Logging

Logs are stored in `logs/` directory:
- `adx_strategy.log`: Main strategy log
- `websocket.log`: WebSocket connection log
- `backtest.log`: Backtesting results
- `trades.log`: Trade execution log

Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

## ️ Important Notes

### Critical Requirements

1. **3:20 PM Square-Off**: All positions are automatically closed at 3:20 PM IST daily. This is NON-NEGOTIABLE.
2. **No Overnight Positions**: System will not hold any positions beyond market hours.
3. **Volume Filtering**: Signals without volume confirmation are automatically rejected.

### Risk Disclaimer

**This software is for educational purposes only. Trading involves substantial risk of loss. Past performance is not indicative of future results. Always test thoroughly in paper trading mode before live deployment.**

### Regulatory Compliance

Ensure compliance with:
- SEBI regulations for algorithmic trading
- NSE/BSE broker requirements
- Risk management guidelines

## 🛠️ Troubleshooting

### WebSocket Connection Issues

```bash
# Test WebSocket connection
python main.py test

# Check diagnostics
python main.py diagnostics
```

### Authentication Errors

```bash
# Refresh authentication
python main.py auth

# Update PIN
python main.py update-pin
```

### Data Issues

```bash
# Validate data sources
python main.py validate

# Check symbol availability
python main.py symbols --validate
```

## 📚 Documentation

- [Strategy Guide](docs/strategy_guide.md)
- [API Reference](docs/api_reference.md)
- [Configuration Guide](docs/configuration.md)
- [Backtesting Guide](docs/backtesting.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🆘 Support

For issues and questions:
- GitHub Issues: [Create an issue]
- Email: support@example.com
- Documentation: [https://docs.example.com]

## 🙏 Acknowledgments

- Fyers API for market data integration
- Based on ADX indicator by J. Welles Wilder Jr.
- Inspired by FyersORB project architecture

---

**Version**: 1.0.0  
**Last Updated**: 2025-01-15  
**Status**: Production Ready