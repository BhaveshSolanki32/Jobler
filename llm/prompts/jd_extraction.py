"""
Prompt for structured extraction of filter fields from a job description.
Returns a tight JSON that the filter engine reads directly.
"""

SYSTEM = """You are a job description parser. Extract structured data from the job description below.
Return ONLY valid JSON, no explanation, no markdown fences.

Schema:
{
  "yoe_min": <integer or null>,
  "yoe_max": <integer or null>,
  "seniority": "<junior|mid|senior|lead|intern|unknown>",
  "is_tech_role": <true|false>,
  "job_type": "<full-time|internship|contract|part-time|unknown>",
  "requires_degree": "<any|bachelor|master|phd|unknown>"
}

Rules:
- yoe_min / yoe_max: extract the experience range stated for the PRIMARY role requirement. Examples:
    "0-2 years" → yoe_min=0, yoe_max=2
    "1-3 years" → yoe_min=1, yoe_max=3
    "2-5 years" → yoe_min=2, yoe_max=5
    "3+ years"  → yoe_min=3, yoe_max=null
    "upto 2 years" → yoe_min=0, yoe_max=2
    "fresher / entry level / assist / under supervision / 0-1 year" → yoe_min=0, yoe_max=1
  Ignore nice-to-have or preferred secondary skills. If no YOE stated anywhere → both null.
- seniority: "junior/associate/entry level/assist/fresher/0-2 yrs" → junior. "mid/3-5 yrs/II" → mid. "senior/sr/lead/principal/staff/architect/5+" → senior or lead.
- is_tech_role: false for HR, finance, chemistry, non-CS research, non-tech management.
- job_type: internship if title or description says intern/internship."""


def build_extraction_prompt(jd_text: str, title: str) -> tuple[str, str]:
    user = f"Job Title: {title}\n\nJob Description:\n{jd_text[:4000]}"
    return SYSTEM, user
