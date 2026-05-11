from typing import Optional, Type


class SiteSkillRegistry:
    _registry: dict[str, Type] = {}

    @classmethod
    def register(cls, domain: str, skill_class: Type) -> None:
        cls._registry[domain] = skill_class

    @classmethod
    def get(cls, url: str) -> Optional[Type]:
        for domain, skill in cls._registry.items():
            if domain in url:
                return skill
        return None

    @classmethod
    def all_domains(cls) -> list[str]:
        return list(cls._registry.keys())
