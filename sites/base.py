import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class JobListing:
    job_id: str
    url: str
    site: str
    title: str
    company: str
    location: str
    posted_date: str
    jd_text: str = ""
    company_info: str = ""
    keyword_score: float = 0.0
    summary: str = ""
    slm_response: Optional[dict] = None

    def to_db_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "site": self.site,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "posted_date": self.posted_date,
            "jd_text": self.jd_text,
            "company_info": self.company_info,
            "keyword_score": self.keyword_score,
            "summary": self.summary,
            "slm_response": json.dumps(self.slm_response) if self.slm_response else None,
            "status": "pending_initial_approval",
        }


class Searchable(ABC):
    @abstractmethod
    def search(self, terms: list[str], config: dict) -> list[JobListing]:
        ...


class Extractable(ABC):
    @abstractmethod
    def extract(self, listing: JobListing) -> JobListing:
        ...
