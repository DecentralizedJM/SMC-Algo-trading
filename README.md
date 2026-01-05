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
pip install git+https://github.com/DecentralizedJM/mudrex-api-trading-python-sdk.git
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
- `MUDREX_API_KEY`
- `MUDREX_API_SECRET`
