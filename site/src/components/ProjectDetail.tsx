import { useEffect, useRef } from "react";

import { DEMOS } from "../demos/registry";
import type { Project } from "../data/types";
import { CategoryTag } from "./ProjectCard";
import { Terminal } from "./Terminal";

const REPO = "https://github.com/anita-huangz/anita-huangz.github.io";

interface Props {
  project: Project;
  onClose: () => void;
  baseUrl: string;
}

export function ProjectDetail({ project, onClose, baseUrl }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const demo = DEMOS[project.slug];

  // Escape closes, and focus moves into the sheet so keyboard users are not
  // left behind on the card underneath.
  useEffect(() => {
    sheetRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className={`sheet${demo ? " wide" : ""}`}
        ref={sheetRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={project.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-head">
          <div>
            <CategoryTag category={project.category} />
            <h2>{project.title}</h2>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="lede">{project.detail}</p>

        {demo && (
          <>
            <h4>{demo.title} — live, in your browser</h4>
            {/*
              The demos are configurable, which only helps if you know what you
              are configuring. Dotted terms carry a definition, and saying so
              once here is cheaper than hoping the underline is noticed.
            */}
            <p className="demo-legend">
              Everything below is interactive. Terms marked{" "}
              <span className="term-sample">
                like this<span className="term-mark" aria-hidden="true">?</span>
              </span>{" "}
              explain themselves — hover or click for a plain-English
              definition. No finance or statistics background needed.
            </p>
            <demo.component />
          </>
        )}

        {project.io && (
          <dl className="io">
            <div>
              <dt>In</dt>
              <dd>{project.io.input}</dd>
            </div>
            <div>
              <dt>Out</dt>
              <dd>{project.io.output}</dd>
            </div>
            {project.io.scale && (
              <div>
                <dt>Scale</dt>
                <dd>{project.io.scale}</dd>
              </div>
            )}
          </dl>
        )}

        <div className="techrow">
          {project.tech.map((t) => (
            <span className="tech" key={t}>
              {t}
            </span>
          ))}
        </div>

        {project.images && project.images.length > 0 && (
          <>
            <h4>Interface</h4>
            {project.images.map((img) => (
              <img
                key={img.src}
                className="shot"
                src={`${baseUrl}${img.src}`}
                alt={img.alt}
                loading="lazy"
              />
            ))}
          </>
        )}

        {project.highlights && project.highlights.length > 0 && (
          <>
            <h4>What's interesting</h4>
            <ul>
              {project.highlights.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          </>
        )}

        {project.output && (
          <>
            <h4>Actual output</h4>
            <Terminal caption={project.output.caption} text={project.output.text} />
          </>
        )}

        {project.sources && project.sources.length > 0 && (
          <>
            <h4>Data sources</h4>
            <ul className="sources">
              {project.sources.map((src) => (
                <li key={src.url}>
                  <a href={src.url} target="_blank" rel="noreferrer">
                    {src.label}
                  </a>
                  {src.note && <span className="source-note">{src.note}</span>}
                </li>
              ))}
            </ul>
          </>
        )}

        <div className="sheet-links">
          <a
            className="primary"
            href={`${REPO}/tree/main/${project.path}`}
            target="_blank"
            rel="noreferrer"
          >
            View source
          </a>
          <a
            href={`${REPO}/blob/main/${project.path}/README.md`}
            target="_blank"
            rel="noreferrer"
          >
            Read the write-up
          </a>
          {project.tests !== undefined && (
            <span className="tests" style={{ alignSelf: "center", marginLeft: 4 }}>
              ✓ {project.tests} tests, running offline in CI
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
