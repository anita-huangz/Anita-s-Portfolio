"""Content-based recommendation, scored leave-one-out against a random baseline."""

from .data import (
    BrowsingLeak,
    Catalogue,
    Customers,
    SchemaError,
    browsing_leak,
    load_catalogue,
    load_customers,
)
from .evaluate import Evaluation, leave_one_out
from .metrics import (
    RankingScores,
    average_precision,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_rankings,
)
from .recommenders import (
    Context,
    browsing_oracle,
    different_category,
    popularity,
    random_ranking,
    same_category,
    similar_products,
)

__all__ = [
    "BrowsingLeak",
    "Catalogue",
    "Context",
    "Customers",
    "Evaluation",
    "RankingScores",
    "SchemaError",
    "average_precision",
    "browsing_leak",
    "browsing_oracle",
    "different_category",
    "leave_one_out",
    "load_catalogue",
    "load_customers",
    "ndcg_at_k",
    "popularity",
    "precision_at_k",
    "random_ranking",
    "recall_at_k",
    "reciprocal_rank",
    "same_category",
    "score_rankings",
    "similar_products",
]
