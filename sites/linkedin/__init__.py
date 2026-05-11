from sites.linkedin.searcher import LinkedInSearcher
from sites.linkedin.extractor import LinkedInExtractor
from sites.base import JobListing
from sites.registry import SiteSkillRegistry


class LinkedInSkill:
    def __init__(self):
        self._searcher = LinkedInSearcher()
        self._extractor = LinkedInExtractor()

    def search(self, terms: list[str], config: dict) -> list[JobListing]:
        return self._searcher.search(terms, config)

    def extract(self, listing: JobListing) -> JobListing:
        return self._extractor.extract(listing)


SiteSkillRegistry.register("linkedin.com", LinkedInSkill)
