# Current ORBIT Public Release Path

This reference captures the current private-to-public release topology for `/home/ubuntu/orbit`.

## Repositories

- Private source: `wangtong10086/orbit`
- Public target: `AffineFoundation/ORBIT`
- Working tree: `/home/ubuntu/orbit`

## Authoritative Files

- Export manifest:
  - `/home/ubuntu/orbit/release/public-export.yaml`
- Export script:
  - `/home/ubuntu/orbit/scripts/export_public.py`
- Snapshot validator:
  - `/home/ubuntu/orbit/scripts/validate_public_snapshot.sh`
- Private publish workflow:
  - `/home/ubuntu/orbit/.github/workflows/publish-public.yml`
- Public workflows that must pass after publish:
  - `/home/ubuntu/orbit/.github/workflows/ci.yml`
  - `/home/ubuntu/orbit/.github/workflows/docs.yml`
  - `/home/ubuntu/orbit/.github/workflows/docker.yml`

## Accounts And Auth

- Private repo `gh` account usually active locally: `wangtong10086`
- Public repo Actions inspection account: `wang-tong0`
- Switch accounts:
  - `gh auth switch -u wangtong10086`
  - `gh auth switch -u wang-tong0`
- Private workflow publish secret:
  - `AFFINEFOUNDATION_ORBIT_TOKEN`
- Local cached token path if needed:
  - `~/.config/orbit/github_token`

## Default Release Path

1. Push to private `main`.
2. Private `Publish Public Snapshot` workflow exports a clean snapshot.
3. The workflow validates the snapshot in isolation.
4. The workflow force-pushes to `AffineFoundation/ORBIT:main`.
5. The workflow dispatches or watches public `CI`, `Docs`, and `Docker`.
6. The release is healthy only when all three public workflows pass.

## Local Snapshot Dry Run

Use this when debugging export or validation logic before touching Actions:

```bash
SOURCE_SHA=$(git -C /home/ubuntu/orbit rev-parse HEAD)
python3 /home/ubuntu/orbit/scripts/export_public.py \
  --output-dir /tmp/orbit-public-debug \
  --force \
  --source-sha "$SOURCE_SHA" \
  --metadata-out /tmp/orbit-public-debug.metadata.json \
  --report-out /tmp/orbit-public-debug.report.json

bash /home/ubuntu/orbit/scripts/validate_public_snapshot.sh /tmp/orbit-public-debug
```

Useful outputs:

- `/tmp/orbit-public-debug.metadata.json`
- `/tmp/orbit-public-debug.report.json`

## Public Workflow Inspection

Switch to `wang-tong0` before querying the public repo:

```bash
gh auth switch -u wang-tong0
gh run list -R AffineFoundation/ORBIT --limit 20
gh run view RUN_ID -R AffineFoundation/ORBIT --log
```

Switch back when done:

```bash
gh auth switch -u wangtong10086
```

## Release Mapping

The export script can emit metadata with:

- `source_repo`
- `source_sha`
- `public_repo`
- `public_branch`
- `public_sha`
- `export_manifest_digest`
- `snapshot_dir`

Prefer using that metadata instead of reconstructing the mapping by hand.

## Known Failure Modes

### `.gitignore` drops exported files

Symptom:

- snapshot is missing files that should be public

Fix area:

- `/home/ubuntu/orbit/scripts/export_public.py`

Guardrail:

- publish path must use `git add -A --force .`

### Validation byproducts leak into the public repo

Symptom:

- public CI fails on `.venv`, `dist`, `logs`, `orbit.egg-info`, or similar generated content

Fix area:

- `/home/ubuntu/orbit/.github/workflows/publish-public.yml`

Guardrail:

- remove validation byproducts before archiving or publishing the snapshot

### Publish fails on git identity

Symptom:

- `git commit` fails inside the publish step

Fix area:

- export script publish step or workflow env

Guardrail:

- set explicit author fields:
  - `EXPORT_PUBLIC_GIT_AUTHOR_NAME`
  - `EXPORT_PUBLIC_GIT_AUTHOR_EMAIL`

### Public status is checked too early

Symptom:

- private publish workflow reports success before public `CI/Docs/Docker` actually finish

Fix area:

- `/home/ubuntu/orbit/.github/workflows/publish-public.yml`

Guardrail:

- watch the exact public run IDs or explicit public SHA-triggered runs

### Docs reference non-exported files

Symptom:

- public docs or link checks fail

Fix area:

- either export the referenced file or change the docs to reference a public path

## When Auditing Private/Public Alignment

Check:

1. export manifest and overlays
2. exported file tree
3. private publish workflow logic
4. public workflow definitions
5. latest `public_sha`
6. public `CI`, `Docs`, and `Docker` status

Do not assume green private CI means the public snapshot is correct. The snapshot itself is the validation target.
