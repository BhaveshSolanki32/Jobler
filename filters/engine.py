from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from filters.definitions import FilterRule
from filters.rules.keyword_rank import KeywordScorer
from sites.base import JobListing


@dataclass
class FilterResult:
    passing: list[JobListing]
    rejected: list[tuple[JobListing, str]]  # (job, rule.label)


def _get_value(job: JobListing, rule: FilterRule):
    if rule.source == "job":
        return getattr(job, rule.field, None)
    slm = job.slm_response or {}
    return slm.get(rule.field)


def _apply_range(rule: FilterRule, value) -> bool:
    if value is None:
        return rule.null_passes
    try:
        v = float(value)
    except (TypeError, ValueError):
        return rule.null_passes
    if rule.min is not None and v < float(rule.min):
        return False
    if rule.max is not None and v > float(rule.max):
        return False
    return True


def _apply_keyword(rule: FilterRule, value) -> bool:
    if value is None:
        return rule.null_passes
    v = str(value).lower()
    vals = rule.values  # already lowercased in FilterRule.from_dict

    if rule.mode == "allowlist":
        if not vals:
            return True
        return v in vals
    if rule.mode == "blocklist":
        return v not in vals
    if rule.mode == "contains_any":
        if not vals:
            return True
        return any(kw in v for kw in vals)
    if rule.mode == "not_contains_any":
        return not any(kw in v for kw in vals)
    return True


def _check(job: JobListing, rule: FilterRule) -> bool:
    value = _get_value(job, rule)
    if rule.type == "range":
        return _apply_range(rule, value)
    if rule.type == "keyword":
        return _apply_keyword(rule, value)
    return True


class FilterEngine:
    def __init__(self, scorers=None):
        self._scorers = scorers or [KeywordScorer()]

    def run(self, jobs: list[JobListing], config: dict) -> FilterResult:
        rules = [FilterRule.from_dict(r) for r in config.get("filters", {}).get("rules", [])]
        passing, rejected = [], []

        for job in jobs:
            fail_reason: Optional[str] = None
            for rule in rules:
                if not _check(job, rule):
                    fail_reason = rule.label
                    break
            if fail_reason:
                rejected.append((job, fail_reason))
            else:
                job.keyword_score = sum(s.score(job, config) for s in self._scorers)
                passing.append(job)

        passing.sort(key=lambda j: j.keyword_score, reverse=True)
        return FilterResult(passing=passing, rejected=rejected)
