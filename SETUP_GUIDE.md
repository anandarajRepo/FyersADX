# FyersADX - Complete Setup Guide

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Fyers API Setup](#fyers-api-setup)
4. [Configuration](#configuration)
5. [Testing](#testing)
6. [Running the Strategy](#running-the-strategy)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **Python**: 3.9 or higher
- **Operating System**: Windows, macOS, or Linux
- **RAM**: Minimum 2GB (4GB recommended)
- **Disk Space**: 500MB free space

### Knowledge Requirements

- Basic understanding of Python
- Familiarity with command line/terminal
- Understanding of stock market trading
- Knowledge of algorithmic trading concepts

---

## Installation

### Step 1: Clone/Download Project

```bash
# If using git
git clone <repository-url>
cd FyersADX

# Or download and extract the ZIP file
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt

# Verify installation
pip list
```

---

## Fyers API Setup

### Step 1: Create Fyers Account

1. Visit [Fyers](https://fyers.in/)
2. Create a trading account
3. Complete KYC verification

### Step 2: Get API Credentials

1. Log in to [Fyers API Dashboard](https://myapi.fyers.in/)
2. Create a new app:
   - **App Name**: FyersADX
   - **Redirect URI**: `http://localhost:8000/callback`
   - **App Type**: Web App
3. Note down:
   - **Client ID** (e.g., `ABC123-100`)
   - **Secret Key**

### Step 3: Set Trading PIN

1. In your Fyers account, go to Settings
2. Set up your Trading PIN
3. Remember this PIN (required for order placement)

---

## Configuration

### Step 1: Environment Setup

```bash
# Copy the template
cp .env.template .env

# Edit the .env file
nano .env  # or use any text editor
```

### Step 2: Configure Credentials

Edit `.env` and fill in your Fyers credentials:

```bash
# Fyers API Credentials
FYERS_CLIENT_ID=YOUR_CLIENT_ID_HERE
FYERS_SECRET_KEY=YOUR_SECRET_KEY_HERE
FYERS_PIN=YOUR_TRADING_PIN
```

### Step 3: Configure Strategy Parameters

Adjust strategy settings in `.env`:

```bash
# Portfolio Settings
PORTFOLIO_VALUE=100000        # Your capital
RISK_PER_TRADE=1.0           # Risk 1% per trade
MAX_POSITIONS=5              # Maximum 5 concurrent positions

# ADX Parameters
DI_PERIOD=14                 # Standard ADX period
MIN_DI_SEPARATION=2.0        # Minimum +DI/-DI gap
MIN_ADX_STRENGTH=20.0        # Minimum ADX for signals

# CRITICAL: Square-off time (IST)
SQUARE_OFF_TIME=15:20        # 3:20 PM mandatory exit
```

### Step 4: Trading Mode Selection

Choose your trading mode:

```bash
# For paper trading (recommended for testing)
ENABLE_PAPER_TRADING=true
ENABLE_ORDER_EXECUTION=false

# For live trading (REAL MONEY - use with caution)
ENABLE_PAPER_TRADING=false
ENABLE_ORDER_EXECUTION=true
```

⚠️ **WARNING**: Always start with paper trading!

---

## Testing

### Step 1: Validate Configuration

```bash
# Check if configuration is valid
python main.py validate
```

Expected output:
```
✓ Configuration is valid
✓ All settings valid
```

### Step 2: Test Authentication

```bash
# Run authentication setup
python main.py auth
```

This will:
1. Generate authorization URL
2. Open browser for OAuth flow
3. Save access tokens

### Step 3: Check Market Status

```bash
# Verify market timing
python main.py market
```

### Step 4: Run System Diagnostics

```bash
# Complete system check
python main.py diagnostics
```

All checks should show ✓ (green checkmark).

---

## Running the Strategy

### Paper Trading (Recommended First)

```bash
# Start strategy in paper trading mode
python main.py run --paper
```

What happens:
- Strategy monitors all configured symbols
- Generates signals based on DI crossovers
- Simulates position entry/exit
- NO REAL ORDERS are placed
- All positions squared off at 3:20 PM

### Live Trading (Real Money)

⚠️ **CRITICAL WARNING**: This involves REAL money!

Before live trading:
1. ✅ Test thoroughly in paper trading mode
2. ✅ Understand the strategy completely
3. ✅ Start with small capital
4. ✅ Set appropriate risk limits
5. ✅ Monitor continuously during market hours

```bash
# Ensure live trading is enabled in .env
ENABLE_PAPER_TRADING=false
ENABLE_ORDER_EXECUTION=true

# Start live trading
python main.py run
```

### Monitoring

The strategy will display real-time updates:

```
ADX Strategy Status:
  Time: 2025-01-15 14:30:00 IST
  Positions: 3/5 (Long: 2, Short: 1)
  Daily P&L: ₹2,450.50
  Time to Square-Off: 50 minutes
```

### Stopping the Strategy

To stop gracefully:
- Press `Ctrl+C` once
- Strategy will attempt to close positions
- Wait for confirmation

---

## Backtesting

### Prepare Data

```bash
# Place your SQLite databases in data/ folder
mkdir -p data
# Copy your .db files to data/
```

### Run Backtest

```bash
# Backtest all symbols
python main.py backtest

# Backtest specific date range
python main.py backtest --start-date 2024-01-01 --end-date 2024-12-31

# Backtest specific symbols
python main.py backtest -sym NSE:RELIANCE-EQ -sym NSE:TCS-EQ
```

### Review Results

Results are saved in `backtest_results/`:
- `trades_YYYYMMDD_HHMMSS.csv`: All trades
- `equity_curve_YYYYMMDD_HHMMSS.csv`: Portfolio value over time
- `summary_YYYYMMDD_HHMMSS.txt`: Performance summary

---

## Troubleshooting

### Issue: "Configuration Errors"

**Solution**:
1. Check `.env` file exists
2. Verify all required fields are filled
3. Run `python main.py validate`

### Issue: "Fyers Auth Failed"

**Solution**:
1. Verify credentials in `.env`
2. Check Client ID format (should include `-100`)
3. Ensure redirect URI matches: `http://localhost:8000/callback`
4. Re-run `python main.py auth`

### Issue: "Market is closed"

**Solution**:
- Strategy only runs during market hours (9:15 AM - 3:30 PM IST)
- Check time with `python main.py market`
- Wait for market to open

### Issue: "No signals generated"

**Possible reasons**:
1. **Market conditions**: No DI crossovers occurring
2. **Volume filter**: Current volume too low
3. **ADX strength**: ADX below minimum threshold (20)
4. **Time**: After 2:00 PM (signal cutoff time)

**Solution**:
- Check ADX indicators are calculating correctly
- Review filter settings in `.env`
- Monitor during more volatile market periods

### Issue: "Positions not squaring off at 3:20 PM"

**Solution**:
This is a CRITICAL issue. Check:
1. System time is correct and in IST
2. `SQUARE_OFF_TIME` in `.env` is set to `15:20`
3. Review logs in `logs/` directory
4. If problem persists, STOP live trading immediately

### Issue: "Import errors"

**Solution**:
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify Python version
python --version  # Should be 3.9+
```

### Issue: "WebSocket connection failed"

**Solution**:
1. Check internet connection
2. Verify Fyers API is accessible
3. Check firewall settings
4. Review logs for specific error

---

## Important Notes

### Daily Workflow

1. **Before Market Open (9:15 AM)**:
   - Verify system is running
   - Check market status: `python main.py market`
   - Review configuration

2. **During Market Hours**:
   - Monitor strategy output
   - Keep terminal/console open
   - Don't interrupt the process

3. **3:20 PM (Square-off Time)**:
   - All positions will be automatically closed
   - Review daily performance
   - Check logs for any issues

4. **After Market Close**:
   - Review `logs/` for the day's activity
   - Analyze performance
   - Adjust parameters if needed (for next day)

### Risk Management

- **Never risk more than 2% per trade**
- **Set `MAX_POSITIONS` appropriately** (5 is recommended)
- **Use stop losses** (automatically managed)
- **Monitor daily loss limit**: Strategy stops if exceeded
- **Always paper trade first**: Test for at least 1-2 weeks

### Emergency Procedures

If something goes wrong:

1. **Stop the strategy**: Press `Ctrl+C`
2. **Check positions**: Log in to Fyers app/web
3. **Manual square-off**: If needed, close positions manually
4. **Review logs**: Check `logs/` directory
5. **Contact support**: If issue persists

### Support Contacts

- **Fyers Support**: support@fyers.in
- **Fyers API**: api@fyers.in
- **Project Issues**: [GitHub Issues]

---

## Next Steps

After successful setup:

1. ✅ Run paper trading for 1-2 weeks
2. ✅ Analyze backtest results
3. ✅ Understand all exit scenarios
4. ✅ Optimize parameters based on data
5. ✅ Start live trading with small capital
6. ✅ Gradually increase position sizes

---

## Helpful Commands

```bash
# Quick reference
python main.py validate      # Check configuration
python main.py auth          # Setup authentication
python main.py market        # Show market status
python main.py diagnostics   # System health check
python main.py symbols       # List available symbols
python main.py run --paper   # Paper trading
python main.py run           # Live trading
python main.py backtest      # Historical backtesting
python main.py status        # Current status
python main.py performance   # Performance metrics
```

---

## Updates and Maintenance

### Updating Dependencies

```bash
# Activate virtual environment first
pip install -r requirements.txt --upgrade
```

### Backing Up Data

```bash
# Backup important files
cp .env .env.backup
cp -r logs/ logs_backup/
cp -r data/ data_backup/
```

### Log Rotation

Logs are saved daily in `logs/` directory:
- Keep recent logs for analysis
- Archive/delete old logs regularly
- Consider automated log rotation

---

## Disclaimer

⚠️ **IMPORTANT DISCLAIMER**:

This software is for **EDUCATIONAL AND RESEARCH PURPOSES ONLY**.

- **Trading involves substantial risk** of loss
- **Past performance is NOT indicative** of future results
- **No guarantees** of profitability
- **Test thoroughly** before live deployment
- **Use at your own risk**
- **The authors/contributors are NOT responsible** for any financial losses

Always consult with a qualified financial advisor before trading.

---

## License

See LICENSE file for details.

---

## Version History

- **v1.0.0** (2025-01-15): Initial release
  - Core ADX DI Crossover strategy
  - Real-time WebSocket integration
  - Backtesting engine
  - Mandatory 3:20 PM square-off
  - Paper and live trading modes

---

**Happy Trading! 🚀📈**