import { hasDemo } from "../demos/registry";
import { CATEGORY_LABELS } from "../data/types";
import type { Category, Project } from "../data/types";

export const CATEGORY_COLOR: Record<Category, string> = {
  "ai-platform": "var(--ai)",
  "software-engineering": "var(--se)",
  "data-science": "var(--ds)",
};

export function CategoryTag({ category }: { category: Category }) {
  return (
    <span className="tag" style={{ color: CATEGORY_COLOR[category] }}>
      {/* Dot plus label: the category never depends on colour alone. */}
      <span className="dot" style={{ background: CATEGORY_COLOR[category] }} />
      {CATEGORY_LABELS[category]}
    </span>
  );
}

interface Props {
  project: Project;
  onOpen: (project: Project) => void;
  baseUrl: string;
}

export function ProjectCard({ project, onOpen, baseUrl }: Props) {
  // A project may ship a light and a dark capture. Both are rendered and CSS
  // shows whichever matches the active theme — the site's theme is a data
  // attribute set by its own toggle, not just a media query, so `<picture>`
  // with `prefers-color-scheme` would ignore the toggle and leave a blazing
  // white screenshot on a dark card.
  const [light, dark] = [project.images?.[0], project.images?.[1]];

  return (
    <button
      className={`card${project.featured ? " featured" : ""}`}
      onClick={() => onOpen(project)}
      aria-label={`Open details for ${project.title}`}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-head">
          <CategoryTag category={project.category} />
          {project.tests !== undefined && (
            <span className="tests">✓ {project.tests} tests</span>
          )}
          {hasDemo(project.slug) && <span className="live">▶ Live demo</span>}
        </div>
        <h3>{project.title}</h3>
        <p>{project.summary}</p>
        <div className="techrow">
          {project.tech.slice(0, project.featured ? 8 : 5).map((t) => (
            <span className="tech" key={t}>
              {t}
            </span>
          ))}
          {project.tech.length > (project.featured ? 8 : 5) && (
            <span className="tech">
              +{project.tech.length - (project.featured ? 8 : 5)}
            </span>
          )}
        </div>
      </div>

      {project.featured && light && (
        <div className="shot-frame">
          <img
            className={`shot${dark ? " light-only" : ""}`}
            src={`${baseUrl}${light.src}`}
            alt={light.alt}
            loading="lazy"
          />
          {dark && (
            <img
              className="shot dark-only"
              src={`${baseUrl}${dark.src}`}
              alt={dark.alt}
              loading="lazy"
            />
          )}
        </div>
      )}
    </button>
  );
}
