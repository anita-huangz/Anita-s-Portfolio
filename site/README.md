# Portfolio site

The project showcase at
**[anita-huangz.github.io/Anita-s-Portfolio](https://anita-huangz.github.io/Anita-s-Portfolio/)**.

![The portfolio site](docs/screenshot.png)

A static React + Vite single-page app: a filterable grid of every project in
the repository, with a detail panel per project covering the design decisions,
the bugs that were fixed, and real captured output.

```bash
npm install
npm run dev            # http://localhost:5173
npm run build          # production bundle for GitHub Pages
npm run build -- --mode local && npm run preview   # preview with root-relative paths
```

## Notes

- **The terminal output is real.** It was captured by running each project and
  pasted into [`src/data/projects.ts`](src/data/projects.ts), not written by
  hand. When a project's behaviour changes, re-run it and update the string.
- **Project content is data, not markup.** Adding a project means one entry in
  `projects.ts`; no component changes.
- **Category colour is always paired with a text label**, so identity never
  rests on hue alone. Light and dark are both selected from a validated palette
  against their own surface rather than being an automatic inversion.
- **`base` differs by build.** GitHub project pages serve from
  `/Anita-s-Portfolio/`, so that's the default; `--mode local` emits
  root-relative paths for `vite preview`.

Deployed by [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) on
every push to `main` that touches `site/`.
