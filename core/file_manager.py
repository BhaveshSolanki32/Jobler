import os
import shutil
from pathlib import Path


class FileManager:
    def __init__(self, jobs_root: str):
        self.root = Path(jobs_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def job_path(self, job_id: str) -> Path:
        return self.root / job_id

    def job_folder_exists(self, job_id: str) -> bool:
        return self.job_path(job_id).exists()

    def create_job_folder(self, job: dict) -> Path:
        base = self.job_path(job["job_id"])
        (base / "about_job").mkdir(parents=True, exist_ok=True)
        (base / "application").mkdir(exist_ok=True)
        (base / "proof").mkdir(exist_ok=True)
        return base

    def write_jd(self, job_id: str, jd_text: str) -> None:
        path = self.job_path(job_id) / "about_job" / "jd.md"
        path.write_text(jd_text, encoding="utf-8")

    def write_company_info(self, job_id: str, info: str) -> None:
        path = self.job_path(job_id) / "about_job" / "about_company.md"
        path.write_text(info, encoding="utf-8")

    def write_questions(self, job_id: str, questions: str) -> None:
        path = self.job_path(job_id) / "application" / "questions.md"
        path.write_text(questions, encoding="utf-8")

    def save_proof(self, job_id: str, screenshot_paths: list[str]) -> None:
        proof_dir = self.job_path(job_id) / "proof"
        for src in screenshot_paths:
            src_path = Path(src)
            if src_path.exists():
                dest = proof_dir / src_path.name
                if str(src_path) != str(dest):
                    shutil.copy2(src_path, dest)

    def delete_job_folder(self, job_id: str) -> None:
        path = self.job_path(job_id)
        if path.exists():
            shutil.rmtree(path)

    def proof_paths(self, job_id: str) -> list[str]:
        proof_dir = self.job_path(job_id) / "proof"
        if not proof_dir.exists():
            return []
        return sorted(str(p) for p in proof_dir.iterdir() if p.suffix in (".png", ".jpg"))
