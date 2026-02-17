"""Market data client contracts and implementations."""

from .client import MarketClient
from .finnhub import FinnhubMarketClient

__all__ = ["FinnhubMarketClient", "MarketClient"]
