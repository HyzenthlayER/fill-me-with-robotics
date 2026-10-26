# Contact Composer — Product Requirements

Version: 0.1 | Date: 2026-10-26 | Status: implemented first release; executed evidence in [DEBUG_LOG.md](DEBUG_LOG.md)

This document records the product requirements. Its scope and technology choices apply only to Contact Composer. [MODULES.md](MODULES.md) describes the actual implementation, including bounded sampling, polling progress, and tested platform limits.

## 1. Product definition

Contact Composer lets a user author a slow robot motion by editing when each hand or foot touches a surface and where that contact occurs. A solver proposes poses, support forces, and a trajectory. The user can inspect constraint violations and run a separate dynamics replay.

The primary interaction is a four-track contact timeline synchronized with a robot scene. The user edits contact intent rather than individual joint angles at every frame.

### Users and jobs

| User | Job |
| --- | --- |
| Robotics learner | Understand how changing support contacts changes possible poses and loads. |
| Researcher or developer | Prototype a contact sequence and export an inspectable reference trajectory. |
| Contributor | Add a small scenario, solver improvement, or regression case with reproducible evidence. |

### Intended first demonstration

1. Start with both feet on the floor.
2. Move the right hand to a wall and establish support.
3. Transfer load and lift the right foot.
4. Return the right foot to the floor and transfer load back.
5. Release the hand and return to a standing pose.

A paired case removes hand support while retaining a torso/center-of-mass target that requires it under the chosen model. The comparison must actually be established by computation. Removing a hand contact is not inherently infeasible if the robot can change posture.

The complete demonstration has passed independent torque-driven replay. The paired necessary-support comparison is established at its fixed peak pose; posture-search outcomes remain separate.

## 2. Scope and priorities

### P0: complete first release

- One original planar robot, one floor, one wall, and a small set of rectangular obstacles.
- Four contact tracks: left foot, right foot, left hand, right hand.
- Create, move, resize, duplicate, and remove contact blocks; edit anchors and targets.
- Undo/redo, project save/load, timeline scrubbing, and playback.
- Fixed user-authored contact sequence; approach, load transfer, swing, and release handling.
- Joint limits, nonpenetration, planar friction, unilateral contacts, and actuator torque limits.
- Sampled quasi-static trajectory generation with explicit solve status and residuals.
- Separate simulation replay with a controller and measured contact data.
- Time-local diagnostics, reference/measured comparison, and export.
- CPU-only local execution; headless core and example checks.

### P1: after the first release

- Scenario comparison, additional robot presets, improved warm starts, more diagnostic suggestions.
- GIF/video export, reusable motion snippets, and optional automatic retiming.
- Explicit sliding-contact mode and wider contact-model coverage.

### P2: later investigations

- Three-dimensional humanoids, finite-area feet, full contact wrenches, and arbitrary robot imports.
- Dynamic motion optimization, jumps, contact-order search, moving objects, and manipulation.
- External motion-library or training-pipeline adapters.

The first release does not include hardware control, RL training, text-to-motion, automatic contact-order planning, arbitrary URDF support, grasping, adhesion, or flight phases.

## 3. Interaction and screens

### Main workspace

| Region | Contents and actions |
| --- | --- |
| Top bar | New/open/save/export, example selection, undo/redo, project dirty indicator. |
| Scene | Robot, surfaces, contact anchors, center of mass, optional force arrows, reference/measured overlay. |
| Timeline | Four labeled tracks, contact blocks, event markers, current time, issue markers, zoom and scroll. |
| Inspector | Selected contact/surface/target properties with units and input validation. |
| Bottom panel | Generate, cancel, preview, simulate, stop, progress, validation status, diagnostics and plots. |

Color must be supplemented with text or icons. Selecting an issue jumps to its time and highlights the affected contact or joint. Playback does not modify the project.

### Core workflow

Load example → edit blocks and anchors → validate inputs → generate candidate → inspect preview and issues → simulate → compare planned/measured behavior → save/export.

Editing invalidates results for the previous project revision. An old result may remain visible only with an explicit stale label. Simulation never silently starts after an edit or generation.

## 4. Functional requirements

