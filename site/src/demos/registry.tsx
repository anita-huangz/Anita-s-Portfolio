import type { ComponentType } from "react";

import { CacheDemo } from "./components/CacheDemo";
import { CardsDemo } from "./components/CardsDemo";
import { EarningsDemo } from "./components/EarningsDemo";
import { FactorDemo } from "./components/FactorDemo";
import { ScheduleDemo } from "./components/ScheduleDemo";
import { TrieDemo } from "./components/TrieDemo";

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
};

export function hasDemo(slug: string): boolean {
  return slug in DEMOS;
}
