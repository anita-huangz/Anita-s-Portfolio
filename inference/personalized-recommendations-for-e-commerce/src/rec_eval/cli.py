"""Run the evaluation and print it. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

from .data import browsing_leak, load_catalogue, load_customers
from .evaluate import leave_one_out
from .recommenders import (
    browsing_oracle,
    category_share_of_similar_lists,
    different_category,
    expected_category_share,
    popularity,
    probability_column_correlations,
    random_ranking,
    same_category,
    similar_products,
)

RULE = "-" * 74


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def what_the_data_is(customers, catalogue) -> None:
    _heading("WHAT THE DATA SUPPORTS")
    print(f"  {len(customers):,} customers, {len(catalogue):,} products, "
          f"{len(catalogue.subcategories)} shared subcategories")
    print("\n  There is no user-item interaction matrix. Purchase history is a")
    print("  list of subcategory *names*, and product IDs appear nowhere in the")
    print("  customer table -- so collaborative filtering is undefined here, not")
    print("  merely hard. Content-based recommendation over the 24 shared")
    print("  subcategories is what the data supports.")

    leak = browsing_leak(customers, catalogue)
    print(f"\n  browsing covers a purchased category for {leak.matching:,}"
          f"/{leak.customers:,} customers = {leak.rate:.4f}")
    print(f"  -> purchases were generated from browsing: {leak.is_deterministic}")

    observed = category_share_of_similar_lists(catalogue)
    print(f"\n  Similar_Product_List entries in the listing product's category: "
          f"{observed:.4f}")
    print(f"  (chance would be {expected_category_share(catalogue):.4f})")

    correlations = probability_column_correlations(catalogue)
    print("\n  Probability_of_Recommendation correlates with nothing; the")
    print(f"  strongest is {correlations.max():.4f} against "
          f"{correlations.index[0]}.")
    print("  It was the notebook's regression target.")


def evaluate(customers, catalogue, k: int) -> None:
    _heading(f"LEAVE-ONE-OUT RANKING, k={k}")
    recommenders = {
        "random": random_ranking(),
        "popularity": popularity(catalogue),
        "same category": same_category(catalogue),
        "different category": different_category(catalogue),
        "similar-product graph": similar_products(catalogue),
        "browsing (ORACLE)": browsing_oracle(catalogue),
    }
    result = leave_one_out(customers, catalogue, recommenders, k=k)
    print(f"  {result.evaluated:,} customers evaluated, {result.excluded:,} "
          "excluded for having a single purchase\n")
    print(f"  {'recommender':<22}{'recall@' + str(k):>10}{'prec@' + str(k):>11}"
          f"{'MAP@' + str(k):>10}{'MRR':>8}{'NDCG@' + str(k):>9}")
    for score in result.scores:
        print("  " + score.row())

    chance = result.named("random").ndcg
    print("\n  Every customer's purchases sit in distinct categories, so the")
    print("  obvious content rule -- more of the same -- ranks the held-out")
    print(f"  item's category *last*. It scores "
          f"{chance / max(result.named('same category').ndcg, 1e-9):.0f}x worse than random.")
    print("  Its inverse beats random, on this dataset and no other.")
    print("\n  The oracle reaches recall@5 = 1.0000 because browsing names the")
    print("  held-out category exactly. A recommender that good on this data is")
    print("  a bug report, not a result.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", default=None)
    parser.add_argument("--products", default=None)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument(
        "--section", choices=["all", "data", "evaluate"], default="all"
    )
    args = parser.parse_args(argv)

    try:
        catalogue = (
            load_catalogue(args.products) if args.products else load_catalogue()
        )
        customers = (
            load_customers(args.customers) if args.customers else load_customers()
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.section in {"all", "data"}:
        what_the_data_is(customers, catalogue)
    if args.section in {"all", "evaluate"}:
        evaluate(customers, catalogue, args.k)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