| ID | Priority | Requirement | Acceptance evidence |
| --- | --- | --- | --- |
| R01 | P0 | Create, load, save, and round-trip a versioned project with units, robot identity, scene, schedule, targets, and settings. | A01 |
| R02 | P0 | Render the built-in planar robot and editable supported scene primitives; drag anchors along their selected surface. | A02 |
| R03 | P0 | Provide four editable timeline tracks, tick snapping, keyboard deletion, numeric editing, and at least 50 undoable edits. | A02, A03 |
| R04 | P0 | Validate IDs, types, ranges, contact intervals, surface coordinates, initial state, and unsupported modes before solving. | A03 |
| R05 | P0 | Compile contacts into phases, approach/swing tasks, and load-transfer envelopes without silently changing intent. | A04 |
| R06 | P0 | Solve contact poses and static force/torque balance subject to declared model constraints. | A05, A06 |
| R07 | P0 | Construct a continuous candidate trajectory and validate it at dense samples and event boundaries. | A07 |
| R08 | P0 | Explain failures with location, measured residual, threshold, solver status, and a bounded interpretation. | A06, A08 |
| R09 | P0 | Scrub and play a clearly labeled kinematic preview, including partial/failed candidates. | A02, A07 |
| R10 | P0 | Run a separately requested forward-dynamics replay with logged controller and engine settings. | A09 |
| R11 | P0 | Display planned and measured contacts, tracking error, torque saturation, and contact drift separately. | A09, A10 |
| R12 | P0 | Export the project, trajectory, diagnostics, replay results when available, and provenance. | A01, A10 |
| R13 | P0 | Run long operations asynchronously, allow cancellation, and prevent stale jobs from replacing current results. | A11 |
| R14 | P0 | Ship original examples, setup instructions, headless checks, license notices, and honest validation limits. | A12 |

## 5. Robot and physics contract

### Robot

The first model is approximately human-shaped but intentionally simple: one torso, two two-link arms, and two two-link legs. Configuration has 11 coordinates: unactuated base x, base z, base pitch, and eight actuated revolute joints. All motion is in the x–z plane; rotation axes are y. State and joint order are explicit in the model manifest.

Masses, inertias, link geometry, endpoint radii, joint limits, and torque limits must be finite and physically consistent. The model uses original primitive geometry, avoiding third-party mesh dependencies. Planar constraints are part of the model and are disclosed in replay results.

Feet and hands use point-force contact abstractions. They transmit planar forces, not contact moments. This is not a finite-area human-foot model. Collision checks include robot–environment pairs and a published set of self-collision pairs; adjacent and intentionally overlapping planar limb pairs are excluded explicitly.

### Surfaces and contacts

- World coordinates use meters, seconds, radians, kilograms, newtons, and newton-meters.
- A surface is a directed line segment with an explicit tangent and a unit outward normal toward free space.
- An anchor is a point on that surface. The endpoint-center target includes the declared endpoint radius along the normal.
- Each contact block has one effector, surface, fixed anchor, start tick, and end tick.
- Each effector can have at most one active block at a time. Changing an anchor requires a release/transfer interval; discontinuous anchor jumps are invalid.
- Active contacts are sticking contacts. Inactive effectors have zero planned contact force.
- Contact force is `f = tangent * f_t + normal * f_n`, with `f_n >= 0`, `abs(f_t) <= mu * f_n`, and a configured force cap. No pulling or adhesion is allowed.
- Scheduled contact indicates an allowed sticking support; actual load may be zero during acquisition or release. The UI distinguishes scheduled, planned-loaded, and measured-loaded contacts.

### Equilibrium and solve meaning

At a fixed candidate pose, static balance uses:

`G(q) = S^T tau + sum(J_i(q)^T f_i)`

`G` is gravity compensation, `S` selects the eight actuated joints, and each `J_i` maps generalized velocity to the contact-point planar velocity. Floating-base equilibrium is included. Joint torques are bounded.

Joint optimization over pose, collision geometry, and forces is nonlinear. A convex force-allocation QP at one fixed pose does not establish feasibility of the whole motion. A nonlinear solver timeout or failed convergence must be reported as unresolved, not as proof that no motion exists.

A floor support interval may be shown for floor-only intuition. With hand/wall contacts, acceptance depends on full force and moment balance, friction, and torque limits; center-of-mass projection alone is insufficient.

