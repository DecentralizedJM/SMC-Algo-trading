"""
SMC Trading Bot - Main Orchestrator
Scans the market, calculates SMC indicators, and executes trades via Mudrex.
"""

import logging
import time
import json
import os
from typing import Tuple, Optional
from market_data import BybitDataFetcher
from smc_indicators import calculate_smc
from strategy import StrategyManager
from executor import MudrexExecutor
from tracker import TradeTracker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SMCTradingBot:
    """Main trading bot class."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the bot with configuration."""
        import os
        
        # Load config - try primary path first, then template
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        elif os.path.exists("config.template.json"):
            logger.info("⚠️ config.json not found, using config.template.json")
            with open("config.template.json", 'r') as f:
                self.config = json.load(f)
        else:
            raise FileNotFoundError(f"Could not find {config_path} or config.template.json")
        
        # Override with environment variables if set (for Railway deployment)
        logger.info(f"Environment keys available: {[k for k in os.environ.keys() if 'API' in k or 'MUDREX' in k]}")
        
        api_key = os.environ.get("MUDREX_API_KEY", self.config["mudrex"].get("api_key", ""))
        api_secret = os.environ.get("MUDREX_API_SECRET", self.config["mudrex"].get("api_secret", ""))
        
        if not api_secret:
            raise ValueError("MUDREX_API_SECRET must be set in environment or config.json")
        
        self.config["mudrex"]["api_key"] = api_key
        self.config["mudrex"]["api_secret"] = api_secret
        
        # Trading settings from env vars
        if os.environ.get("MARGIN_PER_TRADE"):
            self.config["mudrex"]["margin_per_trade"] = float(os.environ.get("MARGIN_PER_TRADE"))
        if os.environ.get("LEVERAGE"):
            self.config["mudrex"]["leverage"] = int(os.environ.get("LEVERAGE"))
        if os.environ.get("MAX_POSITIONS"):
            self.config["mudrex"]["max_positions"] = int(os.environ.get("MAX_POSITIONS"))
        if os.environ.get("DRY_RUN"):
            self.config["bot"]["dry_run"] = os.environ.get("DRY_RUN").lower() == "true"
            
        # Initialize components
        self.fetcher = BybitDataFetcher()
        self.strategy = StrategyManager(self.config)
        self.executor = MudrexExecutor(self.config)
        self.tracker = TradeTracker()
        
        self.dry_run = self.config["bot"].get("dry_run", False)
        
        if self.dry_run:
            logger.info("⚠️ Bot starting in DRY RUN mode - No real trades will be executed")
        else:
            logger.info("🚨 Bot starting in LIVE TRADING mode")
            
    def scan_symbol(self, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        """Scan a single symbol for trading signals."""
        try:
            # 1. Fetch data
            timeframe = self.config["strategy"].get("timeframe", "15")
            
            # Fetch enough candles for all strategies (200 is safe default)
            df = self.fetcher.get_klines(symbol, timeframe, 200)
            
            if df is None:
                return None, None
                
            # 2. Calculate Indicators
            # Note: StrategyManager expects DF with indicators
            # We use common settings for indicators, strategies might use subsets
            df = calculate_smc(
                df, 
                swing_length=self.config["strategy"].get("swing_length", 10), # Legacy or common
                atr_period=self.config["strategy"].get("common", {}).get("atr_period", 14)
            )
            
            # 3. Check for Signals
            side, details = self.strategy.check_signals(df, symbol)
            
            if side:
                logger.info(f"✅ Found {side} signal on {symbol}: {details}")
                return side, details
                
            return None, None
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            return None, None
            
    def execute_signal(self, symbol: str, side: str, details: dict):
        """Execute a trade signal."""
        try:
            # Get current price
            price = self.fetcher.get_current_price(symbol)
            if not price:
                logger.error(f"Could not get current price for {symbol}")
                return

            # Calculate Exit Levels (SL/TP)
            # StrategyManager helper needs DF for ATR. Re-fetch minimal data.
            timeframe = self.config["strategy"].get("timeframe", "15")
            df = self.fetcher.get_klines(symbol, timeframe, 50)
            df = calculate_smc(df) # Need ATR
            
            sl_price, tp_price = self.strategy.get_exit_levels(price, side, df, details)
            
            logger.info(f"🚀 Executing {side} on {symbol} | Price: {price} | SL: {sl_price} | TP: {tp_price}")
            
            if self.dry_run:
                self.tracker.log_trade({
                    "symbol": symbol,
                    "side": side,
                    "entry_price": price,
                    "position_size": self.config["mudrex"]["margin_per_trade"],
                    "pnl": 0,
                    "status": "dry_run"
                })
                return

            # Execute via Mudrex
            order = self.executor.place_market_order(
                symbol, 
                side, 
                sl_price=sl_price, 
                tp_price=tp_price
            )
            
            if order:
                self.tracker.log_trade({
                    "symbol": symbol,
                    "side": side,
                    "entry_price": price,
                    "position_size": self.config["mudrex"]["margin_per_trade"],
                    "pnl": 0,
                    "status": "open",
                    "order_id": order.get("id")
                })
                
        except Exception as e:
            logger.error(f"Execution failed for {symbol}: {e}")

    def run(self):
        """Run the main bot loop."""
        logger.info("============================================================")
        logger.info("🧠 SMC Trading Bot - Smart Money Concepts")
        logger.info("============================================================")
        
        # Get count of symbols to scan
        symbols = self.executor.get_available_symbols()
        # Filter symbols
        quote_currency = self.config["mudrex"]["filter"]["quote_currency"]
        symbols = [s for s in symbols if s.endswith(quote_currency)]
        max_symbols = self.config["mudrex"]["filter"]["max_symbols"]
        symbols = symbols[:max_symbols]
        
        logger.info(f"Total Symbols:   {len(symbols)}")
        logger.info(f"Timeframe:       {self.config['strategy'].get('timeframe', '15')}m")
        logger.info(f"Leverage:        {self.config['mudrex']['leverage']}x")
        logger.info(f"Margin/Trade:    ${self.config['mudrex']['margin_per_trade']}")
        logger.info(f"Max Positions:   {self.config['mudrex']['max_positions']}")
        mode = "DRY RUN 🧪" if self.dry_run else "LIVE TRADING ⚠️"
        logger.info(f"Mode:            {mode}")
        logger.info("------------------------------------------------------------")
        
        # Print active strategies
        active = self.config["strategy"].get("active_strategies", ["order_block"])
        logger.info(f"Active Strategies: {active}")
        logger.info("============================================================")
        
        while True:
            try:
                # 1. Check open positions (Take Profit / Stop Loss is handled by Mudrex/Exchange)
                # But we can track them here
                open_positions = self.executor.get_open_positions()
                
                # Update tracker
                self.tracker.print_summary()
                
                if len(open_positions) >= self.config["mudrex"]["max_positions"]:
                    logger.info(f"⏳ Max positions reached ({len(open_positions)}). Waiting...")
                    time.sleep(60)
                    continue
                
                logger.info(f"🔍 Scanning {len(symbols)} symbols for SMC setups...")
                
                for i, symbol in enumerate(symbols):
                    # Progress log every 25 symbols
                    if i > 0 and i % 25 == 0:
                        logger.info(f"   Progress: {i}/{len(symbols)}...")
                        
                    # Scan
                    side, details = self.scan_symbol(symbol)
                    
                    if side:
                        self.execute_signal(symbol, side, details)
                        
                        # Stop scanning if max positions reached
                        if len(self.executor.get_open_positions()) >= self.config["mudrex"]["max_positions"]:
                            break
                            
                    # Rate limit scan delay
                    time.sleep(self.config["mudrex"]["scan_delay_ms"] / 1000)
                    
                logger.info("⏳ Scan complete. Waiting for next cycle...")
                
                # Wait for next cycle
                time.sleep(self.config["bot"]["check_interval_seconds"])
                
            except KeyboardInterrupt:
                logger.info("\n👋 Bot stopped by user")
                self.tracker.print_summary()
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    bot = SMCTradingBot() # Uses config.json or fallback
    bot.run()
