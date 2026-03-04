from typing import Literal
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high"]


class UserProfile(BaseModel):
    name: str
    risk_level: str  # TODO: revert to RiskLevel when done testing
    watchlist: list[str] = Field(default_factory=list)
