from abc import ABC, abstractmethod
from sites.base import JobListing


class BaseScorer(ABC):
    """Adds a numeric score contribution; never rejects a job."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def score(self, job: JobListing, config: dict) -> float: ...
