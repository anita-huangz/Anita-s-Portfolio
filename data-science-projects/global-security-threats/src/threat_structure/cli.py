"""Run the analysis and print it. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

from .anomalies import detector_agreement, tail_checks
from .clustering import compare_with_null, gap_statistic, stability
from .data import load
from .structure import associations, balance, uniformity

RULE = "-" * 74


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def structure(data) -> None:
    _heading("IS THERE ANY STRUCTURE TO FIND?")
    uniform = uniformity(data)
    print("  Kolmogorov-Smirnov against a uniform on each column's own range:")
    for name, row in uniform.frame.iterrows():
        print(f"    {name[:44]:<46} D={row['D']:.4f}  p={row['p']:.3f}")
    print(f"  -> every numeric column is flat: {uniform.all_uniform}")
    print("     (Real loss figures are heavy-tailed. Flat ones were generated.)")

    balanced = balance(data)
    print("\n  chi-square against equal category frequencies:")
    for name, row in balanced.frame.iterrows():
        print(f"    {name:<30} chi2={row['chi2']:>7.2f}  p={row['p']:.3f}")
    print(f"  -> clears p<0.05: {balanced.unbalanced or 'none'}, and "
          f"{balanced.expected_false_positives:.2f} were expected by chance")
    print(f"  -> consistent with every column being balanced: "
          f"{balanced.consistent_with_chance}")

    linked = associations(data)
    pair, strength = linked.strongest_categorical
    print(f"\n  strongest association between any two categories: {pair}, V={strength:.4f}")
    print(f"  strongest correlation between any two numerics:   {linked.strongest_numeric:.4f}")
    print(f"  -> the columns are independent: {linked.independent}")
    print("\n  Every column is an independent draw. There is no joint structure")
    print("  for a clustering method to find.")


def clusters(data, k: int, draws: int) -> None:
    _heading(f"THE CLUSTERS, JUDGED AGAINST A NULL (k={k})")
    null = compare_with_null(data, k=k, draws=draws)
    print(f"  silhouette on the real data              {null.observed:.4f}")
    print(f"  silhouette on independently shuffled     {null.null_mean:.4f} "
          f"+/- {null.null_std:.4f}")
    print(f"  z = {null.z_score:+.2f},  p = {null.p_value:.3f}  "
          f"(floor {null.smallest_possible_p:.3f})")
    print(f"  -> better than noise: {null.better_than_noise}")
    print("\n  The shuffle keeps every column's marginal exactly and destroys")
    print("  every relationship between them. The score does not move, so what")
    print("  k-means found was geometry.")

    firm = stability(data, k=k, draws=max(12, draws // 2))
    low, high = firm.interval
    print(f"\n  bootstrap stability, adjusted Rand index  {firm.mean_ari:.3f} "
          f"[{low:.3f}, {high:.3f}]")
    print(f"  -> reproducible: {firm.stable}  (0.75 is the usual bar)")

    gap = gap_statistic(data, max_k=6, references=8)
    print("\n  gap statistic:")
    for value, row in gap.frame.iterrows():
        print(f"    k={value}  gap {row['gap']:+.4f}  s_k {row['s_k']:.4f}")
    print(f"  -> chooses k = {gap.best_k}; says there are no clusters: "
          f"{gap.says_no_clusters}")
    print("\n  This is the only criterion here that *can* say that. Silhouette")
    print("  and elbow plots are undefined at k=1, so they are structurally")
    print("  incapable of reporting 'no clusters' however hard you squint.")


def anomalies(data) -> None:
    _heading("THE OUTLIER DETECTORS, AGAINST EACH OTHER")
    agreement = detector_agreement(data)
    print(f"  Isolation Forest flagged {agreement.flagged_a}, LOF flagged "
          f"{agreement.flagged_b}, overlap {agreement.overlap}")
    print(f"  chance overlap would be {agreement.expected_overlap:.1f}")
    print(f"  Jaccard {agreement.jaccard:.4f},  overlap / chance = "
          f"{agreement.excess:.2f}x")
    print(f"  -> they agree: {agreement.agree}")
    print("\n  Which is NOT validation. Both rank distance from the centre of")
    print("  the same cloud, so they agree on uniform noise too. It rules out")
    print("  one of them being broken and says nothing about the rows.")

    print("\n  where do the flagged rows sit in each column's distribution?")
    for check in tail_checks(data):
        print(f"    percentile {check.flagged_mean_percentile:.3f}  "
              f"{check.column[:44]:<46} just a tail: {check.is_just_a_tail}")
    print("\n  Not in any single column's tail, so the machinery is finding")
    print("  rare *combinations* of categories -- which, on independent")
    print("  uniform columns, occur at random.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None)
    parser.add_argument("-k", type=int, default=4)
    parser.add_argument("--draws", type=int, default=25)
    parser.add_argument(
        "--section",
        choices=["all", "structure", "clusters", "anomalies"],
        default="all",
    )
    args = parser.parse_args(argv)

    try:
        data = load(args.csv) if args.csv else load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(data):,} incidents, {data.encoded().shape[1]} encoded columns")
    want = args.section
    if want in {"all", "structure"}:
        structure(data)
    if want in {"all", "clusters"}:
        clusters(data, args.k, args.draws)
    if want in {"all", "anomalies"}:
        anomalies(data)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
