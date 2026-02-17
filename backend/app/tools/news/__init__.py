"""News client contracts and implementations."""

from .client import NewsClient
from .finnhub import FinnhubNewsClient
from .tavily import TavilyNewsClient

__all__ = [
    "FinnhubNewsClient",
    "NewsClient",
    "TavilyNewsClient",
]
