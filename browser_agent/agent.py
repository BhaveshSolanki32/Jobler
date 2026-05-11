import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CHROMIUM = Path.home() / '.cache/ms-playwright/chromium-1217/chrome-linux64/chrome'
_SKILLS_BASE = Path(__file__).parent / 'skills' / 'site'

_BASE_SYSTEM_PROMPT = """
You are a browser agent performing a specific task on a website.
A skill file below tells you exactly how to navigate the site for this task.
At every step you receive browser_state with interactive elements as [index]<tag>.
Only interact with elements that have an [index].
Respond ONLY with valid JSON — no text outside JSON.

After filling any field, before clicking Next or Review, read all text visible near those fields in browser_state. If you see any message indicating invalid input, a format requirement, or an error indicator — fix the field to match what it is asking for before proceeding.
If you clicked Next or Review and the form did not advance to a new page, do NOT click it again. Instead read the current browser_state carefully, find what is preventing submission, and fix it.
"""

_SITE_MAP: dict[str, tuple[str, str]] = {
    'linkedin.com': ('linkedin', 'linkedin.json'),
}


@dataclass
class AgentResult:
    success: bool
    collected: list[str] = field(default_factory=list)
    error: Optional[str] = None


def resolve_skill(url: str) -> Optional[Path]:
    for domain, (folder, _) in _SITE_MAP.items():
        if domain in url:
            return _SKILLS_BASE / folder / 'base.md'
    return None


def resolve_session(url: str, session_dir: Path) -> Optional[Path]:
    for domain, (_, session_file) in _SITE_MAP.items():
        if domain in url:
            p = session_dir / session_file
            return p if p.exists() else None
    return None


def extract_task(url: str, answers: dict) -> str:
    answers_str = '\n'.join(f'- {k}: {v}' for k, v in answers.items())
    return f"""
Go to {url}
Mode: EXTRACT
Follow the skill instructions exactly.
Navigate every page of the application form and call save_item for every form field label you see.
Do NOT submit. Stop when you reach the review page and call done with success=true.

Answers available (use these to fill required fields so you can proceed past each page):
{answers_str}
"""


def submit_task(url: str, qa_content: str) -> str:
    return f"""
Go to {url}
Mode: SUBMIT
Follow the skill instructions exactly.
Navigate every page of the application form, fill all fields using the answers below, then submit.
After submitting call done with success=true.

Questions and answers:
{qa_content}
"""


def run(task: str, skill: Optional[Path], cfg: dict) -> AgentResult:
    try:
        return asyncio.run(_run_async(task, skill, cfg))
    except Exception as e:
        logger.exception('Browser agent crashed')
        return AgentResult(success=False, error=str(e))


async def _run_async(task: str, skill: Optional[Path], cfg: dict) -> AgentResult:
    from browser_use import Agent, Controller
    from browser_use.agent.views import ActionResult
    from browser_use.browser.profile import BrowserProfile
    from browser_use.llm.openai.like import ChatOpenAILike

    llm_cfg = cfg.get('llm', {})
    collected: list[str] = []

    llm = ChatOpenAILike(
        model=llm_cfg.get('model', 'anthropic/claude-3-5-haiku'),
        api_key=cfg['_env']['openrouter_api_key'],
        base_url=llm_cfg.get('base_url', 'https://openrouter.ai/api/v1'),
        add_schema_to_system_prompt=True,
    )

    profile_args: dict = {
        'executable_path': str(_CHROMIUM),
        'headless': cfg.get('browser', {}).get('headless', False),
        'args': ['--no-sandbox', '--disable-dev-shm-usage'],
        'wait_for_network_idle_page_load_time': 5.0,
        'page_load_timeout': 30,
    }
    session_file = cfg.get('_session_file')
    if session_file and Path(session_file).exists():
        profile_args['storage_state'] = str(session_file)
        logger.info('Browser agent: loaded session from %s', session_file)
    else:
        logger.warning('Browser agent: no session — may hit login wall')

    profile = BrowserProfile(**profile_args)
    controller = Controller()

    @controller.action('Save a collected item such as a form field label or question')
    def save_item(label: str):
        collected.append(label)
        return ActionResult(extracted_content=f'Saved: {label}')

    skill_text = skill.read_text(encoding='utf-8') if skill and skill.exists() else ''
    if skill_text:
        system_prompt = _BASE_SYSTEM_PROMPT.strip() + '\n\n## Skill\n\n' + skill_text
    else:
        logger.warning('Browser agent: no skill loaded — running with base prompt only')
        system_prompt = _BASE_SYSTEM_PROMPT.strip()

    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=profile,
        controller=controller,
        use_vision=False,
        override_system_message=system_prompt,
    )

    result = await agent.run(max_steps=30)
    final = result.final_result() or ''
    success = result.is_done() and 'success=true' in final.lower()

    return AgentResult(
        success=success,
        collected=collected,
        error=None if success else (final or 'Agent did not complete — no final result'),
    )
