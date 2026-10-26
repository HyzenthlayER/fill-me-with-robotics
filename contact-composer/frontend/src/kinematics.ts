import { Model, V2 } from "./types";
export function rotate(p: V2, angle: number): V2 {
  return [
    Math.cos(angle) * p[0] + Math.sin(angle) * p[1],
    -Math.sin(angle) * p[0] + Math.cos(angle) * p[1],
  ];
}
export function add(a: V2, b: V2): V2 {
  return [a[0] + b[0], a[1] + b[1]];
}
export function kinematics(q: number[], m: Model) {
  const base: V2 = [q[0], q[1]];
  let weighted = add(base, rotate(m.torso_center, q[2])).map(
    (x) => x * m.torso_mass,
  ) as V2;
  const limbs = Array.from({ length: 4 }, (_, i) => {
    const leg = i < 2,
      side = i % 2;
    const lengths = leg ? m.leg_lengths : m.arm_lengths;
    const masses = leg ? m.leg_masses : m.arm_masses;
    const origin = add(
      base,
      rotate(
        [
          (leg ? m.hip_offsets : m.shoulder_offsets)[side],
          leg ? 0 : m.shoulder_height,
        ],
        q[2],
      ),
    );
    const a = q[2] + q[3 + i * 2],
      b = a + q[4 + i * 2];
    const mid = add(origin, rotate([0, -lengths[0]], a));
    const end = add(mid, rotate([0, -lengths[1]], b));
    weighted = add(weighted, [
      ((origin[0] + mid[0]) * masses[0] + (mid[0] + end[0]) * masses[1]) / 2 +
        end[0] * m.endpoint_mass,
      ((origin[1] + mid[1]) * masses[0] + (mid[1] + end[1]) * masses[1]) / 2 +
        end[1] * m.endpoint_mass,
    ]);
    return [origin, mid, end];
  });
  return { limbs, com: weighted.map((x) => x / m.total_mass) as V2 };
}
