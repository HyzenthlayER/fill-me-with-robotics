# Offline ZMP trace analyzer

Inspect recorded or simulated humanoid gait samples by comparing the planar
zero moment point (ZMP) with the supplied support polygon for each sample. The
report gives containment, a signed geometric margin, and consecutive outside
sample intervals to help review controller behavior.

This tool reads a local file and writes JSON to standard output. It has no
hardware interface, network access, credentials, or third-party dependencies.
The geometric margin cannot establish dynamic walking stability or certify
hardware safety. The analyzer does not check whether a supplied polygon models
the actual support contacts correctly.

## Run

Use Python 3.12 and its standard library. No installation or build is required.
From the repository root:

```sh
python tools/zmp_trace/analyze.py tools/zmp_trace/fixtures/synthetic.jsonl
python tools/zmp_trace/analyze.py trace.jsonl --tolerance 0.000001
```

The optional `--tolerance` is a finite, nonnegative boundary tolerance in the
input length unit; its default is `1e-9`. Use `--tolerance 0` for an exact
boundary comparison at the represented floating-point precision. The CLI
returns exit code 0 for a valid trace, including traces containing outside
samples. Invalid input returns a nonzero exit code and a diagnostic on standard
error. Record errors include the one-based physical line number. No partial
JSON report is written on input failure. File access and argument errors are
reported separately from record errors.

## JSON Lines input

The file must contain one UTF-8 JSON object per line and at least one sample,
with these required fields:

| Field | Meaning |
| --- | --- |
| `timestamp` | Finite numeric time in seconds, strictly increasing in file order. Negative times are allowed. |
| `zmp` | Exactly two finite numeric coordinates: `[x, y]`. |
| `support_polygon` | Array of at least three ordered vertices, each `[x, y]`. |

For example, one complete sample is:

```json
{"timestamp": 0.0, "zmp": [1, 1], "support_polygon": [[0, 0], [2, 0], [2, 2], [0, 2]]}
```

All ZMP and polygon coordinates must use the same planar coordinate frame and
length unit across the trace. The tool does not infer, transform, or convert
frames or units. Supply vertices along the polygon boundary, clockwise or
counterclockwise. Concave simple polygons are accepted. Each sample may have a
different support polygon. The closing edge is implicit: do not repeat the
first vertex at the end.

Duplicate vertices, zero-length edges, zero-area polygons, self-intersections,
self-touching, and overlapping edges are rejected. Collinear consecutive edges
are accepted when they continue along the boundary without overlapping. Holes
and multiple disjoint support regions are not represented by this schema.

Blank lines, comments, malformed JSON, duplicate object fields, missing required
fields, wrong dimensions, booleans used as numbers, non-finite numbers
(`NaN`, `Infinity`, or overflow such as `1e400`), and non-increasing timestamps
are errors. Additional object fields are ignored, but must still be valid JSON.
A final newline is optional; sample order is never sorted or repaired.

## Geometry and report

For each ZMP, the margin magnitude is the minimum Euclidean distance to a
**finite boundary segment**, including its endpoints. It is not distance to an
infinite line or to the convex hull. Classification uses these rules:

| `status` | `included` | `signed_distance` |
| --- | --- | --- |
| `inside` | `true` | Positive distance to the closest boundary segment. |
| `outside` | `false` | Negative distance to the closest boundary segment. |
| `boundary` | `true` | Exactly `0`, when distance is less than or equal to the tolerance, on either side. |

For the square in the example, `[1, 1]` has margin `+1`, `[3, 1]` has margin
`-1`, `[3, 3]` has margin `-sqrt(2)`, and edge or vertex points have margin `0`.

The JSON report contains `tolerance`, `sample_count`, `samples`, and
`outside_intervals`. Sample indices are zero-based; line numbers in errors are
one-based. For example, the second sample of the supplied synthetic fixture
produces this entry in `samples`:

```json
{
  "index": 1,
  "timestamp": 0.1,
  "status": "outside",
  "included": false,
  "signed_distance": -1.0
}
```

The fixture's complete `outside_intervals` value is:

```json
[
  {"start_index": 1, "end_index": 2, "start_timestamp": 0.1, "end_timestamp": 0.2, "sample_count": 2},
  {"start_index": 5, "end_index": 5, "start_timestamp": 0.5, "end_timestamp": 0.5, "sample_count": 1}
]
```

Endpoints are the first and last **outside samples**, inclusive. An inside or
boundary sample ends the current interval. Consecutive outside samples remain
one interval regardless of time gaps, and an interval still active at end of
file is included. There is no interpolation, inferred crossing time, or claim
about what happened between samples. A trace with every sample included has an
empty `outside_intervals` array.

## Precision and limits

Input numbers are converted to IEEE 754 binary64 floats. Very large integers,
very small numbers, closely spaced coordinates, and closely spaced timestamps
can lose precision during conversion; distinct values may become equal and be
rejected. Polygon predicates and projections use exact rational arithmetic on
those converted values to avoid intermediate overflow and cancellation.
Distances are rounded
back to floating point for the report and tolerance comparison. Results near
the tolerance threshold remain subject to floating-point rounding. Choose a
tolerance appropriate to the recording's length unit and precision; the
default has no physical safety meaning.

A distance that overflows, or a nonzero distance that rounds to zero, is an
explicit input error. Choose coordinate scales that give representable
distances. The tool performs pairwise edge checks per polygon (quadratic in
vertex count) and retains the report in memory (linear in sample count). It is
intended for offline diagnostic traces, not real-time control.

## Checks and sources

Run the standard-library acceptance suite from the repository root:

```sh
python -m unittest discover -s tools/zmp_trace/tests -p 'test_*.py'
```

Tests launch the CLI as a subprocess and check its JSON output, signed distances,
boundary semantics, interval endpoints, and error diagnostics. Cases include
clockwise and counterclockwise polygons, concavity, sloping edges, changing
support areas, invalid geometry, malformed records, and numeric extremes. The
tests explicitly assert that the CLI exists before attempting any subprocess,
making its absence a direct acceptance failure.

The fixture and test inputs are original synthetic data, not robot recordings
or third-party datasets. Source, tests, documentation, and fixture use the
repository's [Apache License 2.0](../../LICENSE).
