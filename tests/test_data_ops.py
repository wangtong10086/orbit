"""Tests for runtime-facing data operations and remediation fixes."""

import os
import sys
from pathlib import Path
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.data.aggregate import build_mixed_records, publish_mixed_dataset
from forge.data.collect_adapters import collect_navworld
from forge.data.collect_publish import _as_collect_sync_result
from forge.data.collect_service import swe_sync_pipeline
from forge.data.canonical_ops import download_from_hf, hf_sync_repo, upload_dataset_card, validate_entry
from forge.data.game_gen import generate_game_data
from forge.data.memorygym_split import split_trajectory
from forge.data.swe_ops import distill_status, sync_new_trajectories
from forge.execution.contracts import NavworldCollectConfig
from forge.foundation.data_contracts import CanonicalSyncReport, PublishReport, SweSyncRequest
from forge.foundation.environment_catalog import default_environment_catalog


class TestSweOps:
    def test_distill_status_reports_infra_error_instead_of_parsing_crash(self, monkeypatch):
        responses = iter(
            [
                ("", 1),
                ("", 0),
                ("wrk-remote: Permission denied (publickey).", 255),
            ]
        )
        monkeypatch.setattr("forge.data.swe_ops._ssh_run", lambda *args, **kwargs: next(responses))

        status = distill_status()

        assert status["infra_error"] == (
            "container probe failed: wrk-remote: Permission denied (publickey)."
        )
        assert status["containers"] == 0

    def test_sync_new_trajectories_returns_blocked_reason(self, monkeypatch):
        monkeypatch.setattr(
            "forge.data.swe_ops.distill_status",
            lambda: {
                "running": False,
                "processes": [],
                "output_files": [],
                "containers": 0,
                "infra_error": "process probe failed: permission denied",
            },
        )

        result = sync_new_trajectories(dry_run=True)

        assert result["blocked_reason"] == "process probe failed: permission denied"
        assert result["new_count"] == 0


class TestHfDataOps:
    def test_hf_sync_repo_downloads_matching_prefixes(self, monkeypatch, tmp_path):
        class FakeApi:
            def __init__(self, token=None):
                pass

            def list_repo_files(self, repo_id, repo_type="dataset"):
                return ["canonical/game.jsonl", "raw/game/run1.jsonl", "misc/ignore.txt"]

        def fake_download(**kwargs):
            target = tmp_path / kwargs["filename"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")
            return str(target)

        monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)
        monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)

        result = hf_sync_repo(repo_id="user/repo", local_dir=str(tmp_path))

        assert result.status == "success"
        assert len(result.downloaded) == 2

    def test_download_from_hf_creates_empty_file_when_missing(self, monkeypatch, tmp_path):
        def fail_download(**kwargs):
            raise RuntimeError("missing")

        monkeypatch.setattr("huggingface_hub.hf_hub_download", fail_download)

        result = download_from_hf("GAME", repo_id="user/repo", canonical_dir=str(tmp_path))

        assert result.status == "missing"
        assert (tmp_path / "game.jsonl").exists()

    def test_build_mixed_records_includes_metadata(self, tmp_path):
        canonical = tmp_path / "canonical"
        canonical.mkdir()
        (canonical / "game.jsonl").write_text(
            '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"GAME","score":1.0,"source":"smoke"}\n',
            encoding="utf-8",
        )

        records = build_mixed_records(envs=["GAME"], canonical_dir=str(canonical))

        assert len(records) == 1
        assert records[0]["env"] == "GAME"
        assert records[0]["source"] == "smoke"
        assert records[0]["fingerprint"]

    def test_upload_dataset_card_includes_explicit_config_metadata(self, monkeypatch, tmp_path):
        uploaded = {}

        class FakeApi:
            def __init__(self, token=None):
                self.token = token

            def upload_file(
                self,
                path_or_fileobj,
                path_in_repo,
                repo_id,
                repo_type="dataset",
                commit_message="",
            ):
                uploaded["path_in_repo"] = path_in_repo
                uploaded["repo_id"] = repo_id
                uploaded["content"] = Path(path_or_fileobj).read_text(encoding="utf-8")

        monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)

        result = upload_dataset_card(
            repo_id="user/repo",
            token="hf-test",
            dataset_config="mixed",
            split="train",
        )

        assert result.status == "success"
        assert uploaded["path_in_repo"] == "README.md"
        assert uploaded["repo_id"] == "user/repo"
        assert uploaded["content"].startswith("---\nconfigs:\n")
        assert "config_name: mixed" in uploaded["content"]
        assert "path: mixed/*.parquet" in uploaded["content"]

    def test_publish_mixed_dataset_returns_structured_report(self, monkeypatch, tmp_path):
        canonical = tmp_path / "canonical"
        canonical.mkdir()
        (canonical / "game.jsonl").write_text(
            '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"GAME","score":1.0,"source":"smoke"}\n',
            encoding="utf-8",
        )

        class FakeDataset:
            def __len__(self):
                return 1

            def to_parquet(self, path):
                Path(path).write_text("parquet", encoding="utf-8")

            def push_to_hub(self, *args, **kwargs):
                return None

        monkeypatch.setattr("forge.data.aggregate.build_mixed_dataset", lambda **kwargs: FakeDataset())

        report = publish_mixed_dataset(
            token="hf-test",
            repo_id="user/repo",
            canonical_dir=str(canonical),
            output_dir=str(tmp_path / "mixed"),
        )

        assert isinstance(report, PublishReport)
        assert report.status == "success"
        assert report.rows == 1
        assert report.repo_id == "user/repo"


