export type Category = "ai-platform" | "software-engineering" | "data-science";

export interface Project {
  slug: string;
  title: string;
  category: Category;
  /** One line. Shown on the card. */
  summary: string;
  /** A few sentences. Shown in the detail panel. */
  detail: string;
  tech: string[];
  /** Repository-relative path to the project. */
  path: string;
  /** Tests in the project's suite, when it has one. */
  tests?: number;
  /** Bullet points worth calling out. */
  highlights?: string[];
  /** Real captured output, shown in a terminal pane. */
  output?: { caption: string; text: string };
  /** Screenshot filenames under public/. */
  images?: { src: string; alt: string }[];
  /** Marks the lead project. */
  featured?: boolean;
  /**
   * Engineering complexity rank within the category, 1 = most complex.
   * Judged on interacting subsystems, algorithmic depth, and how much domain
   * reasoning the correctness depends on -- not on line count alone.
   */
  rank?: number;
}

export const CATEGORY_LABELS: Record<Category, string> = {
  "ai-platform": "AI Platform",
  "software-engineering": "Software Engineering",
  "data-science": "Data Science",
};
