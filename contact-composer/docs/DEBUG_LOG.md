# Module implementation and debugging log

Executed on 2026-10-26. Requirements and design targets are not substituted for test results.

## Environment and final checks

- Windows host, Python 3.12.7, Node 24.14.1, npm 11.11.0.
- Dedicated `.venv`; a second, empty `.venv-smoke` was created, installed from `requirements.lock`, and given an editable package installation. The installed CLI was executed in that environment.
- Backend: **43 passed** in the fresh environment (`python -m pytest -q --basetemp runs/pytest-clean`, 22.66 s on this run).
- Frontend: **4 passed** (`npm test`); TypeScript and Vite production build passed (`npm run build`).
- Ruff import/undefined/unused checks and formatting passed; Prettier formatting applied to frontend source; Git whitespace checks passed.
- One dependency warning remains: Starlette's TestClient imports a deprecated AnyIO BlockingPortal alias. It did not fail tests.
- The optional external dev-workflow skill was not installed or applied, by user choice.

## Independent module debugging

Each Python test file was run independently or with only its directly changed dependencies during implementation. The final suite integrates them.

| Module | Independent evidence | Result |
| --- | --- | --- |
| M01 Project | `tests/test_m01_project.py` (13 cases); frontend history tests | Round-trip, atomic save, schema/size bounds, nonfinite input, bad IDs, overlap, anchor jumps, 50+ undo/redo transactions pass. |
| M02 Model | `tests/test_m02_model.py` (4); frontend MuJoCo fixture comparison (1) | DOF/actuator map, anchor positions, finite-difference Jacobians, potential-energy gravity gradient, collision fixture and three browser FK/CoM poses pass. |
| M03 Timeline | Frontend editor tests (3) and actual browser interactions | Tick moves/resizes, overlap rejection, history, create/copy/delete, numeric edit, drag, anchor move and stale-result labels verified. |
| M04 Schedule | `tests/test_m04_schedule.py` (4) | Half-open events, terminal support, continuity, adjacent identical anchors and foot clearance pass. |
| M05 Planner | `tests/test_m05_planning.py` (6) | Static equilibrium, inactive zeros, insufficient support/cap, unreachable anchors, timeout/cancel and necessary wall support at fixed peak pose pass. |
| M06 Trajectory | `tests/test_m06_trajectory.py` (4) | Dense complete coverage, force/pose tampering, forged derivatives, NaN, missing times and cancellation pass. Full demo includes 1,200 extra midpoint geometry checks. |
| M07 Replay | `tests/test_m07_simulation.py` (5) | Torque-driven stand, force signs, stale/unvalidated rejection, cancellation, deliberately unstable PD failure and complete wall/lift/return replay pass. |
| M08 Diagnostics | `tests/test_m08_diagnostics.py` (2); browser evidence plots | Adjacent evidence aggregation, source isolation and scoped timeout language pass. Browser shows separate planned/measured plots and replay metrics. |
| M09 Service | `tests/test_m09_service.py` (3) | Real spawned process solve/replay, ZIP response, stale hash rejection, concurrent-job rejection, cancellation, origin/body-size checks pass. |
| M10 Export | `tests/test_m10_export.py` (2); installed CLI solve/replay | Array/project round-trip, checksum corruption, no overwrite, CLI invalid input and complete result bundles pass. |

## Problems found and resolved

1. **Penetration distance:** some intersecting convex pairs returned zero from `mj_geomDistance`. Signed distances from generated MuJoCo contacts now supplement distance queries. An obstacle penetration regression exercises this.
2. **Sampled PD instability:** gains 180/12 at a 10 ms controller interval saturated the small limb actuators and fell. A gain sweep found stable standing gains; 60/1 remains the optional PD default. The unstable configuration remains a failure regression, not a relaxed acceptance threshold.
3. **Floating-base drift:** joint PD tracked joints but the full wall-assisted sequence drifted by about 31 cm. A constrained whole-body inverse-dynamics controller now regulates base and contact tasks using only the eight actuator torques. The same original replay thresholds pass.
4. **Imported-result trust:** passed labels alone were insufficient. Complete time/shape/finite checks, derivative consistency, FK endpoints, masks and independent physical checks now validate arrays before replay.
5. **Invalid numeric UI edits:** rejected interval edits left an uncommitted number in the inspector. Fields now reset to the committed value while showing the rejection reason.
6. **Anchor selection:** a click without movement originally incremented the revision. The final build applies an anchor edit only when its value changes; a browser check confirmed selection leaves revision zero unchanged.
7. **Windows sandbox test hang:** the API TestClient initially blocked in Python's local `socketpair` before issuing an API request. Running local socket/process tests with permission resolved it; all three API tests passed.

## Full demo result

The installed CLI generated and exported `examples/wall-assisted.json`, then loaded that bundle for independent replay. Compact raw evidence is committed in [DEMO_REPORT.json](DEMO_REPORT.json). Full arrays and contact-pair records are reproduced with the README commands.

| Quantity | Measured | Limit |
| --- | ---: | ---: |
| Duration / samples | 12 s / 1,201 | Complete coverage |
| Joint RMS | 0.016788 rad (0.962 degrees) | 2 degrees |
| Maximum base-position error | 0.004291 m | 0.03 m |
| Maximum pitch error | 0.008637 rad | 0.087266 rad |
| Loaded-contact drift | 0.010741 m | 0.02 m |
| Maximum loaded-support loss | 0.03 s | 0.10 s |
| Penetration | 0.000234 m | 0.005 m |
| Unexpected loaded contact | 0 s | 0.10 s |
| Saturation fraction | 0 | 0.05 |
| Joint-limit excess | 0 rad | 0.01 rad |

The default demonstration passed both planning checks and dynamics replay. Necessary-support and zero-ground-friction comparisons are established at the same fixed peak pose, not claimed for all possible postures. Planning time for the exported CLI run was 4.719 s on this host; this is one observation, not a p95 performance benchmark.

## Browser verification and limits

An actual browser against the local production build verified: rendering; generate then replay; separate status badges; reference/measured plots; select/edit/undo; move a hand block by 0.50 s; resize its end only; drag a wall anchor; add/duplicate/delete a contact; reject a right-foot overlap without changing its stored interval; invalidate old results after edits. The completed demo showed the same replay metrics as the CLI.

The browser automation download-event wait timed out and did not return a downloaded path. Consequently the browser Save/Open file-dialog round-trip is **not claimed as verified**. Schema/file round-trip, the installed CLI, exported NPZ/JSON/model bundles, and HTTP ZIP content are covered by successful automated checks. Browser automation also encountered a transient approval timeout when reopening localhost; the permitted retry succeeded.

The current evidence covers Windows CPU execution. Linux, other Python/Node versions, p95 UI timing, hardware use, continuous-time safety, and arbitrary robot import are not validated. Geometric midpoint sampling and simulation do not establish a physical-robot guarantee. The implementation is a first planar software release with those explicit limits.
