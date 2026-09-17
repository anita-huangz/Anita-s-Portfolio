# Portfolio site

The project showcase at
**[anita-huangz.github.io](https://anita-huangz.github.io/)**.

![The portfolio site](docs/screenshot.png)

A static React + Vite single-page app: a filterable grid of every project in
the repository, with a detail panel per project covering the design decisions,
the bugs that were fixed, and real captured output.

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # production bundle for GitHub Pages
npm run preview   # serve the built bundle locally
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
- **No base path.** This is a GitHub *user* site (the repository is named
  `anita-huangz.github.io`), so it publishes at the domain root. A project
  page would need `base: "/<repo>/"` instead.

Deployed by [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) on
every push to `main` that touches `site/`.
