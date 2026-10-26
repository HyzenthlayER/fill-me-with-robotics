import { useState } from "react";
import { Result, colors } from "./types";
export function Diagnostics({
  plan,
  replay,
  stale,
  time,
  onSeek,
}: {
  plan: Result | null;
  replay: Result | null;
  stale: boolean;
  time: number;
  onSeek: (t: number) => void;
}) {
  const [quantity, setQuantity] = useState("force");
  const issues = [
    ...(plan?.summary.issues || []),
    ...(replay?.summary.issues || []),
  ];
  const source = replay || plan;
  const times = (source?.arrays.time_s || []) as number[];
  const duration = Math.max(
    times.at(-1) || 0,
    (plan?.arrays.time_s as number[] | undefined)?.at(-1) || 0,
    1,
  );
  function values(result: Result | null): number[][] {
    if (!result) return [];
    if (quantity === "torque")
      return (result.arrays.tau_commanded ||
        result.arrays.tau_reference) as number[][];
    return (
      (result.arrays.actual_contact_forces_world ||
        result.arrays.contact_force_world) as number[][][]
    ).map((row) => row.map((v) => Math.hypot(...v)));
  }
  const planned = values(plan),
    measured = values(replay),
    all = [...planned, ...measured].flat();
  const max = Math.max(1, ...all.map(Math.abs));
  function trace(data: number[][], result: Result | null, dashed: boolean) {
    if (!data.length) return null;
    const ts = result!.arrays.time_s as number[];
    return data[0].map((_, column) => (
      <polyline
        key={`${dashed}-${column}`}
        fill="none"
        stroke={colors[column % 4]}
        strokeWidth="1.7"
        opacity={dashed ? 0.5 : 1}
        strokeDasharray={dashed ? "5 4" : undefined}
        points={data
          .filter((_, i) => i % 4 === 0)
          .map(
            (row, k) =>
              `${30 + (ts[k * 4] / duration) * 850},${quantity === "force" ? 145 - (row[column] / max) * 110 : 85 - (row[column] / max) * 60}`,
          )
          .join(" ")}
      />
    ));
  }
  return (
    <section className="panel diagnostics">
      <div className="panel-head">
        <div>
          <span className="eyebrow">EVIDENCE & DIAGNOSTICS</span>
          <h2>
            {stale
              ? "Results from an earlier revision"
              : source
                ? "Inspect the result"
                : "Ready when you are"}
          </h2>
        </div>
        <select
          aria-label="Plot quantity"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
        >
          <option value="force">Contact force magnitude · N</option>
          <option value="torque">Actuator torque · N·m</option>
        </select>
      </div>
      {source ? (
        <>
          <svg
            viewBox="0 0 910 180"
            className="chart"
            aria-label="Planned and measured forces or torques"
          >
            <path d="M30 25V145H880" stroke="#344257" fill="none" />
            <text x="30" y="17" fill="#8e9caf" fontSize="11">
              {max.toFixed(1)}
            </text>
            {trace(planned, plan, !!replay)}
            {trace(measured, replay, false)}
            <line
              x1={30 + (time / duration) * 850}
              y1="25"
              x2={30 + (time / duration) * 850}
              y2="145"
              stroke="#fff"
              opacity=".4"
            />
            <text x="30" y="169" fill="#8e9caf" fontSize="11">
              0s
            </text>
            <text x="845" y="169" fill="#8e9caf" fontSize="11">
              {duration.toFixed(1)}s
            </text>
          </svg>
          <p className="legend">
            {replay
              ? "Solid: measured replay · dashed: planned reference"
              : "Planned reference · run dynamics to obtain measured values"}
          </p>
        </>
      ) : (
        <div className="empty">
          Generate a trajectory to inspect forces, actuator torques and
          diagnostics. Then run an independent dynamics replay.
        </div>
      )}
      {replay?.summary.checks && (
        <div className="metrics">
          {Object.entries(replay.summary.checks).map(([key, value]) => (
            <div key={key}>
              <span>{key.replaceAll("_", " ")}</span>
              <strong>{value.toPrecision(3)}</strong>
            </div>
          ))}
        </div>
      )}
      {issues.length > 0 ? (
        <div className="issues">
          {issues.slice(0, 100).map((issue, i) => (
            <button
              className="issue"
              key={i}
              onClick={() => onSeek(issue.time_interval_s[0])}
            >
              <span className="issue-time">
                {issue.time_interval_s[0].toFixed(2)}s
              </span>
              <span>
                <b>{issue.code}</b> · {issue.message}
                <small>
                  {issue.source} · {issue.scope}
                  {issue.measured !== undefined && issue.measured !== null
                    ? ` · ${issue.measured.toPrecision(3)} / limit ${issue.limit} ${issue.unit || ""}`
                    : ""}
                </small>
              </span>
              <span>↗</span>
            </button>
          ))}
          {issues.length > 100 && (
            <p>
              Showing 100 of {issues.length} issues. Export the full report for
              all records.
            </p>
          )}
        </div>
      ) : (
        source && (
          <p className="check-note">
            No issues recorded for this {replay ? "replay" : "sampled plan"}.{" "}
            {stale
              ? "Regenerate for the current project."
              : "This is a planar simulation result."}
          </p>
        )
      )}
    </section>
  );
}
