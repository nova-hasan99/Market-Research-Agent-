"""
Pydantic request / response models.
"""
from typing import Optional, Literal
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    asset_type: Literal["forex", "stock"] = "forex"
    symbol: str          # forex → base currency (e.g. "EUR"); stock → ticker (e.g. "AAPL")
    quote: Optional[str] = "USD"   # forex only (e.g. "USD")
    timeframe: str = "1d"          # 1m/5m/15m/1h/4h/8h/1d/1w/1mo
