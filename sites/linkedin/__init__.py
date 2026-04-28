from sites.linkedin.searcher import LinkedInSearcher
from sites.linkedin.extractor import LinkedInExtractor
from sites.linkedin.easy_apply import LinkedInEasyApplier
from sites.base import BaseSiteSkill, JobListing, ApplicationResult
from sites.registry import SiteSkillRegistry


class LinkedInSkill(BaseSiteSkill):
    def __init__(self):
        self._searcher = LinkedInSearcher()
        self._extractor = LinkedInExtractor()
        self._applier = LinkedInEasyApplier()

    def search(self, terms: list[str], config: dict) -> list[JobListing]:
        return self._searcher.search(terms, config)

    def extract(self, listing: JobListing) -> JobListing:
        return self._extractor.extract(listing)

    def apply(self, listing: JobListing, answers: dict, resume_path: str) -> ApplicationResult:
        return self._applier.apply(listing, answers, resume_path)


SiteSkillRegistry.register("linkedin.com", LinkedInSkill)
