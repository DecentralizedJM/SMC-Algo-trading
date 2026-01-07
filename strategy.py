"""
SMC Strategy Module - Implements multiple Smart Money Concept strategies.
Strategies:
1. Order Block (Conservative) - Entry at OB with structure confirmation
2. Liquidity Sweep (Aggressive) - Entry after sweep of key level + rejection
3. Silver Bullet (Time-based) - Entry at specific windows with FVG confluence
"""

import logging
import pandas as pd
from datetime import datetime
import pytz
from typing import Dict, Tuple, Optional, List
from smc_indicators import calculate_smc, get_active_order_blocks, get_active_fvgs, get_latest_structure

logger = logging.getLogger(__name__)

class BaseStrategy:
    """Base class for all strategies."""
    
    def __init__(self, config: dict):
        self.config = config
        
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        """Return ('LONG'/'SHORT', details) or (None, None)."""
        raise NotImplementedError

class OrderBlockStrategy(BaseStrategy):
    """
    Original Conservative Strategy:
    1. Identify active unmitigated Order Blocks (OB)
    2. Wait for price to touch OB
    3. Confirm with Break of Structure (BOS) or Change of Character (CHoCH)
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = config.get("order_block", {})
        
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        if df is None or len(df) < 50:
            return None, None
            
        current_price = df.iloc[-1]["close"]
        
        # Get active OBs
        obs = get_active_order_blocks(df, lookback=self.cfg.get("lookback", 50))
        
        # Check Long (Bullish OB)
        for ob in obs["bullish"]:
            # OB format: (index, top, bottom, strength)
            ob_top = ob[1]
            ob_bottom = ob[2]
            
            # Check if price is inside or near OB
            if ob_bottom <= current_price <= ob_top * 1.001:
                # Check confirmation if required
                if self.cfg.get("require_structure", True):
                    structure = get_latest_structure(df, lookback=20)
                    # Need bullish structure (CHOCH or BOS = 1)
                    if structure["direction"] != 1:
                        continue
                        
                return "LONG", {
                    "strategy": "OrderBlock",
                    "entry_price": current_price,
                    "stop_loss": ob_bottom,  # SL below OB
                    "ob_level": ob_top
                }

        # Check Short (Bearish OB)
        for ob in obs["bearish"]:
            ob_top = ob[1]
            ob_bottom = ob[2]
            
            if ob_bottom * 0.999 <= current_price <= ob_top:
                if self.cfg.get("require_structure", True):
                    structure = get_latest_structure(df, lookback=20)
                    # Need bearish structure (CHOCH or BOS = -1)
                    if structure["direction"] != -1:
                        continue
                        
                return "SHORT", {
                    "strategy": "OrderBlock",
                    "entry_price": current_price,
                    "stop_loss": ob_top,  # SL above OB
                    "ob_level": ob_bottom
                }
                
        return None, None

class LiquiditySweepStrategy(BaseStrategy):
    """
    High-Frequency Strategy:
    1. Identify Swing Highs/Lows (Liquidity)
    2. Wait for price to sweep (go beyond) structure level
    3. Wait for close BACK inside the range (Rejection)
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = config.get("liquidity_sweep", {})
        
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        if df is None or len(df) < 50:
            return None, None
            
        # Get recent swing points - only check last 2 (reduced from 5)
        recent_swings = df[df["swing_hl"] != 0].tail(2)
        
        # Current candle
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Volume filter - require above average volume on sweep candle
        avg_volume = df["volume"].tail(20).mean()
        require_volume = self.cfg.get("require_volume", True)
        
        # Check Long (Sweep of Swing Low)
        for idx, swing in recent_swings.iterrows():
            if swing["swing_hl"] == -1: # Swing Low
                level = swing["low"]
                
                # Logic: Price went below level but closed above it
                swept = df["low"].iloc[-2] < level or df["low"].iloc[-1] < level
                rejected = df["close"].iloc[-1] > level
                
                # Additional filters
                has_volume = curr["volume"] > avg_volume * 1.2 if require_volume else True
                
                # Minimum sweep distance (0.1% beyond level)
                min_sweep = level * 0.001
                actual_sweep = level - min(df["low"].iloc[-2], df["low"].iloc[-1])
                meaningful_sweep = actual_sweep > min_sweep
                
                if swept and rejected and has_volume and meaningful_sweep:
                    return "LONG", {
                        "strategy": "LiquiditySweep",
                        "entry_price": curr["close"],
                        "stop_loss": min(curr["low"], prev["low"]), # Tight stop below sweep
                        "sweep_level": level
                    }
                    
        # Check Short (Sweep of Swing High)
        for idx, swing in recent_swings.iterrows():
            if swing["swing_hl"] == 1: # Swing High
                level = swing["high"]
                
                # Logic: Price went above level but closed below it
                swept = df["high"].iloc[-2] > level or df["high"].iloc[-1] > level
                rejected = df["close"].iloc[-1] < level
                
                # Additional filters
                has_volume = curr["volume"] > avg_volume * 1.2 if require_volume else True
                
                # Minimum sweep distance
                min_sweep = level * 0.001
                actual_sweep = max(df["high"].iloc[-2], df["high"].iloc[-1]) - level
                meaningful_sweep = actual_sweep > min_sweep
                
                if swept and rejected and has_volume and meaningful_sweep:
                    return "SHORT", {
                        "strategy": "LiquiditySweep",
                        "entry_price": curr["close"],
                        "stop_loss": max(curr["high"], prev["high"]), # Tight stop above sweep
                        "sweep_level": level
                    }
                    
        return None, None

