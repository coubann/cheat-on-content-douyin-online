"""Pydantic models for cheat-state and scoring"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RubricWeights(BaseModel):
    ER: float = 1.0
    HP: float = 1.0
    QL: float = 1.0
    NA: float = 1.0
    AB: float = 1.0
    SR: float = 1.0
    SAT: float = 1.0
    TS: float = 1.0
    MS: float = 1.0
    CC: float = 1.0


class CheatState(BaseModel):
    schema_version: str = "1.4-ext"
    your_project_version: str = "0.1.0"
    rubric_version: str = "v0"
    content_form: str = "opinion-video"
    platforms: list[str] = Field(default_factory=lambda: ["douyin"])
    typical_duration_seconds: int = 240
    target_publish_cadence_days: int = 2
    baseline_plays: int | None = None
    calibration_samples: int = 0
    last_bump_at: str | None = None
    rubric_weights: RubricWeights = Field(default_factory=RubricWeights)
    enabled_trend_sources: list[str] = Field(default_factory=lambda: ["douyin-hot", "xhs-explore"])
    pending_retros: list[str] = Field(default_factory=list)
    shoots: list[str] = Field(default_factory=list)
    in_progress_session: str | None = None
    hooks_installed: bool = False
    initialized_at: datetime = Field(default_factory=datetime.now)


class DimensionScore(BaseModel):
    dimension: str
    score: float = Field(ge=0, le=5)
    confidence: float = Field(ge=0, le=1)
    reason: str
    self_check: str


class ScoreResult(BaseModel):
    dimensions: list[DimensionScore]
    composite: float = Field(ge=0, le=10)
    rubric_version: str
