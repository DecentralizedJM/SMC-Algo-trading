"""
Market Data Fetcher - Fetch OHLCV data from Bybit REST API.
Uses direct requests instead of pybit for Python 3.14 compatibility.
"""

import logging
import time
from typing import Optional
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BybitDataFetcher:
    """Fetch market data from Bybit public REST API."""
    
    BASE_URL = "https://api.bybit.com"
    
    def __init__(self):
        """Initialize with rate limiting."""
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms between requests
        self.session = requests.Session()
    
    def _rate_limit(self):
        """Simple rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()
    
    def get_klines(
        self,
        symbol: str,
        interval: str = "15",
        limit: int = 200
    ) -> Optional[pd.DataFrame]:
        """
        Fetch kline/candlestick data.
        
        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            interval: Timeframe ("1", "5", "15", "60", "240", "D")
            limit: Number of candles (max 1000)
        
        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/v5/market/kline"
            params = {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            
            response = self.session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("retCode") != 0:
                logger.error(f"Bybit API error: {data.get('retMsg')}")
                return None
            
            klines = data.get("result", {}).get("list", [])
            if not klines:
                return None
            
            # Convert to DataFrame
            # Bybit returns: [startTime, open, high, low, close, volume, turnover]
            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "turnover"
            ])
            
            # Convert types
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            
            # Sort by time ascending (Bybit returns newest first)
            df = df.sort_values("timestamp").reset_index(drop=True)
            
            # Keep only OHLCV columns (SMC expects lowercase)
            df = df[["timestamp", "open", "high", "low", "close", "volume"]]
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            return None
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/v5/market/tickers"
            params = {
                "category": "linear",
                "symbol": symbol
            }
            
            response = self.session.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("retCode") != 0:
                return None
            
            tickers = data.get("result", {}).get("list", [])
            if tickers:
                return float(tickers[0]["lastPrice"])
            return None
            
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None


if __name__ == "__main__":
    # Test
    fetcher = BybitDataFetcher()
    
    print("📊 Fetching BTCUSDT 15m candles...")
    df = fetcher.get_klines("BTCUSDT", "15", 200)
    
    if df is not None:
        print(f"✅ Got {len(df)} candles")
        print(f"   Columns: {df.columns.tolist()}")
        print(f"   Latest: {df.iloc[-1].to_dict()}")
        
        price = fetcher.get_current_price("BTCUSDT")
        print(f"\n💰 Current BTC price: ${price:,.2f}")
    else:
        print("❌ Failed to fetch data")
