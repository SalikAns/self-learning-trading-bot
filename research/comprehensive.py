# research/comprehensive.py
import yfinance as yf
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class ComprehensiveResearch:
    """Research engine for stock analysis"""
    
    def __init__(self):
        logger.info("ComprehensiveResearch initialized")
    
    def research(self, ticker: str) -> dict:
        """Get comprehensive analysis for a ticker"""
        try:
            logger.info(f"Researching {ticker}...")
            
            # Get stock data
            stock = yf.Ticker(ticker)
            hist = stock.history(period="3mo")
            
            if hist.empty:
                logger.error(f"No data found for {ticker}")
                return {
                    'ticker': ticker,
                    'error': 'No data found',
                    'total_score': 0,
                    'price': 0,
                    'technical': 0,
                    'fundamental': 0,
                    'sentiment': 0,
                    'risk': 0
                }
            
            # Current price
            current_price = hist['Close'].iloc[-1]
            
            # Calculate scores
            technical = self._technical_score(hist)
            fundamental = self._fundamental_score(stock)
            sentiment = self._sentiment_score(hist)
            risk = self._risk_score(hist)
            
            # Total score (average of all)
            total_score = (technical + fundamental + sentiment + risk) / 4
            
            result = {
                'ticker': ticker,
                'price': float(current_price),
                'technical': float(technical),
                'fundamental': float(fundamental),
                'sentiment': float(sentiment),
                'risk': float(risk),
                'total_score': float(total_score),
                'volatility': float(hist['Close'].pct_change().std() * 100),
                'volume_trend': 'increasing' if hist['Volume'].iloc[-5:].mean() > hist['Volume'].mean() else 'decreasing'
            }
            
            logger.info(f"Research complete for {ticker}: Score={total_score:.1f}")
            return result
            
        except Exception as e:
            logger.error(f"Error researching {ticker}: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'total_score': 0,
                'price': 0,
                'technical': 0,
                'fundamental': 0,
                'sentiment': 0,
                'risk': 0
            }
    
    def _technical_score(self, hist: pd.DataFrame) -> float:
        """Calculate technical score (0-100)"""
        try:
            current = hist['Close'].iloc[-1]
            sma_20 = hist['Close'].rolling(20).mean().iloc[-1]
            sma_50 = hist['Close'].rolling(50).mean().iloc[-1]
            
            # RSI
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if not pd.isna(rs.iloc[-1]) else 50
            
            score = 50
            
            # Price vs SMAs
            if current > sma_20:
                score += 15
            if current > sma_50:
                score += 15
            
            # RSI
            if rsi < 30:
                score += 20
            elif rsi > 70:
                score -= 20
            elif 40 < rsi < 60:
                score += 10
            
            return max(0, min(100, score))
            
        except Exception as e:
            logger.error(f"Technical score error: {e}")
            return 50
    
    def _fundamental_score(self, stock) -> float:
        """Calculate fundamental score (0-100)"""
        try:
            info = stock.info
            score = 50
            
            # Market cap
            market_cap = info.get('marketCap', 0)
            if market_cap > 100000000000:  # $100B
                score += 15
            elif market_cap > 10000000000:  # $10B
                score += 5
            
            # Profit margin
            profit_margin = info.get('profitMargins', 0)
            if profit_margin > 0.1:
                score += 15
            elif profit_margin > 0:
                score += 5
            
            # PE ratio
            pe = info.get('trailingPE', 0)
            if 10 < pe < 30:
                score += 10
            elif pe > 50:
                score -= 10
            elif pe < 0:
                score -= 5
            
            return max(0, min(100, score))
            
        except Exception as e:
            logger.error(f"Fundamental score error: {e}")
            return 50
    
    def _sentiment_score(self, hist: pd.DataFrame) -> float:
        """Calculate sentiment score (0-100)"""
        try:
            score = 50
            
            # Volume trend
            avg_volume = hist['Volume'].mean()
            recent_volume = hist['Volume'].iloc[-5:].mean()
            
            if recent_volume > avg_volume * 1.2:
                score += 15
            elif recent_volume < avg_volume * 0.8:
                score -= 10
            
            # Price trend (last 5 days)
            if len(hist) >= 5:
                price_change = (hist['Close'].iloc[-1] - hist['Close'].iloc[-5]) / hist['Close'].iloc[-5]
                if price_change > 0.05:
                    score += 15
                elif price_change < -0.05:
                    score -= 15
            
            return max(0, min(100, score))
            
        except Exception as e:
            logger.error(f"Sentiment score error: {e}")
            return 50
    
    def _risk_score(self, hist: pd.DataFrame) -> float:
        """Calculate risk score (higher = safer)"""
        try:
            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * 100
            
            if volatility < 20:
                return 80
            elif volatility < 40:
                return 60
            elif volatility < 60:
                return 40
            else:
                return 20
                
        except Exception as e:
            logger.error(f"Risk score error: {e}")
            return 50
