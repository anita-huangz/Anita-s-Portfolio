/**
 * Plain-English definitions for the jargon in the demos.
 *
 * The demos are configurable, which is only useful if you know what you are
 * configuring. "Hold top 3" and "Rebalance quarterly" are levers with real
 * consequences and no meaning at all to someone who has not met them before,
 * and a portfolio nobody can operate is a portfolio nobody can judge.
 *
 * Two rules for the text. **No term is defined using another undefined term** —
 * a definition that needs a second lookup has not explained anything. And each
 * entry says what the number is *for*, not just what it measures: "above 1 is
 * good, and easy to inflate with a short sample" is the part that lets a reader
 * decide whether to believe the figure on screen.
 *
 * `aliases` exist because the same idea appears under several labels across the
 * demos (Annualised / Annualized, Sharpe / Sharpe ratio).
 */

export interface GlossaryEntry {
  /** The heading shown in the popover. */
  term: string;
  /** The definition. Two or three sentences, no jargon of its own. */
  body: string;
  /** What it means for the thing on screen right now. Optional. */
  here?: string;
  /** Other labels that should resolve to this entry. */
  aliases?: string[];
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // ----------------------------------------------------------------- markets
  backtest: {
    term: "Backtest",
    body:
      "Running a strategy over past prices to see what it would have done. It " +
      "is not evidence that the strategy will work — it is a check that the " +
      "rules are coherent and that the result is not an accident of one lucky " +
      "stretch.",
    here:
      "Every number here comes from real daily closes, replayed one day at a " +
      "time. No money was ever at risk.",
  },
  factor: {
    term: "Factor",
    body:
      "A measurable characteristic of a company that has historically lined up " +
      "with its future returns — how much its price has risen lately, how " +
      "steady that price is, how cheap it looks against its earnings. A factor " +
      "strategy scores every company in its list on that characteristic and " +
      "buys the highest scorers.",
    here:
      "Pick more than one and the scores are combined, so a company has to do " +
      "well on both to be bought.",
    aliases: ["factors"],
  },
  momentum: {
    term: "Momentum",
    body:
      "The observation that shares which have risen over the past year tend to " +
      "keep rising for a while longer. Nobody fully agrees on why; the usual " +
      "explanations are that investors react to news slowly, or that they chase " +
      "what is already going up.",
    here: "Measured as the return over the previous 252 trading days, about one year.",
  },
  "low-volatility": {
    term: "Low volatility",
    body:
      "Shares whose price moves less from day to day. Historically they have " +
      "delivered returns comparable to jumpier shares while putting their " +
      "holders through smaller swings, which is a better deal for the same " +
      "destination.",
    here: "Measured from the spread of daily moves over the previous 21 trading days.",
    aliases: ["low volatility"],
  },
  universe: {
    term: "Universe",
    body:
      "The list of companies a strategy is allowed to buy. It matters more than " +
      "it sounds: a strategy that only ever looks at large, successful " +
      "companies has already made most of its decision before any ranking " +
      "happens.",
  },
  "hold-top": {
    term: "Hold top N",
    body:
      "How many of the ranked companies to actually buy. Holding the top 3 " +
      "means buying the three highest scorers and nothing else.",
    here:
      "Fewer names means more of the outcome rides on each pick — higher " +
      "potential return, and a worse result when one of them is wrong.",
  },
  rebalance: {
    term: "Rebalance",
    body:
      "Re-scoring every company and rebuilding the portfolio to match the new " +
      "ranking. Prices move constantly, so yesterday's best picks are not " +
      "always today's.",
    here:
      "More often follows the signal more closely but trades more, and every " +
      "trade costs money. Monthly here means every 21 trading days.",
    aliases: ["rebalances"],
  },
  nav: {
    term: "NAV",
    body:
      "Net asset value — what the portfolio is worth at a given moment, cash " +
      "and holdings together. Plotting it over time is the most direct picture " +
      "of whether a strategy made or lost money.",
  },
  "total-return": {
    term: "Total return",
    body:
      "The whole gain or loss from the first day to the last, as a percentage. " +
      "It says nothing about the path: +50% could mean a steady climb or a " +
      "crash followed by a recovery.",
  },
  annualised: {
    term: "Annualised return",
    body:
      "The total return restated as a per-year rate, so results over different " +
      "lengths of time can be compared. A 21% gain over three years is about 7% " +
      "a year.",
    aliases: ["annualized", "annualised return", "annualized return"],
  },
  volatility: {
    term: "Volatility",
    body:
      "How much the return bounces around, stated as a per-year figure. Higher " +
      "means a bumpier ride, not necessarily a worse destination — it is a " +
      "measure of uncertainty, not of loss.",
    aliases: ["annualised volatility", "annualized volatility"],
  },
  sharpe: {
    term: "Sharpe ratio",
    body:
      "Return divided by volatility — roughly, how much you were paid for the " +
      "bumpiness. Two strategies returning 10% are not equal if one of them " +
      "got there calmly.",
    here:
      "Above 1 is considered good. It is also easy to inflate with a short " +
      "sample or a well-chosen window, so treat a high number from a few years " +
      "of data with suspicion.",
    aliases: ["sharpe ratio"],
  },
  drawdown: {
    term: "Max drawdown",
    body:
      "The worst fall from a previous high point to the low that followed. If " +
      "it reads 36%, then at some moment the portfolio was worth 36% less than " +
      "its own best day.",
    here:
      "This is the number that decides whether a strategy actually gets held. " +
      "A single figure hides how long the fall lasted, which matters just as " +
      "much as how deep it went.",
    aliases: ["max drawdown", "maximum drawdown"],
  },
  "look-ahead": {
    term: "Look-ahead bias",
    body:
      "Accidentally using information that was not available at the time. A " +
      "strategy that picks 2021 holdings using 2024 prices will look brilliant " +
      "and mean nothing, because nobody could have run it.",
    here:
      "Toggle it on to see the same strategy over the same prices report 95% " +
      "instead of 3%. It is the most common way a backtest lies.",
  },
  benchmark: {
    term: "Benchmark",
    body:
      "A simple standard to measure a strategy against, usually a broad market " +
      "index such as the S&P 500. A strategy up 300% in a period the market " +
      "rose 400% lost money in the only sense that matters.",
  },
  "trading-day": {
    term: "Trading day",
    body:
      "A day the stock market is open — weekdays, minus public holidays, about " +
      "252 a year. Prices do not exist for weekends, so every window here is " +
      "counted in trading days rather than calendar days.",
    aliases: ["trading days", "session", "sessions"],
  },

