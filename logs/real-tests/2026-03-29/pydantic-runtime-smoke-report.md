# Pydantic Migration Runtime Smoke Report

Date: 2026-03-29

## Scope

This session reran real execution-plane smoke tests after the Pydantic migration.

Validated path:

- `forge worker`
- runtime: `targon`
- profile: `bootstrap`
- dataset repo: `monokoco/affine-sft-data`
- gpu type: `H200`

The goal was to confirm that the new Pydantic request/response contracts did not break
real remote startup for:

- `train`
- `collect`
- `eval`

## Capacity

Command:

```bash
./.venv/bin/python -m forge remote compute capacity
```

Observed:

- `h200-small`: `102`
- `h200-medium`: `49`
- `h200-large`: `23`
- `h200-xlarge`: `10`

## Bundles

Working directory:

- `tmp/real-smoke-2026-03-29/`

Rendered bundles:

- `bundle-train`
- `bundle-collect`
- `bundle-eval`

## Worker Train

Run:

```bash
./.venv/bin/python -m forge worker run tmp/real-smoke-2026-03-29/bundle-train \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200
```

Observed:

- run id: `wrk-zs1bv8t4hs67`
- `forge worker status ...` returned:
  - `state=submitted`
  - `detail=provisioning`
- `forge worker logs ...` returned bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/real-smoke-2026-03-29/bundle-train
```

Result:

- `pass`

## Worker Collect

Run:

```bash
./.venv/bin/python -m forge worker run tmp/real-smoke-2026-03-29/bundle-collect \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200
```

Observed:

- run id: `wrk-oekwjnmhjsym`
- `forge worker status ...` returned:
  - `state=running`
  - `detail=running`
- `forge worker logs ...` returned bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/real-smoke-2026-03-29/bundle-collect
```

Result:

- `pass`

## Worker Eval

Run:

```bash
./.venv/bin/python -m forge worker run tmp/real-smoke-2026-03-29/bundle-eval \
  --runtime targon \
  --profile bootstrap \
  --dataset-repo monokoco/affine-sft-data \
  --gpu-type H200
```

Observed:

- run id: `wrk-qxozah2e0rhb`
- `forge worker status ...` returned:
  - `state=running`
  - `detail=running`
- `forge worker logs ...` returned bootstrap output:
  - `[AFFINE] Affine Forge Bootstrap — starting`
  - `[AFFINE] Phase 0: Installing system packages...`

Terminate:

```bash
./.venv/bin/python -m forge worker terminate tmp/real-smoke-2026-03-29/bundle-eval
```

Result:

- `pass`

## Overall

All three execution-plane smoke tasks passed startup validation on real Targon runtime after the Pydantic migration.

Validated:

- bundle rendering still produces runnable bundles
- typed `forge worker run/status/logs/terminate` still works against real remote execution
- train / collect / eval all reach a real remote started state

Not covered in this session:

- full completion to final artifacts
- control-plane resubmission smoke on the migrated schema

## Final Verdict

Execution-plane real smoke after the Pydantic migration: **pass**
