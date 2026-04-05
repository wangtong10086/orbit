# Affine Swarm: Verifier-Grounded Semi-On-Policy Distillation (VG-SOPD)

Branch target: `refactor/three-layer-architecture`

## 1. Purpose

This document defines a high-level training algorithm and repository integration direction for implementing a new AffineTes post-training method in `affine-swarm`.

The method should satisfy all of the following:

1. Dense learning signal, closer to distillation than sparse RL.
2. As on-policy as practical, but not strictly pure on-policy.
3. Full use of environment-provided ground truth and deterministic scoring.
4. Support both white-box and black-box teachers.
5. Fit the current `refactor/three-layer-architecture` repository model.
6. Reuse `ms-swift` as the actual training backend instead of replacing the trainer stack.

This document is intentionally high level. It defines architecture, algorithm shape, data products, and boundaries. It does **not** provide a step-by-step implementation plan or low-level code design.

---

## 2. Branch-Aligned Architectural Assumptions

Implementation must respect the current repository architecture on `refactor/three-layer-architecture`.

### 2.1 Control Plane
The control plane owns:
- experiment records
- template-driven orchestration
- run submission
- status/log/artifact collection
- config-driven launch flows

### 2.2 Execution Plane
The execution plane owns:
- generic bundle layout
- placement / launch mode backends
- runtime execution
- artifact and runtime log collection

It must remain task-agnostic.

### 2.3 Task Plugins
Task plugins own:
- task-specific request parsing
- task-specific bundle construction
- task-specific result summarization

### 2.4 Sidecars
Sidecars may support:
- remote machine operations
- monitoring
- domain-specific operational workflows

They must not become the hidden main architecture path.

### 2.5 Training Backend Constraint
Training must continue to run through the current `TrainingPlugin -> TrainBundleBuilder -> ms-swift` path. The algorithm should be expressed primarily as:

- rollout / relabel / compilation logic above the execution core
- dataset construction and training mode selection
- optional multi-stage `ms-swift` runs

The preferred implementation strategy is to compile the algorithm into data views and training configs that the existing `ms-swift` integration can already execute.

---

## 3. Why Existing Baselines Are Not Enough

### 3.1 Pure RFT is not enough
Rejection-style filtering of successful trajectories is a strong baseline, but it saturates:
- it wastes failed trajectories
- it becomes sample-inefficient on hard environments
- it underuses environment process information
- it cannot efficiently expand the student frontier when success probability is very low

### 3.2 Pure On-Policy Distillation is not enough
Standard on-policy distillation is closer to the desired behavior-distribution constraint, but it also leaves signal unused:
- environment feedback is often only used as a final scalar filter
- dense teacher knowledge is underused when only a small number of successful student trajectories exist
- hard tasks such as SWE and LIVEWEB may produce too few successful fully-student trajectories

### 3.3 Pure RL is not the target
Sparse-reward RL is too slow and too unstable for the intended training regime. The desired regime is:
- distillation-like density
- verifier-grounded correctness
- on-policy-ish state distribution
- minimal damage to base model capabilities

---

## 4. Proposed Method: VG-SOPD

## Name
**Verifier-Grounded Semi-On-Policy Distillation (VG-SOPD)**

## Core idea
Train the student mainly on trajectories that remain close to its own state distribution, while using:
- environment ground truth to create dense progress labels and correctness signals
- white-box teacher supervision where logits or rankings are available
- black-box teacher repair / critique / ranking when logits are unavailable
- preference and negative signals from failed or lower-quality trajectories
- `ms-swift` training stages that consume compiled SFT / GKD / DPO-style views

This is not pure RFT and not pure RL.
It is a **distillation-first, verifier-grounded, semi-on-policy training loop**.

---

## 5. Algorithm Overview

VG-SOPD has six logical stages.

### Stage A. Cold Start
Use a small, curated, high-quality bootstrap set only.
This set should be intentionally limited and should not become the dominant source of training signal.

Cold-start data may include:
- carefully selected successful trajectories
- environment-specific expert traces
- GAME expert datasets from search-based teachers
- small quantities of high-quality teacher demonstrations for hard environments

The goal is only to move the model into a regime where on-policy-ish rollout becomes informative.

### Stage B. Student Frontier Rollout
Use the current student to generate trajectories on target environments.

