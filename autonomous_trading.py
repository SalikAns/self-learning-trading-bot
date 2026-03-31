# autonomous_trading.py
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class AutonomousTradingEngine:
    """Self-running trading bot that trades without commands"""
    
    def __init__(self, db, ml_engine):
        self.db = db
        self.ml = ml_engine
        self.active = True  # Start active
        self.trading_hours = (9, 16)  # 9 AM to 4 PM EST
        self.max_trades_per_day = 5
        self.risk_per_trade = 0.02  # 2% of portfolio per trade
        self.min_score_threshold = 50  # Minimum score to enter trade
        self.trades_today = 0
        self.last_cycle = None
        logger.info("🤖 Autonomous trading engine initialized")
        
    async def run_trading_cycle(self):
        """Main trading loop - runs every 30 minutes"""
        if not self.active:
            return
            
        # Check if market is open
        if not self.is_market_open():
            logger.info("Market closed - skipping trading cycle")
            return
            
        # Reset daily trade count if new day
        self.reset_daily_count()
        
        logger.info(f"🔄 Running autonomous trading cycle (Trades today: {self.trades_today})")
        
        # Get watchlist or scan for opportunities
        watchlist = await self.get_watchlist()
        
        for ticker in watchlist:
            if self.trades_today >= self.max_trades_per_day:
                logger.info(f"Reached max trades per day ({self.max_trades_per_day})")
                break
                
            try:
                # Analyze stock
                analysis = await self.analyze_opportunity(ticker)
                
                # Make decision: BUY, SELL, or HOLD
                decision = await self.make_decision(analysis)
                
                if decision['action'] in ['BUY', 'SELL']:
                    await self.execute_trade(decision)
                    self.trades_today += 1
                    await asyncio.sleep(5)  # Delay between trades
                    
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                continue
                
        # After trades, run learning cycle
        await self.learn_from_trades()
        self.last_cycle = datetime.now()
        
    def reset_daily_count(self):
        """Reset daily trade counter at midnight EST"""
        now = datetime.now()
        if self.last_cycle and self.last_cycle.date() != now.date():
            self.trades_today = 0
            
    def is_market_open(self):
        """Check if US markets are open"""
        now = datetime.now()
        # Weekday and within trading hours
        if now.weekday() >= 5:  # Weekend
            return False
        if now.hour < self.trading_hours[0] or now.hour >= self.trading_hours[1]:
            return False
        return True
        
    async def get_watchlist(self) -> List[str]:
        """Get stocks to monitor"""
        # Default watchlist - you can make this dynamic
        default_watchlist = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA']
        
        # Try to get user-defined watchlist from database
        try:
            watchlist = await self.db.get_watchlist()
            if watchlist:
                return watchlist
        except:
            pass
            
        return default_watchlist
        
    async def analyze_opportunity(self, ticker: str) -> Dict:
        """Deep analysis for autonomous decisions"""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            
            if hist.empty:
                return {'error': 'No data', 'ticker': ticker}
                
            # Current price
            current_price = hist['Close'].iloc[-1]
            
            # SMA indicators
            sma_20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma_50 = hist['Close'].rolling(50).mean().iloc[-1]
            
            # RSI calculation (14-day)
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50
            
            # Volume analysis
            avg_volume = hist['Volume'].rolling(20).mean().iloc[-1]
            current_volume = hist['Volume'].iloc[-1]
            volume_surge = current_volume / avg_volume if avg_volume > 0 else 1
            
            # MACD
            exp12 = hist['Close'].ewm(span=12, adjust=False).mean()
            exp26 = hist['Close'].ewm(span=26, adjust=False).mean()
            macd = exp12 - exp26
            macd_signal = macd.ewm(span=9, adjust=False).mean()
            macd_histogram = macd - macd_signal
            
            # Trend
            trend = 'bullish' if current_price > sma_20 else 'bearish'
            if current_price > sma_20 and sma_20 > sma_50:
                trend = 'strong_bullish'
            elif current_price < sma_20 and sma_20 < sma_50:
                trend = 'strong_bearish'
                
            # Volatility
            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0.3
            
            return {
                'ticker': ticker,
                'price': current_price,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'rsi': rsi,
                'volume_surge': volume_surge,
                'macd_histogram': macd_histogram.iloc[-1] if not pd.isna(macd_histogram.iloc[-1]) else 0,
                'trend': trend,
                'volatility': volatility,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            return {'error': str(e), 'ticker': ticker}
            
    async def make_decision(self, analysis: Dict) -> Dict:
        """AI-powered decision making"""
        if 'error' in analysis:
            return {'action': 'HOLD', 'ticker': analysis.get('ticker', 'UNKNOWN'), 'score': 0}
            
        score = 0
        reasons = []
        
        # Technical scoring
        if analysis['trend'] in ['bullish', 'strong_bullish']:
            score += 30
            reasons.append(f"Trend: {analysis['trend']}")
        elif analysis['trend'] in ['bearish', 'strong_bearish']:
            score -= 20
            reasons.append(f"Trend: {analysis['trend']}")
            
        # RSI scoring (oversold = buy signal)
        if analysis['rsi'] < 30:
            score += 25
            reasons.append(f"Oversold RSI: {analysis['rsi']:.1f}")
        elif analysis['rsi'] > 70:
            score -= 30
            reasons.append(f"Overbought RSI: {analysis['rsi']:.1f}")
        elif 40 < analysis['rsi'] < 60:
            score += 10
            reasons.append(f"Neutral RSI: {analysis['rsi']:.1f}")
            
        # Volume surge
        if analysis['volume_surge'] > 1.5:
            score += 15
            reasons.append(f"Volume surge: {analysis['volume_surge']:.1f}x")
        elif analysis['volume_surge'] < 0.5:
            score -= 10
            reasons.append("Low volume")
            
        # MACD momentum
        if analysis['macd_histogram'] > 0:
            score += 15
            reasons.append("Bullish MACD")
        else:
            score -= 10
            reasons.append("Bearish MACD")
            
        # Price vs SMAs
        if analysis['price'] > analysis['sma_20']:
            score += 10
            reasons.append("Above 20-day SMA")
        if analysis['price'] > analysis['sma_50']:
            score += 5
            reasons.append("Above 50-day SMA")
            
        # Learn from past mistakes (ML adjustment)
        try:
            mistake_adjustment = await self.ml.get_adjustment(analysis['ticker'])
            score += mistake_adjustment.get('score', 0)
            if mistake_adjustment.get('reason'):
                reasons.append(mistake_adjustment['reason'])
        except:
            pass
            
        # Decision threshold
        if score > self.min_score_threshold:
            return {
                'action': 'BUY',
                'ticker': analysis['ticker'],
                'score': score,
                'reasons': reasons,
                'price': analysis['price']
            }
        elif score < -30:
            return {
                'action': 'SELL',
                'ticker': analysis['ticker'],
                'score': score,
                'reasons': reasons,
                'price': analysis['price']
            }
        else:
            return {
                'action': 'HOLD',
                'ticker': analysis['ticker'],
                'score': score,
                'reasons': reasons
            }
            
    async def execute_trade(self, decision: Dict):
        """Execute autonomous trade"""
        try:
            if decision['action'] == 'BUY':
                # Get portfolio value
                portfolio_value = await self.get_portfolio_value()
                
                # Calculate position size
                position_value = portfolio_value * self.risk_per_trade
                shares = position_value / decision['price']
                
                if shares < 0.01:  # Minimum shares
                    return
                    
                # Record trade
                trade_data = {
                    'ticker': decision['ticker'],
                    'action': 'BUY',
                    'shares': shares,
                    'price': decision['price'],
                    'timestamp': datetime.now(),
                    'reason': ', '.join(decision['reasons']),
                    'score': decision['score'],
                    'autonomous': True
                }
                
                if self.db:
                    await self.db.record_trade(trade_data)
                    
                logger.info(f"🤖 AUTO-BUY: {decision['ticker']} - {shares:.2f} shares @ ${decision['price']:.2f}")
                
            elif decision['action'] == 'SELL':
                # Get holdings
                holdings = await self.get_holdings(decision['ticker'])
                
                if holdings > 0:
                    trade_data = {
                        'ticker': decision['ticker'],
                        'action': 'SELL',
                        'shares': holdings,
                        'price': decision['price'],
                        'timestamp': datetime.now(),
                        'reason': ', '.join(decision['reasons']),
                        'score': decision['score'],
                        'autonomous': True
                    }
                    
                    if self.db:
                        await self.db.record_trade(trade_data)
                        
                    logger.info(f"🤖 AUTO-SELL: {decision['ticker']} - {holdings:.2f} shares @ ${decision['price']:.2f}")
                    
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            
    async def get_portfolio_value(self) -> float:
        """Get current portfolio value"""
        try:
            if self.db:
                return await self.db.get_portfolio_value()
            return 10000  # Default starting capital
        except:
            return 10000
            
    async def get_holdings(self, ticker: str) -> float:
        """Get current holdings for a ticker"""
        try:
            if self.db:
                return await self.db.get_holdings(ticker)
            return 0
        except:
            return 0
            
    async def learn_from_trades(self):
        """Analyze past trades and evolve strategy"""
        try:
            # Get closed positions from last 24h
            trades = await self.db.get_recent_trades(hours=24) if self.db else []
            
            if not trades:
                return
                
            winners = [t for t in trades if t.get('pnl', 0) > 0]
            losers = [t for t in trades if t.get('pnl', 0) < 0]
            
            total_trades = len(trades)
            win_rate = len(winners) / total_trades if total_trades > 0 else 0
            
            # Adjust strategy based on performance
            adjustments = {}
            
            if win_rate < 0.4:  # Poor performance
                adjustments['risk_per_trade'] = self.risk_per_trade * 0.8
                adjustments['min_score_threshold'] = self.min_score_threshold + 10
                logger.info("📉 Strategy adjustment: Reducing risk due to poor performance")
                
            elif win_rate > 0.6:  # Good performance
                adjustments['risk_per_trade'] = min(self.risk_per_trade * 1.2, 0.05)
                adjustments['min_score_threshold'] = max(self.min_score_threshold - 10, 30)
                logger.info("📈 Strategy adjustment: Increasing risk due to strong performance")
                
            # Apply adjustments
            for key, value in adjustments.items():
                setattr(self, key, value)
                
            # Log strategy evolution
            if self.db:
                await self.db.log_strategy_evolution({
                    'timestamp': datetime.now(),
                    'risk': self.risk_per_trade,
                    'win_rate': win_rate,
                    'adjustments': adjustments
                })
                
        except Exception as e:
            logger.error(f"Error in learn_from_trades: {e}")
            
    async def get_stats(self) -> Dict:
        """Get autonomous trading statistics"""
        try:
            if self.db:
                trades = await self.db.get_autonomous_trades()
                winners = [t for t in trades if t.get('pnl', 0) > 0]
                losers = [t for t in trades if t.get('pnl', 0) < 0]
                
                return {
                    'active': self.active,
                    'total_trades': len(trades),
                    'win_rate': len(winners) / len(trades) if trades else 0,
                    'total_pnl': sum(t.get('pnl', 0) for t in trades),
                    'risk_per_trade': self.risk_per_trade,
                    'min_score': self.min_score_threshold,
                    'trades_today': self.trades_today,
                    'max_daily': self.max_trades_per_day,
                    'market_open': self.is_market_open()
                }
        except:
            pass
            
        return {
            'active': self.active,
            'risk_per_trade': self.risk_per_trade,
            'min_score': self.min_score_threshold,
            'trades_today': self.trades_today
        }
