import json
import logging
from openai import OpenAI
from llm.prompts.job_summary import build_summary_prompt
from llm.prompts.jd_extraction import build_extraction_prompt

logger = logging.getLogger(__name__)

_EXTRACTION_DEFAULTS = {
    "yoe_min": None,
    "yoe_max": None,
    "seniority": "unknown",
    "is_tech_role": True,
    "job_type": "unknown",
    "requires_degree": "unknown",
}


class LLMClient:
    def __init__(self, config: dict):
        llm_cfg = config.get("llm", {})
        api_key = config.get("_env", {}).get("openrouter_api_key", "")
        self._model = llm_cfg.get("model", "anthropic/free")
        self._client = OpenAI(
            api_key=api_key,
            base_url=llm_cfg.get("base_url", "https://openrouter.ai/api/v1"),
        )

    def complete(self, system: str, user: str, max_tokens: int = 300) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()

    def extract_jd_fields(self, jd_text: str, title: str = "") -> dict:
        """
        Call LLM to extract structured filter fields from a JD.
        Returns a dict matching _EXTRACTION_DEFAULTS schema.
        Always returns a valid dict — never raises.
        """
        if not jd_text or len(jd_text) < 50:
            return dict(_EXTRACTION_DEFAULTS)
        try:
            system, user = build_extraction_prompt(jd_text, title)
            raw = self.complete(system, user, max_tokens=150)
            # Strip markdown fences if model ignores instructions
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
            result = dict(_EXTRACTION_DEFAULTS)
            result.update({k: data[k] for k in _EXTRACTION_DEFAULTS if k in data})
            return result
        except Exception as e:
            logger.warning("JD extraction failed for '%s': %s", title, e)
            return dict(_EXTRACTION_DEFAULTS)

    def summarize_job(self, jd_text: str, title: str = "", company: str = "") -> str:
        try:
            system, user = build_summary_prompt(jd_text, title, company)
            return self.complete(system, user, max_tokens=200)
        except Exception as e:
            logger.warning("Summary failed: %s", e)
            return ""
