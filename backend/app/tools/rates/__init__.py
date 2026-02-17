"""Rates client contracts and implementations."""

from .client import RatesClient
from .fred import FredRatesClient

__all__ = ["FredRatesClient", "RatesClient"]