class SilverBulletStrategy(BaseStrategy):
    """
    Time-Based Strategy:
    Only trades during NY AM (10-11 AM EST) or PM (2-3 PM EST).
    Entries based on FVG formation.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = config.get("silver_bullet", {})
        
    def _is_in_window(self) -> bool:
        # Get current time in NY
        try:
            ny_tz = pytz.timezone('America/New_York')
            now = datetime.now(ny_tz)
        except Exception:
            # Fallback if tz database not found
            now = datetime.now()
            
        # Windows breakdown (hour, start_min, end_min)
        windows = []
        sessions = self.cfg.get("sessions", [])
        
        if "london_open" in sessions:
            windows.append((3, 0, 4, 0)) # 3 AM - 4 AM
        if "ny_am" in sessions:
            windows.append((10, 0, 11, 0)) # 10 AM - 11 AM
        if "ny_pm" in sessions:
            windows.append((14, 0, 15, 0)) # 2 PM - 3 PM
            
        for h_start, m_start, h_end, m_end in windows:
            start_dt = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
            end_dt = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)
            if start_dt <= now <= end_dt:
                return True
                
        return False
        
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        if not self._is_in_window():
            return None, None
            
        # Simplified logic: Trade strictly on FVG confluence
        active_fvgs = get_active_fvgs(df, lookback=10)
        current_price = df.iloc[-1]["close"]
        
        # Long at Bullish FVG
        for fvg in active_fvgs["bullish"]:
            # FVG: (index, top, bottom)
            if fvg[2] <= current_price <= fvg[1]: # Inside FVG
                 return "LONG", {
                    "strategy": "SilverBullet",
                    "entry_price": current_price,
                    "stop_loss": fvg[2] * 0.999, # Below FVG
                    "fvg_level": fvg[1]
                }
                
        # Short at Bearish FVG
        for fvg in active_fvgs["bearish"]:
            if fvg[2] <= current_price <= fvg[1]: # Inside FVG
                 return "SHORT", {
                    "strategy": "SilverBullet",
                    "entry_price": current_price,
                    "stop_loss": fvg[1] * 1.001, # Above FVG
                    "fvg_level": fvg[2]
                }

        return None, None

class StrategyManager:
    """Manages multiple strategies."""
    
    def __init__(self, config: dict):
        self.strategies = []
        self.config = config
        
        # Determine strategy settings path - handle flat or nested structure
        strategy_config = config.get("strategy_settings", config.get("strategy", {}))
        active = config.get("strategy", {}).get("active_strategies", ["order_block"])
        
        if not active:
             # Fallback
             active = ["order_block"]
        
        logger.info(f"🧠 Initializing Strategies: {active}")
        
        if "order_block" in active:
            self.strategies.append(OrderBlockStrategy(strategy_config))
        if "liquidity_sweep" in active:
            self.strategies.append(LiquiditySweepStrategy(strategy_config))
        if "silver_bullet" in active:
            self.strategies.append(SilverBulletStrategy(strategy_config))
            
    def check_signals(self, df: pd.DataFrame, symbol: str) -> Tuple[Optional[str], Optional[dict]]:
        """Run all strategies and return the first valid signal."""
        
        for strategy in self.strategies:
            try:
                side, details = strategy.get_signal(df, symbol)
                if side:
                    return side, details
            except Exception as e:
                logger.error(f"Strategy {strategy.__class__.__name__} failed on {symbol}: {e}")
                continue
                
        return None, None
    
    def get_exit_levels(self, entry_price: float, side: str, df: pd.DataFrame, details: dict) -> Tuple[float, float]:
        """
        Calculate SL and TP levels.
        delegates to common logic or strategy specific if needed.
        """
        # Common ATR fallback
        atr_period = 14
        try:
             atr = df.iloc[-1][f"atr_{atr_period}"]
        except Exception:
             atr = entry_price * 0.01

        if pd.isna(atr):
            atr = entry_price * 0.01
            
        sl_price = 0.0
        tp_price = 0.0
        
        # Strategy specific stop loss basis
        # If strategy provided a hard stop level (e.g. OB limit or Sweep low), use it
        stop_basis = details.get("stop_loss", entry_price)
        
        # Default multipliers
        tp_mult = 2.0
        
        if side == "LONG":
            sl_price = stop_basis
            if sl_price >= entry_price: # Safety
                 sl_price = entry_price - (atr * 1.0)
            
            risk = entry_price - sl_price
            tp_price = entry_price + (risk * tp_mult)
                
        elif side == "SHORT":
            sl_price = stop_basis
            if sl_price <= entry_price:
                 sl_price = entry_price + (atr * 1.0)
                 
            risk = sl_price - entry_price
            tp_price = entry_price - (risk * tp_mult)
                
        return sl_price, tp_price
