import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Deployed as a GitHub *project* page, so assets live under /<repo>/ rather
// than the domain root. `vite build --mode local` emits root-relative paths
// for a local `vite preview`.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "local" ? "/" : "/Anita-s-Portfolio/",
  build: { outDir: "dist" },
}));
