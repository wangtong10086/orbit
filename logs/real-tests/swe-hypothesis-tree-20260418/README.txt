SWE Hypothesis-Tree Validation
Date: 2026-04-18
Runtime: local CPU + Docker
Student endpoint: Chutes OpenAI-compatible `/v1`
Student model: `hippo-master/affine-17-5D7H7grKtvLJLy9GJWX8HEx2Z4swukjb9f8jAySR21UQEK9c`
Teacher endpoint: `.env OPENAI_BASE_URL`
Teacher model: `gpt-5`

Purpose
- Validate the new root-race + repair-hypothesis realization tree search on fixed real R2-loaded SWE tasks.
- Keep `A` pure, allow `T` for feasibility, and measure the new search-specific counters.

Fixed task files
- `mini-rubocop`: `/tmp/orbit-swe-taskfiles/rubocop.txt` -> `rubocop__rubocop-7660`
- `codex-geopy`: `/tmp/orbit-swe-taskfiles/geopy.txt` -> `geopy__geopy-388`
- `codex-rails`: `/tmp/orbit-swe-taskfiles/rails.txt` -> `rails__rails-38448`

Common sample recipe
- `teacher_online=true`
- `teacher_online_budget=12`
- `teacher_branch_fanout=2`
- `max_steps=4`
- `localization_budget=8`
- `localization_top_k=3`
- `plan_samples_per_state=2`
- `max_realizations=4`
- `search_node_budget=12`
- `attempts_per_node=3`
- `max_live_nodes=6`
- `full_verify_budget=2`
- `root_race_rounds=2`
- `root_race_keep=3`
- `progressive_bias_beta=0.30`

Exact sample command template
- `./.venv/bin/python -m orbit data swe-collect sample --task-file <task_file> --format <fmt> --student-endpoint https://llm.chutes.ai/v1 --student-model hippo-master/affine-17-5D7H7grKtvLJLy9GJWX8HEx2Z4swukjb9f8jAySR21UQEK9c --student-api-key $CHUTES_API_KEY --teacher-endpoint $OPENAI_BASE_URL --teacher-model gpt-5 --teacher-api-key $OPENAI_API_KEY --teacher-online --teacher-online-budget 12 --teacher-branch-fanout 2 --max-steps 4 --localization-budget 8 --localization-top-k 3 --plan-samples-per-state 2 --max-realizations 4 --search-node-budget 12 --attempts-per-node 3 --max-live-nodes 6 --full-verify-budget 2 --root-race-rounds 2 --root-race-keep 3 --progressive-bias-beta 0.30 --output-dir <output_dir>`

Downstream commands
- `./.venv/bin/python -m orbit data swe-collect relabel --input-dir <output_dir> --cache-dir /tmp/orbit-swe-task-cache --teacher-endpoint $OPENAI_BASE_URL --teacher-model gpt-5 --teacher-api-key $OPENAI_API_KEY --window-radius 1 --max-repairs 2`
- `./.venv/bin/python -m orbit data swe-collect build-buckets --input-dir <output_dir>`

Results

1. `mini-rubocop`
- `sampled_trajectories=4`
- `successful_trajectories=0`
- raw terminal status:
  - `verify_fail=1`
  - `no_patch=1`
  - `max_steps=2`
- funnel:
  - `changed_files=3/4`
  - `syntax_ok=1/4`
  - `verify_fail=1/4`
- tree metrics:
  - `root_nodes_total=4`
  - `root_race_rounds_run=2`
  - `hypothesis_nodes_total=16`
  - `hypothesis_children_total=7`
  - `teacher_hypotheses_total=5`
  - `selection_tier_histogram={"3":2,"2":1,"1":4,"0":3}`
- bucket output:
  - `A=0 B=2 C=2 J=12 O=3 T=0 V=4`

2. `codex-geopy`
- `sampled_trajectories=4`
- `successful_trajectories=0`
- raw terminal status:
  - `quality_fail=1`
  - `no_patch=3`
- funnel:
  - `changed_files=0/4`
  - `syntax_ok=0/4`
  - `verify_fail=0/4`
- tree metrics:
  - `root_nodes_total=4`
  - `root_race_rounds_run=2`
  - `hypothesis_nodes_total=15`
  - `hypothesis_children_total=0`
  - `teacher_hypotheses_total=5`
  - `selection_tier_histogram={"0":4}`
- bucket output:
  - `A=0 B=0 C=0 J=11 O=0 T=0 V=4`

3. `codex-rails`
- `sampled_trajectories=4`
- `successful_trajectories=0`
- raw terminal status:
  - `quality_fail=2`
  - `no_patch=1`
  - `max_steps=1`
- funnel:
  - `changed_files=3/4`
  - `syntax_ok=0/4`
  - `verify_fail=0/4`
- tree metrics:
  - `root_nodes_total=4`
  - `root_race_rounds_run=2`
  - `hypothesis_nodes_total=16`
  - `hypothesis_children_total=6`
  - `teacher_hypotheses_total=1`
  - `selection_tier_histogram={"3":2,"1":4,"0":1}`
- bucket output:
  - `A=0 B=2 C=2 J=12 O=3 T=0 V=4`

Feasibility verdict
- Implementation: PASS
- Targeted regression: PASS
- Real fixed-task validation: FAIL

Why it failed
- No `A` or `T` success on any of the three fixed tasks.
- The search-shape changes did materially alter the funnel and now produce the intended new artifacts:
  - `search/checkpoints.jsonl`
  - `search/hypotheses.jsonl`
  - `search/nodes.jsonl`
  - `search/teacher_state_summaries.jsonl`
- `mini-rubocop` and `codex-rails` reached changed-file states and produced `B/C/O/J`.
- `codex-geopy` regressed relative to the earlier success-prob rerun and failed to reach changed-files under this hypothesis-tree recipe.

Interpretation
- Root race + hypothesis-tree + multi-fidelity backup is alive on real tasks.
- The new counters and artifacts are trustworthy enough to analyze.
- This run did not satisfy the original feasibility gate because the strategy still produced `0` verified successes.
- The remaining bottleneck still looks like patch landing quality rather than collector honesty:
  - `mini-rubocop`: real changed-files but insufficient syntax/verify conversion
  - `codex-rails`: real changed-files but poor syntax conversion
  - `codex-geopy`: hypothesis generation/realization did not land any real patch
