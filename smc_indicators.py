"""
SMC Indicators - Wrapper around smartmoneyconcepts package.

Calculates Smart Money Concepts indicators:
- Swing Highs and Lows
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Liquidity levels
"""

import logging
import pandas as pd
import numpy as np
import sys
import os

# Suppress "Thank you for using SmartMoneyConcepts" message
try:
    with open(os.devnull, 'w') as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            from smartmoneyconcepts import smc
        finally:
            sys.stdout = old_stdout
except Exception:
    # Fallback if suppression fails
    from smartmoneyconcepts import smc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Add ATR indicator to DataFrame."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df[f"atr_{period}"] = tr.rolling(window=period).mean()
    
    return df


def calculate_smc(
    df: pd.DataFrame,
    swing_length: int = 10,
    fvg_join_consecutive: bool = True,
    atr_period: int = 14
) -> pd.DataFrame:
    """
    Calculate all SMC indicators on OHLCV DataFrame.
    
    Args:
        df: OHLCV DataFrame with lowercase columns
        swing_length: Lookback for swing detection
        fvg_join_consecutive: Merge consecutive FVGs
        atr_period: Period for ATR calculation
    
    Returns:
        DataFrame with all SMC indicators added
    """
    if df is None or len(df) < swing_length * 2 + 10:
        logger.warning("Insufficient data for SMC calculation")
        return df
    
    # Ensure lowercase columns (SMC requirement)
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    
    # Add ATR
    df = add_atr(df, atr_period)
    
    # 1. Swing Highs and Lows
    swing_hl = smc.swing_highs_lows(df, swing_length=swing_length)
    df["swing_hl"] = swing_hl["HighLow"]
    df["swing_level"] = swing_hl["Level"]
    
    # 2. Fair Value Gaps
    fvg = smc.fvg(df, join_consecutive=fvg_join_consecutive)
    df["fvg"] = fvg["FVG"]  # 1=bullish, -1=bearish
    df["fvg_top"] = fvg["Top"]
    df["fvg_bottom"] = fvg["Bottom"]
    df["fvg_mitigated"] = fvg["MitigatedIndex"]
    
    # 3. Break of Structure & Change of Character
    bos_choch = smc.bos_choch(df, swing_hl, close_break=True)
    df["bos"] = bos_choch["BOS"]  # 1=bullish, -1=bearish
    df["choch"] = bos_choch["CHOCH"]  # 1=bullish, -1=bearish
    df["structure_level"] = bos_choch["Level"]
    df["structure_broken_idx"] = bos_choch["BrokenIndex"]
    
    # 4. Order Blocks
    ob = smc.ob(df, swing_hl, close_mitigation=False)
    df["ob"] = ob["OB"]  # 1=bullish, -1=bearish
    df["ob_top"] = ob["Top"]
    df["ob_bottom"] = ob["Bottom"]
    df["ob_volume"] = ob["OBVolume"]
    df["ob_mitigated"] = ob["MitigatedIndex"]
    df["ob_strength"] = ob["Percentage"]
    
    # 5. Liquidity
    liq = smc.liquidity(df, swing_hl, range_percent=0.01)
    df["liquidity"] = liq["Liquidity"]  # 1=bullish, -1=bearish
    df["liq_level"] = liq["Level"]
    df["liq_swept"] = liq["Swept"]
    
    return df


def get_active_order_blocks(df: pd.DataFrame, lookback: int = 50) -> dict:
    """
    Find unmitigated (active) order blocks in recent history.
    
    Returns:
        {
            "bullish": [(index, top, bottom, strength), ...],
            "bearish": [(index, top, bottom, strength), ...]
        }
    """
    if df is None or "ob" not in df.columns:
        return {"bullish": [], "bearish": []}
    
    recent = df.iloc[-lookback:]
    current_idx = len(df) - 1
    
    bullish_obs = []
    bearish_obs = []
    
    for i in range(len(recent)):
        idx = recent.index[i]
        ob_type = recent.iloc[i]["ob"]
        
        if pd.isna(ob_type):
            continue
        
        # Check if OB is mitigated
        mitigated_idx = recent.iloc[i]["ob_mitigated"]
        if not pd.isna(mitigated_idx) and mitigated_idx <= current_idx:
            continue  # Already mitigated
        
        ob_data = (
            idx,
            recent.iloc[i]["ob_top"],
            recent.iloc[i]["ob_bottom"],
            recent.iloc[i]["ob_strength"]
        )
        
        if ob_type == 1:
            bullish_obs.append(ob_data)
        elif ob_type == -1:
            bearish_obs.append(ob_data)
    
    return {"bullish": bullish_obs, "bearish": bearish_obs}


