"""Tests for runtime-facing data operations and remediation fixes."""

import os
import sys
from pathlib import Path
import json
import asyncio

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.data.aggregate import build_mixed_records, publish_mixed_dataset
from forge.data.collect_adapters import collect_navworld
from forge.data.collect_publish import _as_collect_sync_result
from forge.data.collect_service import swe_sync_pipeline
from forge.data.canonical_ops import download_from_hf, hf_sync_repo, upload_dataset_card, validate_entry
from forge.data.game_gen import generate_game_data
from forge.data.game_policy_models import (
    default_policy_model_dir,
    play_record,
    policy_model_status,
    resolve_policy_model_dir,
    select_policy_model_action,
    train_policy_model,
)
from forge.data.game_teacher_repo import upload_teacher_snapshot
from forge.data.memorygym_split import split_trajectory
from forge.data.swe_ops import distill_status, sync_new_trajectories
from forge.tasks.collection.specs import NavworldCollectConfig
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

    def test_upload_teacher_snapshot_creates_private_model_repo_and_uploads_artifacts(self, monkeypatch, tmp_path):
        uploads = []
        created = {}
        snapshot_path = tmp_path / "policy.pkl"
        snapshot_path.write_bytes(b"teacher")

        class FakeApi:
            def __init__(self, token=None):
                self.token = token

            def create_repo(self, repo_id, repo_type="model", private=True, exist_ok=True):
                created["repo_id"] = repo_id
                created["repo_type"] = repo_type
                created["private"] = private
                created["exist_ok"] = exist_ok

            def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type="model", commit_message=""):
                uploads.append(
                    {
                        "path_in_repo": path_in_repo,
                        "repo_id": repo_id,
                        "repo_type": repo_type,
                        "commit_message": commit_message,
                        "content": Path(path_or_fileobj).read_bytes(),
                    }
                )

        class FakeLoaded:
            def __init__(self):
                self.metadata = type(
                    "Meta",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "game": "leduc_poker",
                            "family": "cfr",
                            "iterations": 200,
                        }
                    },
                )()

        monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)
        monkeypatch.setattr("forge.data.game_teacher_repo._resolve_token", lambda token="": "hf-test")
        monkeypatch.setattr("forge.data.game_teacher_repo.load_policy_snapshot", lambda path: (FakeLoaded(), object()))

        report = upload_teacher_snapshot(
            game_name="leduc_poker",
            family="cfr",
            policy_path=str(snapshot_path),
            repo_id="user/private-teachers",
            private=True,
            update_readme=True,
        )

        assert report.status == "success"
        assert created["repo_id"] == "user/private-teachers"
        assert created["repo_type"] == "model"
        assert created["private"] is True
        assert [item["path_in_repo"] for item in uploads] == [
            "teachers/leduc_poker/cfr/policy.pkl",
            "teachers/leduc_poker/cfr/metadata.json",
            "README.md",
        ]
        assert report.readme_updated is True


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
    def test_game_generation_uses_registry_generator(self, monkeypatch, tmp_path):
        calls = []

        monkeypatch.setattr("forge.data.game_gen.require_game_deps", lambda: None)
        monkeypatch.setattr(
            "forge.data.game_gen.resolve_game_trajectory_generator",
            lambda game: __import__(
                "forge.data.game_trajectory_generators",
                fromlist=["GameTrajectoryGeneratorSpec"],
            ).GameTrajectoryGeneratorSpec(
                name="liars_dice_mccfr",
                family="mccfr",
                policy_path=str(tmp_path / "policy.pkl"),
            ),
        )

        class FakeGenerator:
            def generate_batch(self, **kwargs):
                calls.append(kwargs)
                output_path = Path(kwargs["output_path"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(
                    '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}],"env":"GAME","score":1.0,"game":"liars_dice"}\n',
                    encoding="utf-8",
                )
                from forge.data.game_generators.base import GameTrajectoryGeneratorReport

                return GameTrajectoryGeneratorReport(
                    game="liars_dice",
                    generator_name="liars_dice_mccfr",
                    generator_family="mccfr",
                    output=str(output_path),
                    records=1,
                    wins=1,
                    attempts=1,
                )

        monkeypatch.setattr(
            "forge.data.game_gen.build_game_trajectory_generator",
            lambda game, generator_source="default": FakeGenerator(),
        )

        result = generate_game_data(
            output_path=str(tmp_path / "game.jsonl"),
            game_name="liars_dice",
            sample_count=1,
            start_seed=123,
            attempt_multiplier=1,
        )

        assert result["records"] == 1
        assert len(calls) == 1
        assert calls[0]["start_seed"] == 123
        assert result["generators"]["liars_dice"] == "mccfr:liars_dice_mccfr"

    def test_game_generation_can_select_policy_model_source(self, monkeypatch, tmp_path):
        calls = []

        monkeypatch.setattr("forge.data.game_gen.require_game_deps", lambda: None)
        monkeypatch.setattr(
            "forge.data.game_gen.resolve_game_trajectory_generator",
            lambda game: __import__(
                "forge.data.game_trajectory_generators",
                fromlist=["GameTrajectoryGeneratorSpec"],
            ).GameTrajectoryGeneratorSpec(
                name="leduc_poker_cfr",
                family="cfr",
                policy_path=str(tmp_path / "policy.pkl"),
                policy_model_dir=str(tmp_path / "model"),
            ),
        )

        class FakeGenerator:
            def generate_batch(self, **kwargs):
                calls.append(kwargs)
                output_path = Path(kwargs["output_path"])
                output_path.write_text(
                    '{"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"1"}],"env":"GAME","score":1.0,"game":"leduc_poker"}\n',
                    encoding="utf-8",
                )
                from forge.data.game_generators.base import GameTrajectoryGeneratorReport

                return GameTrajectoryGeneratorReport(
                    game="leduc_poker",
                    generator_name="leduc_poker_policy_model",
                    generator_family="policy_model",
                    output=str(output_path),
                    records=1,
                    wins=1,
                    attempts=1,
                )

        monkeypatch.setattr(
            "forge.data.game_gen.build_game_trajectory_generator",
            lambda game, generator_source="default": calls.append({"source": generator_source}) or FakeGenerator(),
        )

        result = generate_game_data(
            output_path=str(tmp_path / "game.jsonl"),
            game_name="leduc_poker",
            sample_count=1,
            start_seed=123,
            attempt_multiplier=1,
            generator_source="policy_model",
        )

        assert result["generator_source"] == "policy_model"
        assert result["generators"]["leduc_poker"] == "policy_model:leduc_poker_policy_model"
        assert calls[0]["source"] == "policy_model"

    def test_registry_exposes_explicit_nonrandom_families(self):
        from forge.data.game_trajectory_generators import resolve_game_trajectory_generator

        assert resolve_game_trajectory_generator("othello").family == "mcts"
        assert resolve_game_trajectory_generator("hex").family == "mcts"
        assert resolve_game_trajectory_generator("clobber").family == "mcts"
        assert resolve_game_trajectory_generator("leduc_poker").family == "cfr"
        assert resolve_game_trajectory_generator("goofspiel").family == "cfr"
        assert resolve_game_trajectory_generator("liars_dice").family == "mccfr"
        assert resolve_game_trajectory_generator("gin_rummy").family == "mccfr"

    def test_registry_allows_env_param_overrides_for_game_smoke(self, monkeypatch):
        from forge.data.game_trajectory_generators import resolve_game_trajectory_generator

        monkeypatch.setenv("AFFINE_GAME_PARAM_LIARS_DICE_NUMDICE", "1")
        monkeypatch.setenv("AFFINE_GAME_PARAM_GOOFSPIEL_IMP_INFO", "false")

        liars = resolve_game_trajectory_generator("liars_dice")
        goofspiel = resolve_game_trajectory_generator("goofspiel")

        assert liars.game_params["numdice"] == 1
        assert goofspiel.game_params["imp_info"] is False


class TestGamePolicyModels:
    def test_extract_state_features_falls_back_to_hashed_strings(self):
        from forge.data.game_policy_models.featurizers import extract_state_features

        class FakeState:
            def information_state_tensor(self, player_id):
                raise RuntimeError("unimplemented")

            def observation_tensor(self, player_id):
                raise RuntimeError("unimplemented")

            def information_state_string(self, player_id):
                return "hand=A score=3 discard=K"

        features = extract_state_features(FakeState(), 0)

        assert features.ndim == 1
        assert float(features.sum()) > 0.0

    def test_perfect_info_feature_specs_use_board_planes(self):
        import pyspiel
        from forge.data.game_policy_models.featurizers import feature_spec_for_state

        cases = [
            ("othello", {}, [6, 8, 8], 65),
            ("hex", {"board_size": 7}, [7, 11, 11], 49),
            ("clobber", {"rows": 5, "columns": 5}, [7, 7, 7], 100),
        ]
        for game_name, params, feature_shape, action_dim in cases:
            game = pyspiel.load_game(game_name, params)
            state = game.new_initial_state()
            spec = feature_spec_for_state(game_name, state, 0)
            assert spec.source == "board_planes"
            assert spec.feature_shape == feature_shape
            assert spec.input_dim == int(np.prod(feature_shape))
            assert spec.action_dim == action_dim

    def test_build_policy_model_module_supports_spatial_resnet(self):
        import torch
        from forge.data.game_policy_models.models import build_policy_model_module

        model = build_policy_model_module(
            input_dim=6 * 8 * 8,
            hidden_dim=128,
            action_dim=65,
            model_kind="policy_value",
            residual_blocks=2,
            architecture="resnet",
            feature_shape=[6, 8, 8],
        )
        logits, value = model(torch.zeros(3, 6 * 8 * 8))
        assert logits.shape == (3, 65)
        assert value.shape == (3,)

    def test_train_policy_model_writes_torch_artifact(self, tmp_path):
        dataset = tmp_path / "expert_dataset.npz"
        np.savez_compressed(
            dataset,
            features=np.asarray([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float32),
            legal_masks=np.asarray([[1.0, 1.0], [1.0, 1.0], [1.0, 1.0]], dtype=np.float32),
            actions=np.asarray([0, 1, 1], dtype=np.int64),
            seeds=np.asarray([1, 2, 3], dtype=np.int64),
            trajectory_ids=np.asarray([0, 1, 2], dtype=np.int64),
        )

        report = train_policy_model(
            game_name="leduc_poker",
            dataset_path=str(dataset),
            output_dir=str(tmp_path / "model"),
            hidden_dim=16,
            batch_size=2,
            epochs=2,
        )

        assert report.train_rows == 3
        assert report.checkpoint_path.endswith("model.pt")
        assert (tmp_path / "model" / "model.pt").exists()
        assert (tmp_path / "model" / "metadata.json").exists()

    def test_policy_model_status_reports_saved_artifact(self, tmp_path):
        model_dir = tmp_path / "artifacts" / "game_policy_models" / "leduc_poker" / "default"
        model_dir.mkdir(parents=True)
        (model_dir / "model.pt").write_bytes(b"placeholder")
        (model_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "game": "leduc_poker",
                    "model_dir": str(model_dir),
                    "checkpoint_path": str(model_dir / "model.pt"),
                    "dataset_path": "",
                    "input_dim": 4,
                    "action_dim": 3,
                    "hidden_dim": 16,
                    "batch_size": 2,
                    "epochs": 1,
                    "learning_rate": 0.001,
                    "weight_decay": 0.0001,
                    "train_rows": 10,
                    "device": "cpu",
                    "metrics": {"accuracy": 1.0},
                }
            ),
            encoding="utf-8",
        )

        from forge.data.game_policy_models.inference import PolicyModelStatusEntry

        status = policy_model_status(game_name="leduc_poker", model_dir=str(model_dir))

        assert isinstance(status, PolicyModelStatusEntry)
        assert status.exists is True
        assert status.metadata["game"] == "leduc_poker"

    def test_resolve_policy_model_dir_prefers_best_checkpoint(self, tmp_path):
        model_dir = tmp_path / "artifacts" / "game_policy_models" / "leduc_poker" / "default"
        best_dir = model_dir / "best"
        best_dir.mkdir(parents=True)
        (best_dir / "model.pt").write_bytes(b"x")
        (best_dir / "metadata.json").write_text("{}", encoding="utf-8")

        resolved = resolve_policy_model_dir(str(model_dir))

        assert resolved.endswith("/best")

    def test_select_policy_model_action_masks_illegal_actions(self):
        import torch
        from forge.data.game_policy_models.models import PolicyModelArtifact

        class FakeState:
            def legal_actions(self, player_id):
                return [1]

            def information_state_tensor(self, player_id):
                return [1.0, 0.0]

        class FakeGame:
            def num_distinct_actions(self):
                return 3

        class FixedModel(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.register_parameter("dummy", torch.nn.Parameter(torch.zeros(1)))

            def forward(self, x):
                return torch.tensor([[10.0, 2.0, 9.0]], device=x.device)

        artifact = PolicyModelArtifact(
            game="leduc_poker",
            model_dir=".",
            checkpoint_path="./model.pt",
            input_dim=2,
            action_dim=3,
        )
        action = select_policy_model_action(
            artifact=artifact,
            model=FixedModel(),
            game=FakeGame(),
            state=FakeState(),
            player_id=0,
        )

        assert action == 1




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