Key principles:
- prefer student-generated prefixes
- keep rollout temperature / decoding behavior compatible with downstream deployment
- collect more than one trajectory per task when budget allows
- record full trajectory structure, not only final text

The purpose of this stage is to expose the model’s actual frontier.

### Stage C. Environment-Grounded Relabel
For each trajectory, use environment feedback to produce richer labels than simple pass/fail.

Relabel products should include:
- final success / score
- intermediate progress signal when available
- first-error localization or first-bad-decision approximation
- task-specific structured quality labels
- verifier-derived pairwise ranking between candidate trajectories

The environment is not just a filter. It is an active label source.

### Stage D. Teacher Augmentation
Augment frontier trajectories using one or more teachers.

Teacher behavior should be **local**, not full replacement by default.

Teacher operations may include:
- white-box logit / top-k / ranking annotation on selected spans or steps
- white-box local action/value guidance
- black-box critique of incorrect step or suffix
- black-box repaired suffix generation from a student prefix
- black-box pairwise ranking between multiple candidate trajectories
- GAME search/equilibrium teacher replacement for action policy targets

Teacher use must be selective and verifier-aware.

### Stage E. Data Compilation
Compile collected and relabeled data into multiple training views rather than a single monolithic dataset.

Required conceptual views:
- positive SFT view
- repaired SFT view
- white-box KD / GKD view
- preference view
- negative view
- optional RL-style reward view for specific cheap deterministic settings

The same underlying trajectory store may feed multiple training views.

### Stage F. Multi-Stage Training
Run one or more `ms-swift` stages on compiled views.

The default ordering should be:
1. SFT / GKD-like dense supervision stage
2. preference optimization stage
3. optional verifier-driven RL stage only where justified

The method should remain distillation-dominant, not RL-dominant.

---

## 6. Semi-On-Policy Definition

The intended meaning of “semi-on-policy” in this project is:

- prefixes should usually come from the current student
- the state distribution should be mostly induced by the student
- teacher intervention is allowed after the student reaches a frontier prefix
- repaired suffixes are allowed
- branch exploration is allowed
- verifier-guided resampling is allowed
- full teacher-only replacement of every trajectory is not the main path

A trajectory is acceptable even if it is not fully generated by the student, as long as:
- the important decision context was reached by the student, or
- the repaired trajectory is explicitly tied to a student frontier prefix

This is the working compromise between capability retention and usable positive-sample density.

---

## 7. Dense Signal Construction

Dense signal is the main requirement. The algorithm must generate dense training information from two sources.

### 7.1 Teacher-Derived Density
Teacher-derived density may come from:
- white-box logits
- local ranking over candidate actions
- top-k overlap or support alignment
- repaired continuation from a frontier prefix
- critique or preference labels for competing continuations

### 7.2 Environment-Derived Density
Environment-derived density may come from:
- deterministic step reward when available
- structured sub-score breakdown
- branch comparison under the same prefix
- first-error approximation
- prefix replay and suffix scoring
- multi-candidate ranking from the same task
- success margin, not only binary success

The implementation should prefer turning environment signal into reusable process labels rather than treating it as only a terminal reward.

---

## 8. Training Data Taxonomy

VG-SOPD should treat trajectory data as typed objects.

## 8.1 Positive trajectory
A trajectory that reaches verified success or a sufficiently high verified score.

Use for:
- SFT
- GKD
- chosen side of preference training

## 8.2 Near-miss trajectory
A trajectory that is not fully correct but reaches a strong frontier prefix.

Use for:
- repair generation
- step-level critique
- prefix-preserving correction
- preference construction against weaker variants

## 8.3 Negative trajectory
A clearly incorrect or lower-quality trajectory.

Use for:
- rejected side of preference training
- negative-aware training
- trajectory ranking
- environment-specific veto examples

## 8.4 Repaired trajectory
A trajectory whose prefix is student-generated but whose suffix is replaced or corrected.

Use for:
- repaired SFT
- chosen example in preference training
- partial KD targets

## 8.5 Teacher-annotated trajectory
A trajectory or span annotated with white-box information.

Use for:
- GKD-style training
- local action supervision
- distillation on selected decisions instead of all tokens

---

## 9. Environment-Specific Strategy

A single teacher policy is not appropriate for all AffineTes environments.

### 9.1 GAME
Primary teacher should be non-LLM expert/search teacher where available.

