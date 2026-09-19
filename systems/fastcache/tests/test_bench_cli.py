"""The benchmark's command line. It produces the tables quoted in the README,
so a change that breaks it silently invalidates the documentation.

Timings are never asserted — a test that fails when the machine is busy is
worse than no test. What is asserted is that each mode runs, that the numbers
it prints are in range, and that the policy comparison covers every policy.
"""

import pytest

from fastcache.benchmark import compare_policies, main


class TestTimingMode:
    def test_the_default_sweep_runs(self, capsys):
        assert main(["--calls", "500", "--sizes", "8,64"]) == 0
        out = capsys.readouterr().out
        assert "fastcache" in out and "functools" in out

    def test_it_reports_every_size_asked_for(self, capsys):
        assert main(["--calls", "400", "--sizes", "8,64,256"]) == 0
        out = capsys.readouterr().out
        for size in ("8", "64", "256"):
            assert size in out


class TestPolicyMode:
    def test_it_compares_all_three_policies(self, capsys):
        assert main(["--policies", "--calls", "2000", "--keys", "200",
                     "--cache-size", "40"]) == 0
        out = capsys.readouterr().out
        for label in ("LRU", "LFU", "W-TinyLFU"):
            assert label in out

    def test_every_workload_gets_a_hit_rate_for_every_policy(self):
        results = compare_policies(keys=200, calls=2000, max_size=40)
        assert len(results) >= 5
        for workload, byp in results.items():
            assert set(byp) == {"lru", "lfu", "tinylfu"}, workload
            for policy, (rate, micros) in byp.items():
                assert 0.0 <= rate <= 1.0, f"{workload}/{policy}"
                assert micros > 0, f"{workload}/{policy}"

    def test_a_pure_scan_hits_nothing_under_any_policy(self):
        """The one result that is a fact about the workload, not the machine."""
        results = compare_policies(keys=400, calls=2000, max_size=40)
        for rate, _ in results["sequential scan"].values():
            assert rate == 0.0

    def test_the_window_can_be_fixed_from_the_command_line(self, capsys):
        assert main(["--policies", "--calls", "2000", "--keys", "200",
                     "--cache-size", "40", "--window", "0.4"]) == 0
        assert capsys.readouterr().out.strip()


class TestWindowSweep:
    def test_it_prints_a_row_per_fraction(self, capsys):
        assert main(["--window-sweep", "0.05,0.5", "--calls", "2000",
                     "--keys", "200", "--cache-size", "40"]) == 0
        out = capsys.readouterr().out
        assert "5%" in out and "50%" in out
        assert "LRU" in out and "LFU" in out, "the baselines belong in the table"

    def test_the_global_default_is_restored_afterwards(self, capsys):
        from fastcache.policy import TinyLFUPolicy

        before = TinyLFUPolicy.WINDOW_FRACTION
        main(["--window-sweep", "0.4", "--calls", "1000", "--keys", "100",
              "--cache-size", "20"])
        capsys.readouterr()
        assert before == TinyLFUPolicy.WINDOW_FRACTION


def test_help_exits_cleanly():
    with pytest.raises(SystemExit) as exit:
        main(["--help"])
    assert exit.value.code == 0
