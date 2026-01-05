"""
SMC Strategy Engine - Entry/exit logic using Smart Money Concepts.

Entry Requirements:
- LONG: Bullish BOS/CHoCH + Price at active bullish Order Block
- SHORT: Bearish BOS/CHoCH + Price at active bearish Order Block
"""

import logging
import pandas as pd
from typing import Tuple, Dict, Optional
from smc_indicators import (
    calculate_smc,
    get_active_order_blocks,
    get_active_fvgs,
    get_latest_structure
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SMCStrategy:
    """
    Smart Money Concepts based trading strategy.
    
    Entry Logic:
    - LONG: Bullish structure (BOS/CHoCH) + Price touches bullish OB
    - SHORT: Bearish structure (BOS/CHoCH) + Price touches bearish OB
    
    Optional: FVG confluence for higher probability
    """
    
    def __init__(
        self,
        swing_length: int = 10,
        ob_lookback: int = 50,
        fvg_join_consecutive: bool = True,
        atr_period: int = 14,
        tp_atr_mult: float = 2.0,
        sl_atr_mult: float = 1.5,
        require_fvg_confluence: bool = False
    ):
        self.swing_length = swing_length
        self.ob_lookback = ob_lookback
        self.fvg_join_consecutive = fvg_join_consecutive
        self.atr_period = atr_period
        self.tp_atr_mult = tp_atr_mult
        self.sl_atr_mult = sl_atr_mult
        self.require_fvg_confluence = require_fvg_confluence
    
    def analyze(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all SMC indicators on the DataFrame."""
        return calculate_smc(
            df,
            swing_length=self.swing_length,
            fvg_join_consecutive=self.fvg_join_consecutive,
            atr_period=self.atr_period
        )
    
    def _price_at_ob(
        self,
        current_price: float,
        order_blocks: list,
        tolerance_pct: float = 0.005  # 0.5% tolerance
    ) -> Optional[tuple]:
        """
        Check if current price is at or near an Order Block.
        
        Returns:
            (ob_index, ob_top, ob_bottom, strength) if at OB, else None
        """
        for ob in order_blocks:
            idx, top, bottom, strength = ob
            
            if pd.isna(top) or pd.isna(bottom):
                continue
            
            # Expand zone by tolerance
            zone_range = top - bottom
            tolerance = max(zone_range * 0.2, current_price * tolerance_pct)
            
            # Check if price is within expanded OB zone
            if (bottom - tolerance) <= current_price <= (top + tolerance):
                return ob
        
        return None
    
    def _has_fvg_confluence(
        self,
        current_price: float,
        fvgs: list,
        tolerance_pct: float = 0.01
    ) -> bool:
        """Check if price is near an FVG zone."""
        for fvg in fvgs:
            idx, top, bottom = fvg
            
            if pd.isna(top) or pd.isna(bottom):
                continue
            
            tolerance = current_price * tolerance_pct
            if (bottom - tolerance) <= current_price <= (top + tolerance):
                return True
        
        return False
    
    def check_long_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Check for LONG entry signal.
        
        Requirements:
        1. Recent bullish structure (BOS or CHoCH)
        2. Price at active bullish Order Block
        3. (Optional) FVG confluence
        
        Returns:
            (signal_valid, details_dict)
        """
        if df is None or len(df) < 50:
            return False, {"reason": "Insufficient data"}
        
        latest = df.iloc[-1]
        current_price = latest["close"]
        atr = latest.get(f"atr_{self.atr_period}", latest.get("atr_14", 0))
        
        if pd.isna(atr) or atr == 0:
            return False, {"reason": "ATR not available"}
        
        # 1. Check structure - need bullish bias
        structure = get_latest_structure(df, lookback=30)
        
        if structure["direction"] != 1:  # Not bullish
            return False, {
                "reason": "No bullish structure",
                "last_structure": structure
            }
        
        # 2. Check if price is at bullish Order Block
        active_obs = get_active_order_blocks(df, lookback=self.ob_lookback)
        bullish_obs = active_obs["bullish"]
        
        if not bullish_obs:
            return False, {"reason": "No active bullish OBs"}
        
        ob_at_price = self._price_at_ob(current_price, bullish_obs)
        
        if not ob_at_price:
            return False, {
                "reason": "Price not at bullish OB",
                "active_obs": len(bullish_obs),
                "price": current_price
            }
        
        # 3. Optional FVG confluence
        if self.require_fvg_confluence:
            active_fvgs = get_active_fvgs(df, lookback=30)
            has_fvg = self._has_fvg_confluence(current_price, active_fvgs["bullish"])
            if not has_fvg:
                return False, {
                    "reason": "No FVG confluence",
                    "ob_found": True
                }
        
        # Signal valid!
        ob_idx, ob_top, ob_bottom, ob_strength = ob_at_price
        
        return True, {
            "price": current_price,
            "atr": atr,
            "structure_type": structure["type"],
            "structure_level": structure["level"],
            "ob_index": ob_idx,
            "ob_top": ob_top,
            "ob_bottom": ob_bottom,
            "ob_strength": ob_strength
        }
    
    def check_short_signal(self, df: pd.DataFrame) -> Tuple[bool, Dict]:
        """
        Check for SHORT entry signal.
        
        Requirements:
        1. Recent bearish structure (BOS or CHoCH)
        2. Price at active bearish Order Block
        3. (Optional) FVG confluence
        
        Returns:
            (signal_valid, details_dict)
        """
        if df is None or len(df) < 50:
            return False, {"reason": "Insufficient data"}
        
        latest = df.iloc[-1]
        current_price = latest["close"]
        atr = latest.get(f"atr_{self.atr_period}", latest.get("atr_14", 0))
        
        if pd.isna(atr) or atr == 0:
            return False, {"reason": "ATR not available"}
        
        # 1. Check structure - need bearish bias
        structure = get_latest_structure(df, lookback=30)
        
        if structure["direction"] != -1:  # Not bearish
            return False, {
                "reason": "No bearish structure",
                "last_structure": structure
            }
        
        # 2. Check if price is at bearish Order Block
        active_obs = get_active_order_blocks(df, lookback=self.ob_lookback)
        bearish_obs = active_obs["bearish"]
        
        if not bearish_obs:
            return False, {"reason": "No active bearish OBs"}
        
        ob_at_price = self._price_at_ob(current_price, bearish_obs)
        
        if not ob_at_price:
            return False, {
                "reason": "Price not at bearish OB",
                "active_obs": len(bearish_obs),
                "price": current_price
            }
        
        # 3. Optional FVG confluence
        if self.require_fvg_confluence:
            active_fvgs = get_active_fvgs(df, lookback=30)
            has_fvg = self._has_fvg_confluence(current_price, active_fvgs["bearish"])
            if not has_fvg:
                return False, {
                    "reason": "No FVG confluence",
                    "ob_found": True
                }
        
        # Signal valid!
        ob_idx, ob_top, ob_bottom, ob_strength = ob_at_price
        
        return True, {
            "price": current_price,
            "atr": atr,
            "structure_type": structure["type"],
            "structure_level": structure["level"],
            "ob_index": ob_idx,
            "ob_top": ob_top,
            "ob_bottom": ob_bottom,
            "ob_strength": ob_strength
        }
    
    def calculate_tp_sl(
        self,
        entry_price: float,
        atr: float,
        side: str,
        ob_bottom: Optional[float] = None,
        ob_top: Optional[float] = None
    ) -> Tuple[float, float]:
        """
        Calculate take profit and stop loss.
        
        For LONG: SL below OB bottom, TP based on ATR
        For SHORT: SL above OB top, TP based on ATR
        
        Returns:
            (take_profit_price, stop_loss_price)
        """
        tp_distance = atr * self.tp_atr_mult
        sl_distance = atr * self.sl_atr_mult
        
        # Minimum distances
        min_tp = entry_price * 0.01  # 1% minimum
        min_sl = entry_price * 0.005  # 0.5% minimum
        
        tp_distance = max(tp_distance, min_tp)
        sl_distance = max(sl_distance, min_sl)
        
        if side == "LONG":
            tp = entry_price + tp_distance
            
            # SL: Use OB bottom if available, else ATR-based
            if ob_bottom and not pd.isna(ob_bottom):
                sl = min(ob_bottom - (atr * 0.2), entry_price - sl_distance)
            else:
                sl = entry_price - sl_distance
                
        else:  # SHORT
            tp = entry_price - tp_distance
            
            # SL: Use OB top if available, else ATR-based
            if ob_top and not pd.isna(ob_top):
                sl = max(ob_top + (atr * 0.2), entry_price + sl_distance)
            else:
                sl = entry_price + sl_distance
        
        return round(tp, 6), round(sl, 6)


if __name__ == "__main__":
    # Test
    from market_data import BybitDataFetcher
    
    fetcher = BybitDataFetcher()
    df = fetcher.get_klines("BTCUSDT", "15", 200)
    
    if df is not None:
        strategy = SMCStrategy(
            swing_length=10,
            ob_lookback=50,
            require_fvg_confluence=False
        )
        
        # Analyze
        df = strategy.analyze(df)
        
        # Check signals
        long_signal, long_details = strategy.check_long_signal(df)
        short_signal, short_details = strategy.check_short_signal(df)
        
        print("📊 SMC Strategy Analysis:\n")
        
        print(f"🔼 LONG Signal: {'✅ YES' if long_signal else '❌ NO'}")
        if long_signal:
            tp, sl = strategy.calculate_tp_sl(
                long_details["price"],
                long_details["atr"],
                "LONG",
                ob_bottom=long_details.get("ob_bottom")
            )
            print(f"   Entry: ${long_details['price']:,.2f}")
            print(f"   OB: ${long_details['ob_bottom']:,.2f} - ${long_details['ob_top']:,.2f}")
            print(f"   Structure: {long_details['structure_type']}")
            print(f"   TP: ${tp:,.2f} | SL: ${sl:,.2f}")
        else:
            print(f"   Reason: {long_details.get('reason')}")
        
        print(f"\n🔽 SHORT Signal: {'✅ YES' if short_signal else '❌ NO'}")
        if short_signal:
            tp, sl = strategy.calculate_tp_sl(
                short_details["price"],
                short_details["atr"],
                "SHORT",
                ob_top=short_details.get("ob_top")
            )
            print(f"   Entry: ${short_details['price']:,.2f}")
            print(f"   OB: ${short_details['ob_bottom']:,.2f} - ${short_details['ob_top']:,.2f}")
            print(f"   Structure: {short_details['structure_type']}")
            print(f"   TP: ${tp:,.2f} | SL: ${sl:,.2f}")
        else:
            print(f"   Reason: {short_details.get('reason')}")
