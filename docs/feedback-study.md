# Feedback study

From v0.2 the leaderboard ranks by c@3: the score within three attempts, each retry shown what the
environment reported about the one before ([c@k](methodology.md#ck-attempts-with-the-environments-feedback-v02)).
A third attempt is also a third chance, so a better score within three attempts could come from
trying again rather than from the feedback. This study separates the two: on tasks each model had
already failed, three attempts with feedback against three independent answers without it.

It ran in October 2026 on four local models, before c@k was built into the harness, and shaped
how c@k works. Its runs are not published; this page has the aggregates.

## Design

- **Pools.** Per model, the tasks it had failed in its earlier full run(s) of the same
  configuration, from the suites graded by running the answer in an org: Apex, Flow, Permissions &
  access, Governor limits & pushback, fflib Enterprise Patterns, Nonprofit Success Pack, Trigger
  Actions Framework and SOQL. Multiple-choice and short-answer tasks were left out (a failed choice
  has nothing to feed back), and so was LWC, which is graded offline.
- **Answer chains.** Three per task. Round 0 is three independent first answers, sampled at
  temperature 1.0 (on TensorFold, which seeds every request alike, each with its own seed). Each answer that failed got a second attempt, and a third if that failed too, in the same
  conversation, shown the environment's output: deploy and compile errors, failing tests' names and
  messages, query errors. Hidden tests' source was never shown.
- **Control.** The three round-0 answers alone. Their pass@k (the unbiased estimator) is the chance
  that at least one of k fresh answers passes: as many answers as k attempts, without the feedback.
  Self-repair studies make the same comparison (Olausson et al., *Is Self-Repair a Silver Bullet
  for Code Generation?*, 2024).
- **Scores.** Per task, the share of its three chains solved within k attempts; the score is the
  mean over the pool's tasks. Intervals are 95% bootstrap intervals over tasks; the difference is
  paired by task.

| Model | Quantisation · engine | Effort | Pool (tasks) |
|---|---|---|---|
| Qwen3.8 27B | AWQ-INT4 · vLLM | medium | 89 |
| Gemma 4 26B-A4B | NVFP4 · vLLM | thinking on | 82 |
| Gemma 4 31B | QAT W4A16 · vLLM | thinking on | 83 |
| GLM-5.3 Flash | EXL3 4.0bpw experts, 4-bit dense · TensorFold | high | 57 |

## Results

Within three attempts, feedback solved clearly more than three fresh answers for every model: from
about a third more (Gemma 4 26B-A4B) to about twice as many (Gemma 4 31B, GLM-5.3 Flash).

| Model | 1 attempt | 2 attempts with feedback | pass@2, fresh | 3 attempts with feedback | pass@3, fresh | Difference at 3 (95% CI) |
|---|---|---|---|---|---|---|
| Qwen3.8 27B | 4.5% | 16.1% | 8.6% | 22.5% | 12.4% | +10.1 pts (+3.0 to +17.2) |
| Gemma 4 26B-A4B | 10.6% | 22.0% | 16.7% | 27.6% | 20.7% | +6.9 pts (+0.4 to +13.8) |
| Gemma 4 31B | 10.8% | 24.1% | 14.5% | 31.3% | 15.7% | +15.7 pts (+9.2 to +22.9) |
| GLM-5.3 Flash | 9.4% | 29.2% | 15.8% | 36.8% | 19.3% | +17.5 pts (+8.8 to +26.9) |

The second attempt already does most of the work: at two attempts the difference is +7.5, +5.3,
+9.6 and +13.5 points, each clearly above zero. With one attempt the two arms are the same answers,
so they score the same by construction.

### By suite

Answer chains solved at the first attempt, then within three attempts, out of the pool's chains:

| Suite | Qwen3.8 27B | Gemma 4 26B-A4B | Gemma 4 31B | GLM-5.3 Flash |
|---|---|---|---|---|
| Apex | 4 → 20 of 48 | 4 → 15 of 30 | 6 → 24 of 39 | 1 → 12 of 21 |
| fflib Enterprise Patterns | 1 → 5 of 54 | 3 → 5 of 54 | 0 → 7 of 51 | 3 → 11 of 45 |
| Flow | 0 → 0 of 42 | 0 → 0 of 42 | 0 → 1 of 42 | 0 → 4 of 42 |
| Governor limits & pushback | 1 → 8 of 21 | 6 → 14 of 15 | 7 → 9 of 9 | 1 → 3 of 6 |
| Nonprofit Success Pack | 1 → 2 of 18 | 3 → 9 of 21 | 1 → 4 of 18 | 0 → 4 of 12 |
| Permissions & access | 2 → 10 of 27 | 2 → 6 of 27 | 2 → 8 of 27 | 4 → 12 of 15 |
| SOQL | 2 → 7 of 21 | 7 → 15 of 18 | 8 → 13 of 21 | 2 → 5 of 6 |
| Trigger Actions Framework | 1 → 8 of 36 | 1 → 4 of 39 | 3 → 12 of 42 | 5 → 12 of 24 |

Apex, SOQL, permissions and governor limits gain most: their errors tend to name the problem (a compile
error, a failing assertion, a governor limit). Flow barely moves. The models invent Flow metadata
elements, and the org's deploy reports one parse error at a time, so a retry can fix one invented
element only to hit the next. fflib and NPSP move little, except GLM-5.3 Flash on fflib.

## Limits

- **Hard pools by design.** Each pool is the model's own earlier failures, so first attempts pass
  rarely (4.5% to 10.8%). The study measures recovering from a failure, not overall skill. The fresh
  round 0 is the baseline, so regression to the mean shows up in both arms equally.
- **Four local models, one configuration each,** on the v0.1.0 tasks, one run of each. Pools of 57
  to 89 tasks give wide intervals: Gemma 4 26B-A4B's gain is clear, but its interval starts at
  +0.4 points.
- **One rule differs from c@k.** Here, a failure found only by checks against the expected answer
  was retried, shown "does not meet all of the task's requirements" (13, 19, 36 and 5 of the
  failures fed back, in the order of the tables). c@k never retries those: it would be a guess, not
  a fix.
- **These are not leaderboard numbers.** c@3 on the leaderboard retries the published run's failed
  answers, one answer per task, on every suite whose grader reports tool output.
