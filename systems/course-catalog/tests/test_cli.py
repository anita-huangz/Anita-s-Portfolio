"""The command line and the snapshot writer, exercised offline.

Between them these were 163 untested statements — the largest gap in the
project, and the reason it sat at 74% while everything around it was in the
high eighties.

Every test here uses the bundled CSV. `--quarter` fetches from the department
live and is covered by the fetcher's own tests with an injected client; a suite
that reached the network would fail in CI, which runs offline.
"""

import csv

import pytest

from course_catalog.cli import main
from course_catalog.snapshot import write_csv


class TestSearch:
    def test_it_lists_the_bundled_catalog(self, capsys):
        assert main([]) == 0
        assert capsys.readouterr().out.strip()

    def test_a_code_prefix_filters(self, capsys):
        assert main(["--code", "MPCS 55001"]) == 0
        out = capsys.readouterr().out
        assert "55001" in out

    def test_a_keyword_matches_title_or_instructor(self, capsys):
        assert main(["--keyword", "algorithms"]) == 0
        assert capsys.readouterr().out.strip()

    def test_a_day_filter_runs(self, capsys):
        assert main(["--day", "Tue"]) == 0
        assert capsys.readouterr().out.strip()

    def test_an_impossible_filter_says_so_rather_than_printing_nothing(self, capsys):
        # Silence on an empty result reads as a crash. The count and the filter
        # that produced it both have to appear, so the user can see it was the
        # query that matched nothing rather than the catalogue that failed.
        assert main(["--code", "MPCS 99999"]) == 0
        out = capsys.readouterr().out
        assert "0 course(s)" in out
        assert "MPCS 99999" in out


class TestScheduleBuilding:
    def test_it_builds_a_schedule(self, capsys):
        assert main(["--build", "3", "--options", "1"]) == 0
        out = capsys.readouterr().out
        assert "cost" in out.lower()

    def test_preferences_are_honoured_as_costs_not_crashes(self, capsys):
        assert main([
            "--build", "3", "--options", "1",
            "--no-earlier-than", "10am", "--days-off", "Fri,Sat,Sun",
        ]) == 0
        assert "cost" in capsys.readouterr().out.lower()

    def test_a_hard_days_off_constraint_runs(self, capsys):
        assert main([
            "--build", "2", "--options", "1",
            "--days-off", "Sat,Sun", "--strict-days-off",
        ]) == 0
        assert capsys.readouterr().out.strip()

    def test_it_reports_how_much_of_the_search_it_did(self, capsys):
        assert main(["--build", "3", "--options", "1"]) == 0
        assert "nodes" in capsys.readouterr().out.lower()

    def test_an_unbuildable_size_is_reported_not_raised(self, capsys):
        """More courses than the catalog can supply conflict-free."""
        assert main(["--build", "99", "--options", "1"]) in (0, 1)
        captured = capsys.readouterr()
        assert (captured.out + captured.err).strip()


class TestBadInput:
    def test_a_missing_csv_is_reported_not_raised(self, capsys):
        assert main(["--csv", "does-not-exist.csv"]) == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_an_unparseable_time_is_reported(self, capsys):
        # 2 rather than 1: a malformed argument is a usage error, which is what
        # argparse itself returns. A missing file above is a runtime failure
        # and returns 1. The split is deliberate and worth pinning.
        assert main(["--build", "2", "--no-earlier-than", "half past ten"]) == 2
        assert "error" in capsys.readouterr().err.lower()

    def test_an_unknown_flag_exits_nonzero(self):
        with pytest.raises(SystemExit) as exit:
            main(["--not-a-real-flag"])
        assert exit.value.code != 0

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0


class TestSnapshotWriter:
    def test_it_round_trips_through_the_loader(self, tmp_path, capsys):
        """A snapshot nobody can read back is not a snapshot."""
        from course_catalog.mpcs import parse_listing

        # A tbody is required: the parser anchors on it rather than on the
        # table, because the page wraps its header row in a thead.
        html = (
            "<table><tbody><tr><td>MPCS 51040-1</td><td>Intro</td>"
            "<td>A Teacher</td><td>Monday 6:00pm - 8:00pm</td></tr></tbody></table>"
        )
        courses = parse_listing(html)
        out = tmp_path / "snap.csv"
        write_csv(courses, out)

        rows = list(csv.DictReader(out.open()))
        assert len(rows) == len(courses)
        assert main(["--csv", str(out)]) == 0
        assert capsys.readouterr().out.strip()

    def test_it_writes_a_header_even_with_no_courses(self, tmp_path):
        out = tmp_path / "empty.csv"
        write_csv([], out)
        assert out.read_text().strip(), "an empty file would not be loadable"
