from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ErrorBucket:
    lead_hours: int
    n: int
    bias_f: float
    sigma_f: float


class ForecastErrorModel:
    def __init__(self, payload: dict):
        self.payload = payload
        self.buckets: dict[int, ErrorBucket] = {}
        for lead, stats in payload.get("buckets", {}).items():
            self.buckets[int(lead)] = ErrorBucket(
                lead_hours=int(lead),
                n=int(stats["n"]),
                bias_f=float(stats["bias_f"]),
                sigma_f=float(stats["sd_error_f"]),
            )
        if not self.buckets:
            raise ValueError("error model contains no fitted lead-time buckets")

    @classmethod
    def load(cls, path: str | Path) -> "ForecastErrorModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def nearest(self, lead_hours: float, max_distance: float | None = None) -> ErrorBucket:
        bucket = min(self.buckets.values(), key=lambda x: abs(x.lead_hours - lead_hours))
        if max_distance is not None and abs(bucket.lead_hours - lead_hours) > max_distance:
            raise ValueError(
                f"nearest fitted lead bucket ({bucket.lead_hours}h) is too far from {lead_hours:.1f}h"
            )
        return bucket
