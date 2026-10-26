import { describe, it, expect } from "vitest";
import { edit, travel, validateEdit, moveContact, History } from "./editor";
import { kinematics } from "./kinematics";
import fixture from "./test-fixture.json";
import { Project, Model } from "./types";

const project = fixture.project as unknown as Project;
describe("M01/M03 project editing", () => {
  it("preserves 100 independent edits and revisions across undo/redo", () => {
    let h: History = {
      current: structuredClone(project),
      past: [],
      future: [],
    };
    for (let i = 0; i < 110; i++)
      h = edit(h, { ...h.current, name: "Edit " + i });
    expect(h.past).toHaveLength(100);
    const revision = h.current.revision;
    for (let i = 0; i < 50; i++) h = travel(h, "undo");
    expect(h.current.name).toBe("Edit 59");
    expect(h.current.revision).toBe(revision + 50);
    h = travel(h, "redo");
    expect(h.current.name).toBe("Edit 60");
    h = edit(h, { ...h.current, name: "New branch" });
    expect(h.future).toHaveLength(0);
  });
  it("rejects overlaps and leaves the original history intact", () => {
    const h: History = {
      current: structuredClone(project),
      past: [],
      future: [],
    };
    const p = structuredClone(project);
    p.contacts.push({ ...p.contacts[0], id: "duplicate" });
    expect(() => edit(h, p)).toThrow("overlap");
    expect(h.current).toEqual(project);
    expect(h.past).toHaveLength(0);
  });
  it("moves and resizes in discrete ticks without clamping invalid values", () => {
    const c = project.contacts[1];
    expect(moveContact(c, 4, "move").end_tick).toBe(c.end_tick + 4);
    expect(moveContact(c, 4, "start").end_tick).toBe(c.end_tick);
    const p = structuredClone(project);
    p.contacts[0] = moveContact(p.contacts[0], -2, "move");
    expect(() => validateEdit(p)).toThrow("timeline");
  });
});
describe("M02 browser forward kinematics", () => {
  it("matches MuJoCo poses and mass-weighted CoM at three different configurations", () => {
    for (const sample of fixture.samples) {
      const actual = kinematics(sample.q, fixture.model as unknown as Model);
      actual.limbs.forEach((limb, i) =>
        limb.forEach((point, j) =>
          point.forEach((value, k) =>
            expect(value).toBeCloseTo(sample.geometry.limbs[i].points[j][k], 9),
          ),
        ),
      );
      actual.com.forEach((value, i) =>
        expect(value).toBeCloseTo(sample.geometry.com[i], 9),
      );
    }
  });
});