class TestCollectAdapters:
    def test_collect_navworld_reports_uniform_counts(self, monkeypatch, tmp_path):
        async def fake_generate_batch(**kwargs):
            Path(kwargs["output_path"]).write_text(
                '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"NAVWORLD","score":1.0}\n'
                '{"messages":[{"role":"system","content":"s2"},{"role":"user","content":"u2"},{"role":"assistant","content":"a2"}],"env":"NAVWORLD","score":1.0}\n',
                encoding="utf-8",
            )
            return [{"task_id": 1}, {"task_id": 2}]

        monkeypatch.setattr("forge.data.navworld_gen.generate_batch", fake_generate_batch)
        monkeypatch.setenv("AMAP_API_KEY", "test-amap")
        monkeypatch.setenv("QWEN_API_KEY", "test-qwen")

        result = asyncio.run(
            collect_navworld(
                NavworldCollectConfig(
                    num=2,
                    model="qwen3-max",
                    start_id=0,
                    concurrency=1,
                    problem_type=None,
                    phase1=False,
                ),
                str(tmp_path / "navworld.jsonl"),
            )
        )

        assert result.records == 2
        assert result.success == 2
        assert result.failed == 0
        assert result.output.endswith("navworld.jsonl")


class TestCollectService:
    def test_swe_sync_pipeline_returns_structured_blocked_report(self, monkeypatch):
        monkeypatch.setattr(
            "forge.data.swe_ops.sync_new_trajectories",
            lambda **kwargs: {
                "new_count": 0,
                "skipped_dup": 0,
                "skipped_invalid": 0,
                "total": 12,
                "blocked_reason": "process probe failed: permission denied",
            },
        )

        report = swe_sync_pipeline(SweSyncRequest(machine="", dry_run=True, upload=False, repo_id="user/repo"))

        assert report.status == "blocked"
        assert report.collect.blocked_reason == "process probe failed: permission denied"
        assert report.collect.total == 12
        assert report.sync[0].status == "blocked"


class TestCollectPublish:
    def test_sync_result_adapter_accepts_canonical_sync_report(self):
        report = _as_collect_sync_result(
            CanonicalSyncReport(
                status="success",
                env="GAME",
                path="/tmp/game.jsonl",
                repo_id="user/repo",
            )
        )

        assert report.status == "success"
        assert report.env == "GAME"
        assert report.path == "/tmp/game.jsonl"
        assert report.repo_id == "user/repo"


class TestGameGeneration:
    def test_game_generation_uses_nonsequential_batch_seeds(self, monkeypatch, tmp_path):
        commands = []

        monkeypatch.setattr("forge.data.game_gen.require_game_script", lambda: tmp_path / "generate_random.py")
        monkeypatch.setattr("forge.data.game_gen.require_game_deps", lambda: None)
        monkeypatch.setattr(
            "forge.data.game_gen.resolve_game_trajectory_generator",
            lambda game: __import__(
                "forge.data.game_trajectory_generators",
                fromlist=["GameTrajectoryGeneratorSpec"],
            ).GameTrajectoryGeneratorSpec(
                name="random",
                script_path=str(tmp_path / "generate_random.py"),
            ),
        )

        def fake_run(cmd, cwd=None, capture_output=False, text=False, env=None):
            commands.append(cmd)
            output_path = Path(cmd[cmd.index("-o") + 1])
            start_seed = int(cmd[cmd.index("--start-seed") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"GAME","score":1.0,"game":"liars_dice"}\n',
                encoding="utf-8",
            )
            return type("Completed", (), {"stdout": f"seed={start_seed}", "stderr": "", "returncode": 0})()

        monkeypatch.setattr("forge.data.game_gen.subprocess.run", fake_run)

        result = generate_game_data(
            output_path=str(tmp_path / "game.jsonl"),
            game_name="liars_dice",
            sample_count=1,
            start_seed=123,
            attempt_multiplier=1,
        )

        assert result["records"] == 1
        assert len(commands) == 1
        seen_seeds = [int(cmd[cmd.index("--start-seed") + 1]) for cmd in commands]
        assert len(set(seen_seeds)) == len(seen_seeds)
        assert seen_seeds[0] != 123

    def test_all_games_can_resolve_to_random_generator(self, monkeypatch, tmp_path):
        seen = []

        monkeypatch.setattr("forge.data.game_gen.require_game_script", lambda: tmp_path / "generate_random.py")
        monkeypatch.setattr("forge.data.game_gen.require_game_deps", lambda: None)
        monkeypatch.setattr(
            "forge.data.game_gen.resolve_game_trajectory_generator",
            lambda game: __import__(
                "forge.data.game_trajectory_generators",
                fromlist=["GameTrajectoryGeneratorSpec"],
            ).GameTrajectoryGeneratorSpec(
                name="random",
                script_path=str(tmp_path / "generate_random.py"),
            ),
        )

        def fake_run(cmd, cwd=None, capture_output=False, text=False, env=None):
            seen.append(Path(cmd[1]).name)
            output_path = Path(cmd[cmd.index("-o") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"GAME","score":1.0,"game":"gin_rummy"}\n',
                encoding="utf-8",
            )
            return type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()

        monkeypatch.setattr("forge.data.game_gen.subprocess.run", fake_run)

        result = generate_game_data(
            output_path=str(tmp_path / "game.jsonl"),
            game_name="gin_rummy",
            sample_count=1,
            start_seed=456,
            attempt_multiplier=1,
        )

        assert result["records"] == 1
        assert seen == ["generate_random.py"]

        seen.clear()
        result = generate_game_data(
            output_path=str(tmp_path / "liars.jsonl"),
            game_name="liars_dice",
            sample_count=1,
            start_seed=789,
            attempt_multiplier=1,
        )

        assert result["records"] == 1
        assert seen == ["generate_random.py"]


