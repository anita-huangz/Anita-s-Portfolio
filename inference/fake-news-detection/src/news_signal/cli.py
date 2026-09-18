"""Run the analysis and print it. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

from .data import TEXT_COLUMNS, label_index_correlation, load, template_report
from .signal import (
    cross_validated_auc,
    feature_tests,
    gradient_boosting,
    learning_curve,
    minimum_detectable_auc,
    permutation_test,
)

RULE = "-" * 74


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def contents(data) -> None:
    _heading("WHAT IS ACTUALLY IN THE FILE")
    print(f"  {'column':<10}{'distinct':>10}{'skeletons':>11}{'templated':>12}")
    for column in TEXT_COLUMNS:
        if column not in data.frame:
            continue
        report = template_report(data.frame, column)
        print(
            f"  {column:<10}{report.distinct:>10,}{report.distinct_after_removing_digits:>11,}"
            f"{report.is_templated!s:>12}"
        )
    title = template_report(data.frame, "title")
    body = template_report(data.frame, "text")
    print(f"\n  title[0]: {title.example!r}")
    print(f"  text[0] : {body.example[:72]!r}")
    print("\n  Strip the digits and 4,000 distinct titles become one. The text is")
    print("  the row index in prose, so a TF-IDF model over it is a model of the")
    print("  row number.")
    print(f"\n  label against row order: r = {label_index_correlation(data):+.4f}")
    print("  (Near zero, so the file is shuffled. Had it been sorted, a text")
    print("  model would have scored well by reading the number.)")


def signal(data, permutations: int) -> None:
    _heading("IS THERE ANY SIGNAL?")
    simple = cross_validated_auc(data)
    boosted = cross_validated_auc(data, gradient_boosting())
    print(f"  logistic regression, 5-fold out-of-fold AUC  {simple:.4f}")
    print(f"  gradient boosting, 200 trees                 {boosted:.4f}")
    print("  Extra capacity finds nothing, which points at the data not the model.")

    result = permutation_test(data, permutations=permutations)
    low, high = result.null_interval()
    print(f"\n  permutation test, {result.permutations} shuffles of the label:")
    print(f"    observed                 {result.observed:.4f}")
    print(f"    shuffled-label null      {result.null_mean:.4f} +/- {result.null_std:.4f}")
    print(f"    95% of shuffles fall in  [{low:.4f}, {high:.4f}]")
    print(f"    z = {result.z_score:+.2f},  p = {result.p_value:.3f}")
    verdict = "ARE" if result.distinguishable else "are NOT"
    print(f"    -> the real labels {verdict} distinguishable from random ones.")
    print("\n  Only the labels are shuffled, so every feature-feature correlation")
    print("  survives and only the relationship being tested is destroyed.")


def power(data) -> None:
    _heading("WHAT THAT RULES OUT")
    effect = minimum_detectable_auc(len(data), int(data.label.sum()))
    print(f"  {effect.summary}.")
    print(f"  The observed AUC is {cross_validated_auc(data):.4f}, below that threshold.")
    print("\n  This is the number that turns \"we found nothing\" into \"there is")
    print("  nothing bigger than this to find\", which is the stronger claim and")
    print("  the one a reader needs. Without it, no signal and not enough data")
    print("  to see the signal look identical.")

    curve = learning_curve(data)
    print("\n  learning curve:")
    for size, score in zip(curve.sizes, curve.scores, strict=True):
        print(f"    {size:>5,} rows -> AUC {score:.4f}")
    print(f"    slope {curve.slope:+.4f} AUC per 1,000 rows")
    print(f"    -> more data would help: {curve.improves_with_data}")


def features(data) -> None:
    _heading("PER-FEATURE TESTS, CORRECTED FOR TESTING MANY")
    result = feature_tests(data)
    print(f"  {'feature':<20}{'r':>9}{'p':>10}{'BH threshold':>15}{'reject':>9}")
    for name, row in result.frame.head(8).iterrows():
        print(
            f"  {name:<20}{row['r']:>+9.4f}{row['p']:>10.4f}"
            f"{row['bh_threshold']:>15.4f}{bool(row['reject'])!s:>9}"
        )
    print(f"\n  significant after correction: {result.significant or 'none'}")
    print(
        f"  Testing {len(result.frame)} features at p<0.05 produces about "
        f"{result.expected_false_positives:.2f} false"
    )
    print("  positives by chance, so an uncorrected result here means little.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--permutations", type=int, default=150)
    parser.add_argument(
        "--section",
        choices=["all", "contents", "signal", "power", "features"],
        default="all",
    )
    args = parser.parse_args(argv)

    try:
        data = load(args.csv) if args.csv else load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(data):,} articles, {data.fake_rate:.1%} labelled fake")
    want = args.section
    if want in {"all", "contents"}:
        contents(data)
    if want in {"all", "signal"}:
        signal(data, args.permutations)
    if want in {"all", "power"}:
        power(data)
    if want in {"all", "features"}:
        features(data)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
