import type { ComponentType } from "react";

import { CacheDemo } from "./components/CacheDemo";
import { CardsDemo } from "./components/CardsDemo";
import { EarningsDemo } from "./components/EarningsDemo";
import { FactorDemo } from "./components/FactorDemo";
import { ScheduleDemo } from "./components/ScheduleDemo";
import { TrieDemo } from "./components/TrieDemo";
import {
  BitcoinDemo,
  StockBondDemo,
  WeatherDemo,
} from "./components/QuantDemos";
import {
  ChurnDemo,
  FakeNewsDemo,
  RecommendDemo,
  ThreatsDemo,
} from "./components/NotebookDemos";

/**
 * Project slug -> live demo. A project without an entry simply renders its
 * write-up, so adding a demo never requires touching the detail panel.
 */
export const DEMOS: Record<string, { title: string; component: ComponentType }> = {
  "factor-based-portfolio-simulator": {
    title: "Run the backtest",
    component: FactorDemo,
  },
  "earnings-drift-tracker": {
    title: "Explore the drift",
    component: EarningsDemo,
  },
  "web-crawler-and-search-engine": {
    title: "Search the index",
    component: TrieDemo,
  },
  "course-catalog-scheduling-system": {
    title: "Build a schedule",
    component: ScheduleDemo,
  },
  "card-game-system": {
    title: "Play a round",
    component: CardsDemo,
  },
  "performance-optimization": {
    title: "Watch the cache evict",
    component: CacheDemo,
  },
  "customer-churn-prediction": {
    title: "See what the model caught and missed",
    component: ChurnDemo,
  },
  "fake-news-detection": {
    title: "See why this one does not work",
    component: FakeNewsDemo,
  },
  "global-security-threats": {
    title: "Explore the clusters",
    component: ThreatsDemo,
  },
  "personalized-recommendations-for-e-commerce": {
    title: "Explore the catalogue",
    component: RecommendDemo,
  },
  "stock-bond-portfolio-analysis": {
    title: "Solve the allocation",
    component: StockBondDemo,
  },
  "bitcoin-and-asset-trading": {
    title: "See the model against a one-line baseline",
    component: BitcoinDemo,
  },
  "weather-trends-and-forecast": {
    title: "Chart the trend",
    component: WeatherDemo,
  },
};

export function hasDemo(slug: string): boolean {
  return slug in DEMOS;
}
