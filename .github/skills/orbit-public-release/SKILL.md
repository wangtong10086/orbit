---
name: orbit-public-release
description: "Use this skill when a task involves exporting, validating, publishing, auditing, or repairing the public ORBIT snapshot that is mirrored from the private repo to wangtong10086/ORBIT. Trigger it for requests about public snapshot drift, release automation, public GitHub Actions, release/public-export.yaml, scripts/export_public.py, scripts/validate_public_snapshot.sh, or the publish-public GitHub workflow."
---

# ORBIT Public Release

Operate the private-to-public release path for ORBIT without falling back to ad hoc local export-and-push steps. Prefer validating the exported snapshot itself, then publishing and watching the public workflows.

## Trigger Cues

- `wangtong10086/ORBIT`
- `release/public-export.yaml`
- `scripts/export_public.py`
- `scripts/validate_public_snapshot.sh`
- `.github/workflows/publish-public.yml`
- requests to "publish the public repo", "check public Actions", "repair snapshot drift", "verify public export", or "sync private repo to public repo"

## Use This Skill For

- exporting a fresh public snapshot from `/home/ubuntu/orbit`
- validating the snapshot before publish
- debugging private or public release workflows
- checking whether the public repo is missing files, docs, or workflows
- auditing whether private and public CI/CD are aligned
- recording or verifying `source_sha -> public_sha` release mappings

## Do Not Use This Skill For

- generic GitHub issue or PR work with no ORBIT public-release context
- private-only training, Targon, or runtime debugging
- unrelated package publishing or container registry release work

## Current Release Model

- Private source repo: `wangtong10086/orbit`
- Public target repo: `wangtong10086/ORBIT`
- Private repo `main` owns the release workflow.
- Public repo is a generated snapshot, not the development trunk.
- The authoritative export rules live in [release/public-export.yaml](/home/ubuntu/orbit/release/public-export.yaml).
- The authoritative export tool is [scripts/export_public.py](/home/ubuntu/orbit/scripts/export_public.py).
- The authoritative snapshot validator is [scripts/validate_public_snapshot.sh](/home/ubuntu/orbit/scripts/validate_public_snapshot.sh).

Read [references/current-release-path.md](/home/ubuntu/orbit/.github/skills/orbit-public-release/references/current-release-path.md) when you need exact commands, workflow names, secrets, and known failure modes.

## Operating Rules

1. Validate the exported snapshot, not just the private source tree.
2. Treat `release/public-export.yaml` as the only export manifest source of truth.
3. Do not bypass the private `publish-public` workflow with manual local push unless the user explicitly asks for an emergency override.
4. When checking public workflow health, use the public commit SHA and the exact public workflow runs, not assumptions from private CI.
5. Keep git author identity explicit when publishing.
6. Remove validation byproducts from the snapshot before publishing.
7. If public CI is green but the snapshot is wrong, inspect export rules and the exported file tree before changing workflow logic.

## Standard Workflow

### 1. Inspect release inputs

Check:

- [release/public-export.yaml](/home/ubuntu/orbit/release/public-export.yaml)
- [scripts/export_public.py](/home/ubuntu/orbit/scripts/export_public.py)
- [scripts/validate_public_snapshot.sh](/home/ubuntu/orbit/scripts/validate_public_snapshot.sh)
- [.github/workflows/publish-public.yml](/home/ubuntu/orbit/.github/workflows/publish-public.yml)

If the task is about a public failure, also inspect:

- the latest private `Publish Public Snapshot` run
- the latest public `CI`, `Docs`, and `Docker` runs

### 2. Reproduce on the snapshot

Export to a temp dir and validate the snapshot there first. Use the local validator before changing code. The detailed commands are in [references/current-release-path.md](/home/ubuntu/orbit/.github/skills/orbit-public-release/references/current-release-path.md).

### 3. Fix the right layer

- Missing or extra files: fix `release/public-export.yaml` or `scripts/export_public.py`
- Snapshot validation failures: fix snapshot contents or `scripts/validate_public_snapshot.sh`
- Publish failures: fix `.github/workflows/publish-public.yml`, auth, or git metadata
- Public CI failures after publish: fix the exported snapshot or public-facing docs/scripts, then rerun publish

### 4. Verify both the original failure and a downstream dependency

For release bugs, rerun:

1. the original failing command or workflow condition
2. a downstream dependent step

Examples:

- if `python -m orbit control --help` failed in the snapshot, rerun that exact command in the exported tree and then rerun the relevant public `CI`
- if docs links failed, rerun `lychee` in the exported tree and then rerun public `Docs`

### 5. Publish and watch public workflows

- Prefer the private workflow to publish.
- After push, verify the `public_sha`.
- Wait for public `CI`, `Docs`, and `Docker`.
- Do not mark the release healthy until all three are green.

## Troubleshooting Heuristics

- If exported files are unexpectedly missing, suspect `.gitignore` interaction or wrong include/exclude rules first.
- If public CI fails on files like `.venv`, `dist`, `logs`, or `orbit.egg-info`, suspect snapshot validation byproducts leaked into the published tree.
- If the publish step succeeds but the private workflow reports success too early, confirm it is watching the exact public runs for the published SHA.
- If `gh` cannot see the public repo state, switch to the `wang-tong0` account before assuming the repo is inaccessible.
- If docs reference files that are absent in the public repo, confirm those files are exported before editing the docs.

## Output Contract

When using this skill, provide:

1. the private source SHA and public SHA when relevant
2. the exact workflow or command that failed
3. the file or config that owns the fix
4. the rerun or verification commands
5. whether public `CI`, `Docs`, and `Docker` are green

## References

- [references/current-release-path.md](/home/ubuntu/orbit/.github/skills/orbit-public-release/references/current-release-path.md): repos, workflows, secrets, commands, and known pitfalls