Preferred supervision:
- improved action policy
- value target
- action ranking
- search-derived preference
- self-play or expert-play distributions

LLM teacher is secondary for GAME.
Search/equilibrium teacher is primary.

### 9.2 QQR / NAVWORLD
Primary challenge:
- tool selection
- argument construction
- information integration
- final structured plan quality

Preferred supervision:
- student-prefix rollout
- verifier-based ranking
- local repair on tool step or argument step
- teacher critique / repaired suffix
- dense process labels from step scores where available

### 9.3 LIVEWEB
Primary challenge:
- long horizon browser control
- branching and recovery
- action correctness under changing page state

Preferred supervision:
- student frontier rollout
- branch-and-verify under shared prefix
- teacher correction only at key decision points
- preference pairs between successful and failed action branches
- process relabel where replay is practical

### 9.4 MEMORYGYM
Primary challenge:
- write / update / retrieve / abstain policy
- memory management under budget

Preferred supervision:
- operation-policy labels
- positive / negative comparisons on memory actions
- verifier-grounded sub-score relabel
- teacher intervention mainly for difficult update / conflict cases

### 9.5 SWE
Primary challenge:
- low success probability
- long horizon patch generation
- verifier imperfection if relying only on tests

Preferred supervision:
- student frontier collection
- localization / repair / validation decomposition
- repaired suffixes from strong teacher for hard prefixes
- pairwise ranking between candidate patches
- conservative use of environment ground truth with additional ranking signals

---

## 10. Teacher Policy by Teacher Type

## 10.1 White-Box Teacher
Use white-box teacher for dense local supervision.

Primary uses:
- logit or top-k annotation
- local action ranking
- selected-span KD
- repaired suffix generation
- confidence / disagreement scoring

White-box teacher should be the default dense teacher where available.

## 10.2 Black-Box Teacher
Use black-box teacher for sparse but high-value supervision.

Primary uses:
- critique
- reranking
- repaired suffix generation
- pairwise preference judgment
- hard-case proposal generation

Black-box teacher should not be the main source of bulk static demonstrations unless there is no better signal.

## 10.3 Search / Specialized Teacher
For GAME and any similar structured environment, specialized teacher should outrank LLM teacher.

Primary uses:
- action policy targets
- value targets
- search-improved branch selection
- self-play expert data

---

## 11. ms-swift Mapping

The algorithm should map into existing `ms-swift` training modes instead of inventing a new trainer first.

### 11.1 SFT stage
Use for:
- curated cold start
- positive verified trajectories
- repaired trajectories
- selected high-confidence teacher-labeled examples

### 11.2 GKD stage
Use for:
- white-box teacher supervision on student-distribution data
- distillation on frontier states
- dense local behavior transfer

This should be the preferred distillation stage when white-box teacher exists.

### 11.3 DPO / ORPO / KTO stage
Use for:
- success vs failure
- repaired vs original
- higher-score vs lower-score
- teacher-ranked candidate pairs

Preference optimization is the preferred way to use negative trajectories without moving fully into sparse RL.

### 11.4 GRPO stage
Use only where environment reward is cheap, deterministic, and already well-shaped.

GRPO is optional.
It should not be the first implementation target unless a specific environment clearly benefits.

### 11.5 Multi-Stage Preference
The expected default training pattern is:

1. small cold-start SFT
2. iterative frontier collection
3. compiled positive / repaired / KD training
4. preference optimization
5. optional limited RL-style polishing

The method should remain mostly a data-compilation + staged-`ms-swift` system.

---

## 12. Repository Integration Direction

Implementation should respect branch boundaries.

## 12.1 Control Plane Responsibilities
The control plane should orchestrate:
- experiment records
- launch config interpretation
- iterative outer-loop stages
- run submission and artifact collection
- mapping between experiment id and generated datasets / model revisions

The control plane should not implement environment-specific teacher logic directly.

## 12.2 Execution Plane Responsibilities
The execution plane should remain generic.

No environment-specific logic should be added to:
- placement backends
- launch mode logic
- generic worker runtime

At most, execution may gain neutral support for:
- artifact metadata
- richer manifests
- run provenance logging

## 12.3 Task Plugin Responsibilities
The main algorithm logic should live here or above here.

Expected plugin-level or plugin-adjacent responsibilities:
- frontier rollout request parsing
- bundle building for collection / relabel jobs
- training bundle generation using compiled datasets
- result summary extraction
- typed task specs for rollout / relabel / compile / train stages