## 6. Time, transitions, and trajectory

- Authoring grid: 50 ms integer ticks; duration 2–20 s; at most 400 intervals and 100 contact blocks.
- Contact intervals are half-open `[start_tick, end_tick)`. The final displayed state is the left-hand limit at the project endpoint. Initial contacts describe the initial settled support state.
- Blocks last at least four ticks. New contacts ramp their force cap up; released contacts ramp it down, initially over two ticks. Initial supports do not all ramp from zero at time zero; supports ending with the project are held through the final state.
- Compile phases from all contact and target events. Validate both sides of each event. Contact transitions must preserve pose continuity and arrive/depart with zero endpoint velocity in the initial implementation.
- A contact becoming active first requires an approach trajectory. A release unloads before lift-off. Noncontact motion must respect obstacle clearance and joint-rate limits.
- The planner may propose additional time or a changed target, but applying that edit is an explicit user action.
- Construct candidates directly at 100 Hz with event alignment. Validate those samples independently and add geometry midpoint checks near small clearances or rapid changes. Record actual sampling and gaps; no continuous-time guarantee is claimed.
- Interpolation must preserve active-contact constraints through constrained refinement/projection and revalidation. Interpolated joint angles alone do not guarantee contact consistency.
- Dense sampled validation is not a continuous-time mathematical guarantee.

## 7. Preview, replay, and status

### Evidence levels

| Level | Meaning |
| --- | --- |
| Input valid | The authored project satisfies schema and supported-mode rules. |
| Kinematic candidate | A displayed pose/trajectory exists; it may violate physical constraints. |
| Quasi-static checks passed | The required sampled kinematic, collision, force-balance, friction, torque, and rate checks passed under the declared model. |
| Simulation replay passed | A particular controller and engine run passed the recorded replay checks. |

These are separate fields, not a single green “safe” badge. Solver status includes success, partial, invalid input, no solution found, timeout, numerical error, and cancelled. A fixed-pose QP may additionally report infeasibility for that exact pose and constraint set.

### Replay behavior

Use MuJoCo forward dynamics with the planar model. Initialize state once, then step the simulator with bounded feedforward-plus-feedback joint torques. Do not overwrite the base pose or all joint positions at each step, weld scheduled contacts, or add hidden support forces. Any settling period must be logged and checked; it must not silently replace the intended initial state with a materially different one.

Initial target settings are a 2 ms physics step and a 10 ms controller interval. These are configurable and stored in provenance. Playback speed changes viewing only; changing simulation timing requires a new run.

Measured contact forces come from the simulator and are mapped to the common world/contact convention. Planned and measured forces remain separate. Record unexpected contacts, slip, contact loss, joint/torque violations, tracking errors, and nonfinite states. MuJoCo's soft contact model can differ from the planner's idealized sticking constraints.

## 8. Numerical acceptance targets

The following are proposed gates for the approximately one-meter built-in model. They are not measured performance. Freeze the actual model and thresholds before accepting the demonstration. Any later change must be recorded and rerun.

| Check | Initial target |
| --- | --- |
| Active endpoint position error | At most 1 mm at validation samples. |
| Joint-limit excess | At most 1e-5 rad. |
| Static generalized-force residual | At most 1e-4 after scaling force rows by `m*g` and moment rows by `m*g*L`; `L` is the manifest characteristic length. |
| Friction/unilateral/cap violation | At most 1e-4 of `m*g`; apply absolute checks as well when displaying near-zero contacts. |
| Torque-limit excess | At most 1e-4 of each strictly positive actuator torque scale. |
| Geometric penetration in candidate | At most 1 mm numerical allowance for checked pairs. |
| Quasi-static rate screen | Model-declared joint/base rates; inertial generalized forces no more than 5% of the same gravity scales. This is a screening rule, not a stability proof. |
| Replay tracking | Joint RMS error <= 2 degrees, maximum base-position error <= 3 cm, maximum base-pitch error <= 5 degrees. |
| Replay support | Loaded-contact drift <= 2 cm; no loaded-support loss longer than 100 ms. “Loaded” means planned normal force > 0.02*m*g; measured contact presence threshold is 0.01*m*g. |
| Replay penetration | <= 5 mm for checked pairs; unexpected sustained load-bearing contacts fail the demo. |

