# Othello Convergence Diagnostics

This note records the current understanding of the Othello 8x8 convergence problem in the PyTorch/OpenSpiel MuZero stack.

The intent is to preserve the evidence trail before changing teacher quality, target semantics, or search/eval budgets again.

## Scope

This document is about the Othello-specific failure mode only.

It is separate from the Hex/Clobber replay-starvation issue:

- Hex/Clobber were blocked by terminal-only online replay emission.
- Othello is not blocked by replay starvation.

## Current Symptom

Othello online training can run for a long time with:

- large replay occupancy
- many completed self-play games
- stable learner steps

but quick evaluation still remains near zero.

Observed examples from the current diagnostic pass:

- warm-start quick eval: `2 / 200 = 1.0%`
- online quick eval: `0 / 200 = 0.0%`

## What We Already Ruled Out

### 1. This is not primarily a replay-starvation problem

Diagnostic evidence from the online run showed:

- replay rows filling to capacity
- many completed self-play games
- actor heartbeats with healthy active slot counts

This is the opposite of the Hex/Clobber failure mode.

### 2. This is not currently best explained by model capacity

We already ran a fixed-subset overfit comparison:

- current Othello-sized model: loss decreased from about `3.21` to `2.46`
- enlarged model with `repr_blocks=20`: loss worsened from about `3.21` to `4.41`

That does not prove the current model is optimal, but it is strong evidence that simply making the residual trunk much deeper is not the right next move.

### 3. This is not explained by the `replay_ratio` bug

The old online path had a real bug where configured `train.replay_ratio` was ignored and the learner silently used a hardcoded `50/50` live/expert split.

That bug has now been fixed.

Remote progress files after the fix show the configured split is active:

- Othello `batch_size=2048`
- `live_batch_size=1229`
- `expert_batch_size=819`

So the current Othello failure persists even after the online replay mix was corrected.

## Most Relevant Evidence

## Teacher-quality audit

We compared the current rollout teacher against a stronger label setting on a small sampled Othello corpus.

Sampled results:

- `states_evaluated = 32`
- `current_policy_entropy_mean = 1.3219`
- `strong_policy_entropy_mean = 1.2452`
- `chosen_action_agreement = 0.71875`
- `current_value_mean = 0.1432`
- `strong_value_mean = 0.1693`

Interpretation:

- the stronger teacher is somewhat sharper
- the stronger teacher does not completely disagree with the current teacher
- the difference is meaningful, but not dramatic enough by itself to explain a total collapse to `0%`

## Warm-start expert-target audit

The current expert shard distribution is not obviously degenerate.

Observed summary:

- `rows_total = 1227`
- `policy_entropy_mean = 1.4376`
- `value_target_mean = 0.0672`
- `reward_target_mean = 0.0155`

Interpretation:

- policy targets are not near-uniform noise
- rewards are sparse, which is expected
- value targets are low-magnitude on average, which is plausible for balanced board states, but still worth monitoring

## Budget mismatch audit

The current Othello budget stack is materially asymmetric:

- online self-play search: `64` simulations
- teacher labeling: `64` simulations, `8` rollouts
- quick eval agent: `64` simulations
- quick eval baseline: `128` simulations, `8` rollouts
- official eval baseline: `1000` simulations, `20` rollouts

Interpretation:

- the quick eval opponent is already stronger than the self-play and teacher budget
- the official eval opponent is much stronger than both
- if training targets are only moderately informative, this mismatch can easily suppress measured win rate

This does not prove the budgets are the root cause, but it makes the current quick/official win-rate targets much harder to reach.

## Most Likely Failure Mode

The current best explanation is:

1. Othello online replay is healthy enough to train.
2. The model can fit at least part of the teacher distribution.
3. The online policy/value targets are still not strong enough to produce a competitive searched agent against the current evaluation baseline.

The most plausible sub-causes are:

- teacher quality is too weak relative to the eval baseline
- online self-play targets are too noisy or low-signal
- train/search/eval budgets are misaligned
- search quality is insufficient for Othello even when throughput is healthy

## What To Investigate Next

Recommended next experiments, in order:

1. Increase Othello teacher/search quality before changing model size.
   Compare current teacher labels against a meaningfully stronger label budget and measure whether expert-target entropy and action agreement change materially.

2. Audit online target quality directly from emitted replay rows.
   Measure:
   - policy entropy
   - value variance
   - chosen-action concentration
   - consistency between self-play root value and later realized outcomes on sampled games

3. Align the Othello quick-eval budget with the training/search budget for one controlled experiment.
   This is not the final benchmark, but it can separate "agent is weak" from "evaluation baseline is too far ahead of the training signal".

4. Only revisit model capacity after the above are understood.
   The current evidence does not support deepening the residual stack as the next move.

## Current Recommendation

Do not scale Othello model depth yet.

Treat Othello as a teacher/target/search-quality problem first, not a capacity problem.
