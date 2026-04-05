"""CLI wiring tests for GAME long-run remote sidecar commands."""

from __future__ import annotations

from click.testing import CliRunner

from orbit.cli import cli


class TestRemoteGameLongRunCli:
    def test_launch_requires_policy_repo(self, config_factory, monkeypatch, tmp_path):
        cfg = config_factory(tmp_path).model_copy(update={"hf_game_policy_repo": ""})
        inst = type("Inst", (), {"id": "m1"})()
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: cfg)
        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.get_rental", lambda config, machine_selector=None: (object(), inst))

        result = CliRunner().invoke(cli, ["remote", "machine", "-m", "m1", "game-longrun", "launch"])

        assert result.exit_code != 0
        assert "HF_GAME_POLICY_REPO not set" in result.output

    def test_launch_invokes_remote_service(self, config_factory, monkeypatch, tmp_path):
        calls = []
        cfg = config_factory(tmp_path).model_copy(update={"hf_game_policy_repo": "user/private-policy"})
        inst = type("Inst", (), {"id": "m1"})()
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: cfg)
        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.get_rental", lambda config, machine_selector=None: ("backend", inst))

        async def fake_launch(**kwargs):
            calls.append(kwargs)
            return {"stdout": "SESSION job1\nLOG /root/logs/job1.log\nROOT /root/affine-swarm/artifacts/game_longrun/job1"}

        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.launch_game_longrun_job", fake_launch)

        result = CliRunner().invoke(
            cli,
            ["remote", "machine", "-m", "m1", "game-longrun", "launch", "--job-name", "job1", "--episodes", "32"],
        )

        assert result.exit_code == 0
        assert "SESSION job1" in result.output
        assert calls[0]["backend"] == "backend"
        assert calls[0]["env"]["AFFINE_GAME_POLICY_REPO"] == "user/private-policy"
        assert calls[0]["env"]["AFFINE_GAME_LONGRUN_SELFPLAY_EPISODES"] == "32"
        assert calls[0]["env"]["AFFINE_GAME_LONGRUN_AUTOTUNE_BATCH"] == "1"
        assert calls[0]["env"]["AFFINE_GAME_LONGRUN_QUICK_GATE_INTERVAL"] == "3"
        assert calls[0]["env"]["AFFINE_GAME_LONGRUN_TEACHER_GATE_INTERVAL"] == "5"
        assert calls[0]["env"]["AFFINE_GAME_LONGRUN_SYNC_INTERVAL"] == "10"

    def test_status_reads_remote_state(self, config_factory, monkeypatch, tmp_path):
        cfg = config_factory(tmp_path)
        inst = type("Inst", (), {"id": "m1"})()
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: cfg)
        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.get_rental", lambda config, machine_selector=None: ("backend", inst))

        async def fake_status(**kwargs):
            return {"job_name": "job1", "screen_active": True, "state": {"status": "running", "phase": "training"}}

        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.read_game_longrun_status", fake_status)

        result = CliRunner().invoke(cli, ["remote", "machine", "-m", "m1", "game-longrun", "status", "--job-name", "job1"])

        assert result.exit_code == 0
        assert '"screen_active": true' in result.output
        assert '"status": "running"' in result.output

    def test_stop_requests_remote_stop(self, config_factory, monkeypatch, tmp_path):
        cfg = config_factory(tmp_path)
        inst = type("Inst", (), {"id": "m1"})()
        monkeypatch.setattr("orbit.cli.OrbitConfig.load", lambda: cfg)
        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.get_rental", lambda config, machine_selector=None: ("backend", inst))

        async def fake_stop(**kwargs):
            return "STOPPED"

        monkeypatch.setattr("orbit.domain_jobs.game_longrun.remote.stop_game_longrun_job", fake_stop)

        result = CliRunner().invoke(cli, ["remote", "machine", "-m", "m1", "game-longrun", "stop", "--job-name", "job1"])

        assert result.exit_code == 0
        assert "STOPPED" in result.output
