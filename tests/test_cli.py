"""CLI tests for command-family boundaries and active command paths."""

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from click.testing import CliRunner

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from forge.cli import cli
from forge.compute.base import GpuInstance
from forge.config import ForgeConfig
from forge.execution.contracts import RunHandle


def _config_for(tmp_path):
    return ForgeConfig(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        machines_file=tmp_path / "machines.json",
    )


class TestRootCliFamilies:
    def test_pyproject_exposes_forge_console_script(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())
        assert data["project"]["scripts"]["forge"] == "forge.cli:main"

    def test_root_help_lists_family_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for command in ["data", "control", "worker", "remote", "monitor"]:
            assert command in result.output

    def test_remote_help_lists_sidecar_subgroups(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "--help"])
        assert result.exit_code == 0
        for command in ["machine", "compute", "deploy"]:
            assert command in result.output

    def test_monitor_help_lists_leaderboard_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["monitor", "--help"])
        assert result.exit_code == 0
        for command in ["leaderboard", "weaknesses"]:
            assert command in result.output

    def test_control_list_respects_experiments_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["control", "--dir", str(tmp_path), "list"])
        assert result.exit_code == 0

    def test_control_create_and_show(self, tmp_path):
        runner = CliRunner()
        create = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )
        assert create.exit_code == 0
        show = runner.invoke(cli, ["control", "--dir", str(tmp_path), "show", "v-test", "--json"])
        assert show.exit_code == 0
        payload = json.loads(show.output)
        assert payload["id"] == "v-test"
        assert payload["variable"] == "improve_navworld"

    def test_control_render_train_records_bundle(self, tmp_path):
        runner = CliRunner()
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )
        bundle_dir = tmp_path / "bundle"
        result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "render-train",
                "v-test",
                str(dataset),
                "--bundle-dir",
                str(bundle_dir),
            ],
        )
        assert result.exit_code == 0
        assert bundle_dir.exists()

    def test_control_submit_train_uses_runtime_backend(self, monkeypatch, tmp_path):
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )

        class FakeRuntime:
            async def run(self, request):
                from forge.execution.bundle import JobBundle
                bundle = JobBundle(request.bundle_path)
                return RunHandle(
                    runtime_kind="fake",
                    run_id="run-123",
                    target_id="fake-target",
                    bundle_path=str(bundle.path),
                )

        monkeypatch.setattr("forge.cli_control._runtime_for", lambda config, runtime_name: FakeRuntime())
        result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "submit-train",
                "v-test",
                str(dataset),
                "--runtime",
                "docker",
                "--bundle-dir",
                str(tmp_path / "bundle"),
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["run_id"] == "run-123"

    def test_control_render_eval_and_collect(self, tmp_path):
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )
        eval_bundle = tmp_path / "bundle-eval"
        collect_bundle = tmp_path / "bundle-collect"
        eval_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "render-eval",
                "v-test",
                "--model",
                "Qwen/Qwen2.5-0.5B-Instruct",
                "--envs",
                "GAME",
                "--bundle-dir",
                str(eval_bundle),
            ],
        )
        collect_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "render-collect-navworld",
                "v-test",
                "-n",
                "1",
                "--bundle-dir",
                str(collect_bundle),
            ],
        )
        assert eval_result.exit_code == 0
        assert collect_result.exit_code == 0
        assert eval_bundle.exists()
        assert collect_bundle.exists()

    def test_control_submit_eval_and_collect_and_status_task_switch(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )

        class FakeRuntime:
            async def run(self, request):
                from forge.execution.bundle import JobBundle
                bundle = JobBundle(request.bundle_path)
                return RunHandle(
                    runtime_kind="fake",
                    run_id="run-123",
                    target_id="fake-target",
                    bundle_path=str(bundle.path),
                )

            async def status(self, request):
                handle = request.handle
                from forge.execution.contracts import RunState, RunStatus

                return RunStatus(runtime_kind="fake", run_id=handle.run_id, state=RunState.RUNNING, detail="alive")

            async def logs(self, request):
                return "fake-log\n"

            async def collect(self, request):
                from forge.execution.contracts import ArtifactManifest

                return ArtifactManifest(logs={"eval.log": "artifacts/eval.log"}, artifacts={"eval_summary.json": "artifacts/eval/eval_summary.json"})

            async def terminate(self, request):
                return None

        monkeypatch.setattr("forge.cli_control._runtime_for", lambda config, runtime_name: FakeRuntime())
        eval_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "submit-eval",
                "v-test",
                "--model",
                "Qwen/Qwen2.5-0.5B-Instruct",
                "--envs",
                "GAME",
                "--runtime",
                "docker",
                "--bundle-dir",
                str(tmp_path / "bundle-eval"),
            ],
        )
        collect_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "submit-collect-navworld",
                "v-test",
                "--runtime",
                "docker",
                "-n",
                "1",
                "--bundle-dir",
                str(tmp_path / "bundle-collect"),
            ],
        )
        status_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "run-status",
                "v-test",
                "--task",
                "eval",
            ],
        )
        collect_run_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "collect-run",
                "v-test",
                "--task",
                "collect",
            ],
        )
        assert eval_result.exit_code == 0
        assert collect_result.exit_code == 0
        assert status_result.exit_code == 0
        assert collect_run_result.exit_code == 0
        assert json.loads(status_result.output)["state"] == "running"
        assert "eval_summary.json" in collect_run_result.output

    def test_control_run_status_can_infer_runtime_from_saved_handle(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "create",
                "--id",
                "v-test",
                "--variable",
                "improve_navworld",
                "--hypothesis",
                "more data helps",
                "--train-config",
                '{"model":"Qwen/Qwen3-32B","learning_rate":0.0001,"lora_rank":64,"max_length":4096,"num_train_epochs":1,"output_dir":"/tmp/checkpoints"}',
                "--data-config",
                '{"GAME":{"count":100}}',
            ],
        )

        class FakeRuntime:
            async def run(self, request):
                return RunHandle(runtime_kind="docker", run_id="run-123", target_id="fake-target", bundle_path=request.bundle_path)

            async def status(self, request):
                handle = request.handle
                from forge.execution.contracts import RunState, RunStatus

                return RunStatus(runtime_kind="docker", run_id=handle.run_id, state=RunState.RUNNING, detail="alive")

            async def logs(self, request):
                return "fake-log\n"

            async def collect(self, request):
                from forge.execution.contracts import ArtifactManifest

                return ArtifactManifest()

            async def terminate(self, request):
                return None

        monkeypatch.setattr("forge.cli_control._runtime_for", lambda config, runtime_name: FakeRuntime())
        dataset = tmp_path / "train.jsonl"
        dataset.write_text('{"messages":[]}\n')
        submit_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "submit-train",
                "v-test",
                str(dataset),
                "--runtime",
                "docker",
                "--bundle-dir",
                str(tmp_path / "bundle"),
            ],
        )
        status_result = runner.invoke(
            cli,
            [
                "control",
                "--dir",
                str(tmp_path),
                "run-status",
                "v-test",
            ],
        )
        assert submit_result.exit_code == 0
        assert status_result.exit_code == 0
        assert json.loads(status_result.output)["state"] == "running"

    def test_remote_machine_exec_runs_sidecar_command(self, monkeypatch, tmp_path):
        backend_calls = []

        class FakeBackend:
            async def exec(self, inst, command, timeout=60):
                backend_calls.append((inst.id, command, timeout))
                return 0, "remote-ok\n", ""

        instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost")

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.remote_ops.machine_runtime.get_rental", lambda config, machine_selector=None: (FakeBackend(), instance))

        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "machine", "exec", "echo ok"])
        assert result.exit_code == 0
        assert "remote-ok" in result.output
        assert backend_calls == [("m1", "echo ok", 60)]

    def test_data_status_reads_repo_root_synth_config(self, monkeypatch, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        output_file = data_dir / "game.jsonl"
        output_file.write_text('{"messages":[]}\n{"messages":[]}\n')
        synth_config = {
            "status": "active",
            "environments": {
                "GAME": {
                    "enabled": True,
                    "priority": 1,
                    "current_count": 2,
                    "target_count": 4,
                    "output": "data/game.jsonl",
                }
            },
        }
        (tmp_path / "synth_config.json").write_text(json.dumps(synth_config))

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "status"])
        assert result.exit_code == 0
        assert "GAME" in result.output
        assert "need 2" in result.output

    def test_data_aggregate_accepts_remote_name_and_uses_it_for_upload(self, monkeypatch, tmp_path):
        uploads = []

        def fake_build_from_canonical(**kwargs):
            return {"total": 3, "by_env": {"GAME": 3}, "output_path": kwargs["output_path"]}

        def fake_upload_merged(path, token, remote_filename, repo_id="unused"):
            uploads.append((path, token, remote_filename, repo_id))

        config = _config_for(tmp_path)
        config.hf_token = "token"
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: config)
        monkeypatch.setattr("forge.cli_data.build_from_canonical", fake_build_from_canonical, raising=False)
        monkeypatch.setattr("forge.data.aggregate.build_from_canonical", fake_build_from_canonical)
        monkeypatch.setattr("forge.data.aggregate.upload_merged", fake_upload_merged)

        runner = CliRunner()
        output_path = tmp_path / "train.jsonl"
        result = runner.invoke(
            cli,
            ["data", "aggregate", "-o", str(output_path), "--envs", "GAME", "--remote-name", "custom.jsonl"],
        )

        assert result.exit_code == 0
        assert uploads == [(str(output_path), "token", "custom.jsonl", "unused")]

    def test_swe_sync_surfaces_infra_blocker_without_traceback(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "forge.data.swe_ops.sync_new_trajectories",
            lambda dry_run=False: {
                "new_count": 0,
                "skipped_dup": 0,
                "skipped_invalid": 0,
                "total": 0,
                "blocked_reason": "process probe failed: permission denied",
            },
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "swe-sync", "--dry-run"])

        assert result.exit_code != 0
        assert "SWE sync blocked: process probe failed: permission denied" in result.output
        assert "Traceback" not in result.output

    def test_swe_status_shows_blocked_remote_state(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr(
            "forge.data.swe_ops.distill_status",
            lambda: {
                "running": False,
                "processes": [],
                "output_files": [],
                "containers": 0,
                "infra_error": "container probe failed: permission denied",
            },
        )
        monkeypatch.setattr("forge.data.swe_ops.count_local_canonical", lambda: {"total": 0, "by_language": {}})

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "swe-status"])

        assert result.exit_code == 0
        assert "[BLOCKED] container probe failed: permission denied" in result.output

    def test_remote_machine_register_persists_machine_entry(self, monkeypatch, tmp_path):
        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "remote",
                "machine",
                "register",
                "smoke",
                "ssh.deployments.targon.com",
                "--user",
                "wrk-test",
                "--key",
                "~/.ssh/affine_rental",
                "--gpu-type",
                "RTX4090",
            ],
        )

        assert result.exit_code == 0
        machines = json.loads((tmp_path / "machines.json").read_text())
        assert machines["machines"] == [
            {
                "name": "smoke",
                "host": "ssh.deployments.targon.com",
                "port": 22,
                "user": "wrk-test",
                "key": "~/.ssh/affine_rental",
            }
        ]

    def test_remote_machine_start_sglang_uses_bootstrap_env(self, monkeypatch, tmp_path):
        backend_calls = []

        class FakeBackend:
            def __init__(self):
                self.calls = 0

            async def exec(self, inst, command, timeout=60):
                self.calls += 1
                backend_calls.append((command, timeout))
                if self.calls == 1:
                    return 1, "", ""
                return 0, "", ""

        instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost")

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.remote_ops.machine_eval.get_rental", lambda config, machine_selector=None: (FakeBackend(), instance))

        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "machine", "start-sglang", "Qwen/Qwen2.5-0.5B-Instruct", "--no-wait"])

        assert result.exit_code == 0
        assert "source /data/.affine/sglang-venv/bin/activate" in backend_calls[1][0]
        assert "sglang[all]==0.4.9.post4" in backend_calls[1][0]
        assert "apt-get install -y libnuma1" in backend_calls[1][0]
        assert "uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz" in backend_calls[1][0]
        assert backend_calls[2][0] == "mkdir -p /root/logs /root/tmp /root/.triton_cache"
        assert "if [ -f /root/.env ]; then source /root/.env; fi" in backend_calls[4][0]

    def test_remote_machine_start_training_uses_bootstrap_env(self, monkeypatch, tmp_path):
        uploads = []
        exec_calls = []

        class FakeBackend:
            async def upload(self, inst, local_path, remote_path):
                uploads.append((local_path, remote_path))

            async def exec(self, inst, command, timeout=60):
                exec_calls.append((command, timeout))
                return 0, "", ""

        instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost")
        script_path = tmp_path / "train.py"
        script_path.write_text("print('ok')\n")

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.remote_ops.machine_runtime.get_rental", lambda config, machine_selector=None: (FakeBackend(), instance))

        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "machine", "start-training", str(script_path)])

        assert result.exit_code == 0
        assert uploads == [(str(script_path), "/root/scripts/train.py")]
        assert "source /data/.affine/activate.sh" in exec_calls[0][0]
        assert "[ ! -f /root/.env ] || source /root/.env" in exec_calls[0][0]

    def test_remote_machine_start_sglang_tolerates_bridge_probe_timeout(self, monkeypatch, tmp_path):
        backend_calls = []

        class FakeBackend:
            def __init__(self):
                self.calls = 0

            async def exec(self, inst, command, timeout=60):
                self.calls += 1
                backend_calls.append((command, timeout))
                if self.calls == 1:
                    return 0, "", ""
                if self.calls in (2, 3, 4):
                    return 0, "", ""
                if self.calls == 5:
                    return 0, '{"object":"list","data":[{"id":"model"}]}', ""
                if self.calls == 6:
                    raise subprocess.TimeoutExpired(command, timeout)
                return 0, "", ""

        instance = GpuInstance(id="m1", backend="ssh", gpu_type="H200", status="ready", host="localhost")

        monkeypatch.setattr("forge.cli.ForgeConfig.load", lambda: _config_for(tmp_path))
        monkeypatch.setattr("forge.remote_ops.machine_eval.get_rental", lambda config, machine_selector=None: (FakeBackend(), instance))
        monkeypatch.setattr("time.sleep", lambda _: None)

        runner = CliRunner()
        result = runner.invoke(cli, ["remote", "machine", "start-sglang", "Qwen/Qwen2.5-0.5B-Instruct"])

        assert result.exit_code == 0
        assert "sglang ready after 15s" in result.output
        assert "WARNING: Docker bridge (172.17.0.1) probe timed out" in result.output
