/**
 * The bundled MPCS catalog, quarter by quarter.
 *
 * The browser cannot fetch <https://mpcs-courses.cs.uchicago.edu/> itself:
 * the site sends no `access-control-allow-origin` header, so the request is
 * blocked before it leaves the page. The quarters are fetched by
 * `site/scripts/generate_demo_data.py` and refreshed weekly by a GitHub
 * Action, which is the same arrangement the price data uses.
 */

import data from "../../data/demos/courses.json";

import type { Course } from "./schedule";

export interface Quarter {
  slug: string;
  label: string;
  /** How many of its courses have a published meeting time. */
  scheduled: number;
  courses: Course[];
}

export interface CatalogData {
  source: string;
  fetched: string;
  default: string;
  quarters: Quarter[];
}

export const CATALOG = data as CatalogData;

/** Quarters the department has published, newest first. */
export const QUARTERS: Quarter[] = CATALOG.quarters;

/**
 * The quarter to open on: the newest one with published meeting times.
 *
 * Not simply the newest. A quarter's course list goes up months before its
 * times do -- Winter 2026-27 was published with all thirty courses and not
 * one meeting time -- and opening the timetable builder on a quarter that
 * cannot be scheduled looks broken rather than early.
 */
export const DEFAULT_QUARTER: Quarter =
  QUARTERS.find((q) => q.slug === CATALOG.default) ?? QUARTERS[0];

export function quarterBySlug(slug: string): Quarter {
  return QUARTERS.find((q) => q.slug === slug) ?? DEFAULT_QUARTER;
}

/** Courses that can actually be placed on a timetable. */
export function scheduledCourses(quarter: Quarter): Course[] {
  return quarter.courses.filter((c) => c.meetings.length > 0);
}
