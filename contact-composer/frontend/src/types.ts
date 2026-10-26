export const effectors = [
  "left_foot",
  "right_foot",
  "left_hand",
  "right_hand",
] as const;
export const colors = ["#51d9b0", "#62adff", "#f6c76e", "#d09bff"];
export type Effector = (typeof effectors)[number];
export type V2 = [number, number];
export type Contact = {
  id: string;
  effector_id: Effector;
  surface_id: string;
  anchor_u: number;
  start_tick: number;
  end_tick: number;
  mode: "stick";
};
export type Surface = {
  id: string;
  segment_start: V2;
  segment_end: V2;
  normal: V2;
  mu: number;
  force_cap_n: number;
};
export type Target = {
  id: string;
  tick: number;
  kind: "base_position" | "base_pitch" | "joint_posture" | "swing_endpoint";
  effector_id: Effector | null;
  target: number[];
  weight: number;
  tolerance: number;
  hardness: "soft" | "hard";
};
export type Project = {
  schema_version: string;
  id: string;
  name: string;
  revision: number;
  units: string;
  robot: Record<string, string>;
  timeline: { duration_ticks: number; tick_seconds: number };
  initial_state: { q: number[]; dq: number[] };
  surfaces: Surface[];
  obstacles: { id: string; primitive: "box"; position: V2; dimensions: V2 }[];
  contacts: Contact[];
  targets: Target[];
  settings: {
    planning: {
      max_iterations: number;
      timeout_s: number;
      swing_clearance: number;
    };
    validation: Record<string, number>;
    replay: Record<string, number | string>;
  };
};
export type Model = {
  radius: number;
  hip_offsets: number[];
  shoulder_offsets: number[];
  shoulder_height: number;
  leg_lengths: number[];
  arm_lengths: number[];
  torso_mass: number;
  torso_center: V2;
  torso_half_size: V2;
  leg_masses: number[];
  arm_masses: number[];
  endpoint_mass: number;
  total_mass: number;
};
export type Issue = {
  code: string;
  message: string;
  time_interval_s: [number, number];
  source: string;
  scope: string;
  measured?: number;
  limit?: number;
  unit?: string;
};
export type Summary = {
  solve_status?: string;
  check_status?: string;
  status?: string;
  project_hash: string;
  issues: Issue[];
  checks?: Record<string, number>;
};
export type Result = {
  id: string;
  revision: number;
  summary: Summary;
  arrays: Record<string, number[] | number[][] | number[][][]>;
};
export type Job = {
  id: string;
  revision: number;
  project_hash: string;
  kind: "solve" | "replay";
  status: string;
  progress: number;
  message: string;
  summary?: Summary;
};
