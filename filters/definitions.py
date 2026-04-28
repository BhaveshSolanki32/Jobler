from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FilterRule:
    """
    One filter rule loaded from user_config.json filters.rules[].

    type="range"   — numeric field must fall within [min, max] (either bound optional)
    type="keyword" — string/bool field checked against a value list via mode:
                     allowlist        : value must be in values
                     blocklist        : value must NOT be in values
                     contains_any     : field string must contain at least one value as substring
                     not_contains_any : field string must contain none of the values
    source="slm"   — read from job.slm_response dict
    source="job"   — read from job attribute directly (title, location, company, …)
    null_passes    — if the field is missing/null, True = pass, False = fail
    """

    type: str
    field: str
    source: str = "slm"
    null_passes: bool = True
    # range
    min: Any = None
    max: Any = None
    # keyword
    mode: str = "allowlist"
    values: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> FilterRule:
        return cls(
            type=d["type"],
            field=d["field"],
            source=d.get("source", "slm"),
            null_passes=d.get("null_passes", True),
            min=d.get("min"),
            max=d.get("max"),
            mode=d.get("mode", "allowlist"),
            values=[str(v).lower() for v in d.get("values", [])],
        )

    @property
    def label(self) -> str:
        return f"{self.type}:{self.field}"
