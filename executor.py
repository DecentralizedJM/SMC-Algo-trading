"""
Mudrex Trade Executor - Execute trades using the SDK.
"""

import logging
import time
from typing import Optional, Tuple
from mudrex import MudrexClient
from mudrex.models import Order, Position
from mudrex.utils import calculate_order_from_usd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MudrexExecutor:
    """Execute trades on Mudrex with the SDK."""
    
    def __init__(
        self,
        api_secret: str,
        margin_per_trade: float = 2.0,
        max_leverage: int = 20
    ):
        """
        Initialize executor.
        
        Args:
            api_secret: Mudrex API secret
            margin_per_trade: Margin to use per trade (e.g., $2)
            max_leverage: Maximum allowed leverage
        """
        self.client = MudrexClient(api_secret=api_secret)
        self.margin_per_trade = margin_per_trade
        self.max_leverage = max_leverage
        
        logger.info(f"Executor initialized - Margin/Trade: ${margin_per_trade}, Max Leverage: {max_leverage}x")
    
    def check_balance(self) -> float:
        """Get current futures balance."""
        try:
            balance = self.client.wallet.get_futures_balance()
            return float(balance.balance)
        except Exception as e:
            logger.error(f"Failed to check balance: {e}")
            return 0.0
    
    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        leverage: int
    ) -> Tuple[str, float]:
        """
        Calculate position size from margin per trade and leverage.
        
        Args:
            symbol: Trading symbol
            price: Entry price
            leverage: Leverage to use
        
        Returns:
            (quantity_str, usd_value)
        """
        try:
            asset = self.client.assets.get(symbol)
            quantity_step = float(asset.quantity_step)
        except Exception as e:
            logger.error(f"Failed to get asset info: {e}")
            quantity_step = 0.001
        
        # Calculate from margin per trade * leverage
        notional_value = self.margin_per_trade * leverage
        
        # Use SDK utility
        qty, actual_value = calculate_order_from_usd(
            usd_amount=notional_value,
            price=price,
            quantity_step=quantity_step
        )
        
        return qty, actual_value
    
    def place_order(
        self,
        symbol: str,
        side: str,
        leverage: int,
        tp: float,
        sl: float,
        entry_price: Optional[float] = None
    ) -> Optional[Order]:
        """
        Place a market order with SL/TP.
        
        Args:
            symbol: Trading pair
            side: "LONG" or "SHORT"
            leverage: Leverage to use
            tp: Take profit price
            sl: Stop loss price
            entry_price: Expected entry price (for position sizing)
        
        Returns:
            Order object if successful
        """
        try:
            actual_leverage = min(leverage, self.max_leverage)
            
            if not entry_price:
                from market_data import BybitDataFetcher
                entry_price = BybitDataFetcher().get_current_price(symbol)
                if not entry_price:
                    logger.error("Failed to get current price")
                    return None
            
            # Calculate quantity
            qty, value = self.calculate_position_size(symbol, entry_price, actual_leverage)
            
            logger.info(f"📊 Position sizing: margin=${self.margin_per_trade}, leverage={actual_leverage}x")
            logger.info(f"   Notional: ${self.margin_per_trade * actual_leverage:.2f}")
            logger.info(f"Placing {side} order: {qty} {symbol} @ ${entry_price:,.4f} (${value:,.2f})")
            logger.info(f"TP: ${tp:,.4f}, SL: ${sl:,.4f}")
            
            # Set leverage
            self.client.leverage.set(
                symbol=symbol,
                leverage=str(actual_leverage),
                margin_type="ISOLATED"
            )
            
            # Place market order
            order = self.client.orders.create_market_order(
                symbol=symbol,
                side=side,
                quantity=qty,
                leverage=str(actual_leverage)
            )
            
            logger.info(f"✅ Order placed: {order.order_id if hasattr(order, 'order_id') else 'N/A'}")
            
            # Set SL/TP via positions API (with fallback)
            self._set_sltp(symbol, sl, tp)
            
            return order
            
        except Exception as e:
            logger.error(f"❌ Order failed: {e}")
            return None
    
    def _set_sltp(self, symbol: str, sl: float, tp: float):
        """Set SL/TP on position with fallback logic."""
        try:
            time.sleep(1)  # Wait for position to be created
            positions = self.client.positions.list_open()
            
            for pos in positions:
                if pos.symbol == symbol:
                    # Try setting both together first
                    try:
                        self.client.positions.set_risk_order(
                            position_id=pos.position_id,
                            stoploss_price=str(sl),
                            takeprofit_price=str(tp)
                        )
                        logger.info(f"✅ SL/TP set: SL=${sl:.4f}, TP=${tp:.4f}")
                    except Exception as e1:
                        logger.warning(f"⚠️ Combined SL/TP failed, trying separately: {e1}")
                        
                        # Try separately
                        try:
                            self.client.positions.set_risk_order(
                                position_id=pos.position_id,
                                takeprofit_price=str(tp)
                            )
                            logger.info(f"✅ TP set: ${tp:.4f}")
                        except Exception as e2:
                            logger.warning(f"⚠️ TP failed: {e2}")
                        
                        try:
                            self.client.positions.set_risk_order(
                                position_id=pos.position_id,
                                stoploss_price=str(sl)
                            )
                            logger.info(f"✅ SL set: ${sl:.4f}")
                        except Exception as e3:
                            logger.warning(f"⚠️ SL failed: {e3}")
                    break
        except Exception as e:
            logger.warning(f"⚠️ Failed to set SL/TP: {e}")
    
    def get_open_positions(self) -> list:
        """Get all open positions."""
        try:
            return self.client.positions.list_open()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_position_for_symbol(self, symbol: str) -> Optional[Position]:
        """Check if there's an open position for this symbol."""
        try:
            positions = self.client.positions.list_open()
            for pos in positions:
                if pos.symbol == symbol:
                    return pos
            return None
        except Exception as e:
            logger.error(f"Failed to check positions: {e}")
            return None
    
    def close_position(self, symbol: str) -> bool:
        """Close position for a symbol."""
        try:
            position = self.get_position_for_symbol(symbol)
            if not position:
                logger.warning(f"No open position for {symbol}")
                return False
            
            # Use SDK close method if available
            try:
                self.client.positions.close(position.position_id)
                logger.info(f"✅ Position closed: {symbol}")
                return True
            except:
                # Fallback: place opposite order
                opposite_side = "SHORT" if position.side == "LONG" else "LONG"
                
                self.client.orders.create_market_order(
                    symbol=symbol,
                    side=opposite_side,
                    quantity=position.quantity,
                    leverage=position.leverage,
                    reduce_only=True
                )
                
                logger.info(f"✅ Position closed via reverse order: {symbol}")
                return True
            
        except Exception as e:
            logger.error(f"❌ Failed to close position: {e}")
            return False
    
    def get_available_symbols(self) -> list:
        """Get list of available trading symbols."""
        try:
            markets = self.client.markets.get_futures_markets()
            return [m.symbol for m in markets]
        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

if __name__ == "__main__":
    # Test
    import json
    
    with open("config.json", "r") as f:
        config = json.load(f)
    
    executor = MudrexExecutor(
        api_secret=config["mudrex"]["api_secret"],
        margin_per_trade=config["mudrex"]["margin_per_trade"],
        max_leverage=config["mudrex"]["leverage"]
    )
    
    balance = executor.check_balance()
    print(f"💰 Current Balance: ${balance:.2f} USDT")
    
    # Test position sizing
    qty, value = executor.calculate_position_size("BTCUSDT", 100000, 20)
    print(f"\n📊 Position Size for BTCUSDT @ $100k, 20x:")
    print(f"   Quantity: {qty}")
    print(f"   Notional: ${value:,.2f}")
    
    # Check open positions
    positions = executor.get_open_positions()
    print(f"\n📍 Open Positions: {len(positions)}")
    for pos in positions:
        print(f"   {pos.symbol}: {pos.side} {pos.quantity}")