  // -------------------------------------------------------- earnings / drift
  earnings: {
    term: "Earnings",
    body:
      "A public company's profit, which it must report every three months. " +
      "Analysts at banks publish an estimate of that figure beforehand, and the " +
      "gap between the estimate and the actual number is what moves the share " +
      "price on the day.",
  },
  surprise: {
    term: "Earnings surprise",
    body:
      "How far the reported profit came in above or below what analysts had " +
      "estimated, as a percentage of the estimate. +10% means the company " +
      "earned a tenth more than expected.",
    here:
      "The whole question here is whether a bigger surprise is followed by a " +
      "bigger move in the weeks afterwards.",
    aliases: ["earnings surprise", "median surprise"],
  },
  drift: {
    term: "Post-earnings drift",
    body:
      "The tendency for a share to keep moving in the direction of its earnings " +
      "surprise for weeks after the announcement, rather than adjusting all at " +
      "once on the day. If it is real, the market absorbs news more slowly than " +
      "it is supposed to.",
    aliases: ["post-earnings drift", "pead"],
  },
  abnormal: {
    term: "Abnormal return",
    body:
      "A share's return with the market's return over the same days subtracted. " +
      "It isolates the part of the move that was about this company rather than " +
      "about everything going up or down together.",
    here:
      "It matters a lot: the raw drift here is +1.43% and the abnormal drift is " +
      "+0.43%, so two thirds of the apparent effect was just the market.",
    aliases: ["abnormal return", "abnormal drift", "market-adjusted"],
  },
  "beat-rate": {
    term: "Beat rate",
    body:
      "The share of announcements where the company reported more profit than " +
      "analysts estimated. It usually sits well above half, because estimates " +
      "tend to be set at a level companies can clear.",
    aliases: ["beat rate"],
  },
  quintile: {
    term: "Quintile",
    body:
      "One fifth of a sorted list. Splitting announcements into surprise " +
      "quintiles puts the 20% biggest surprises in one bucket and the 20% " +
      "smallest in another, so the two extremes can be compared directly.",
    aliases: ["quintiles"],
  },
  "t-stat": {
    term: "t-statistic",
    body:
      "A measure of whether a difference is bigger than the noise around it. " +
      "Above about 2 is the usual bar for calling a result unlikely to be " +
      "chance — it is a test of whether the effect is detectable, not of " +
      "whether it is large enough to be useful.",
    aliases: ["t-statistic", "t stat"],
  },

