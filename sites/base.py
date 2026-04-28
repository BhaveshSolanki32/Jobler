import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    slm_response: Optional[dict] = None  # structured extraction from LLM

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


@dataclass
class ApplicationResult:
    success: bool
    screenshots: list[str] = field(default_factory=list)
    error_reason: Optional[str] = None
    pending_review: bool = False


class Searchable(ABC):
    @abstractmethod
    def search(self, terms: list[str], config: dict) -> list[JobListing]:
        """Search site; return partial listings (no full JD yet)."""
        ...


class Extractable(ABC):
    @abstractmethod
    def extract(self, listing: JobListing) -> JobListing:
        """Fetch full JD + company info for a listing."""
        ...


class Applyable(ABC):
    @abstractmethod
    def apply(
        self, listing: JobListing, answers: dict, resume_path: str, mode: str = "extract"
    ) -> ApplicationResult:
        """Fill and submit application. Return result with screenshot paths."""
        ...


class BaseSiteSkill(Searchable, Extractable, Applyable):
    """Convenience base for sites that implement all three interfaces."""
    pass