Replay must also satisfy finite-state, physical limit, and controller-saturation checks with explicit model-specific thresholds. Do not combine these into an unexplained weighted score.

## 9. Acceptance scenarios

| ID | Scenario and expected outcome |
| --- | --- |
| A01 | Save/load preserves all meaningful settings; export ties files to the same project/model hashes and can be inspected without the UI. |
| A02 | Create and edit a contact, move its anchor, scrub to it, inspect its values, undo/redo, and restore the same state. |
| A03 | Reject overlapping contacts on one effector, out-of-range anchors, unknown IDs, nonfinite numbers, invalid times, and unsupported contact modes with field-local messages. |
| A04 | Verify phase boundaries, initial/final support semantics, approach/release ordering, load ramps, and exact event sampling. |
| A05 | An analytic simple-support fixture matches known force/moment balance; normal signs, torque limits, and inactive-contact zero forces are checked. |
| A06 | At a fixed pose, removing necessary wall support violates balance; allowing posture changes is a separate solve. Unreachable anchors and friction-limited cases produce bounded diagnoses. |
| A07 | Endpoints look valid but interpolation crosses an obstacle or breaks contact: dense validation must reject it. Event continuity and rate/acceleration checks are included. |
| A08 | Solver timeout and numerical failure are distinguishable from invalid input and fixed-pose QP infeasibility. |
| A09 | The complete floor/wall/lift/return demo passes torque-driven replay; a deliberately degraded controller fails replay while leaving the planning result unchanged. |
| A10 | Export and plots distinguish reference from measured state/forces, include thresholds, and retain failed-run evidence. |
| A11 | Editing during a solve marks the result stale; a cancelled or old job cannot overwrite the latest project result. |
| A12 | A clean documented install runs the examples and headless checks without a GPU, account, external dataset, or robot hardware. |

## 10. Nonfunctional requirements

- Local single-user application; localhost service; no account, cloud service, or automatic network data upload.
- Target Windows 11 and Ubuntu 22.04/24.04 with 8 GB RAM and a mainstream CPU. Actual tested platforms and package versions must be recorded at implementation time.
- UI interaction target: p95 edit response under 100 ms, excluding solving. Pose-preview target: under 500 ms. A 10 s reference scenario has a proposed 30 s generation budget with cancellation and partial diagnostics. Report actual hardware and distributions; do not advertise these targets as achieved.
- Repeat runs use pinned dependencies, model/settings hashes, seeds where relevant, and tolerance-based numerical comparison. No cross-platform bitwise-determinism claim.
- Imported projects are structured data, never executable expressions. Bound size/count/depth and reject unsupported schema versions. Arbitrary model files, plugins, and archive extraction are outside P0.
- Store no credentials. Hardware operation is outside this component.

## 11. Delivery sequence

1. **Physics spike:** original model, analytical equilibrium checks, fixed-pose wall-support example, and one torque-driven hold. This determines whether the planned demonstration is viable.
2. **Authoring slice:** scene, four tracks, schema, phase compiler, save/load, and pose generation.
3. **Motion slice:** transitions, trajectory refinement, dense validation, and time-local diagnostics.
4. **Release candidate:** dynamic replay, export, complete demo and failure cases, documentation, and clean-install checks.

A draft PR may contain earlier slices if labeled accurately. A complete Contact Composer demo requires all P0 acceptance scenarios; the existence of this design document is not implementation evidence.

## 12. Sources

The product and its acceptance targets are proposed here. These sources inform specific implementation choices:

- [MuJoCo computation](https://mujoco.readthedocs.io/en/stable/computation/index.html): soft-contact behavior and interpretation of simulation evidence.
- [MuJoCo API functions](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html): forward simulation, kinematics/Jacobians, and contact-force queries.
- [OSQP solver documentation](https://osqp.org/docs/solver/index.html): fixed-pose convex QPs, residuals, and scoped infeasibility certificates.
- [Optimized user-guided motion control of modular robots](https://www.nature.com/articles/s41467-025-63706-6): related work on interactive control with contact constraints; not a claim of reproducing that system.