  // ------------------------------------------------------------------- cache
  cache: {
    term: "Cache",
    body:
      "A store of answers already worked out, so the same question does not " +
      "have to be answered twice. Caching is how a slow function becomes a fast " +
      "one, and almost everything you use is doing it somewhere.",
  },
  "hit-rate": {
    term: "Hit rate",
    body:
      "The share of requests the cache could answer from memory. A hit is free; " +
      "a miss means doing the real work. This is the single number that says " +
      "whether a cache is earning its keep.",
    aliases: ["hit rate", "hits", "misses"],
  },
  capacity: {
    term: "Capacity",
    body:
      "How many answers the cache is allowed to keep. Memory is finite, so once " +
      "it is full, storing something new means throwing something else out.",
  },
  eviction: {
    term: "Eviction",
    body:
      "Throwing an entry out of a full cache to make room. Which one to throw " +
      "is the whole design problem: get it wrong and you discard the entry you " +
      "were about to need.",
    aliases: ["evictions", "evicted"],
  },
  lru: {
    term: "LRU",
    body:
      "Least Recently Used. When the cache is full, discard whatever has gone " +
      "untouched for longest. It assumes that what you used just now is what " +
      "you will use next, which is true surprisingly often.",
    here:
      "Its weakness is a scan: read ten thousand things once each and LRU " +
      "throws away everything useful to make room for them.",
  },
  lfu: {
    term: "LFU",
    body:
      "Least Frequently Used. When the cache is full, discard whatever has been " +
      "asked for fewest times. It protects a popular entry from being pushed " +
      "out by a crowd of one-off requests.",
    here:
      "Its weakness is the mirror image: when what is popular changes, the old " +
      "favourites have counts the newcomers can never catch, so they sit there " +
      "forever serving nobody.",
  },
  ttl: {
    term: "TTL",
    body:
      "Time to live — how long a cached answer stays usable before it has to be " +
      "worked out again. An exchange rate is not wrong to cache, it is wrong to " +
      "cache forever.",
    aliases: ["time to live"],
  },

  // ------------------------------------------------------------------ search
  crawler: {
    term: "Crawler",
    body:
      "A program that fetches a web page, finds the links on it, fetches those, " +
      "and keeps going. It is how a search engine discovers what exists before " +
      "it can index anything.",
    aliases: ["crawl"],
  },
  trie: {
    term: "Trie",
    body:
      "A tree that stores words one letter per level, so all the words " +
      "beginning \"par\" hang below the same branch. That shape makes " +
      "\"everything starting with par\" a short walk down the tree instead of a " +
      "scan through every word you know.",
  },
  bm25: {
    term: "BM25",
    body:
      "The standard way to score how relevant a page is to a query. It rewards " +
      "a page for using your words often, discounts words that appear " +
      "everywhere and so distinguish nothing, and adjusts for page length so a " +
      "long page cannot win by simply containing more text.",
    here:
      "Try \"park\": the short page wins on fewer mentions, because 4 mentions " +
      "in 32 words is denser than 5 in 64.",
    aliases: ["score"],
  },
  and: {
    term: "AND search",
    body:
      "Requiring every word you typed to appear, rather than any of them. Two " +
      "words almost always means both — an any-of search buries the good " +
      "results under pages that merely used the commoner word.",
  },
  wildcard: {
    term: "Wildcard",
    body:
      "A placeholder standing in for characters you do not want to spell out. " +
      "Here `?` matches exactly one character, so `d?g` finds dog and dig, and a " +
      "trailing `*` matches any ending, so `par*` finds park, parks and parking.",
  },

  // ---------------------------------------------------------------- schedule
  section: {
    term: "Section",
    body:
      "One of several sittings of the same course, at different times with " +
      "different instructors. You take one of them, never two — which is why " +
      "picking the right section is most of the work in building a timetable.",
    aliases: ["sections"],
  },
  conflict: {
    term: "Conflict",
    body:
      "Two classes whose times overlap, so you cannot attend both. A class " +
      "ending at 19:30 and one starting at 19:30 do not conflict — they are " +
      "back to back.",
    aliases: ["clash", "conflicts"],
  },
  cost: {
    term: "Cost",
    body:
      "How annoying a schedule is, in minutes. An extra day on campus is priced " +
      "at 60, an hour of dead time between classes at 30, a class on a day you " +
      "asked to keep free at 480. Lower is better.",
    here:
      "Everything is in one unit on purpose, so the total means something " +
      "instead of being an arbitrary score, and `why:` shows what drove it.",
  },
  "proven-optimal": {
    term: "Proven optimal",
    body:
      "Whether the search checked enough possibilities to be certain nothing " +
      "better exists, or simply ran out of budget first. \"The best there is\" " +
      "and \"the best I had time to find\" are different claims, and reporting " +
      "the second as the first would be the real bug.",
    aliases: ["nodes", "nodes searched"],
  },

