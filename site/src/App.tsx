import { useEffect, useMemo, useState } from "react";

import { ProjectCard } from "./components/ProjectCard";
import { ProjectDetail } from "./components/ProjectDetail";
import { PROJECTS } from "./data/projects";
import { CATEGORY_LABELS } from "./data/types";
import type { Category, Project } from "./data/types";

const REPO = "https://github.com/anita-huangz/anita-huangz.github.io";
const CATEGORIES = Object.keys(CATEGORY_LABELS) as Category[];
const CATEGORY_COLOR: Record<Category, string> = {
  "llm-platform": "var(--ai)",
  "systems": "var(--se)",
  "markets": "var(--mk)",
  "inference": "var(--ds)",
};

type Theme = "light" | "dark";

export default function App() {
  const [active, setActive] = useState<Category | "all">("all");
  const [open, setOpen] = useState<Project | null>(null);
  const [theme, setTheme] = useState<Theme | null>(null);

  // Published as a user site, so BASE_URL is "/". Read it rather than
  // hardcoding, so asset paths stay correct if the site ever moves under a
  // prefix.
  const baseUrl = import.meta.env.BASE_URL;

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
  }, [theme]);

  const visible = useMemo(() => {
    const pool = active === "all" ? PROJECTS : PROJECTS.filter((p) => p.category === active);
    // Ordered by engineering complexity, most involved first. Projects
    // without a rank keep their authored order, after the ranked ones.
    return [...pool].sort((a, b) => {
      if (a.featured !== b.featured) return a.featured ? -1 : 1;
      if (a.category !== b.category) {
        return CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category);
      }
      return (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER);
    });
  }, [active]);

  const totalTests = useMemo(
    () => PROJECTS.reduce((sum, p) => sum + (p.tests ?? 0), 0),
    [],
  );

  return (
    <>
      <header className="topbar">
        <div className="shell topbar-inner">
          <span className="brand">Anita Huang</span>
          <nav>
            <a href="#projects" className="hide-sm">Projects</a>
            <a href={REPO} target="_blank" rel="noreferrer">GitHub</a>
            <button
              className="ghost-btn"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </nav>
        </div>
      </header>

      <main className="shell">
        <section className="hero">
          <h1>AI platform engineering, backend systems, and quantitative work.</h1>
          <p>
            I build the infrastructure around language models — tool interfaces,
            multi-provider access layers, cost and latency telemetry, and the
            evaluation harnesses that tell you whether any of it actually works.
            Before that, quantitative analysis in finance.
          </p>
          <p>
            Everything below is in one repository. The projects marked with a test
            count run their full suite offline in CI — no network, no API keys.
          </p>

          <div className="links">
            <a className="primary" href="#projects">Browse projects</a>
            <a href={REPO} target="_blank" rel="noreferrer">Source on GitHub</a>
          </div>

          <div className="stats">
            <div className="stat">
              <div className="n">{PROJECTS.length}</div>
              <div className="l">projects</div>
            </div>
            <div className="stat">
              <div className="n">{totalTests}</div>
              <div className="l">tests, all offline</div>
            </div>
            <div className="stat">
              <div className="n">3</div>
              <div className="l">Python versions in CI</div>
            </div>
          </div>
        </section>

        <section id="projects">
          <div className="filters">
            <button
              className="chip"
              aria-pressed={active === "all"}
              onClick={() => setActive("all")}
            >
              All
            </button>
            {CATEGORIES.map((c) => (
              <button
                key={c}
                className="chip"
                aria-pressed={active === c}
                onClick={() => setActive(c)}
              >
                <span className="dot" style={{ background: CATEGORY_COLOR[c] }} />
                {CATEGORY_LABELS[c]}
              </button>
            ))}
            <span className="filter-count">
              {visible.length} of {PROJECTS.length} · most involved first
            </span>
          </div>

          <div className="grid">
            {visible.map((project) => (
              <ProjectCard
                key={project.slug}
                project={project}
                onOpen={setOpen}
                baseUrl={baseUrl}
              />
            ))}
          </div>
        </section>
      </main>

      <footer>
        <div className="shell">
          Built with React and Vite; deployed from this repository by GitHub
          Actions. Terminal output shown on project pages is real — captured by
          running the code, not written by hand.
        </div>
      </footer>

      {open && (
        <ProjectDetail project={open} onClose={() => setOpen(null)} baseUrl={baseUrl} />
      )}
    </>
  );
}
