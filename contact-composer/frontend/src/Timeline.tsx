import { useRef, useState } from "react";
import { Contact, Project, colors, effectors, Effector, Issue } from "./types";
import { moveContact } from "./editor";
export function Timeline({
  project,
  time,
  selected,
  loaded,
  measuredLoaded,
  issues,
  onSelect,
  onChange,
  onAdd,
  onSeek,
}: {
  project: Project;
  time: number;
  selected: string | null;
  loaded?: number[];
  measuredLoaded?: boolean[];
  issues: Issue[];
  onSelect: (id: string) => void;
  onChange: (c: Contact) => void;
  onAdd: (e: Effector, tick: number) => void;
  onSeek: (time: number) => void;
}) {
  const [drag, setDrag] = useState<{
    contact: Contact;
    mode: "move" | "start" | "end";
    x: number;
    delta: number;
    width: number;
  } | null>(null);
  const track = useRef<HTMLDivElement>(null);
  const duration = project.timeline.duration_ticks;
  const percentage = (tick: number) => `${(100 * tick) / duration}%`;
  function begin(
    event: React.PointerEvent,
    c: Contact,
    mode: "move" | "start" | "end",
  ) {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    onSelect(c.id);
    setDrag({
      contact: c,
      mode,
      x: event.clientX,
      delta: 0,
      width: track.current!.getBoundingClientRect().width,
    });
  }
  return (
    <section className="panel timeline" aria-label="Contact timeline">
      <div className="panel-head">
        <div>
          <span className="eyebrow">CONTACT SCORE</span>
          <h2>Four tracks. One composition.</h2>
        </div>
        <span className="muted">
          50 ms grid · drag edges to resize · double-click to add
        </span>
      </div>
      <div
        className="timeline-grid"
        onPointerMove={(e) => {
          if (drag)
            setDrag({
              ...drag,
              delta: Math.round(((e.clientX - drag.x) / drag.width) * duration),
            });
        }}
        onPointerUp={() => {
          if (drag) {
            if (drag.delta)
              onChange(moveContact(drag.contact, drag.delta, drag.mode));
            setDrag(null);
          }
        }}
        onPointerCancel={() => setDrag(null)}
      >
        <div className="track-name">END EFFECTOR</div>
        <div
          className="ruler"
          ref={track}
          onClick={(e) =>
            onSeek(
              Math.max(
                0,
                Math.min(
                  duration,
                  ((e.clientX - e.currentTarget.getBoundingClientRect().left) /
                    e.currentTarget.clientWidth) *
                    duration,
                ),
              ) * 0.05,
            )
          }
        >
          {Array.from({ length: 7 }, (_, i) => (
            <span key={i} style={{ left: `${(i * 100) / 6}%` }}>
              {((duration * 0.05 * i) / 6).toFixed(1)}s
            </span>
          ))}
        </div>
        {effectors.map((effector, index) => (
          <div className="track-row" key={effector}>
            <div className="track-name">
              <i style={{ background: colors[index] }} />
              {effector.replace("_", " ")}
              <span
                className="load-indicator"
                title="P: planned load; M: measured support"
              >
                {loaded?.[index] ? "P" : ""}
                {measuredLoaded?.[index] ? " M" : ""}
              </span>
              <button
                aria-label={`Add ${effector} contact`}
                onClick={() => onAdd(effector, Math.round(time / 0.05))}
              >
                +
              </button>
            </div>
            <div
              className="track"
              onDoubleClick={(e) => {
                if (e.target === e.currentTarget)
                  onAdd(
                    effector,
                    Math.round(
                      ((e.clientX -
                        e.currentTarget.getBoundingClientRect().left) /
                        e.currentTarget.clientWidth) *
                        duration,
                    ),
                  );
              }}
            >
              {issues.slice(0, 100).map((issue, i) => (
                <button
                  key={"issue-" + i}
                  className="timeline-issue"
                  aria-label={`${issue.code} at ${issue.time_interval_s[0]} seconds on ${effector}`}
                  title={issue.message}
                  style={{
                    left: percentage(issue.time_interval_s[0] / 0.05),
                    width: `max(3px, ${percentage((issue.time_interval_s[1] - issue.time_interval_s[0]) / 0.05)})`,
                  }}
                  onClick={() => onSeek(issue.time_interval_s[0])}
                />
              ))}
              {project.contacts
                .filter((c) => c.effector_id === effector)
                .map((original) => {
                  const c =
                    drag?.contact.id === original.id
                      ? moveContact(original, drag.delta, drag.mode)
                      : original;
                  return (
                    <div
                      key={c.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`${c.id} ${c.start_tick * 0.05} to ${c.end_tick * 0.05} seconds`}
                      className={`contact-block ${selected === c.id ? "selected" : ""}`}
                      style={{
                        left: percentage(c.start_tick),
                        width: percentage(c.end_tick - c.start_tick),
                        background: colors[index] + "28",
                        borderColor: colors[index],
                        color: colors[index],
                      }}
                      onClick={() => onSelect(c.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") onSelect(c.id);
                      }}
                      onPointerDown={(e) => begin(e, c, "move")}
                    >
                      <span
                        className="handle start"
                        aria-label={`Resize start ${c.id}`}
                        onPointerDown={(e) => begin(e, c, "start")}
                      />
                      <span className="block-label">{c.surface_id}</span>
                      <span
                        className="handle end"
                        aria-label={`Resize end ${c.id}`}
                        onPointerDown={(e) => begin(e, c, "end")}
                      />
                    </div>
                  );
                })}
              <div
                className="playhead"
                style={{ left: percentage(time / 0.05) }}
              />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