  // ------------------------------------------------------------------- cards
  "expected-points": {
    term: "Expected points",
    body:
      "The average score you would get from a choice if you made it over and " +
      "over. A one-in-twenty shot at 2000 points is worth more than a certain " +
      "50, even though it usually pays nothing.",
    aliases: ["pts", "expected value"],
  },
  "exact-vs-sampled": {
    term: "Exact vs sampled",
    body:
      "Throwing one card away has 45 possible replacements and two has 990, so " +
      "every outcome can simply be counted — those answers are exact. Five " +
      "discards has 1,221,759, too many to count, so a few hundred are drawn at " +
      "random and averaged instead.",
    here:
      "`±` is the margin on a sampled figure. It is widest where one rare huge " +
      "payoff can swing the average, which is a property of the game rather " +
      "than a flaw in the estimate.",
    aliases: ["exact", "sampled"],
  },
  "monte-carlo": {
    term: "Monte Carlo",
    body:
      "Answering a question you cannot compute by trying it at random many " +
      "times and averaging. Used whenever the number of possibilities is too " +
      "large to count but easy to sample from.",
  },

  // ----------------------------------------------------- models & statistics
  accuracy: {
    term: "Accuracy",
    body:
      "The share of predictions that were right. It is the most quoted measure " +
      "and often the least useful: if 3% of customers leave, predicting \"nobody " +
      "leaves\" scores 97% and is worthless.",
  },
  precision: {
    term: "Precision",
    body:
      "Of the cases the model flagged, how many it got right. Low precision " +
      "means crying wolf — you chase customers who were never going to leave.",
  },
  recall: {
    term: "Recall",
    body:
      "Of the cases that really happened, how many the model caught. Low recall " +
      "means quietly missing most of them, which an accuracy score will not " +
      "show you.",
  },
  f1: {
    term: "F1",
    body:
      "A single number blending precision and recall, so a model cannot look " +
      "good by being cautious or by flagging everything. It sits between the " +
      "two, closer to the worse one.",
  },
  auc: {
    term: "ROC AUC",
    body:
      "How well the model separates the two groups, from 0.5 (no better than a " +
      "coin flip) to 1.0 (perfect). Unlike accuracy it does not depend on where " +
      "you set the cut-off, so it measures ranking rather than a decision.",
    aliases: ["roc auc"],
  },
  threshold: {
    term: "Decision threshold",
    body:
      "The score above which the model says yes. Moving it trades the two kinds " +
      "of mistake against each other: catch more real cases, and flag more " +
      "people who were fine.",
    here: "Drag it and watch precision and recall move in opposite directions.",
    aliases: ["decision threshold"],
  },
  "confusion-matrix": {
    term: "Confusion matrix",
    body:
      "A two-by-two count of what the model said against what actually " +
      "happened. The diagonal is the cases it got right; the other two cells " +
      "are the two different ways of being wrong.",
  },
  rmse: {
    term: "RMSE",
    body:
      "Root mean squared error — the typical size of the model's mistake, in " +
      "the units being predicted. An RMSE of $1,400 on a bitcoin price means " +
      "predictions are off by roughly that much, and big misses count for more " +
      "than small ones.",
  },
  mape: {
    term: "MAPE",
    body:
      "Mean absolute percentage error — the typical mistake as a percentage " +
      "rather than an amount. Useful when the thing being predicted changes " +
      "scale, since being $1,000 out matters differently at $20,000 and at " +
      "$60,000.",
  },
  baseline: {
    term: "Naive baseline",
    body:
      "The dumbest prediction that is not obviously stupid — here, \"tomorrow " +
      "will be the same as today\". Every model has to beat it to have earned " +
      "its complexity, and a surprising number do not.",
    here:
      "This one does not: the baseline scores an RMSE of $1,401 and the neural " +
      "network $22,283.",
    aliases: ["naive rmse", "naive"],
  },
  "directional-accuracy": {
    term: "Directional accuracy",
    body:
      "How often the model got the direction right — up or down — regardless of " +
      "by how much. It matters more than the size of the error for anything you " +
      "would trade on, because only the change is tradeable.",
    here:
      "49% here, which is a coin flip. A chart can track a price level " +
      "convincingly while carrying no information about its changes.",
    aliases: ["directional accuracy"],
  },
  lstm: {
    term: "LSTM",
    body:
      "A kind of neural network built for sequences, which keeps a memory of " +
      "what it has seen so far. Popular for price prediction, and prone to " +
      "learning to repeat the most recent value — which looks impressive on a " +
      "chart and predicts nothing.",
  },
  lookback: {
    term: "Lookback window",
    body:
      "How many past days the model is shown before it makes each prediction. " +
      "Longer gives it more context and fewer examples to learn from.",
    aliases: ["lookback window"],
  },
  "train-test": {
    term: "Train / test split",
    body:
      "Fitting the model on one stretch of history and grading it on a later " +
      "stretch it has never seen. Grading a model on the data it learned from " +
      "measures memory, not prediction.",
    aliases: ["train / test days", "train/test"],
  },
  pca: {
    term: "Principal component",
    body:
      "A way of squashing many columns down to two so they can be drawn. The " +
      "first component is the single direction along which the data varies " +
      "most; the second is the next, at right angles to it. The axes are " +
      "mixtures of the original columns, so distance means \"similar\" and the " +
      "numbers on the axes mean nothing by themselves.",
    aliases: ["first principal component", "second principal component", "pca"],
  },
  clustering: {
    term: "Clustering",
    body:
      "Grouping records by similarity with nobody having labelled them first. " +
      "It always returns groups, which is the trap: there is no ground truth to " +
      "check them against, so a clean-looking split can be an artefact of the " +
      "columns you happened to feed it.",
    aliases: ["k-means", "dbscan", "cluster"],
  },
  anomaly: {
    term: "Anomaly detection",
    body:
      "Finding the records that do not look like the rest. Useful for flagging " +
      "things worth a human look, but \"unusual\" and \"important\" are not the " +
      "same thing and nothing in the method knows the difference.",
    aliases: ["isolation forest", "flagged anomalous", "anomalous"],
  },

