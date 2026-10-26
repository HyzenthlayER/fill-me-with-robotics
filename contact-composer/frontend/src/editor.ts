import { Contact, Project } from "./types";
export type History = { current: Project; past: Project[]; future: Project[] };
export function edit(history: History, candidate: Project): History {
  validateEdit(candidate);
  return {
    current: {
      ...structuredClone(candidate),
      revision: history.current.revision + 1,
    },
    past: [...history.past, history.current].slice(-100),
    future: [],
  };
}
export function travel(history: History, direction: "undo" | "redo"): History {
  const source = direction === "undo" ? history.past : history.future;
  if (!source.length) return history;
  const current = {
    ...structuredClone(source.at(-1)!),
    revision: history.current.revision + 1,
  };
  return direction === "undo"
    ? {
        current,
        past: source.slice(0, -1),
        future: [...history.future, history.current],
      }
    : {
        current,
        past: [...history.past, history.current].slice(-100),
        future: source.slice(0, -1),
      };
}
export function validateEdit(p: Project) {
  const end = p.timeline.duration_ticks;
  if (!Number.isInteger(end) || end < 40 || end > 400)
    throw Error("Duration must be 2–20 seconds on the 50 ms grid.");
  if (new Set(p.contacts.map((c) => c.id)).size !== p.contacts.length)
    throw Error("Contact IDs must be unique.");
  for (const c of p.contacts) {
    if (
      !Number.isInteger(c.start_tick) ||
      !Number.isInteger(c.end_tick) ||
      c.start_tick < 0 ||
      c.end_tick > end ||
      c.end_tick - c.start_tick < 4
    )
      throw Error(
        "Contacts need at least 0.20 s and must fit inside the timeline.",
      );
    if (c.anchor_u < 0 || c.anchor_u > 1 || !Number.isFinite(c.anchor_u))
      throw Error("Anchor must lie on the selected surface.");
    for (const other of p.contacts)
      if (other.id !== c.id && other.effector_id === c.effector_id) {
        if (c.start_tick < other.end_tick && c.end_tick > other.start_tick)
          throw Error("Contacts on the same track cannot overlap.");
        if (
          c.end_tick === other.start_tick &&
          (c.surface_id !== other.surface_id || c.anchor_u !== other.anchor_u)
        )
          throw Error("A different anchor needs a release interval.");
      }
  }
}
export function moveContact(
  c: Contact,
  delta: number,
  mode: "move" | "start" | "end",
): Contact {
  return {
    ...c,
    start_tick: c.start_tick + (mode === "end" ? 0 : delta),
    end_tick: c.end_tick + (mode === "start" ? 0 : delta),
  };
}
export function projectAnchor(p: Project, c: Contact): [number, number] {
  const s = p.surfaces.find((s) => s.id === c.surface_id)!;
  return s.segment_start.map(
    (x, i) => x + c.anchor_u * (s.segment_end[i] - x),
  ) as [number, number];
}
