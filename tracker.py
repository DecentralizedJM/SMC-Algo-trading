"""
Trade Tracker - Track win rates and ROI.

Persists trade history to JSON file for analysis.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradeTracker:
    """Track trading performance with persistence."""
    
    def __init__(self, filepath: str = "trades.json"):
        """Initialize tracker with file path for persistence."""
        self.filepath = Path(filepath)
        self.trades: List[Dict] = []
        self.load()
    
    def load(self):
        """Load trade history from file."""
        if self.filepath.exists():
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                    self.trades = data.get("trades", [])
                logger.info(f"📂 Loaded {len(self.trades)} trades from {self.filepath}")
            except Exception as e:
                logger.error(f"Failed to load trades: {e}")
                self.trades = []
        else:
            self.trades = []
    
    def save(self):
        """Save trade history to file."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "stats": self.get_stats(),
                "trades": self.trades
            }
            with open(self.filepath, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"💾 Saved {len(self.trades)} trades to {self.filepath}")
        except Exception as e:
            logger.error(f"Failed to save trades: {e}")
    
    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        leverage: int,
        margin_used: float,
        exit_reason: str = "unknown",  # "TP", "SL", "manual"
        entry_details: Optional[Dict] = None
    ) -> Dict:
        """
        Record a completed trade.
        
        Args:
            symbol: Trading pair
            side: "LONG" or "SHORT"
            entry_price: Entry price
            exit_price: Exit price
            quantity: Position quantity
            leverage: Leverage used
            margin_used: Margin amount
            exit_reason: Why the trade closed
            entry_details: Additional entry info (OB level, structure type, etc.)
        
        Returns:
            Trade record dict
        """
        # Calculate PnL
        if side == "LONG":
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100 * leverage
            pnl_usd = margin_used * (pnl_pct / 100)
        else:  # SHORT
            pnl_pct = ((entry_price - exit_price) / entry_price) * 100 * leverage
            pnl_usd = margin_used * (pnl_pct / 100)
        
        is_win = pnl_usd > 0
        
        trade = {
            "id": len(self.trades) + 1,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "leverage": leverage,
            "margin_used": margin_used,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_usd": round(pnl_usd, 4),
            "is_win": is_win,
            "exit_reason": exit_reason,
            "entry_details": entry_details or {}
        }
        
        self.trades.append(trade)
        self.save()
        
        logger.info(f"{'✅' if is_win else '❌'} Trade recorded: {symbol} {side} - {pnl_pct:+.2f}% (${pnl_usd:+.4f})")
        
        return trade
    
    def get_stats(self) -> Dict:
        """
        Get trading statistics.
        
        Returns:
            {
                "total_trades": int,
                "wins": int,
                "losses": int,
                "win_rate": float (percentage),
                "total_pnl_pct": float,
                "total_pnl_usd": float,
                "avg_win_pct": float,
                "avg_loss_pct": float,
                "best_trade": dict,
                "worst_trade": dict
            }
        """
        if not self.trades:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl_pct": 0.0,
                "total_pnl_usd": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "best_trade": None,
                "worst_trade": None
            }
        
        wins = [t for t in self.trades if t["is_win"]]
        losses = [t for t in self.trades if not t["is_win"]]
        
        total_pnl_pct = sum(t["pnl_pct"] for t in self.trades)
        total_pnl_usd = sum(t["pnl_usd"] for t in self.trades)
        
        avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
        
        best = max(self.trades, key=lambda t: t["pnl_pct"])
        worst = min(self.trades, key=lambda t: t["pnl_pct"])
        
        return {
            "total_trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round((len(wins) / len(self.trades)) * 100, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "total_pnl_usd": round(total_pnl_usd, 4),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "best_trade": {
                "symbol": best["symbol"],
                "pnl_pct": best["pnl_pct"],
                "pnl_usd": best["pnl_usd"]
            },
            "worst_trade": {
                "symbol": worst["symbol"],
                "pnl_pct": worst["pnl_pct"],
                "pnl_usd": worst["pnl_usd"]
            }
        }
    
    def get_recent_trades(self, n: int = 10) -> List[Dict]:
        """Get N most recent trades."""
        return self.trades[-n:][::-1]  # Newest first
    
    def print_summary(self):
        """Print a formatted summary of trading performance."""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("📊 TRADING PERFORMANCE SUMMARY")
        print("="*60)
        print(f"Total Trades:    {stats['total_trades']}")
        print(f"Wins:            {stats['wins']} | Losses: {stats['losses']}")
        print(f"Win Rate:        {stats['win_rate']:.1f}%")
        print("-"*60)
        print(f"Total PnL:       {stats['total_pnl_pct']:+.2f}% (${stats['total_pnl_usd']:+.4f})")
        print(f"Avg Win:         {stats['avg_win_pct']:+.2f}%")
        print(f"Avg Loss:        {stats['avg_loss_pct']:+.2f}%")
        
        if stats["best_trade"]:
            print("-"*60)
            print(f"Best Trade:      {stats['best_trade']['symbol']} ({stats['best_trade']['pnl_pct']:+.2f}%)")
            print(f"Worst Trade:     {stats['worst_trade']['symbol']} ({stats['worst_trade']['pnl_pct']:+.2f}%)")
        
        print("="*60 + "\n")


if __name__ == "__main__":
    # Test
    tracker = TradeTracker("test_trades.json")
    
    # Simulate some trades
    tracker.record_trade(
        symbol="BTCUSDT",
        side="LONG",
        entry_price=100000,
        exit_price=101500,
        quantity=0.001,
        leverage=20,
        margin_used=2.0,
        exit_reason="TP",
        entry_details={"structure": "CHOCH", "ob_strength": 85}
    )
    
    tracker.record_trade(
        symbol="ETHUSDT",
        side="SHORT",
        entry_price=3500,
        exit_price=3550,
        quantity=0.1,
        leverage=20,
        margin_used=2.0,
        exit_reason="SL"
    )
    
    tracker.record_trade(
        symbol="SOLUSDT",
        side="LONG",
        entry_price=200,
        exit_price=210,
        quantity=1.0,
        leverage=20,
        margin_used=2.0,
        exit_reason="TP"
    )
    
    tracker.print_summary()
    
    print("📋 Recent Trades:")
    for trade in tracker.get_recent_trades(5):
        print(f"   {trade['symbol']} {trade['side']}: {trade['pnl_pct']:+.2f}%")
    
    # Cleanup test file
    import os
    os.remove("test_trades.json")
