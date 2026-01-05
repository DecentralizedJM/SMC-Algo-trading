"""
SMC Trading Bot - Smart Money Concepts Automated Trading

Uses ICT concepts (Order Blocks, FVG, BOS/CHoCH) for entry signals
and Mudrex SDK for trade execution on crypto futures.
"""

import json
import time
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict

from mudrex import MudrexClient
from market_data import BybitDataFetcher
from smc_indicators import calculate_smc
from strategy import SMCStrategy
from executor import MudrexExecutor
from tracker import TradeTracker

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SMCTradingBot:
    """Smart Money Concepts automated trading bot."""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the bot with configuration."""
        import os
        
        # Load config
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Override with environment variables if set (for Railway deployment)
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
            self.config["bot"]["dry_run"] = os.environ.get("DRY_RUN", "false").lower() == "true"
        
        # Initialize Mudrex client to fetch symbols
        self.mudrex_client = MudrexClient(api_secret=self.config["mudrex"]["api_secret"])
        
        # Initialize components
        self.data_fetcher = BybitDataFetcher()
        
        self.strategy = SMCStrategy(
            swing_length=self.config["strategy"]["swing_length"],
            ob_lookback=self.config["strategy"]["ob_lookback"],
            fvg_join_consecutive=self.config["strategy"]["fvg_join_consecutive"],
            atr_period=self.config["strategy"]["atr_period"],
            tp_atr_mult=self.config["strategy"]["tp_atr_mult"],
            sl_atr_mult=self.config["strategy"]["sl_atr_mult"],
            require_fvg_confluence=self.config["strategy"]["require_fvg_confluence"]
        )
        
        self.executor = MudrexExecutor(
            api_secret=self.config["mudrex"]["api_secret"],
            margin_per_trade=self.config["mudrex"]["margin_per_trade"],
            max_leverage=self.config["mudrex"]["leverage"]
        )
        
        self.tracker = TradeTracker("trades.json")
        
        # Fetch all available symbols from Mudrex
        self.symbols = self._fetch_tradeable_symbols()
        
        self.timeframe = self.config["strategy"]["timeframe"]
        self.dry_run = self.config["bot"]["dry_run"]
        
        # Track positions
        self.current_positions: Dict[str, dict] = {}  # {symbol: position_data}
        self.max_positions = self.config["mudrex"]["max_positions"]
        self.last_check_time = None
        
        self._print_startup_info()
    
    def _print_startup_info(self):
        """Print startup information."""
        logger.info("="*60)
        logger.info("🧠 SMC Trading Bot - Smart Money Concepts")
        logger.info("="*60)
        logger.info(f"Total Symbols:   {len(self.symbols)}")
        logger.info(f"Timeframe:       {self.timeframe}m")
        logger.info(f"Leverage:        {self.config['mudrex']['leverage']}x")
        logger.info(f"Margin/Trade:    ${self.config['mudrex']['margin_per_trade']}")
        logger.info(f"Max Positions:   {self.max_positions}")
        logger.info(f"Mode:            {'DRY RUN 🧪' if self.dry_run else 'LIVE TRADING ⚠️'}")
        logger.info("-"*60)
        logger.info(f"Strategy: Order Block entries with BOS/CHoCH confirmation")
        logger.info(f"Swing Length:    {self.config['strategy']['swing_length']}")
        logger.info(f"OB Lookback:     {self.config['strategy']['ob_lookback']}")
        logger.info(f"FVG Confluence:  {'Required' if self.config['strategy']['require_fvg_confluence'] else 'Optional'}")
        logger.info("="*60)
        
        # Print current stats
        self.tracker.print_summary()
    
    def _fetch_tradeable_symbols(self) -> List[str]:
        """Fetch all tradeable symbols from Mudrex SDK."""
        logger.info("📊 Fetching available symbols from Mudrex...")
        
        try:
            all_assets = self.mudrex_client.assets.list_all()
            logger.info(f"✅ Found {len(all_assets)} total assets")
            
            # Apply filters
            quote_currency = self.config["mudrex"]["filter"]["quote_currency"]
            max_symbols = self.config["mudrex"]["filter"]["max_symbols"]
            
            filtered = []
            for asset in all_assets:
                if not asset.symbol.endswith(quote_currency):
                    continue
                filtered.append(asset.symbol)
            
            symbols = filtered[:max_symbols] if len(filtered) > max_symbols else filtered
            logger.info(f"✅ Filtered to {len(symbols)} {quote_currency} pairs")
            
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch symbols: {e}")
            fallback = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
            logger.warning(f"⚠️ Using fallback: {fallback}")
            return fallback
    
    def scan_symbol(self, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        """
        Scan a single symbol for entry signals.
        
        Returns:
            (side, details) if signal found, else (None, None)
        """
        try:
            # Fetch klines from Bybit
            df = self.data_fetcher.get_klines(symbol, self.timeframe, limit=200)
            if df is None or len(df) < 100:
                return None, None
            
            # Calculate SMC indicators
            df = self.strategy.analyze(df)
            
            # Check signals
            long_signal, long_details = self.strategy.check_long_signal(df)
            short_signal, short_details = self.strategy.check_short_signal(df)
            
            if long_signal:
                long_details["symbol"] = symbol
                return "LONG", long_details
            elif short_signal:
                short_details["symbol"] = symbol
                return "SHORT", short_details
            
            return None, None
            
        except Exception as e:
            # Silently skip symbols with errors
            return None, None
    
    def scan_all_symbols(self) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
        """
        Scan all configured symbols for signals.
        
        Returns:
            (symbol, side, details) for first signal found
        """
        logger.info(f"🔍 Scanning {len(self.symbols)} symbols for SMC setups...")
        
        delay_ms = self.config["mudrex"].get("scan_delay_ms", 150)
        delay_sec = delay_ms / 1000.0
        
        scanned = 0
        for symbol in self.symbols:
            scanned += 1
            if scanned % 25 == 0:
                logger.info(f"   Progress: {scanned}/{len(self.symbols)}...")
            
            if scanned > 1:
                time.sleep(delay_sec)
            
            side, details = self.scan_symbol(symbol)
            if side:
                logger.info(f"✅ Found {side} signal on {symbol}! (Scanned {scanned}/{len(self.symbols)})")
                return symbol, side, details
        
        logger.info(f"   Completed: {scanned}/{len(self.symbols)} symbols scanned")
        return None, None, None
    
    def execute_signal(self, symbol: str, side: str, details: dict):
        """Execute a trading signal."""
        entry_price = details["price"]
        atr = details["atr"]
        
        # Calculate TP/SL using OB levels
        tp, sl = self.strategy.calculate_tp_sl(
            entry_price,
            atr,
            side,
            ob_bottom=details.get("ob_bottom"),
            ob_top=details.get("ob_top")
        )
        
        logger.info("="*60)
        logger.info(f"🎯 {side} SIGNAL - {symbol}")
        logger.info("="*60)
        logger.info(f"Structure:   {details.get('structure_type')} (Level: ${details.get('structure_level', 0):,.4f})")
        logger.info(f"Order Block: ${details.get('ob_bottom', 0):,.4f} - ${details.get('ob_top', 0):,.4f}")
        logger.info(f"OB Strength: {details.get('ob_strength', 0):.1f}%")
        logger.info(f"Entry Price: ${entry_price:,.4f}")
        logger.info(f"Take Profit: ${tp:,.4f} (+{abs((tp-entry_price)/entry_price*100):.2f}%)")
        logger.info(f"Stop Loss:   ${sl:,.4f} ({-abs((sl-entry_price)/entry_price*100):.2f}%)")
        logger.info(f"ATR:         ${atr:,.4f}")
        logger.info(f"Positions:   {len(self.current_positions)}/{self.max_positions}")
        logger.info("="*60)
        
        if self.dry_run:
            logger.info("💤 DRY RUN MODE - Trade simulated, not executed")
            self.current_positions[symbol] = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "tp": tp,
                "sl": sl,
                "entry_time": datetime.now(),
                "details": details
            }
            return
        
        # Execute real trade
        order = self.executor.place_order(
            symbol=symbol,
            side=side,
            leverage=self.config["mudrex"]["leverage"],
            tp=tp,
            sl=sl,
            entry_price=entry_price
        )
        
        if order:
            self.current_positions[symbol] = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "tp": tp,
                "sl": sl,
                "entry_time": datetime.now(),
                "details": details
            }
            logger.info("✅ Trade executed successfully!")
        else:
            logger.error("❌ Trade execution failed!")
    
    def monitor_positions(self):
        """Monitor all positions for TP/SL and record closed trades."""
        if not self.current_positions:
            return
        
        to_close = []
        
        for symbol, pos in self.current_positions.items():
            current_price = self.data_fetcher.get_current_price(symbol)
            if not current_price:
                continue
            
            side = pos["side"]
            tp = pos["tp"]
            sl = pos["sl"]
            entry = pos["entry_price"]
            
            if side == "LONG":
                pnl_pct = (current_price - entry) / entry * 100
            else:
                pnl_pct = (entry - current_price) / entry * 100
            
            logger.info(f"📍 {symbol} {side}: ${current_price:,.4f} ({pnl_pct:+.2f}%)")
            
            # Check for TP/SL hit
            should_close = False
            exit_reason = "unknown"
            
            if side == "LONG":
                if current_price >= tp:
                    should_close = True
                    exit_reason = "TP"
                elif current_price <= sl:
                    should_close = True
                    exit_reason = "SL"
            else:  # SHORT
                if current_price <= tp:
                    should_close = True
                    exit_reason = "TP"
                elif current_price >= sl:
                    should_close = True
                    exit_reason = "SL"
            
            if should_close:
                pnl_pct_actual = pnl_pct * self.config["mudrex"]["leverage"]
                logger.info(f"🚪 Closing {symbol} @ ${current_price:,.4f} ({pnl_pct_actual:+.2f}% with leverage)")
                
                # Record trade
                self.tracker.record_trade(
                    symbol=symbol,
                    side=side,
                    entry_price=entry,
                    exit_price=current_price,
                    quantity=0,  # We don't track exact qty in dry run
                    leverage=self.config["mudrex"]["leverage"],
                    margin_used=self.config["mudrex"]["margin_per_trade"],
                    exit_reason=exit_reason,
                    entry_details={
                        "structure_type": pos["details"].get("structure_type"),
                        "ob_strength": pos["details"].get("ob_strength"),
                        "ob_bottom": pos["details"].get("ob_bottom"),
                        "ob_top": pos["details"].get("ob_top")
                    }
                )
                
                if not self.dry_run:
                    self.executor.close_position(symbol)
                
                to_close.append(symbol)
        
        for sym in to_close:
            del self.current_positions[sym]
    
    def run(self):
        """Main bot loop."""
        logger.info("🚀 Bot started! Scanning for SMC setups...")
        
        try:
            while True:
                self.last_check_time = datetime.now()
                
                # Monitor existing positions
                if self.current_positions:
                    self.monitor_positions()
                
                # Skip if at max positions
                if len(self.current_positions) >= self.max_positions:
                    logger.info(f"⏸️ Max positions reached ({len(self.current_positions)}/{self.max_positions})")
                    time.sleep(self.config["bot"]["check_interval_seconds"])
                    continue
                
                # Scan for new signals
                symbol, side, details = self.scan_all_symbols()
                
                if symbol and side:
                    if symbol in self.current_positions:
                        logger.info(f"⏭️ Skipping {symbol} - already have position")
                    else:
                        self.execute_signal(symbol, side, details)
                else:
                    logger.info(f"⏳ No signals. Positions: {len(self.current_positions)}/{self.max_positions}")
                
                # Print stats periodically
                if len(self.tracker.trades) > 0 and len(self.tracker.trades) % 5 == 0:
                    self.tracker.print_summary()
                
                # Sleep until next check
                time.sleep(self.config["bot"]["check_interval_seconds"])
                
        except KeyboardInterrupt:
            logger.info("\n👋 Bot stopped by user")
            self.tracker.print_summary()
        except Exception as e:
            logger.error(f"❌ Bot error: {e}", exc_info=True)


if __name__ == "__main__":
    bot = SMCTradingBot("config.json")
    bot.run()