  // ----------------------------------------------------- portfolio optimiser
  "expected-return": {
    term: "Expected return",
    body:
      "The average yearly return an allocation would have produced, estimated " +
      "from past data. \"Expected\" is a statistical word, not a promise — it is " +
      "the centre of a range, and the range is wide.",
    aliases: ["expected return"],
  },
  frontier: {
    term: "Efficient frontier",
    body:
      "The curve of the best available trade-offs: for each level of bumpiness, " +
      "the mix that historically returned the most. Anything below the curve is " +
      "strictly worse than something on it, so there is no reason to hold it.",
    aliases: ["efficient frontier"],
  },
  "risk-preference": {
    term: "Risk preference",
    body:
      "How much return you are willing to give up for a smoother ride. At one " +
      "end the optimiser only minimises bumpiness and ends up almost entirely " +
      "in short-term government bonds; at the other it reaches for return and " +
      "takes on shares.",
    here: "Drag it and watch the whole allocation move.",
    aliases: ["risk preference"],
  },
  etf: {
    term: "ETF",
    body:
      "A single tradeable fund holding a basket of things — every share in the " +
      "S&P 500, or a spread of government bonds. It is how one purchase buys " +
      "a whole market.",
    aliases: ["etfs"],
  },
  "treasuries": {
    term: "Treasuries",
    body:
      "Loans to the US government, which pays them back with interest. Treated " +
      "as the safest thing available, so they are where an allocation goes when " +
      "it is told to avoid risk at any cost.",
    aliases: ["short treasuries"],
  },

  // ------------------------------------------------------------------ weather
  reanalysis: {
    term: "Reanalysis",
    body:
      "A reconstruction of past weather that blends real measurements with a " +
      "physics model to fill the gaps, giving a complete hourly record " +
      "everywhere. It is the closest thing to historical weather observations " +
      "for places and times nobody was measuring.",
    aliases: ["era5"],
  },
  "warming-rate": {
    term: "Warming rate",
    body:
      "How fast average temperature is rising, in degrees per decade, fitted as " +
      "a straight line through the record. A projection from it is that line " +
      "extended — not a climate model, and year-to-year variation is larger " +
      "than a decade of trend.",
    aliases: ["warming rate"],
  },
};

/** Lower-cased label → entry id, including every alias. */
const LOOKUP: Record<string, string> = {};
for (const [id, entry] of Object.entries(GLOSSARY)) {
  LOOKUP[id.toLowerCase()] = id;
  LOOKUP[entry.term.toLowerCase()] = id;
  for (const alias of entry.aliases ?? []) LOOKUP[alias.toLowerCase()] = id;
}

/** Resolve an id, a term, or an alias to an entry. */
export function lookupTerm(key: string): GlossaryEntry | undefined {
  return GLOSSARY[LOOKUP[key.trim().toLowerCase()]];
}

export const GLOSSARY_IDS = Object.keys(GLOSSARY);