class TestNavworldStructuredToolCalls:
    def test_navworld_clean_entry_accepts_structured_tool_calls(self):
        env = default_environment_catalog().make_data("NAVWORLD")
        entry = {
            "messages": [
                {"role": "system", "content": "planner"},
                {"role": "user", "content": "trip request"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "1", "function": {"name": "poi_search", "arguments": "{}"}},
                        {"id": "2", "function": {"name": "weather", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "content": "poi result", "tool_call_id": "1"},
                {"role": "tool", "content": "weather result", "tool_call_id": "2"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "3", "function": {"name": "direction", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "content": "direction result", "tool_call_id": "3"},
                {
                    "role": "assistant",
                    "content": "综合对比后推荐高铁，因为时间和价格更平衡。" + "很详细的规划。" * 40,
                },
            ],
            "env": "NAVWORLD",
            "score": 1.0,
        }
        assert env.clean_entry(json.loads(json.dumps(entry))) is not None


class TestMemorygymSplit:
    def test_split_trajectory_preserves_parent_score(self):
        entry = {
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "=== Event 1/2 [QUESTION] ==="},
                {"role": "assistant", "content": "answer"},
                {"role": "user", "content": "[1/2 done]\n\nYour memory is empty. Budget: 1 writes remaining."},
                {"role": "assistant", "content": "OK."},
                {"role": "user", "content": "=== Event 2/2 [QUESTION] ==="},
                {"role": "assistant", "content": "answer2"},
            ],
            "env": "MEMORYGYM",
            "source": "hybrid_perfect",
            "score": 0.7,
            "template": "company",
            "seed": 0,
        }

        samples = split_trajectory(entry)

        assert samples
        assert all(sample["score"] == 0.7 for sample in samples)


class TestMemorygymGen:
    def test_tier_mix_includes_non_hard_buckets(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.data.memorygym_gen.require_memorygym_repo", lambda: tmp_path)
        monkeypatch.setattr(
            "forge.data.memorygym_gen._memorygym_bindings",
            lambda: {
                "TIERS": {
                    "lite": {"name": "lite"},
                    "standard": {"name": "standard"},
                    "hard": {"name": "hard"},
                },
                "TEMPLATES": {"company": object()},
            },
        )

        calls = []

        def fake_generate_one(item):
            calls.append(item)
            tmpl_name, seed, _strategy, _tier_config, _idx, _total = item
            return {
                "messages": [{"role": "system", "content": tmpl_name}, {"role": "assistant", "content": str(seed)}],
                "env": "MEMORYGYM",
                "score": 1.0,
            }

        monkeypatch.setattr("forge.data.memorygym_gen._generate_one", fake_generate_one)

        from forge.data.memorygym_gen import generate_dataset

        result = generate_dataset(
            output=str(tmp_path / "raw.jsonl"),
            templates=["company"],
            seeds=3,
            tier_mix=True,
            workers=1,
        )

        assert result["trajectories"] == 3
        assert len(calls) == 3


class TestLivewebTerminalToolMessage:
    def test_liveweb_allows_terminal_tool_message(self):
        entry = {
            "messages": [
                {"role": "system", "content": "web task", "tools": []},
                {"role": "user", "content": "navigate"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "1", "function": {"name": "stop", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "content": "Task completed", "tool_call_id": "1"},
            ],
            "env": "LIVEWEB",
            "score": 1.0,
        }

        assert validate_entry(entry, "LIVEWEB") == []
