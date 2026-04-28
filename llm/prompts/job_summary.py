def build_summary_prompt(jd_text: str, title: str, company: str) -> tuple[str, str]:
    system = (
        "You are a job analyst. Given a job description, return exactly 2 sentences: "
        "first sentence summarises what the role does, second lists the top 3 required skills. "
        "Be concise. No bullet points. No preamble."
    )
    user = (
        f"Role: {title} at {company}\n\n"
        f"Job Description:\n{jd_text[:3000]}"
    )
    return system, user
