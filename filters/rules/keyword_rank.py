from filters.base import BaseScorer
from sites.base import JobListing


class KeywordScorer(BaseScorer):
    name = "keyword_scorer"

    def score(self, job: JobListing, config: dict) -> float:
        bank = [k.lower() for k in config.get("keyword_bank", [])]
        if not bank:
            return 0.0
        jd = (job.jd_text or "").lower()
        title = (job.title or "").lower()
        combined = jd + " " + title
        hits = sum(1 for kw in bank if kw in combined)
        return round(hits / len(bank), 4)
