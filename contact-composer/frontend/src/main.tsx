import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Contact,
  Effector,
  Job,
  Model,
  Project,
  Result,
  effectors,
} from "./types";
import { History, edit, travel } from "./editor";
import { Scene } from "./Scene";
import { Timeline } from "./Timeline";
import { Inspector, Field } from "./Inspector";
import { Diagnostics } from "./Diagnostics";
import "./style.css";

async function api(path: string, body?: unknown, method = "POST") {
  const response = await fetch(
    "/api/" + path,
    body === undefined
      ? undefined
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
function download(project: Project) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(project, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = project.id + ".json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function App() {
  const [history, setHistory] = useState<History | null>(null),
    [model, setModel] = useState<Model | null>(null);
  const [selected, setSelected] = useState<string | null>(null),
    [error, setError] = useState(""),
    [valid, setValid] = useState("checking");
  const [time, setTime] = useState(0),
    [playing, setPlaying] = useState(false),
    [mode, setMode] = useState("preview");
  const [job, setJob] = useState<Job | null>(null),
    [plan, setPlan] = useState<Result | null>(null),
    [simulation, setSimulation] = useState<Result | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const project = history?.current;
  const duration = (project?.timeline.duration_ticks || 0) * 0.05;
  const stale = !!project && !!plan && plan.revision !== project.revision;
  const busy = job?.status === "running";
  useEffect(() => {
    Promise.all([api("examples/wall-assisted"), api("models")])
      .then(([p, m]) => {
        setHistory({ current: p, past: [], future: [] });
        setModel(m);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!project) return;
    let active = true;
    setValid("checking");
    const timer = setTimeout(() => {
      api("validate", project)
        .then(() => {
          if (active) setValid("valid");
        })
        .catch((e) => {
          if (active) {
            setValid("invalid");
            setError(e.message);
          }
        });
    }, 180);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [project]);
  useEffect(() => {
    if (!playing) return;
    const start = performance.now(),
      initial = time;
    const id = setInterval(() => {
      const next = initial + (performance.now() - start) / 1000;
      setTime(Math.min(next, duration));
      if (next >= duration) setPlaying(false);
    }, 30);
    return () => clearInterval(id);
  }, [playing, duration]);
  useEffect(() => {
    if (!job || job.status !== "running") return;
    let active = true,
      pending = false;
    const id = setInterval(async () => {
      if (pending) return;
      pending = true;
      try {
        const update: Job = await api("jobs/" + job.id);
        if (update.status !== "running" && update.summary) {
          const result = {
            ...(await api("results/" + job.id)),
            id: job.id,
            revision: job.revision,
          };
          if (active) {
            if (job.kind === "solve") {
              setPlan(result);
              setSimulation(null);
              setMode("preview");
            } else {
              setSimulation(result);
              setMode("replay");
            }
            setTime(0);
          }
        }
        if (active) {
          setJob(update);
          if (update.status === "failed") setError(update.message);
        }
      } catch (e) {
        if (active) setError(String(e));
      } finally {
        pending = false;
      }
    }, 350);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [job?.id, job?.status]);
  function replace(candidate: Project) {
    if (!history) return;
    try {
      setHistory(edit(history, candidate));
      setError("");
      setPlaying(false);
      setTime((t) => Math.min(t, candidate.timeline.duration_ticks * 0.05));
    } catch (e) {
      setError(String(e));
    }
  }
  function remove() {
    if (project && selected)
      replace({
        ...project,
        contacts: project.contacts.filter((c) => c.id !== selected),
      });
    setSelected(null);
  }
  function copy() {
    const contact = project?.contacts.find((c) => c.id === selected);
    if (!project || !contact) return;
    const c = {
      ...contact,
      id: "contact_" + crypto.randomUUID().slice(0, 8),
      start_tick: contact.end_tick + 4,
      end_tick: contact.end_tick + 4 + (contact.end_tick - contact.start_tick),
    };
    replace({ ...project, contacts: [...project.contacts, c] });
  }
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input,textarea,select"))
        return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        setHistory((h) =>
          h ? travel(h, event.shiftKey ? "redo" : "undo") : h,
        );
        setPlaying(false);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
        event.preventDefault();
        copy();
      }
      if (event.key === "Delete") remove();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [history, selected]);
  async function load(name: string) {
    try {
      const p = await api("examples/" + name);
      replace(p);
      setSelected(null);
      setTime(0);
    } catch (e) {
      setError(String(e));
    }
  }
  async function importProject(file: File) {
    try {
      if (file.size > 1_000_000) throw Error("Project exceeds 1 MB");
      const candidate = JSON.parse(await file.text());
      await api("validate", candidate);
      replace(candidate);
      setSelected(null);
    } catch (e) {
      setError("Import rejected: " + String(e));
    }
  }
  async function run(kind: "solve" | "replay") {
    try {
      setError("");
      setPlaying(false);
      setJob(
        await api(kind === "solve" ? "solve" : "replay/" + plan!.id, project),
      );
    } catch (e) {
      setError(String(e));
    }
  }
  if (!project || !model)
    return (
      <main className="loading">
        <h1>Contact Composer</h1>
        <p>{error || "Connecting to the local numerical service…"}</p>
      </main>
    );
  const result = mode === "replay" ? simulation : plan;
  const usable = result && result.revision === project.revision;
  const times = (usable ? result.arrays.time_s : []) as number[];
  const index = times.length
    ? Math.min(
        times.length - 1,
        Math.max(0, Math.round(time / (times[1] || 0.01))),
      )
    : 0;
  const q =
    usable && times.length
      ? ((result.arrays.q_measured || result.arrays.q) as number[][])[index]
      : project.initial_state.q;
  const forces =
    usable && times.length
      ? (
          (result.arrays.actual_contact_forces_world ||
            result.arrays.contact_force_world) as number[][][]
        )[index]
      : undefined;
  const loaded =
    !stale && plan?.arrays.contact_loaded
      ? (plan.arrays.contact_loaded as number[][])[
          Math.min(
            Math.round(time * 100),
            (plan.arrays.time_s as number[]).length - 1,
          )
        ]
      : undefined;
  const selectedContact = project.contacts.find((c) => c.id === selected);
  function updateContact(c: Contact) {
    replace({
      ...project!,
      contacts: project!.contacts.map((x) => (x.id === c.id ? c : x)),
    });
  }
  function add(effector: Effector, tick: number) {
    const c: Contact = {
      id: "contact_" + crypto.randomUUID().slice(0, 8),
      effector_id: effector,
      surface_id: effector.includes("foot") ? "floor" : "wall",
      anchor_u: effector.includes("foot")
        ? effector === "left_foot"
          ? 0.455
          : 0.545
        : 0.5,
      start_tick: tick,
      end_tick: tick + 20,
      mode: "stick",
    };
    if (!project!.surfaces.some((s) => s.id === c.surface_id))
      c.surface_id = project!.surfaces[0].id;
    replace({ ...project!, contacts: [...project!.contacts, c] });
    setSelected(c.id);
  }
  const planState = stale ? "stale" : plan?.summary.check_status || "not run";
  const simState = stale ? "stale" : simulation?.summary.status || "not run";
  return (
    <>
      <header>
        <div className="brand">
          <span className="brand-mark">
            C<span>↗</span>
          </span>
          <div>
            Contact Composer<small>ROBOTICS · MOTION WORKSPACE</small>
          </div>
        </div>
        <div className="header-actions">
          <select
            aria-label="Load example"
            defaultValue="wall-assisted"
            onChange={(e) => load(e.target.value)}
          >
            <option value="wall-assisted">Wall-assisted foot lift</option>
            <option value="standing">Double support</option>
            <option value="low-friction">Insufficient friction</option>
          </select>
          <button onClick={() => file.current?.click()}>Open JSON</button>
          <button onClick={() => download(project)}>Save project</button>
          <input
            hidden
            type="file"
            accept=".json,application/json"
            ref={file}
            onChange={(e) => {
              if (e.target.files?.[0]) importProject(e.target.files[0]);
              e.target.value = "";
            }}
          />
        </div>
      </header>
      <main>
        <div className="workspace-title">
          <div>
            <span className="eyebrow">COMPOSE CONTACT. TEST MOTION.</span>
            <input
              className="project-name"
              aria-label="Project name"
              key={project.id + project.name}
              defaultValue={project.name}
              onBlur={(e) => {
                if (e.target.value !== project.name)
                  replace({ ...project, name: e.target.value });
              }}
            />
            <p className="muted">
              Planar robot · 11 DOF · 8 actuators{" "}
              <span className="separator">/</span> Revision {project.revision}
            </p>
          </div>
          <div className="run-actions">
            <button
              disabled={!history.past.length}
              onClick={() => {
                setHistory(travel(history, "undo"));
                setPlaying(false);
              }}
              title="Ctrl+Z"
            >
              ↶ Undo
            </button>
            <button
              disabled={!history.future.length}
              onClick={() => {
                setHistory(travel(history, "redo"));
                setPlaying(false);
              }}
              title="Ctrl+Shift+Z"
            >
              ↷ Redo
            </button>
            <button
              className="primary"
              disabled={busy || valid !== "valid"}
              onClick={() => run("solve")}
            >
              Generate trajectory <span>→</span>
            </button>
            <button
              className="secondary"
              disabled={
                busy || stale || plan?.summary.check_status !== "passed"
              }
              onClick={() => run("replay")}
            >
              Run dynamics
            </button>
          </div>
        </div>
        <div className="status-strip">
          {[
            ["01", "Input", valid],
            [
              "02",
              "Kinematic candidate",
              stale ? "stale" : plan?.summary.solve_status || "not run",
            ],
            ["03", "Quasi-static checks", planState],
            ["04", "Dynamics replay", simState],
          ].map(([n, label, state]) => (
            <div key={n}>
              <span className="status-number">{n}</span>
              <span>{label}</span>
              <b
                className={
                  ["valid", "passed", "success"].includes(state)
                    ? "good"
                    : [
                          "failed",
                          "invalid",
                          "incomplete",
                          "no_solution_found",
                        ].includes(state)
                      ? "bad"
                      : "neutral"
                }
              >
                {state.replaceAll("_", " ")}
              </b>
            </div>
          ))}
        </div>
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            <button onClick={() => setError("")} aria-label="Dismiss error">
              ×
            </button>
          </div>
        )}
        {busy && (
          <div className="job-progress" role="status">
            <progress max="1" value={job.progress} />
            <span>
              {job.message} · {Math.round(job.progress * 100)}%
            </span>
            <button
              onClick={async () => {
                try {
                  await fetch("/api/jobs/" + job.id, { method: "DELETE" });
                } catch (e) {
                  setError(String(e));
                }
              }}
            >
              Cancel
            </button>
          </div>
        )}
        <div className="workspace">
          <section className="panel viewport">
            <div className="panel-head">
              <div>
                <span className="eyebrow">SCENE VIEW</span>
                <h2>
                  {mode === "replay" ? "Dynamics replay" : "Kinematic preview"}
                </h2>
              </div>
              <div className="segmented">
                <button
                  className={mode === "preview" ? "active" : ""}
                  onClick={() => setMode("preview")}
                >
                  Preview
                </button>
                <button
                  className={mode === "replay" ? "active" : ""}
                  disabled={!simulation || stale}
                  onClick={() => setMode("replay")}
                >
                  Replay
                </button>
              </div>
            </div>
            <Scene
              project={project}
              model={model}
              q={q}
              forces={forces}
              selected={selected}
              onSelect={setSelected}
              onAnchor={(id, u) => {
                const c = project.contacts.find((c) => c.id === id)!;
                updateContact({ ...c, anchor_u: Number(u.toFixed(6)) });
              }}
            />
            <div className="transport">
              <button
                aria-label={playing ? "Pause" : "Play"}
                disabled={!usable || !times.length}
                onClick={() => {
                  if (time >= duration) setTime(0);
                  setPlaying(!playing);
                }}
              >
                {playing ? "Ⅱ" : "▶"}
              </button>
              <input
                aria-label="Playhead"
                type="range"
                min="0"
                max={duration}
                step=".01"
                value={time}
                onChange={(e) => {
                  setPlaying(false);
                  setTime(Number(e.target.value));
                }}
              />
              <span className="mono">
                {time.toFixed(2)} / {duration.toFixed(2)} s
              </span>
            </div>
            <div className="viewport-foot">
              <span>
                {usable
                  ? mode === "replay"
                    ? "Measured state · torque-only simulation"
                    : "Planned poses · 100 Hz sampled checks"
                  : "Authored initial state"}
              </span>
              <span>
                {stale
                  ? "Edited · regenerate to preview"
                  : usable &&
                      times.length &&
                      (times.at(-1) || 0) < duration - 0.01
                    ? `Partial coverage ends at ${times.at(-1)!.toFixed(2)} s`
                    : "CPU · MuJoCo"}
              </span>
            </div>
          </section>
          <Inspector
            project={project}
            selected={selectedContact}
            onEdit={replace}
            onCopy={copy}
            onDelete={remove}
          />
        </div>
        <div className="score-toolbar">
          <span className="muted">
            Contact blocks prescribe the support sequence. Forces are solved
            separately.
          </span>
          <Field
            label="Duration (s)"
            value={duration}
            step={0.05}
            onChange={(v) =>
              replace({
                ...project,
                timeline: {
                  ...project.timeline,
                  duration_ticks: Math.round(v / 0.05),
                },
              })
            }
          />
        </div>
        <Timeline
          project={project}
          time={time}
          selected={selected}
          loaded={loaded}
          measuredLoaded={
            simulation && !stale
              ? effectors.map((e, i) => {
                  const c = project.contacts.find(
                    (c) =>
                      c.effector_id === e &&
                      c.start_tick <=
                        Math.min(
                          time / 0.05,
                          project.timeline.duration_ticks - 1e-6,
                        ) &&
                      c.end_tick >
                        Math.min(
                          time / 0.05,
                          project.timeline.duration_ticks - 1e-6,
                        ),
                  );
                  if (!c) return false;
                  const row = (
                    simulation.arrays
                      .actual_contact_forces_world as number[][][]
                  )[
                    Math.min(
                      Math.round(
                        time /
                          ((simulation.arrays.time_s as number[])[1] || 0.01),
                      ),
                      (simulation.arrays.time_s as number[]).length - 1,
                    )
                  ];
                  const normal = project.surfaces.find(
                    (s) => s.id === c.surface_id,
                  )!.normal;
                  return (
                    !!row &&
                    row[i][0] * normal[0] + row[i][1] * normal[1] >
                      0.01 * model.total_mass * 9.81
                  );
                })
              : undefined
          }
          issues={
            stale
              ? []
              : [
                  ...(plan?.summary.issues || []),
                  ...(simulation?.summary.issues || []),
                ]
          }
          onSelect={setSelected}
          onChange={updateContact}
          onAdd={add}
          onSeek={(t) => {
            setPlaying(false);
            setTime(t);
          }}
        />
        <Diagnostics
          plan={plan}
          replay={simulation}
          stale={stale}
          time={time}
          onSeek={(t) => {
            setTime(Math.min(duration, t));
            setPlaying(false);
          }}
        />
        <footer>
          <span>Contact Composer 0.1 · Original planar model · SI units</span>
          <div>
            {plan && (
              <a href={"/api/results/" + plan.id + "/download"}>
                Export plan bundle ↗
              </a>
            )}
            {simulation && (
              <a href={"/api/results/" + simulation.id + "/download"}>
                Export replay bundle ↗
              </a>
            )}
          </div>
          <span>
            Sampled checks and simulation do not establish hardware validity.
          </span>
        </footer>
      </main>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
