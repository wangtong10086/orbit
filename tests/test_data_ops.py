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
    policy_model_status,
    resolve_policy_model_dir,
    selfplay_status,
    select_policy_model_action,
    train_selfplay_until_gate,
    train_selfplay_policy_model,
    train_policy_model,
)
from forge.data.game_teacher_repo import upload_teacher_snapshot
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

    def test_train_selfplay_policy_model_writes_status_and_best(self, monkeypatch, tmp_path):
        replay_path = tmp_path / "replay_meta" / "latest_replay.npz"
        replay_path.parent.mkdir(parents=True)
        np.savez_compressed(
            replay_path,
            features=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            legal_masks=np.asarray([[1.0, 1.0], [1.0, 1.0]], dtype=np.float32),
            policy_targets=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            value_targets=np.asarray([1.0, -1.0], dtype=np.float32),
            player_ids=np.asarray([0, 1], dtype=np.int64),
            game_steps=np.asarray([0, 1], dtype=np.int64),
            episode_ids=np.asarray([0, 0], dtype=np.int64),
        )

        from forge.data.game_policy_models.selfplay import ReplayBufferReport, ArenaEvalReport

        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.build_selfplay_replay",
            lambda **kwargs: ReplayBufferReport(
                game="leduc_poker",
                output=str(replay_path),
                episodes=8,
                rows=2,
                input_dim=2,
                action_dim=2,
                simulations=4,
                generator_family="ismcts",
            ),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.evaluate_selfplay_policy_model",
            lambda **kwargs: ArenaEvalReport(
                game=kwargs["game_name"],
                opponent=kwargs["opponent"],
                games=kwargs["games"],
                wins=120 if kwargs["opponent"] == "teacher" else 40 if kwargs["opponent"] == "teacher_cheap" else 30,
                losses=80 if kwargs["opponent"] == "teacher" else 10 if kwargs["opponent"] == "teacher_cheap" else 20,
                draws=0,
                win_rate=0.6 if kwargs["opponent"] == "teacher" else 0.8 if kwargs["opponent"] == "teacher_cheap" else 0.6,
                checkpoint_path=str(tmp_path / "latest" / "model.pt"),
                opponent_checkpoint="teacher.pkl",
            ),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.sync_selfplay_artifacts_to_hf",
            lambda **kwargs: "user/private-policy",
        )

        report = train_selfplay_policy_model(
            game_name="leduc_poker",
            output_dir=str(tmp_path / "model"),
            selfplay_episodes=8,
            simulations=4,
            epochs=1,
            batch_size=2,
            quick_gate_games=50,
            teacher_gate_games=200,
            resume=False,
            repo_id="user/private-policy",
        )

        assert report.promoted is True
        assert report.teacher_pass_streak == 1
        assert (tmp_path / "model" / "status.json").exists()
        assert (tmp_path / "model" / "best" / "model.pt").exists()
        status = json.loads((tmp_path / "model" / "status.json").read_text(encoding="utf-8"))
        assert status["replay_window_rounds"] == 24
        assert "coverage" in status

    def test_train_selfplay_policy_model_uses_perfect_info_teacher_defaults(self, monkeypatch, tmp_path):
        replay_path = tmp_path / "replay_meta" / "latest_replay.npz"
        replay_path.parent.mkdir(parents=True)
        np.savez_compressed(
            replay_path,
            features=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            legal_masks=np.asarray([[1.0, 1.0], [1.0, 1.0]], dtype=np.float32),
            policy_targets=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            value_targets=np.asarray([1.0, -1.0], dtype=np.float32),
            player_ids=np.asarray([0, 1], dtype=np.int64),
            game_steps=np.asarray([0, 1], dtype=np.int64),
            episode_ids=np.asarray([0, 0], dtype=np.int64),
        )
        from forge.data.game_policy_models.selfplay import ArenaEvalReport, ReplayBufferReport

        calls = []
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.build_selfplay_replay",
            lambda **kwargs: ReplayBufferReport(
                game="othello",
                output=str(replay_path),
                episodes=4,
                rows=2,
                input_dim=2,
                action_dim=2,
                simulations=4,
                generator_family="perfect_puct",
            ),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.evaluate_selfplay_policy_model",
            lambda **kwargs: calls.append(kwargs)
            or ArenaEvalReport(
                game=kwargs["game_name"],
                opponent=kwargs["opponent"],
                games=kwargs["games"],
                wins=190 if kwargs["opponent"] == "teacher" else 45 if kwargs["opponent"] == "teacher_cheap" else 30,
                losses=10 if kwargs["opponent"] == "teacher" else 5 if kwargs["opponent"] == "teacher_cheap" else 20,
                draws=0,
                win_rate=0.95 if kwargs["opponent"] == "teacher" else 0.90 if kwargs["opponent"] == "teacher_cheap" else 0.60,
                checkpoint_path=str(tmp_path / "latest" / "model.pt"),
                opponent_checkpoint="teacher.pkl",
            ),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.sync_selfplay_artifacts_to_hf",
            lambda **kwargs: "",
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.default_selfplay_model_config",
            lambda game_name: {"hidden_dim": 16, "residual_blocks": 0, "layer_norm": False, "architecture": "mlp"},
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.feature_spec_for_game",
            lambda game_name, params=None: type(
                "Spec",
                (),
                {"input_dim": 2, "action_dim": 2, "feature_shape": [2]},
            )(),
        )
        report = train_selfplay_policy_model(
            game_name="othello",
            output_dir=str(tmp_path / "model"),
            selfplay_episodes=4,
            simulations=4,
            epochs=1,
            batch_size=2,
            resume=False,
        )
        cheap_teacher_call = next(call for call in calls if call["opponent"] == "teacher_cheap")
        teacher_call = next(call for call in calls if call["opponent"] == "teacher")
        assert cheap_teacher_call["games"] == 50
        assert teacher_call["games"] == 200
        assert report.teacher_eval.win_rate == 0.95
        assert report.teacher_eval.passed is False

    def test_train_selfplay_policy_model_throttles_teacher_gate_and_writes_heartbeat(self, monkeypatch, tmp_path):
        replay_path = tmp_path / "replay_meta" / "latest_replay.npz"
        replay_path.parent.mkdir(parents=True)
        np.savez_compressed(
            replay_path,
            features=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            legal_masks=np.asarray([[1.0, 1.0], [1.0, 1.0]], dtype=np.float32),
            policy_targets=np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            value_targets=np.asarray([1.0, -1.0], dtype=np.float32),
            player_ids=np.asarray([0, 1], dtype=np.int64),
            game_steps=np.asarray([0, 1], dtype=np.int64),
            episode_ids=np.asarray([0, 0], dtype=np.int64),
        )
        root = tmp_path / "model"
        root.mkdir()
        (root / "status.json").write_text(
            json.dumps(
                {
                    "game": "goofspiel",
                    "output_dir": str(root),
                    "train_epochs": 1,
                    "learner_updates": 1,
                    "last_teacher_win_rate": 0.25,
                    "replay_rows": 2,
                }
            ),
            encoding="utf-8",
        )

        from forge.data.game_policy_models.selfplay import ReplayBufferReport

        eval_calls = []
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.build_selfplay_replay",
            lambda **kwargs: ReplayBufferReport(
                game="goofspiel",
                output=str(replay_path),
                episodes=8,
                rows=2,
                input_dim=2,
                action_dim=2,
                simulations=4,
                generator_family="puct",
            ),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.evaluate_selfplay_policy_model",
            lambda **kwargs: eval_calls.append(kwargs),
        )
        monkeypatch.setattr("forge.data.game_policy_models.selfplay.sync_selfplay_artifacts_to_hf", lambda **kwargs: "")
        monkeypatch.setattr("forge.data.game_policy_models.selfplay._gpu_snapshot", lambda: (61.0, 42.0))
        monkeypatch.setattr("forge.data.game_policy_models.selfplay._autotune_batch_size", lambda **kwargs: 16)

        report = train_selfplay_policy_model(
            game_name="goofspiel",
            output_dir=str(root),
            selfplay_episodes=8,
            simulations=4,
            epochs=1,
            batch_size=2,
            quick_gate_interval_updates=5,
            teacher_gate_interval_updates=5,
            sync_interval_updates=10,
            autotune_batch_size=True,
            resume=False,
        )

        assert eval_calls == []
        assert report.batch_size == 16
        heartbeat = json.loads((root / "heartbeat.json").read_text(encoding="utf-8"))
        assert heartbeat["gpu_util_avg_5m"] == 61.0
        assert heartbeat["autotuned_batch_size"] == 16

    def test_train_selfplay_until_gate_loops_until_teacher_threshold(self, monkeypatch, tmp_path):
        from forge.data.game_policy_models.selfplay import ArenaEvalReport, SelfPlayTrainReport

        calls = []

        def fake_train(**kwargs):
            calls.append(kwargs)
            round_idx = len(calls)
            win_rate = 0.70 if round_idx == 1 else 0.92
            streak = 0 if round_idx == 1 else 2
            return SelfPlayTrainReport(
                game="othello",
                output_dir=str(tmp_path / "model"),
                latest_checkpoint=str(tmp_path / "model" / "latest" / "model.pt"),
                best_checkpoint=str(tmp_path / "model" / "best" / "model.pt"),
                replay_path=str(tmp_path / "model" / "replay_meta" / "latest_replay.npz"),
                replay_rows=128,
                selfplay_episodes=32,
                train_epochs=round_idx,
                batch_size=1024,
                device="cuda",
                quick_eval=ArenaEvalReport(game="othello", opponent="best", games=50, wins=30, losses=20, win_rate=0.60),
                teacher_eval=ArenaEvalReport(game="othello", opponent="teacher", games=200, wins=int(win_rate * 200), losses=200 - int(win_rate * 200), win_rate=win_rate),
                promoted=round_idx > 1,
                teacher_pass_streak=streak,
                persisted_repo="user/repo",
            )

        monkeypatch.setattr("forge.data.game_policy_models.selfplay.train_selfplay_policy_model", fake_train)

        report = train_selfplay_until_gate(
            game_name="othello",
            output_dir=str(tmp_path / "model"),
            selfplay_episodes=32,
            simulations=64,
            epochs=1,
            batch_size=1024,
            teacher_gate_min_win_rate=0.90,
            teacher_gate_required_streak=2,
            resume=True,
            max_rounds=4,
        )

        assert report.completed is True
        assert report.rounds_completed == 2
        assert report.stop_reason == "teacher_gate_passed"
        assert calls[0]["resume"] is True
        assert calls[1]["resume"] is False

    def test_materialize_replay_model_moves_all_games_to_cuda_when_available(self, monkeypatch):
        from forge.data.game_policy_models.selfplay import _materialize_replay_model
        from forge.data.game_policy_models.models import PolicyModelArtifact

        class FakeTorch:
            class cuda:
                @staticmethod
                def is_available():
                    return True

            @staticmethod
            def set_float32_matmul_precision(value):
                return None

        class FakeModel:
            def __init__(self):
                self.calls = []

            def to(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return self

            def eval(self):
                return self

        monkeypatch.setattr("forge.data.game_policy_models.selfplay._require_torch", lambda: (FakeTorch, None, None))

        perfect_artifact = PolicyModelArtifact(
            game="othello",
            model_dir=".",
            checkpoint_path="./model.pt",
            input_dim=384,
            action_dim=65,
            architecture="resnet",
            feature_shape=[6, 8, 8],
            model_kind="policy_value",
            training_route="selfplay",
        )
        perfect_model = FakeModel()
        _materialize_replay_model("othello", perfect_artifact, perfect_model)
        assert perfect_model.calls[0][0] == ("cuda",)

        imperfect_artifact = PolicyModelArtifact(
            game="leduc_poker",
            model_dir=".",
            checkpoint_path="./model.pt",
            input_dim=30,
            action_dim=3,
            architecture="mlp",
            feature_shape=[30],
            model_kind="policy_value",
            training_route="selfplay",
        )
        imperfect_model = FakeModel()
        _materialize_replay_model("leduc_poker", imperfect_artifact, imperfect_model)
        assert imperfect_model.calls[0][0] == ("cuda",)

    def test_perfect_info_puct_search_batches_leaf_predictions(self, monkeypatch):
        from forge.data.game_policy_models.selfplay import PerfectInfoPuctSearch

        class FakeGame:
            def num_distinct_actions(self):
                return 3

            def num_players(self):
                return 2

        class FakeState:
            def __init__(self, depth=0):
                self.depth = depth
                self.game = FakeGame()

            def clone(self):
                return FakeState(self.depth)

            def get_game(self):
                return self.game

            def is_terminal(self):
                return self.depth >= 2

            def is_chance_node(self):
                return False

            def chance_outcomes(self):
                return []

            def current_player(self):
                return 0

            def apply_action(self, action):
                self.depth += 1

            def legal_actions(self, player_id=None):
                return [0, 1] if not self.is_terminal() else []

            def returns(self):
                return [1.0, -1.0]

        class FakeEvaluator:
            def __init__(self):
                self.batch_sizes = []

            def prior(self, state):
                return [(0, 0.5), (1, 0.5)]

            def evaluate(self, state):
                return [0.0, 0.0]

            def _predict_many(self, requests):
                self.batch_sizes.append(len(requests))
                return [
                    (np.asarray([0.5, 0.5, 0.0], dtype=np.float32), 0.25)
                    for _ in requests
                ]

        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay.legal_action_mask",
            lambda game, state, player_id: np.asarray([1.0, 1.0, 0.0], dtype=np.float32),
        )
        monkeypatch.setattr(
            "forge.data.game_policy_models.selfplay._apply_dirichlet_noise",
            lambda policy, legal_mask, alpha=0.3, epsilon=0.25: policy,
        )

        evaluator = FakeEvaluator()
        search = PerfectInfoPuctSearch(
            evaluator=evaluator,
            simulations=8,
            c_puct=1.5,
            root_noise_alpha=0.0,
            eval_batch_size=4,
        )
        policy = search.policy(FakeState(), root_player=0)

        assert policy.shape == (3,)
        assert any(size > 1 for size in evaluator.batch_sizes)

    def test_build_selfplay_replay_uses_spawn_context_for_perfect_info_workers_without_cuda(self, monkeypatch, tmp_path):
        from forge.data.game_policy_models import selfplay

        captured: dict[str, object] = {}

        class FakeFuture:
            def __init__(self, payload):
                self._payload = payload

            def result(self):
                return self._payload

        class FakeExecutor:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                self.submitted = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, **kwargs):
                future = FakeFuture(
                    {
                        "features": np.ones((2, 384), dtype=np.float32),
                        "legal_masks": np.ones((2, 65), dtype=np.float32),
                        "policy_targets": np.ones((2, 65), dtype=np.float32) / 65.0,
                        "value_targets": np.ones(2, dtype=np.float32),
                        "player_ids": np.zeros(2, dtype=np.int64),
                        "game_steps": np.zeros(2, dtype=np.int64),
                        "episode_ids": np.arange(2, dtype=np.int64),
                        "state_keys": np.asarray(["a", "b"]),
                    }
                )
                self.submitted.append(future)
                return future

        class FakeContext:
            def __init__(self, name):
                self.name = name

        class FakeCuda:
            @staticmethod
            def is_available():
                return False

        class FakeTorch:
            cuda = FakeCuda

        monkeypatch.setattr(selfplay, "_require_torch", lambda: (FakeTorch, None, None))
        monkeypatch.setattr(selfplay, "_compatible_checkpoint_pool", lambda **kwargs: [tmp_path / "best"])
        monkeypatch.setattr(selfplay, "_build_empty_policy_artifact", lambda *args, **kwargs: None)
        monkeypatch.setattr(selfplay, "_expected_feature_shape", lambda game_name: (384, 65))
        monkeypatch.setattr(selfplay, "_selfplay_feature_shape", lambda game_name: [6, 8, 8])
        monkeypatch.setattr(selfplay, "_concat_replays", lambda chunks: chunks[0])
        monkeypatch.setattr(
            selfplay,
            "_payload_coverage",
            lambda payload: {
                "unique_state_keys": 2,
                "unique_action_support": 65,
                "duplicate_ratio": 0.0,
                "mean_policy_entropy": 0.0,
                "step_depth_histogram": {},
            },
        )
        monkeypatch.setattr(selfplay, "_persist_round_replay", lambda **kwargs: tmp_path / "round-1.npz")
        monkeypatch.setattr(selfplay, "_merge_recent_replay_window", lambda **kwargs: kwargs["payload"] if "payload" in kwargs else {
            "features": np.ones((2, 384), dtype=np.float32),
            "legal_masks": np.ones((2, 65), dtype=np.float32),
            "policy_targets": np.ones((2, 65), dtype=np.float32) / 65.0,
            "value_targets": np.ones(2, dtype=np.float32),
            "player_ids": np.zeros(2, dtype=np.int64),
            "game_steps": np.zeros(2, dtype=np.int64),
            "episode_ids": np.arange(2, dtype=np.int64),
            "state_keys": np.asarray(["a", "b"]),
        })
        monkeypatch.setattr(selfplay, "ProcessPoolExecutor", FakeExecutor)
        monkeypatch.setattr(selfplay, "as_completed", lambda futures: list(futures))
        monkeypatch.setattr(selfplay.mp, "get_context", lambda name: FakeContext(name))

        report = selfplay.build_selfplay_replay(
            game_name="othello",
            output_dir=str(tmp_path / "model"),
            episodes=4,
            start_seed=1,
            simulations=8,
        )

        assert isinstance(captured["mp_context"], FakeContext)
        assert captured["mp_context"].name == "spawn"
        assert captured["max_workers"] == 4
        assert report.rows == 2

    def test_evaluate_selfplay_policy_model_stops_early_when_threshold_is_unreachable(self, monkeypatch, tmp_path):
        from forge.data.game_policy_models import selfplay
        from forge.data.game_policy_models.models import PolicyModelArtifact

        class FakeTensor:
            def __init__(self, value=0):
                self.value = value

            def float(self):
                return self

            def to(self, device):
                return self

            def unsqueeze(self, dim):
                return self

        class FakeTorch:
            class cuda:
                @staticmethod
                def is_available():
                    return False

            @staticmethod
            def from_numpy(arr):
                return FakeTensor()

            class no_grad:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

        class FakeModel:
            def parameters(self):
                class P:
                    device = "cpu"
                yield P()

            def to(self, device):
                return self

            def eval(self):
                return self

            def __call__(self, features):
                return FakeTensor()

        class FakeGame:
            def num_players(self):
                return 2

        class FakeState:
            def __init__(self):
                self.turn = 0

            def is_terminal(self):
                return self.turn >= 1

            def is_chance_node(self):
                return False

            def chance_outcomes(self):
                return []

            def current_player(self):
                return 0

            def apply_action(self, action):
                self.turn += 1

            def returns(self):
                return [-1.0, 1.0]

            def legal_actions(self, player_id=None):
                return [0]

            def get_game(self):
                return FakeGame()

        class FakeBaseGame:
            def new_initial_state(self):
                return FakeState()

            def num_players(self):
                return 2

        monkeypatch.setattr(selfplay, "_require_torch", lambda: (FakeTorch, None, None))
        monkeypatch.setattr(
            selfplay,
            "load_policy_model",
            lambda path: (
                PolicyModelArtifact(
                    game="goofspiel",
                    model_dir=str(tmp_path / "latest"),
                    checkpoint_path=str(tmp_path / "latest" / "model.pt"),
                    input_dim=1,
                    action_dim=1,
                    model_kind="policy_value",
                    training_route="selfplay",
                ),
                FakeModel(),
            ),
        )
        monkeypatch.setattr(selfplay, "_base_selfplay_game", lambda game_name: FakeBaseGame())
        monkeypatch.setattr(selfplay, "_model_action", lambda **kwargs: 0)
        monkeypatch.setattr(selfplay, "_best_dir", lambda output_dir: tmp_path / "best")

        report = selfplay.evaluate_selfplay_policy_model(
            game_name="goofspiel",
            output_dir=str(tmp_path / "model"),
            opponent="checkpoint",
            games=10,
            checkpoint=str(tmp_path / "latest"),
            early_stop_min_win_rate=0.9,
        )

        assert report.games < 10
        assert report.wins + (10 - report.games) < 9

    def test_evaluate_selfplay_policy_model_isolates_snapshot_teacher_eval_in_subprocess(self, monkeypatch, tmp_path):
        from forge.data.game_policy_models import selfplay
        from forge.data.game_policy_models.contracts import ArenaEvalReport

        captured: dict[str, object] = {}

        class FakeRecvConn:
            def poll(self):
                return True

            def recv(self):
                return {
                    "ok": True,
                    "report": ArenaEvalReport(
                        game="liars_dice",
                        opponent="teacher",
                        output=str(tmp_path / "arena" / "teacher_eval.json"),
                        games=50,
                        wins=21,
                        losses=29,
                        draws=0,
                        win_rate=0.42,
                        passed=False,
                        checkpoint_path=str(tmp_path / "latest" / "model.pt"),
                        opponent_checkpoint="teacher.pkl",
                    ).model_dump(mode="json"),
                }

            def close(self):
                return None

        class FakeSendConn:
            def close(self):
                return None

        class FakeProcess:
            exitcode = 0

            def __init__(self, *, target, args, daemon):
                captured["target"] = target
                captured["payload"] = args[0]
                captured["daemon"] = daemon

            def start(self):
                captured["started"] = True

            def join(self):
                captured["joined"] = True

        class FakeContext:
            def Pipe(self, duplex=False):
                captured["duplex"] = duplex
                return FakeRecvConn(), FakeSendConn()

            def Process(self, *, target, args, daemon):
                return FakeProcess(target=target, args=args, daemon=daemon)

        monkeypatch.setattr(selfplay.mp, "get_context", lambda name: FakeContext())
        monkeypatch.setattr(
            selfplay,
            "_evaluate_selfplay_policy_model_inline",
            lambda **kwargs: pytest.fail("teacher snapshot eval should run in a subprocess"),
        )

        report = selfplay.evaluate_selfplay_policy_model(
            game_name="liars_dice",
            output_dir=str(tmp_path / "model"),
            opponent="teacher",
            games=50,
            checkpoint=str(tmp_path / "latest"),
        )

        assert captured["started"] is True
        assert captured["joined"] is True
        assert captured["duplex"] is False
        assert captured["payload"]["game_name"] == "liars_dice"
        assert captured["payload"]["opponent"] == "teacher"
        assert report.win_rate == 0.42
        assert report.games == 50

    def test_build_selfplay_replay_uses_process_pool_with_shared_gpu_predictor(self, monkeypatch, tmp_path):
        from forge.data.game_policy_models import selfplay

        captured: dict[str, object] = {}

        class FakeFuture:
            def __init__(self, payload):
                self._payload = payload

            def result(self):
                return self._payload

        class FakeExecutor:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, **kwargs):
                captured["use_process_predictors"] = kwargs.get("use_process_predictors")
                return FakeFuture(
                    {
                        "features": np.ones((2, 30), dtype=np.float32),
                        "legal_masks": np.ones((2, 3), dtype=np.float32),
                        "policy_targets": np.ones((2, 3), dtype=np.float32) / 3.0,
                        "value_targets": np.ones(2, dtype=np.float32),
                        "player_ids": np.zeros(2, dtype=np.int64),
                        "game_steps": np.zeros(2, dtype=np.int64),
                        "episode_ids": np.arange(2, dtype=np.int64),
                        "state_keys": np.asarray(["a", "b"]),
                    }
                )

        class FakeCuda:
            @staticmethod
            def is_available():
                return True

        class FakeTorch:
            cuda = FakeCuda

        class FakeServer:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        fake_server = FakeServer()

        monkeypatch.setattr(selfplay, "_require_torch", lambda: (FakeTorch, None, None))
        monkeypatch.setattr(selfplay, "_compatible_checkpoint_pool", lambda **kwargs: [tmp_path / "best"])
        monkeypatch.setattr(selfplay, "_build_empty_policy_artifact", lambda *args, **kwargs: None)
        monkeypatch.setattr(selfplay, "_expected_feature_shape", lambda game_name: (30, 3))
        monkeypatch.setattr(selfplay, "_selfplay_feature_shape", lambda game_name: [30])
        monkeypatch.setattr(selfplay, "_concat_replays", lambda chunks: chunks[0])
        monkeypatch.setattr(
            selfplay,
            "_payload_coverage",
            lambda payload: {
                "unique_state_keys": 2,
                "unique_action_support": 3,
                "duplicate_ratio": 0.0,
                "mean_policy_entropy": 0.0,
                "step_depth_histogram": {},
            },
        )
        monkeypatch.setattr(selfplay, "_persist_round_replay", lambda **kwargs: tmp_path / "round-1.npz")
        monkeypatch.setattr(
            selfplay,
            "_merge_recent_replay_window",
            lambda **kwargs: {
                "features": np.ones((2, 30), dtype=np.float32),
                "legal_masks": np.ones((2, 3), dtype=np.float32),
                "policy_targets": np.ones((2, 3), dtype=np.float32) / 3.0,
                "value_targets": np.ones(2, dtype=np.float32),
                "player_ids": np.zeros(2, dtype=np.int64),
                "game_steps": np.zeros(2, dtype=np.int64),
                "episode_ids": np.arange(2, dtype=np.int64),
                "state_keys": np.asarray(["a", "b"]),
            },
        )
        monkeypatch.setattr(
            selfplay,
            "_build_process_predictor_pool",
            lambda **kwargs: ({str(tmp_path / "best"): "queue"}, {str(tmp_path / "best"): fake_server}),
        )
        monkeypatch.setattr(selfplay, "ProcessPoolExecutor", FakeExecutor)
        monkeypatch.setattr(selfplay, "as_completed", lambda futures: list(futures))
        monkeypatch.setattr(selfplay.mp, "get_context", lambda name: f"context:{name}")

        report = selfplay.build_selfplay_replay(
            game_name="goofspiel",
            output_dir=str(tmp_path / "model"),
            episodes=4,
            start_seed=1,
            simulations=8,
        )

        assert captured["max_workers"] == 4
        assert captured["mp_context"] == "context:spawn"
        assert captured["initializer"] is selfplay._init_process_predictor_clients
        assert captured["initargs"] == ({str(tmp_path / "best"): "queue"},)
        assert captured["use_process_predictors"] is True
        assert fake_server.closed is True
        assert report.rows == 2

    def test_selfplay_status_reports_best_and_latest(self, tmp_path):
        root = tmp_path / "artifacts" / "game_policy_models" / "goofspiel" / "default"
        latest = root / "latest"
        best = root / "best"
        latest.mkdir(parents=True)
        best.mkdir(parents=True)
        metadata = {
            "game": "goofspiel",
            "model_dir": str(best),
            "checkpoint_path": str(best / "model.pt"),
            "input_dim": 4,
            "action_dim": 3,
            "hidden_dim": 16,
            "residual_blocks": 4,
            "batch_size": 2,
            "epochs": 1,
            "learning_rate": 0.001,
            "weight_decay": 0.0001,
            "train_rows": 10,
            "device": "cpu",
            "model_kind": "policy_value",
            "training_route": "selfplay",
            "layer_norm": False,
            "metrics": {"policy_loss": 0.1},
        }
        for target in (latest, best):
            (target / "model.pt").write_bytes(b"x")
            (target / "metadata.json").write_text(json.dumps({**metadata, "model_dir": str(target), "checkpoint_path": str(target / "model.pt")}), encoding="utf-8")
        (root / "status.json").write_text(
            json.dumps({"game": "goofspiel", "teacher_pass_streak": 2, "persisted_repo": "user/private-policy"}),
            encoding="utf-8",
        )

        status = selfplay_status(game_name="goofspiel", output_dir=str(root))

        assert status.exists is True
        assert status.best_exists is True
        assert status.latest_exists is True
        assert status.persisted_repo == "user/private-policy"

    def test_merge_recent_replay_window_prefers_recent_rows(self, tmp_path):
        from forge.data.game_policy_models import selfplay

        rounds = tmp_path / "model" / "replay_meta" / "rounds"
        rounds.mkdir(parents=True)

        def write_round(path: Path, start: int, count: int):
            np.savez_compressed(
                path,
                features=np.arange(start, start + count, dtype=np.float32).reshape(count, 1),
                legal_masks=np.ones((count, 2), dtype=np.float32),
                policy_targets=np.tile(np.asarray([[1.0, 0.0]], dtype=np.float32), (count, 1)),
                value_targets=np.ones(count, dtype=np.float32),
                player_ids=np.zeros(count, dtype=np.int64),
                game_steps=np.zeros(count, dtype=np.int64),
                episode_ids=np.arange(start, start + count, dtype=np.int64),
                state_keys=np.asarray([f"s{i}" for i in range(start, start + count)]),
            )

        write_round(rounds / "round-1.npz", 0, 10)
        write_round(rounds / "round-2.npz", 100, 10)

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(selfplay, "_expected_feature_shape", lambda _: (1, 2))
            merged = selfplay._merge_recent_replay_window(
                game_name="gin_rummy",
                output_dir=str(tmp_path / "model"),
                rng_seed=7,
                max_rounds=2,
                max_rows=10,
                recent_fraction=0.7,
            )

        episode_ids = set(merged["episode_ids"].tolist())
        recent_hits = sum(1 for value in episode_ids if value >= 100)
        history_hits = sum(1 for value in episode_ids if value < 100)
        assert len(merged["features"]) == 10
        assert recent_hits >= history_hits

    def test_merge_recent_replay_window_skips_stale_incompatible_rounds(self, tmp_path):
        from forge.data.game_policy_models import selfplay

        rounds = tmp_path / "model" / "replay_meta" / "rounds"
        rounds.mkdir(parents=True)

        np.savez_compressed(
            rounds / "round-stale.npz",
            features=np.ones((4, 644), dtype=np.float32),
            legal_masks=np.ones((4, 241), dtype=np.float32),
            policy_targets=np.ones((4, 241), dtype=np.float32) / 241.0,
            value_targets=np.ones(4, dtype=np.float32),
            player_ids=np.zeros(4, dtype=np.int64),
            game_steps=np.zeros(4, dtype=np.int64),
            episode_ids=np.arange(4, dtype=np.int64),
            state_keys=np.asarray([f"stale-{idx}" for idx in range(4)]),
        )
        np.savez_compressed(
            rounds / "round-good.npz",
            features=np.ones((6, 256), dtype=np.float32),
            legal_masks=np.ones((6, 241), dtype=np.float32),
            policy_targets=np.ones((6, 241), dtype=np.float32) / 241.0,
            value_targets=np.ones(6, dtype=np.float32),
            player_ids=np.zeros(6, dtype=np.int64),
            game_steps=np.zeros(6, dtype=np.int64),
            episode_ids=np.arange(100, 106, dtype=np.int64),
            state_keys=np.asarray([f"good-{idx}" for idx in range(6)]),
        )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(selfplay, "_expected_feature_shape", lambda _: (256, 241))
            merged = selfplay._merge_recent_replay_window(
                game_name="gin_rummy",
                output_dir=str(tmp_path / "model"),
                rng_seed=11,
                max_rounds=2,
                max_rows=6,
                recent_fraction=0.7,
            )

        assert merged["features"].shape[1] == 256
        assert len(merged["features"]) == 4
        assert all(value >= 100 for value in merged["episode_ids"].tolist())

    def test_prune_incompatible_replay_state_rewrites_latest_meta(self, tmp_path):
        from forge.data.game_policy_models import selfplay

        root = tmp_path / "model"
        rounds = root / "replay_meta" / "rounds"
        rounds.mkdir(parents=True)
        np.savez_compressed(
            rounds / "round-stale.npz",
            features=np.ones((3, 644), dtype=np.float32),
            legal_masks=np.ones((3, 241), dtype=np.float32),
            policy_targets=np.ones((3, 241), dtype=np.float32) / 241.0,
            value_targets=np.ones(3, dtype=np.float32),
            player_ids=np.zeros(3, dtype=np.int64),
            game_steps=np.zeros(3, dtype=np.int64),
            episode_ids=np.arange(3, dtype=np.int64),
            state_keys=np.asarray([f"stale-{idx}" for idx in range(3)]),
        )
        np.savez_compressed(
            rounds / "round-good.npz",
            features=np.ones((5, 256), dtype=np.float32),
            legal_masks=np.ones((5, 241), dtype=np.float32),
            policy_targets=np.ones((5, 241), dtype=np.float32) / 241.0,
            value_targets=np.ones(5, dtype=np.float32),
            player_ids=np.zeros(5, dtype=np.int64),
            game_steps=np.zeros(5, dtype=np.int64),
            episode_ids=np.arange(100, 105, dtype=np.int64),
            state_keys=np.asarray([f"good-{idx}" for idx in range(5)]),
        )
        np.savez_compressed(
            root / "replay_meta" / "latest_replay.npz",
            features=np.ones((3, 644), dtype=np.float32),
            legal_masks=np.ones((3, 241), dtype=np.float32),
            policy_targets=np.ones((3, 241), dtype=np.float32) / 241.0,
            value_targets=np.ones(3, dtype=np.float32),
            player_ids=np.zeros(3, dtype=np.int64),
            game_steps=np.zeros(3, dtype=np.int64),
            episode_ids=np.arange(3, dtype=np.int64),
            state_keys=np.asarray([f"stale-{idx}" for idx in range(3)]),
        )
        (root / "replay_meta" / "latest.json").write_text(
            json.dumps({"game": "gin_rummy", "input_dim": 644, "action_dim": 241}),
            encoding="utf-8",
        )

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(selfplay, "_expected_feature_shape", lambda _: (256, 241))
            selfplay._prune_incompatible_replay_state(game_name="gin_rummy", output_dir=str(root))

        meta = json.loads((root / "replay_meta" / "latest.json").read_text(encoding="utf-8"))
        payload = np.load(root / "replay_meta" / "latest_replay.npz")
        assert meta["input_dim"] == 256
        assert payload["features"].shape == (5, 256)


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
