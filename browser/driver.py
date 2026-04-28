"""
BrowserDriver — owns the Camoufox/Playwright session.
All Playwright calls are routed through BrowserThread so they always
execute in the single OS thread that created the context.
"""
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from browser.thread import BrowserThread
from browser.captcha import CapMonsterClient


class BrowserDriver:
    _instance: Optional["BrowserDriver"] = None
    _lock = threading.Lock()

    def __init__(self, config: dict) -> None:
        self._config = config
        self._cm = None
        self._browser = None
        self._context = None
        self._is_running = False
        self._bt = BrowserThread.get()
        api_key = config.get("_env", {}).get("capmonster_api_key", "")
        self._capmonster: Optional[CapMonsterClient] = CapMonsterClient(api_key) if api_key else None

    # ── Singleton ──────────────────────────────────────────────────────

    @classmethod
    def init_driver(cls, config: dict) -> "BrowserDriver":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
        return cls._instance

    @classmethod
    def get_instance(cls) -> "BrowserDriver":
        if cls._instance is None:
            raise RuntimeError("BrowserDriver not initialised. Call init_driver(config) first.")
        return cls._instance

    # ── Lifecycle (submitted to browser thread) ────────────────────────

    def launch(self) -> None:
        if self._is_running:
            return
        self._bt.submit(self._do_launch)

    def _do_launch(self) -> None:
        from camoufox.sync_api import Camoufox
        headless = self._config.get("browser", {}).get("headless", False)
        self._cm = Camoufox(headless=headless)
        self._browser = self._cm.__enter__()
        session_dir = Path(self._config.get("browser", {}).get("session_dir", ".sessions"))
        session_dir.mkdir(exist_ok=True)
        session_path = session_dir / "linkedin.json"
        if session_path.exists():
            self._context = self._browser.new_context(storage_state=str(session_path))
        else:
            self._context = self._browser.new_context()
        self._is_running = True

    def open_login_page(self, url: str) -> None:
        """Open browser and navigate to login page. Blocks until page is loaded."""
        def _open():
            if not self._is_running:
                self._do_launch()
            page = self._context.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        self._bt.submit(_open, timeout=60)  # blocks — browser is open when this returns

    def save_session(self, site: str = "linkedin") -> None:
        def _save():
            session_dir = Path(self._config.get("browser", {}).get("session_dir", ".sessions"))
            session_dir.mkdir(exist_ok=True)
            self._context.storage_state(path=str(session_dir / f"{site}.json"))
        self._bt.submit(_save)

    def close(self) -> None:
        def _close():
            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass
            if self._cm:
                try:
                    self._cm.__exit__(None, None, None)
                except Exception:
                    pass
            self._is_running = False
            self._browser = None
            self._context = None
            self._cm = None
        self._bt.submit(_close)

    # ── State queries (safe from any thread — no Playwright calls) ─────

    def is_running(self) -> bool:
        return self._is_running

    def has_session(self, site: str = "linkedin") -> bool:
        session_dir = Path(self._config.get("browser", {}).get("session_dir", ".sessions"))
        return (session_dir / f"{site}.json").exists()

    # ── Run arbitrary browser work in the browser thread ──────────────

    def run(self, fn: Callable[..., Any], timeout: float = 300) -> Any:
        """
        Submit fn to browser thread and return its result.
        fn is called with (context, driver) — use context to open pages,
        use driver for helpers like screenshot() and solve_captcha_if_present().
        """
        return self._bt.submit(lambda: fn(self._context, self), timeout=timeout)

    # ── Helpers — MUST only be called from within the browser thread ──

    def screenshot(self, page, path: str) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=path, full_page=False)
        return path

    def solve_captcha_if_present(self, page) -> bool:
        if not self._capmonster:
            return False
        try:
            iframe = page.query_selector("iframe[src*='recaptcha']")
            if iframe:
                src = iframe.get_attribute("src") or ""
                site_key = next(
                    (p[2:] for p in src.split("&") if p.startswith("k=")), ""
                )
                if site_key:
                    token = self._capmonster.solve_recaptcha_v2(site_key, page.url)
                    page.evaluate(
                        f"document.getElementById('g-recaptcha-response').innerHTML='{token}'"
                    )
                    return True
        except Exception:
            pass
        return False
