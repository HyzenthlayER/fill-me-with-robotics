import { useRef, useState } from "react";
import { Contact, Model, Project, V2, colors, effectors } from "./types";
import { projectAnchor } from "./editor";
import { kinematics } from "./kinematics";

const point = (p: V2): V2 => [255 + p[0] * 255, 389 - p[1] * 255];
export function Scene({
  project,
  model,
  q,
  forces,
  selected,
  onSelect,
  onAnchor,
}: {
  project: Project;
  model: Model;
  q: number[];
  forces?: number[][];
  selected: string | null;
  onSelect: (s: string) => void;
  onAnchor: (id: string, u: number) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ contact: Contact; u: number } | null>(
    null,
  );
  const geometry = kinematics(q, model);
  function coordinate(event: React.PointerEvent): V2 {
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(
      svg.current!.getScreenCTM()!.inverse(),
    );
    return [(p.x - 255) / 255, (389 - p.y) / 255];
  }
  function anchorU(event: React.PointerEvent, c: Contact) {
    const p = coordinate(event);
    const surface = project.surfaces.find((s) => s.id === c.surface_id)!;
    const d = surface.segment_end.map((x, i) => x - surface.segment_start[i]);
    return Math.max(
      0,
      Math.min(
        1,
        ((p[0] - surface.segment_start[0]) * d[0] +
          (p[1] - surface.segment_start[1]) * d[1]) /
          (d[0] ** 2 + d[1] ** 2),
      ),
    );
  }
  return (
    <svg
      ref={svg}
      className="scene"
      viewBox="0 0 550 440"
      aria-label="Planar robot scene"
      onPointerMove={(e) => {
        if (drag) setDrag({ ...drag, u: anchorU(e, drag.contact) });
      }}
      onPointerUp={() => {
        if (drag) {
          if (Math.abs(drag.u - drag.contact.anchor_u) > 1e-8)
            onAnchor(drag.contact.id, drag.u);
          setDrag(null);
        }
      }}
      onPointerCancel={() => setDrag(null)}
    >
      <defs>
        <pattern id="grid" width="51" height="51" patternUnits="userSpaceOnUse">
          <path
            d="M 51 0 L 0 0 0 51"
            fill="none"
            stroke="#233145"
            strokeWidth=".65"
          />
        </pattern>
        <marker
          id="arrow"
          markerWidth="7"
          markerHeight="7"
          refX="5"
          refY="3"
          orient="auto"
        >
          <path d="M0 0L6 3L0 6" fill="#eaf2ff" />
        </marker>
      </defs>
      <rect width="550" height="440" fill="url(#grid)" />
      <text x="22" y="30" className="scene-note">
        SAGITTAL PLANE · X / Z · METERS
      </text>
      {project.surfaces.map((s) => {
        const a = point(s.segment_start),
          b = point(s.segment_end);
        return (
          <g key={s.id}>
            <line
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              stroke="#8390a5"
              strokeWidth="6"
            />
            <text
              x={b[0] - 80}
              y={Math.max(b[1] + 22, 40)}
              className="scene-note"
            >
              {s.id} · μ {s.mu}
            </text>
          </g>
        );
      })}
      {project.obstacles.map((o) => {
        const p = point(o.position);
        return (
          <rect
            key={o.id}
            x={p[0] - o.dimensions[0] * 127.5}
            y={p[1] - o.dimensions[1] * 127.5}
            width={o.dimensions[0] * 255}
            height={o.dimensions[1] * 255}
            fill="#5c3445"
            stroke="#f58a9a"
          />
        );
      })}
      {[...project.contacts]
        .sort((a, b) => Number(a.id === selected) - Number(b.id === selected))
        .map((c) => {
          const a = point(
            projectAnchor(
              project,
              drag?.contact.id === c.id ? { ...c, anchor_u: drag.u } : c,
            ),
          );
          return (
            <g key={c.id}>
              <circle
                cx={a[0]}
                cy={a[1]}
                r={selected === c.id ? 11 : 7}
                stroke={colors[effectors.indexOf(c.effector_id)]}
                fill="#111a27"
                strokeWidth="2"
                className="anchor"
                aria-label={`Anchor ${c.id}`}
                onPointerDown={(e) => {
                  e.currentTarget.setPointerCapture(e.pointerId);
                  onSelect(c.id);
                  setDrag({ contact: c, u: c.anchor_u });
                }}
              />
              <path
                d={`M${a[0] - 3},${a[1]}h6 M${a[0]},${a[1] - 3}v6`}
                stroke="white"
                pointerEvents="none"
              />
            </g>
          );
        })}
      <g
        transform={`translate(${point([q[0], q[1]])}) rotate(${(q[2] * 180) / Math.PI})`}
      >
        <rect
          x={(model.torso_center[0] - model.torso_half_size[0]) * 255}
          y={-(model.torso_center[1] + model.torso_half_size[1]) * 255}
          width={model.torso_half_size[0] * 510}
          height={model.torso_half_size[1] * 510}
          rx="12"
          fill="#223c54"
          stroke="#b9d5ed"
          strokeWidth="2"
        />
        <rect x="-10" y="-64" width="20" height="6" rx="3" fill="#51d9b0" />
        <circle cy="0" r="6" fill="#e7f2ff" />
      </g>
      {geometry.limbs.map((limb, i) => (
        <g key={i}>
          <polyline
            points={limb.map((p) => point(p).join(",")).join(" ")}
            stroke={colors[i]}
            strokeWidth="8"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
          {limb.map((p, j) => (
            <circle
              key={j}
              cx={point(p)[0]}
              cy={point(p)[1]}
              r={j === 2 ? 4 : 5}
              fill="#111a27"
              stroke={colors[i]}
              strokeWidth="2"
            />
          ))}
        </g>
      ))}
      {forces?.map((f, i) => {
        const a = point(geometry.limbs[i][2]);
        return Math.hypot(...f) > 1 ? (
          <g key={i}>
            <line
              x1={a[0]}
              y1={a[1]}
              x2={a[0] + f[0] * 1.2}
              y2={a[1] - f[1] * 1.2}
              stroke="#eaf2ff"
              strokeWidth="2"
              markerEnd="url(#arrow)"
            />
            <text
              x={a[0] + f[0] * 1.2 + 8}
              y={a[1] - f[1] * 1.2}
              fill="white"
              fontSize="11"
            >
              {Math.hypot(...f).toFixed(1)} N
            </text>
          </g>
        ) : null;
      })}
      <circle
        cx={point(geometry.com)[0]}
        cy={point(geometry.com)[1]}
        r="5"
        fill="#ffcf74"
        stroke="#111a27"
        strokeWidth="2"
      />
      <text
        x={point(geometry.com)[0] + 10}
        y={point(geometry.com)[1] - 8}
        className="scene-note"
      >
        CoM
      </text>
      <path
        d="M25 405h35 M25 405v-35"
        stroke="#8193a9"
        markerEnd="url(#arrow)"
      />
      <text x="65" y="409" className="scene-note">
        x
      </text>
      <text x="21" y="363" className="scene-note">
        z
      </text>
      <text x="342" y="423" className="scene-note">
        Drag rings to move anchors
      </text>
    </svg>
  );
}