def get_active_fvgs(df: pd.DataFrame, lookback: int = 30) -> dict:
    """
    Find unmitigated (active) Fair Value Gaps.
    
    Returns:
        {
            "bullish": [(index, top, bottom), ...],
            "bearish": [(index, top, bottom), ...]
        }
    """
    if df is None or "fvg" not in df.columns:
        return {"bullish": [], "bearish": []}
    
    recent = df.iloc[-lookback:]
    current_idx = len(df) - 1
    
    bullish_fvgs = []
    bearish_fvgs = []
    
    for i in range(len(recent)):
        idx = recent.index[i]
        fvg_type = recent.iloc[i]["fvg"]
        
        if pd.isna(fvg_type):
            continue
        
        # Check if FVG is mitigated
        mitigated_idx = recent.iloc[i]["fvg_mitigated"]
        if not pd.isna(mitigated_idx) and mitigated_idx <= current_idx:
            continue  # Already mitigated
        
        fvg_data = (
            idx,
            recent.iloc[i]["fvg_top"],
            recent.iloc[i]["fvg_bottom"]
        )
        
        if fvg_type == 1:
            bullish_fvgs.append(fvg_data)
        elif fvg_type == -1:
            bearish_fvgs.append(fvg_data)
    
    return {"bullish": bullish_fvgs, "bearish": bearish_fvgs}


def get_latest_structure(df: pd.DataFrame, lookback: int = 20) -> dict:
    """
    Get the most recent BOS or CHoCH signal.
    
    Returns:
        {
            "type": "BOS" or "CHOCH" or None,
            "direction": 1 (bullish) or -1 (bearish) or None,
            "level": price level,
            "index": candle index
        }
    """
    if df is None or "bos" not in df.columns:
        return {"type": None, "direction": None, "level": None, "index": None}
    
    recent = df.iloc[-lookback:]
    
    # Find most recent non-NaN BOS or CHOCH
    for i in range(len(recent) - 1, -1, -1):
        row = recent.iloc[i]
        
        if not pd.isna(row["choch"]):
            return {
                "type": "CHOCH",
                "direction": int(row["choch"]),
                "level": row["structure_level"],
                "index": recent.index[i]
            }
        
        if not pd.isna(row["bos"]):
            return {
                "type": "BOS",
                "direction": int(row["bos"]),
                "level": row["structure_level"],
                "index": recent.index[i]
            }
    
    return {"type": None, "direction": None, "level": None, "index": None}


if __name__ == "__main__":
    # Test
    from market_data import BybitDataFetcher
    
    fetcher = BybitDataFetcher()
    df = fetcher.get_klines("BTCUSDT", "15", 200)
    
    if df is not None:
        print("📊 Calculating SMC indicators...")
        df = calculate_smc(df, swing_length=10, atr_period=14)
        
        print(f"✅ Columns added: {[c for c in df.columns if c not in ['timestamp', 'open', 'high', 'low', 'close', 'volume']]}")
        
        # Get active structures
        active_obs = get_active_order_blocks(df)
        print(f"\n🔹 Active Bullish OBs: {len(active_obs['bullish'])}")
        print(f"🔻 Active Bearish OBs: {len(active_obs['bearish'])}")
        
        active_fvgs = get_active_fvgs(df)
        print(f"\n📈 Active Bullish FVGs: {len(active_fvgs['bullish'])}")
        print(f"📉 Active Bearish FVGs: {len(active_fvgs['bearish'])}")
        
        structure = get_latest_structure(df)
        print(f"\n🏗️  Latest Structure: {structure}")
    else:
        print("❌ Failed to fetch data")