## 12.4 Sidecar Responsibilities
Sidecars may assist with:
- Targon operations
- monitoring
- domain-specific helper utilities
- environment adapters that are not part of the generic kernel

But they should not become the hidden implementation of the algorithm core.

---

## 13. Preferred Internal Decomposition

Codex should treat the algorithm as four major subsystems.

### 13.1 Frontier Collection Subsystem
Responsible for:
- student rollout
- branch sampling
- trace capture
- provenance and revision tagging

### 13.2 Relabel / Verifier Subsystem
Responsible for:
- replay or partial replay
- process scoring
- first-error approximation
- candidate ranking
- environment-derived labels

### 13.3 Teacher Augmentation Subsystem
Responsible for:
- white-box local annotation
- black-box critique / repair
- teacher routing per environment
- disagreement mining

### 13.4 Dataset Compiler Subsystem
Responsible for:
- building `ms-swift`-consumable views
- splitting into SFT / KD / preference / optional RL views
- data versioning and reproducibility
- environment balancing rules

The trainer should consume compiler outputs, not raw frontier traces.

---

## 14. Expected Data Products

The system should produce reproducible versioned artifacts.

Minimum conceptual outputs:
- raw rollout traces
- verifier-relabeled traces
- teacher-augmented traces
- compiled positive SFT dataset
- compiled repaired SFT dataset
- compiled KD/GKD dataset
- compiled preference dataset
- experiment summary and metrics report

Each artifact should preserve:
- model revision
- environment
- task id
- seed
- teacher metadata
- verifier metadata
- compilation recipe version

---

## 15. Metrics and Success Criteria

Success should be evaluated on both task performance and capability preservation.

### 15.1 Primary metrics
- AffineTes environment score improvements
- success rate by environment
- verifier-confirmed positive-sample yield
- data efficiency relative to pure RFT baseline
- repair yield on hard environments
- teacher usage efficiency

### 15.2 Secondary metrics
- frontier expansion over training iterations
- fraction of student-prefix trajectories that become trainable
- ratio of positive / repaired / preference samples
- cost per verified positive trajectory

### 15.3 Capability-retention metrics
- holdout generic benchmarks
- task-external reasoning / coding checks
- regression guardrail suite across previously strong capabilities

The project should treat capability retention as a first-class acceptance criterion.

---

## 16. Hard Constraints for Implementation

Codex should preserve the following constraints.

1. Do not collapse the three-layer architecture.
2. Do not put task-specific logic into generic execution backends.
3. Do not replace `ms-swift` with a custom training framework in the first implementation.
4. Do not make the algorithm depend on fully teacher-generated static corpora.
5. Do not reduce environment ground truth to only final pass/fail filtering.
6. Do not define success using only one environment.
7. Do not assume GAME, LIVEWEB, QQR, MEMORYGYM, and SWE should share the same teacher policy.
8. Do not require strict full-trajectory on-policy purity.

---

## 17. Recommended First-Class Deliverables

A successful implementation direction should eventually include, at minimum:

- one or more new high-level config-driven workflows under the current control-plane model
- typed specs for rollout / relabel / compile stages
- dataset compiler outputs that map to current `ms-swift` modes
- an official example config for VG-SOPD-style training
- environment-specific teacher-routing policy
- reproducible experiment reports

---

## 18. Final Design Position

The target method for this branch should be understood as:

> a verifier-grounded, semi-on-policy, distillation-first training loop that uses student-generated frontier states, environment-derived dense relabeling, selective teacher augmentation, and staged `ms-swift` training views.

This is the intended replacement for:
- pure RFT as the main scaling strategy
- pure sparse-reward RL as the main optimization strategy
- pure offline teacher imitation as the main transfer strategy

The correct implementation style in this repository is:
- architecture-respecting
- plugin-oriented
- config-driven
- reproducible
- multi-stage
- environment-aware
- teacher-type-aware

---

## 19. Implementation Instruction to Codex

Use this document as the algorithmic source of truth.

When details are ambiguous:
- keep the execution plane generic
- push task semantics into task plugins and dataset compilation
- prefer extending current `ms-swift` integration over replacing it
- preserve the current config-driven control-plane workflow
- choose the simplest design that preserves verifier grounding and semi-on-policy behavior
