"""Task-source helpers for SWE collection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_R2_BASE = "https://pub-7882418a56434a479bf9a7febd660b36.r2.dev/bugs"


def parse_task_range(spec: str) -> list[int]:
    values: list[int] = []
    if not spec.strip():
        return values
    for chunk in spec.split(","):
        part = chunk.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if end < start:
                raise ValueError(f"invalid task range: {part}")
            values.extend(range(start, end + 1))
        else:
            values.append(int(part))
    return values


class SweTaskSource:
    """Load SWE tasks from cache, task files, or an HTTP task pool."""

    def __init__(
        self,
        *,
        cache_dir: str = "/tmp/orbit-swe-task-cache",
        r2_base: str = DEFAULT_R2_BASE,
        user_agent: str = "orbit-swe-collect/1.0",
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.r2_base = r2_base.rstrip("/")
        self.user_agent = user_agent

    def cache_path_for(self, task_id: int) -> Path:
        return self.cache_dir / f"task_{task_id:011d}.json"

    @staticmethod
    def _normalize_task_payload(task_id: int, payload: dict) -> dict:
        task = dict(payload)
        task.setdefault("task_id", task_id)
        task.setdefault("instance_id", f"task_{task_id:011d}")
        task.setdefault("repo", "")
        task.setdefault("base_commit", "")
        task.setdefault("patch", "")
        task.setdefault("test_patch", "")
        task.setdefault("problem_statement", "")
        task.setdefault("fail_to_pass", [])
        task.setdefault("pass_to_pass", [])
        task.setdefault("dockerhub_tag", "")
        task.setdefault("test_command", "")
        task.setdefault("repo_language", "")
        return task

    def load_task(self, task_id: int) -> dict | None:
        local = self.cache_path_for(task_id)
        if local.exists():
            return self._normalize_task_payload(task_id, json.loads(local.read_text(encoding="utf-8")))

        url = f"{self.r2_base}/task_{task_id:011d}.json"
        try:
            req = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read())
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        task = self._normalize_task_payload(task_id, payload)
        local.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return task

    def iter_task_ids(self, *, task_range: str = "", task_file: str = "") -> list[int]:
        ids = parse_task_range(task_range)
        if task_file:
            path = Path(task_file)
            if not path.exists():
                raise FileNotFoundError(path)
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("{"):
                        payload = json.loads(line)
                        if "task_id" in payload:
                            ids.append(int(payload["task_id"]))
                        elif "id" in payload:
                            ids.append(int(payload["id"]))
                        else:
                            raise ValueError(f"task file row missing task id: {line[:80]}")
                    else:
                        ids.append(int(line))
        seen: set[int] = set()
        ordered: list[int] = []
        for task_id in ids:
            if task_id in seen:
                continue
            seen.add(task_id)
            ordered.append(task_id)
        return ordered

    def iter_tasks(self, *, task_range: str = "", task_file: str = "") -> Iterable[dict]:
        for task_id in self.iter_task_ids(task_range=task_range, task_file=task_file):
            task = self.load_task(task_id)
            if task is not None:
                yield task
