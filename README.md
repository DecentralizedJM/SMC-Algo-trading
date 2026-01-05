# SMC Trading Bot

Smart Money Concepts automated trading bot using ICT indicators and Mudrex API.

## Features

- **Smart Money Concepts**: Order Blocks, FVGs, BOS/CHoCH, Liquidity
- **Mudrex Integration**: Automated futures trading via SDK
- **Performance Tracking**: Win rate and ROI tracking with JSON persistence

## Setup

1. Install dependencies:
```bash
pip install smartmoneyconcepts pandas numpy requests
pip install mudrex-trading-sdk
```

2. Configure `config.json` with your API credentials

3. Run:
```bash
python bot.py
```

## Configuration

Edit `config.json`:
- `api_key` / `api_secret`: Your Mudrex API credentials
- `leverage`: Trading leverage (default: 20x)
- `margin_per_trade`: Margin per position (default: $2)
- `max_positions`: Maximum concurrent positions
- `dry_run`: Set to `false` for live trading

## Strategy

- **Entry**: Order Block + BOS/CHoCH confirmation
- **Take Profit**: 2x ATR
- **Stop Loss**: 1.5x ATR (or below Order Block)

## Environment Variables (for Railway)

Set these in Railway dashboard:

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `MUDREX_API_KEY` | ✅ | Your Mudrex API Key | - |
| `MUDREX_API_SECRET` | ✅ | Your Mudrex API Secret | - |
| `MARGIN_PER_TRADE` | ❌ | Margin per position in USD | 2.0 |
| `LEVERAGE` | ❌ | Trading leverage | 20 |
| `MAX_POSITIONS` | ❌ | Max concurrent positions | 5 |
| `DRY_RUN` | ❌ | Set to "true" for paper trading | false |
