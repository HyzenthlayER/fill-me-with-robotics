"""Inspect recorded ZMP samples against simple planar support polygons offline."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
from typing import Iterable


Point = tuple[Fraction, Fraction]
DEFAULT_TOLERANCE = 1e-9


class TraceError(ValueError):
    """Invalid input or geometry that cannot yield a finite distance."""


def finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceError(f"{name} must be a finite number (not a boolean)")
    try:
        number = float(value)
    except OverflowError as exc:
        raise TraceError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise TraceError(f"{name} must be a finite number")
    return number


def point(value: object, name: str) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise TraceError(f"{name} must be an array of exactly two coordinates")
    return (
        Fraction(finite_number(value[0], f"{name}[0]")),
        Fraction(finite_number(value[1], f"{name}[1]")),
    )


def cross(a: Point, b: Point, c: Point) -> Fraction:
    """Signed turn, evaluated exactly for the parsed binary64 coordinates."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(p: Point, a: Point, b: Point) -> bool:
    return (
        cross(a, b, p) == 0
        and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    turns = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    if any((
        turns[0] == 0 and on_segment(c, a, b),
        turns[1] == 0 and on_segment(d, a, b),
        turns[2] == 0 and on_segment(a, c, d),
        turns[3] == 0 and on_segment(b, c, d),
    )):
        return True
    return turns[0] * turns[1] < 0 and turns[2] * turns[3] < 0


def polygon(value: object) -> list[Point]:
    if not isinstance(value, list) or len(value) < 3:
        raise TraceError("support_polygon must have at least three vertices")
    vertices = [point(vertex, f"support_polygon[{i}]") for i, vertex in enumerate(value)]
    if len(set(vertices)) != len(vertices):
        raise TraceError(
            "support_polygon has duplicate vertices or a zero-length edge; "
            "do not repeat the first vertex"
        )

    count = len(vertices)
    for i, current in enumerate(vertices):
        previous, following = vertices[i - 1], vertices[(i + 1) % count]
        if cross(previous, current, following) == 0 and (
            on_segment(following, previous, current)
            or on_segment(previous, current, following)
        ):
            raise TraceError("support_polygon has overlapping adjacent edges")

    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % count]
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue  # Adjacent edges may share their common endpoint only.
            if segments_intersect(a, b, vertices[j], vertices[(j + 1) % count]):
                raise TraceError("support_polygon is self-intersecting or self-touching")

    twice_area = sum(
        cross(vertices[0], vertices[i], vertices[i + 1])
        for i in range(1, count - 1)
    )
    if twice_area == 0:
        raise TraceError("support_polygon has zero area")
    return vertices


def nearest_distance(p: Point, vertices: list[Point]) -> float:
    """Project onto finite segments, including endpoints, then measure the minimum."""
    nearest_squared = None
    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % len(vertices)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        px, py = p[0] - a[0], p[1] - a[1]
        projection = (px * dx + py * dy) / (dx * dx + dy * dy)
        projection = max(Fraction(0), min(Fraction(1), projection))
        offset = px - projection * dx, py - projection * dy
        squared = offset[0] ** 2 + offset[1] ** 2
        if nearest_squared is None or squared < nearest_squared:
            nearest_squared = squared

    if nearest_squared is None:
        raise TraceError("support_polygon has no boundary segments")
    if nearest_squared == 0:
        return 0.0
    # Scale before converting to binary64: the squared distance can be outside
    # the floating-point range even when its square root is representable.
    exponent = (
        nearest_squared.numerator.bit_length() - nearest_squared.denominator.bit_length()
    ) // 2
    scaled_squared = nearest_squared / Fraction(2) ** (2 * exponent)
    try:
        distance = math.ldexp(math.sqrt(float(scaled_squared)), exponent)
    except OverflowError as exc:
        raise TraceError("geometry cannot produce a finite distance") from exc
    if not math.isfinite(distance):
        raise TraceError("geometry cannot produce a finite distance")
    if distance == 0:
        raise TraceError("nonzero geometry distance is below floating-point resolution")
    return distance


def inside_polygon(p: Point, vertices: list[Point]) -> bool:
    """Even/odd ray crossings with a half-open rule at vertices; accepts concavity."""
    inside = False
    for i, a in enumerate(vertices):
        b = vertices[(i + 1) % len(vertices)]
        if (a[1] > p[1]) != (b[1] > p[1]):
            if (cross(a, b, p) > 0) == (b[1] > a[1]):
                inside = not inside
    return inside


def reject_constant(value: str) -> None:
    raise TraceError(f"non-finite JSON constant {value} is not allowed")


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise TraceError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def analyze(lines: Iterable[bytes], tolerance: float) -> dict:
    samples = []
    intervals = []
    active_interval = None
    previous_timestamp = None
    for line_number, raw_line in enumerate(lines, start=1):
        try:
            record = json.loads(
                raw_line.decode("utf-8"),
                parse_constant=reject_constant,
                object_pairs_hook=unique_object,
            )
            if not isinstance(record, dict):
                raise TraceError("each line must be a JSON object")
            for field in ("timestamp", "zmp", "support_polygon"):
                if field not in record:
                    raise TraceError(f"missing required field {field!r}")
            timestamp = finite_number(record["timestamp"], "timestamp")
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                raise TraceError("timestamp must be strictly increasing")
            zmp = point(record["zmp"], "zmp")
            vertices = polygon(record["support_polygon"])
            distance = nearest_distance(zmp, vertices)
            if distance <= tolerance:
                status, signed_distance = "boundary", 0.0
            elif inside_polygon(zmp, vertices):
                status, signed_distance = "inside", distance
            else:
                status, signed_distance = "outside", -distance
        except (ValueError, OverflowError, RecursionError) as exc:
            raise TraceError(f"line {line_number}: {exc}") from exc

        index = len(samples)
        samples.append({
            "index": index,
            "timestamp": timestamp,
            "status": status,
            "included": status != "outside",
            "signed_distance": signed_distance,
        })
        previous_timestamp = timestamp
        if status == "outside":
            if active_interval is None:
                active_interval = {
                    "start_index": index,
                    "end_index": index,
                    "start_timestamp": timestamp,
                    "end_timestamp": timestamp,
                    "sample_count": 0,
                }
                intervals.append(active_interval)
            active_interval["end_index"] = index
            active_interval["end_timestamp"] = timestamp
            active_interval["sample_count"] += 1
        else:
            active_interval = None

    if not samples:
        raise TraceError("line 1: empty trace; expected at least one sample")
    return {
        "tolerance": tolerance,
        "sample_count": len(samples),
        "samples": samples,
        "outside_intervals": intervals,
    }


def tolerance_argument(value: str) -> float:
    try:
        tolerance = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("tolerance must be a finite nonnegative number") from exc
    if not math.isfinite(tolerance) or tolerance < 0:
        raise argparse.ArgumentTypeError("tolerance must be a finite nonnegative number")
    return tolerance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="UTF-8 JSON Lines trace to read")
    parser.add_argument(
        "--tolerance",
        type=tolerance_argument,
        default=DEFAULT_TOLERANCE,
        help="boundary tolerance in input length units (default: 1e-9)",
    )
    args = parser.parse_args()
    try:
        with args.trace.open("rb") as trace:
            report = analyze(trace, args.tolerance)
    except (OSError, TraceError) as exc:
        print(f"{parser.prog}: {args.trace}: {exc}", file=sys.stderr)
        return 1
    json.dump(report, sys.stdout, indent=2, allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
