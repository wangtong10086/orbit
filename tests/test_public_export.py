from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


def _load_export_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "export_public.py"
    spec = importlib.util.spec_from_file_location("export_public", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_export_snapshot_writes_expected_public_paths(tmp_path):
    module = _load_export_module()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "public"
    report = module.export_snapshot(
        repo_root=repo_root,
        manifest_path=repo_root / "release" / "public-export.yaml",
        output_dir=output_dir,
        force=True,
    )

    assert (output_dir / "orbit" / "core" / "experiments" / "__init__.py").exists()
    assert (output_dir / "scripts" / "vllm_teacher_qwen3_235b_tp8.sh").exists()
    assert not (output_dir / "docs" / "research").exists()
    assert report["snapshot"]["files"] > 0
    assert report["manifest_digest"]


def test_git_publish_forces_ignored_files_into_remote_snapshot(tmp_path, monkeypatch):
    module = _load_export_module()
    bare_remote = tmp_path / "remote.git"
    module._run(["git", "init", "--bare", str(bare_remote)])

    output_dir = tmp_path / "snapshot"
    output_dir.mkdir()
    (output_dir / ".gitignore").write_text("orbit/core/experiments\n", encoding="utf-8")
    target = output_dir / "orbit" / "core" / "experiments"
    target.mkdir(parents=True)
    (target / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setenv("EXPORT_PUBLIC_REMOTE_URL", str(bare_remote))
    public_sha = module.git_publish(
        output_dir=output_dir,
        owner="ignored",
        name="ignored",
        branch="main",
        message="snapshot",
        force_push=True,
    )

    assert public_sha

    checkout_dir = tmp_path / "checkout"
    module._run(["git", "clone", "-b", "main", str(bare_remote), str(checkout_dir)])
    assert (checkout_dir / "orbit" / "core" / "experiments" / "__init__.py").exists()


def test_export_script_metadata_and_report_outputs(tmp_path, monkeypatch):
    module = _load_export_module()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "public"
    report_path = tmp_path / "report.json"
    metadata_path = tmp_path / "metadata.json"

    monkeypatch.chdir(repo_root)
    old_argv = os.sys.argv
    os.sys.argv = [
        "export_public.py",
        "--output-dir",
        str(output_dir),
        "--force",
        "--source-sha",
        "deadbeef",
        "--report-out",
        str(report_path),
        "--metadata-out",
        str(metadata_path),
    ]
    try:
        assert module.main() == 0
    finally:
        os.sys.argv = old_argv

    report = json.loads(report_path.read_text())
    metadata = json.loads(metadata_path.read_text())
    assert metadata["source_sha"] == "deadbeef"
    assert metadata["public_repo"] == "wangtong10086/ORBIT"
    assert report["snapshot"]["files"] > 0
