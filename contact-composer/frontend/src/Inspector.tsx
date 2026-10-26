import { useState } from "react";
import { Project, Contact, Effector, Target, effectors } from "./types";
export function Field({
  label,
  value,
  step = 0.01,
  onChange,
  min,
  max,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}) {
  return (
    <label className="field">
      {label}
      <input
        aria-label={label}
        type="number"
        step={step}
        min={min}
        max={max}
        key={value}
        defaultValue={Number(value.toFixed(6))}
        onBlur={(e) => {
          const n = Number(e.target.value);
          const changed =
            e.target.value !== "" && Number.isFinite(n) && n !== value;
          e.target.value = String(value);
          if (changed) onChange(n);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
      />
    </label>
  );
}
export function Inspector({
  project,
  selected,
  onEdit,
  onCopy,
  onDelete,
}: {
  project: Project;
  selected: Contact | undefined;
  onEdit: (p: Project) => void;
  onCopy: () => void;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState("contact");
  function updateContact(patch: Partial<Contact>) {
    if (selected)
      onEdit({
        ...project,
        contacts: project.contacts.map((c) =>
          c.id === selected.id ? { ...c, ...patch } : c,
        ),
      });
  }
  function updateTarget(id: string, patch: Partial<Target>) {
    onEdit({
      ...project,
      targets: project.targets.map((t) =>
        t.id === id ? { ...t, ...patch } : t,
      ),
    });
  }
  return (
    <aside className="panel inspector">
      <div className="tabs">
        {["contact", "scene", "targets"].map((t) => (
          <button
            className={tab === t ? "active" : ""}
            key={t}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div className="inspector-body">
        {tab === "contact" &&
          (selected ? (
            <>
              <span className="eyebrow">CONTACT PROPERTIES</span>
              <h2>{selected.effector_id.replace("_", " ")}</h2>
              <p className="muted mono">{selected.id}</p>
              <label className="field">
                Surface
                <select
                  value={selected.surface_id}
                  onChange={(e) =>
                    updateContact({ surface_id: e.target.value })
                  }
                >
                  {project.surfaces.map((s) => (
                    <option key={s.id}>{s.id}</option>
                  ))}
                </select>
              </label>
              <Field
                label="Anchor position (0–1)"
                value={selected.anchor_u}
                min={0}
                max={1}
                onChange={(v) => updateContact({ anchor_u: v })}
              />
              <div className="fields">
                <Field
                  label="Start (s)"
                  value={selected.start_tick * 0.05}
                  step={0.05}
                  onChange={(v) =>
                    updateContact({ start_tick: Math.round(v / 0.05) })
                  }
                />
                <Field
                  label="End (s)"
                  value={selected.end_tick * 0.05}
                  step={0.05}
                  onChange={(v) =>
                    updateContact({ end_tick: Math.round(v / 0.05) })
                  }
                />
              </div>
              <div className="note">
                Stick contact · point friction
                <br />
                Loads ramp over 0.10 s at transitions.
              </div>
              <div className="actions">
                <button onClick={onCopy}>Duplicate</button>
                <button className="danger" onClick={onDelete}>
                  Delete
                </button>
              </div>
            </>
          ) : (
            <>
              <span className="eyebrow">AUTHOR YOUR CONTACTS</span>
              <h2>Select a timeline block</h2>
              <p className="muted">
                Drag a block to move it. Drag either edge to resize it. Use + on
                a track to add a contact at the playhead.
              </p>
              <div className="note">
                Green and blue tracks control feet. Amber and violet tracks
                control hands.
              </div>
            </>
          ))}
        {tab === "scene" && (
          <>
            <span className="eyebrow">ENVIRONMENT</span>
            <h2>Surfaces & obstacles</h2>
            {project.surfaces.map((s, i) => (
              <div className="inspector-group" key={s.id}>
                <h3>{s.id}</h3>
                <div className="fields">
                  <Field
                    label={`${s.id} friction μ`}
                    value={s.mu}
                    onChange={(v) =>
                      onEdit({
                        ...project,
                        surfaces: project.surfaces.map((x, j) =>
                          i === j ? { ...x, mu: v } : x,
                        ),
                      })
                    }
                  />
                  <Field
                    label={`${s.id} force cap (N)`}
                    value={s.force_cap_n}
                    step={10}
                    onChange={(v) =>
                      onEdit({
                        ...project,
                        surfaces: project.surfaces.map((x, j) =>
                          i === j ? { ...x, force_cap_n: v } : x,
                        ),
                      })
                    }
                  />
                </div>
              </div>
            ))}
            <Field
              label="Swing clearance (m)"
              value={project.settings.planning.swing_clearance}
              onChange={(v) =>
                onEdit({
                  ...project,
                  settings: {
                    ...project.settings,
                    planning: {
                      ...project.settings.planning,
                      swing_clearance: v,
                    },
                  },
                })
              }
            />
            {project.obstacles.map((o) => (
              <div className="inspector-group" key={o.id}>
                <h3>{o.id}</h3>
                {(["x", "z"] as const).map((name, i) => (
                  <div className="fields" key={name}>
                    <Field
                      label={`Position ${name} (m)`}
                      value={o.position[i]}
                      onChange={(v) =>
                        onEdit({
                          ...project,
                          obstacles: project.obstacles.map((x) =>
                            x.id === o.id
                              ? {
                                  ...x,
                                  position: x.position.map((a, j) =>
                                    j === i ? v : a,
                                  ) as [number, number],
                                }
                              : x,
                          ),
                        })
                      }
                    />
                    <Field
                      label={`Size ${name} (m)`}
                      value={o.dimensions[i]}
                      onChange={(v) =>
                        onEdit({
                          ...project,
                          obstacles: project.obstacles.map((x) =>
                            x.id === o.id
                              ? {
                                  ...x,
                                  dimensions: x.dimensions.map((a, j) =>
                                    j === i ? v : a,
                                  ) as [number, number],
                                }
                              : x,
                          ),
                        })
                      }
                    />
                  </div>
                ))}
                <button
                  className="danger"
                  onClick={() =>
                    onEdit({
                      ...project,
                      obstacles: project.obstacles.filter((x) => x.id !== o.id),
                    })
                  }
                >
                  Remove obstacle
                </button>
              </div>
            ))}
            <button
              onClick={() =>
                onEdit({
                  ...project,
                  obstacles: [
                    ...project.obstacles,
                    {
                      id: "obstacle_" + crypto.randomUUID().slice(0, 8),
                      primitive: "box",
                      position: [0.3, 0.3],
                      dimensions: [0.1, 0.15],
                    },
                  ],
                })
              }
            >
              + Add box obstacle
            </button>
          </>
        )}
        {tab === "targets" && (
          <>
            <span className="eyebrow">POSE INTENT</span>
            <h2>Keyframe targets</h2>
            <p className="muted">
              Targets interpolate between keys. Hard targets must meet their
              tolerance.
            </p>
            {project.targets.map((t) => (
              <div className="inspector-group" key={t.id}>
                <label className="field">
                  Target kind
                  <select
                    value={t.kind}
                    onChange={(e) => {
                      const kind = e.target.value as Target["kind"];
                      updateTarget(t.id, {
                        kind,
                        effector_id:
                          kind === "swing_endpoint" ? "right_hand" : null,
                        target:
                          kind === "joint_posture"
                            ? project.initial_state.q.slice(3)
                            : kind === "base_pitch"
                              ? [0]
                              : kind === "base_position"
                                ? project.initial_state.q.slice(0, 2)
                                : [0.3, 0.8],
                      });
                    }}
                  >
                    {[
                      "base_position",
                      "base_pitch",
                      "joint_posture",
                      "swing_endpoint",
                    ].map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                </label>
                {t.kind === "swing_endpoint" && (
                  <select
                    aria-label="Target effector"
                    value={t.effector_id!}
                    onChange={(e) =>
                      updateTarget(t.id, {
                        effector_id: e.target.value as Effector,
                      })
                    }
                  >
                    {effectors.map((e) => (
                      <option key={e}>{e}</option>
                    ))}
                  </select>
                )}
                <Field
                  label="Target time (s)"
                  value={t.tick * 0.05}
                  step={0.05}
                  onChange={(v) =>
                    updateTarget(t.id, { tick: Math.round(v / 0.05) })
                  }
                />
                <label className="field">
                  Values (meters / radians)
                  <input
                    key={t.target.join(",")}
                    defaultValue={t.target.join(", ")}
                    onBlur={(e) =>
                      updateTarget(t.id, {
                        target: e.target.value.split(",").map(Number),
                      })
                    }
                  />
                </label>
                <label className="field">
                  Constraint
                  <select
                    value={t.hardness}
                    onChange={(e) =>
                      updateTarget(t.id, {
                        hardness: e.target.value as "hard" | "soft",
                      })
                    }
                  >
                    <option>soft</option>
                    <option>hard</option>
                  </select>
                </label>
                <div className="fields">
                  <Field
                    label="Weight"
                    value={t.weight}
                    onChange={(v) => updateTarget(t.id, { weight: v })}
                  />
                  <Field
                    label="Tolerance"
                    value={t.tolerance}
                    step={0.001}
                    onChange={(v) => updateTarget(t.id, { tolerance: v })}
                  />
                </div>
                <button
                  className="danger"
                  onClick={() =>
                    onEdit({
                      ...project,
                      targets: project.targets.filter((x) => x.id !== t.id),
                    })
                  }
                >
                  Remove target
                </button>
              </div>
            ))}
            <button
              onClick={() =>
                onEdit({
                  ...project,
                  targets: [
                    ...project.targets,
                    {
                      id: "target_" + crypto.randomUUID().slice(0, 8),
                      kind: "base_position",
                      effector_id: null,
                      tick: project.timeline.duration_ticks,
                      target: project.initial_state.q.slice(0, 2),
                      weight: 1,
                      tolerance: 0.001,
                      hardness: "soft",
                    },
                  ],
                })
              }
            >
              + Add target
            </button>
          </>
        )}
      </div>
    </aside>
  );
}
