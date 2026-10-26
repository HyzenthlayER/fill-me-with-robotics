"""Acceptance tests for the standalone CLI, using original synthetic traces."""

import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CONTRIBUTION = Path(__file__).resolve().parents[1]
CLI = CONTRIBUTION / "analyze.py"
FIXTURE = CONTRIBUTION / "fixtures" / "synthetic.jsonl"
SQUARE = [[0, 0], [2, 0], [2, 2], [0, 2]]


def sample(timestamp=0, zmp=None, polygon=None):
    return {
        "timestamp": timestamp,
        "zmp": [1, 1] if zmp is None else zmp,
        "support_polygon": SQUARE if polygon is None else polygon,
    }


def interval(start, end, timestamps):
    return {
        "start_index": start,
        "end_index": end,
        "start_timestamp": timestamps[start],
        "end_timestamp": timestamps[end],
        "sample_count": end - start + 1,
    }


class AnalyzerCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # On the original repository, fail for the absent capability explicitly,
        # before attempting a subprocess or importing any contribution module.
        if not CLI.is_file():
            raise AssertionError(f"The offline ZMP analyzer CLI must exist: {CLI}")

    def run_path(self, path, *options):
        return subprocess.run(
            [sys.executable, str(CLI), str(path), *options],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def run_text(self, text, *options):
        with tempfile.TemporaryDirectory(prefix="zmp-trace-test-") as directory:
            path = Path(directory) / "trace.jsonl"
            path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
            return self.run_path(path, *options)

    def run_samples(self, records, *options):
        return self.run_text("\n".join(json.dumps(record) for record in records), *options)

    def report(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

        def reject_constant(value):
            self.fail(f"Output must be strict JSON, found {value}")

        report = json.loads(result.stdout, parse_constant=reject_constant)
        self.assertIsInstance(report, dict)
        self.assertEqual(report["sample_count"], len(report["samples"]))
        return report

    def assert_samples(self, report, statuses, distances):
        self.assertEqual(report["sample_count"], len(statuses))
        self.assertEqual([item["status"] for item in report["samples"]], statuses)
        for index, (item, status, distance) in enumerate(
            zip(report["samples"], statuses, distances)
        ):
            with self.subTest(index=index):
                self.assertEqual(item["index"], index)
                self.assertIs(item["included"], status != "outside")
                self.assertTrue(math.isfinite(item["signed_distance"]))
                self.assertTrue(
                    math.isclose(item["signed_distance"], distance, rel_tol=1e-12, abs_tol=1e-15),
                    (item["signed_distance"], distance),
                )
                if status == "boundary":
                    self.assertEqual(item["signed_distance"], 0)

    def assert_input_error(self, payload, line=1, fragment=None):
        result = self.run_text(payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "", "Invalid input must not emit a partial report")
        self.assertIn(f"line {line}:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if fragment is not None:
            self.assertIn(fragment, result.stderr)

    def test_documented_synthetic_fixture(self):
        self.assertTrue(FIXTURE.is_file(), "The documented synthetic fixture must exist")
        report = self.report(self.run_path(FIXTURE))
        self.assertEqual(report["tolerance"], 1e-9)
        self.assert_samples(
            report,
            ["inside", "outside", "outside", "boundary", "boundary", "outside"],
            [1, -1, -math.sqrt(2), 0, 0, -1],
        )
        self.assertEqual(
            report["outside_intervals"],
            [interval(1, 2, [0, 0.1, 0.2]), interval(5, 5, [0, 0.1, 0.2, 0.3, 0.4, 0.5])],
        )

    def test_square_distances_in_both_vertex_orders(self):
        points = [[1, 1], [3, 1], [3, 3], [2, 1], [0, 0], [2, 0], [2, 2], [0, 2]]
        for polygon in (SQUARE, list(reversed(SQUARE))):
            with self.subTest(polygon=polygon):
                report = self.report(self.run_samples([
                    sample(i, p, polygon) for i, p in enumerate(points)
                ]))
                self.assert_samples(
                    report,
                    ["inside", "outside", "outside"] + ["boundary"] * 5,
                    [1, -1, -math.sqrt(2)] + [0] * 5,
                )
                self.assertEqual([s["timestamp"] for s in report["samples"]], list(range(8)))

    def test_concave_polygon_in_both_vertex_orders(self):
        # The missing upper-right quadrant is outside even though it is in the hull.
        concave = [[0, 0], [3, 0], [3, 1], [1, 1], [1, 3], [0, 3]]
        points = [[0.5, 2], [2, 0.5], [2, 2], [1, 2], [1.5, 1.5], [0, 0]]
        for polygon in (concave, list(reversed(concave))):
            with self.subTest(polygon=polygon):
                report = self.report(self.run_samples([
                    sample(i, p, polygon) for i, p in enumerate(points)
                ]))
                self.assert_samples(
                    report,
                    ["inside", "inside", "outside", "boundary", "outside", "boundary"],
                    [0.5, 0.5, -1, 0, -0.5, 0],
                )

    def test_sloping_edges_and_clamped_endpoint_distance(self):
        triangle = [[0, 0], [4, 0], [0, 3]]
        report = self.report(self.run_samples([
            sample(i, p, triangle) for i, p in enumerate([[1, 1], [3, 2], [5, 0], [2, 1.5]])
        ]))
        self.assert_samples(report, ["inside", "outside", "outside", "boundary"], [1, -1, -1, 0])

    def test_collinear_vertices_without_overlapping_edges_are_valid(self):
        polygon = [[0, 0], [1, 0], [2, 0], [2, 2], [0, 2]]
        report = self.report(self.run_samples([sample(polygon=polygon)]))
        self.assert_samples(report, ["inside"], [1])

    def test_support_polygon_can_change_each_sample(self):
        shifted = [[2, 0], [4, 0], [4, 2], [2, 2]]
        report = self.report(self.run_samples([sample(0), sample(1, polygon=shifted), sample(2)]))
        self.assert_samples(report, ["inside", "outside", "inside"], [1, -1, 1])
        self.assertEqual(report["outside_intervals"], [interval(1, 1, [0, 1, 2])])

    def test_default_tolerance_on_both_sides_and_at_threshold(self):
        offsets = [-2e-9, -1e-9, -0.5e-9, 0, 0.5e-9, 1e-9, 2e-9]
        report = self.report(self.run_samples([
            sample(i, [offset, 1]) for i, offset in enumerate(offsets)
        ]))
        self.assert_samples(
            report,
            ["outside", "boundary", "boundary", "boundary", "boundary", "boundary", "inside"],
            [-2e-9, 0, 0, 0, 0, 0, 2e-9],
        )

    def test_custom_tolerance_and_zero_tolerance(self):
        records = [sample(i, [x, 1]) for i, x in enumerate([-0.05, 0, 0.05, -0.2, 0.2])]
        report = self.report(self.run_samples(records, "--tolerance", "0.1"))
        self.assertEqual(report["tolerance"], 0.1)
        self.assert_samples(
            report, ["boundary", "boundary", "boundary", "outside", "inside"], [0, 0, 0, -0.2, 0.2]
        )
        report = self.report(self.run_samples(records, "--tolerance", "0"))
        self.assertEqual(report["tolerance"], 0)
        self.assert_samples(
            report, ["outside", "boundary", "inside", "outside", "inside"], [-0.05, 0, 0.05, -0.2, 0.2]
        )

    def test_intervals_use_sample_adjacency_and_close_on_boundary(self):
        timestamps = [0, 0.1, 0.2, 5, 6, 7, 8, 20, 80]
        points = [[3, 1], [1, 1], [3, 1], [3, 1], [2, 1], [3, 1], [1, 1], [3, 1], [3, 1]]
        report = self.report(self.run_samples([
            sample(t, p) for t, p in zip(timestamps, points)
        ]))
        self.assertEqual(
            report["outside_intervals"],
            [interval(0, 0, timestamps), interval(2, 3, timestamps),
             interval(5, 5, timestamps), interval(7, 8, timestamps)],
        )

    def test_tolerance_boundary_terminates_an_outside_interval(self):
        report = self.report(self.run_samples([
            sample(0, [-1, 1]), sample(1, [-0.5e-9, 1]), sample(2, [-1, 1])
        ]))
        self.assertEqual(
            report["outside_intervals"], [interval(0, 0, [0, 1, 2]), interval(2, 2, [0, 1, 2])]
        )

    def test_all_included_has_no_outside_intervals(self):
        report = self.report(self.run_samples([sample(0), sample(1, [2, 2]), sample(2, [0, 1])]))
        self.assertEqual(report["outside_intervals"], [])

    def test_all_outside_including_single_sample_and_eof(self):
        for timestamps in ([2], [2, 3, 1000]):
            with self.subTest(timestamps=timestamps):
                report = self.report(self.run_samples([sample(t, [3, 1]) for t in timestamps]))
                self.assertEqual(
                    report["outside_intervals"], [interval(0, len(timestamps) - 1, timestamps)]
                )

    def test_empty_file_and_non_json_lines_are_errors(self):
        for text in ("", "\n", "# comment\n", "{", "[]", "null", "true", "42"):
            with self.subTest(text=text):
                self.assert_input_error(text)

    def test_invalid_json_reports_physical_line_without_partial_output(self):
        prefix = json.dumps(sample()) + "\n"
        for text in ("{", "\n", '{"timestamp": 1,}', '{} {}'):
            with self.subTest(text=text):
                self.assert_input_error(prefix + text, line=2)
        self.assert_input_error(prefix.encode() + b"\xff\n", line=2)

    def test_missing_fields(self):
        for field in ("timestamp", "zmp", "support_polygon"):
            with self.subTest(field=field):
                record = sample()
                del record[field]
                self.assert_input_error(json.dumps(record), fragment=field)

    def test_wrong_dimensions_and_coordinate_types(self):
        cases = [
            ("zmp", []), ("zmp", [1]), ("zmp", [1, 1, 1]),
            ("zmp", {"x": 1, "y": 1}), ("zmp", "1,1"), ("zmp", ["1", 1]),
            ("zmp", [None, 1]), ("zmp", [[1], 1]),
            ("support_polygon", {}), ("support_polygon", "square"),
            ("support_polygon", [[0, 0], [2], [0, 2]]),
            ("support_polygon", [[0, 0], [2, 0, 1], [0, 2]]),
            ("support_polygon", [[0, 0], [2, 0], ["0", 2]]),
            ("timestamp", "0"), ("timestamp", None), ("timestamp", [0]),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                record = sample()
                record[field] = value
                self.assert_input_error(json.dumps(record), fragment=field)

    def test_booleans_are_not_numbers(self):
        for value in (True, False):
            for location in ("timestamp", "zmp_x", "zmp_y", "vertex_x", "vertex_y"):
                with self.subTest(value=value, location=location):
                    record = copy.deepcopy(sample())
                    if location == "timestamp":
                        record["timestamp"] = value
                    elif location.startswith("zmp"):
                        record["zmp"][location.endswith("y")] = value
                    else:
                        record["support_polygon"][0][location.endswith("y")] = value
                    self.assert_input_error(json.dumps(record), fragment="boolean")

    def test_nan_infinity_and_overflowing_numbers(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            for field in ("timestamp", "zmp", "support_polygon"):
                with self.subTest(value=value, field=field):
                    record = sample()
                    record[field] = (
                        value if field == "timestamp" else [value, 1] if field == "zmp"
                        else [[0, 0], [2, 0], [value, 2]]
                    )
                    self.assert_input_error(json.dumps(record), fragment="finite")
        for literal in ("1e400", "-1e400", "1" + "0" * 400):
            with self.subTest(literal=literal):
                self.assert_input_error(
                    '{"timestamp": ' + literal + ', "zmp": [1,1], "support_polygon": [[0,0],[2,0],[0,2]]}',
                    fragment="finite",
                )

    def test_duplicate_json_fields_are_rejected(self):
        self.assert_input_error(
            '{"timestamp": 0, "timestamp": 1, "zmp": [1,1], "support_polygon": [[0,0],[2,0],[0,2]]}',
            fragment="duplicate JSON field",
        )

    def test_timestamps_must_strictly_increase(self):
        for second in (0, -1):
            with self.subTest(second=second):
                self.assert_input_error(
                    json.dumps(sample(0)) + "\n" + json.dumps(sample(second)),
                    line=2, fragment="strictly increasing",
                )

    def test_negative_finite_timestamps_are_valid(self):
        report = self.report(self.run_samples([sample(-3), sample(-2.5)]))
        self.assertEqual([s["timestamp"] for s in report["samples"]], [-3, -2.5])

    def test_invalid_polygons(self):
        cases = {
            "empty": [],
            "one vertex": [[0, 0]],
            "two vertices": [[0, 0], [1, 0]],
            "zero-length edge": [[0, 0], [2, 0], [2, 0], [0, 2]],
            "closing duplicate": SQUARE + [[0, 0]],
            "nonadjacent duplicate": [[0, 0], [2, 0], [2, 2], [0, 0], [0, 2]],
            "collinear zero area": [[0, 0], [1, 0], [2, 0]],
            "bow tie": [[0, 0], [2, 2], [0, 2], [2, 0]],
            "crossing with nonzero signed area": [[0, 0], [4, 3], [0, 3], [3, 0]],
            "adjacent backtracking": [[0, 0], [2, 0], [1, 0], [2, 2], [0, 2]],
            "wraparound backtracking": [[1, 0], [3, 0], [3, 2], [0, 2], [0, 0], [2, 0]],
            "nonadjacent touching": [[0, 0], [2, 0], [2, 2], [1, 0], [0, 2]],
            "nonadjacent overlapping": [[0, 0], [4, 0], [4, 3], [1, 3], [1, 0], [3, 0], [3, 2], [0, 2]],
        }
        for name, polygon in cases.items():
            with self.subTest(name=name):
                self.assert_input_error(json.dumps(sample(polygon=polygon)), fragment="support_polygon")

    def test_invalid_geometry_after_valid_sample_reports_line(self):
        self.assert_input_error(
            json.dumps(sample(0)) + "\n" + json.dumps(sample(1, polygon=[[0, 0], [1, 0], [2, 0]])),
            line=2, fragment="support_polygon",
        )

    def test_nonrepresentable_distance_fails_explicitly(self):
        far_square = [[-1e308, 0], [-9e307, 0], [-9e307, 1], [-1e308, 1]]
        self.assert_input_error(
            json.dumps(sample(zmp=[1e308, 0.5], polygon=far_square)), fragment="finite distance"
        )

    def test_large_finite_geometry_does_not_overflow_squared_distance(self):
        large_square = [[0, 0], [2e200, 0], [2e200, 2e200], [0, 2e200]]
        report = self.report(self.run_samples([sample(zmp=[1e200, 1e200], polygon=large_square)]))
        self.assert_samples(report, ["inside"], [1e200])

    def test_small_finite_geometry_does_not_underflow_squared_distance(self):
        small_square = [[0, 0], [2e-200, 0], [2e-200, 2e-200], [0, 2e-200]]
        report = self.report(self.run_samples(
            [sample(zmp=[1e-200, 1e-200], polygon=small_square)], "--tolerance=0"
        ))
        item = report["samples"][0]
        self.assertEqual(item["status"], "inside")
        self.assertTrue(item["included"])
        self.assertGreater(item["signed_distance"], 0)
        self.assertTrue(math.isclose(item["signed_distance"], 1e-200, rel_tol=1e-12))

    def test_subnormal_distance_is_preserved_when_representable(self):
        smallest = math.ulp(0.0)
        triangle = [[0, 0], [smallest, 0], [0, smallest]]
        report = self.report(self.run_samples(
            [sample(zmp=[smallest, smallest], polygon=triangle)], "--tolerance=0"
        ))
        item = report["samples"][0]
        self.assertEqual(item["status"], "outside")
        self.assertFalse(item["included"])
        self.assertEqual(item["signed_distance"], -smallest)

    def test_nonzero_distance_below_float_resolution_is_an_error(self):
        smallest = math.ulp(0.0)
        triangle = [[0, smallest], [1, 0], [1, 1]]
        self.assert_input_error(
            json.dumps(sample(zmp=[smallest, smallest], polygon=triangle)),
            fragment="floating-point resolution",
        )

    def test_invalid_tolerance_is_a_usage_error(self):
        for value in ("-1", "nan", "inf", "-inf", "1e400", "true", "invalid"):
            with self.subTest(value=value):
                result = self.run_samples([sample()], f"--tolerance={value}")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("tolerance", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_missing_input_file(self):
        with tempfile.TemporaryDirectory(prefix="zmp-trace-test-") as directory:
            result = self.run_path(Path(directory) / "missing.jsonl")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("missing.jsonl", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_help_describes_tolerance(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "--help"], capture_output=True, text=True, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--tolerance", result.stdout)
        self.assertIn("JSON Lines", result.stdout)


if __name__ == "__main__":
    unittest.main()
