export type Category = "llm-platform" | "systems" | "markets" | "inference";

export interface Project {
  slug: string;
  title: string;
  category: Category;
  /** One line. Shown on the card. */
  summary: string;
  /** A few sentences. Shown in the detail panel. */
  detail: string;
  /**
   * What goes in and what comes out, concretely. Abstract descriptions of a
   * project tell a reader its category, not what it actually does.
   */
  io?: { input: string; output: string; scale?: string };
  tech: string[];
  /** Repository-relative path to the project. */
  path: string;
  /**
   * Where the data comes from. A result is only as trustworthy as its input,
   * so the reader should be able to go look at it.
   */
  sources?: { label: string; url: string; note?: string }[];
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
  "llm-platform": "LLM Platform",
  "systems": "Systems",
  "markets": "Quantitative Finance",
  "inference": "Statistical Inference",
};
