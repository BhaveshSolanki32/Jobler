import time
import requests


class CapMonsterClient:
    BASE_URL = "https://api.capmonster.cloud"

    def __init__(self, api_key: str):
        self._key = api_key

    def solve_recaptcha_v2(self, site_key: str, page_url: str, timeout: int = 120) -> str:
        task_id = self._create_task({
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
        })
        return self._poll(task_id, timeout)

    def solve_hcaptcha(self, site_key: str, page_url: str, timeout: int = 120) -> str:
        task_id = self._create_task({
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
        })
        return self._poll(task_id, timeout)

    def _create_task(self, task: dict) -> int:
        resp = requests.post(
            f"{self.BASE_URL}/createTask",
            json={"clientKey": self._key, "task": task},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("errorId"):
            raise RuntimeError(f"CapMonster error: {data.get('errorDescription')}")
        return data["taskId"]

    def _poll(self, task_id: int, timeout: int) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            resp = requests.post(
                f"{self.BASE_URL}/getTaskResult",
                json={"clientKey": self._key, "taskId": task_id},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ready":
                return data["solution"]["gRecaptchaResponse"]
        raise TimeoutError(f"CapMonster did not solve captcha within {timeout}s")
