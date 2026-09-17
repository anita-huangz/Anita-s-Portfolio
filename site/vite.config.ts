import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Deployed as a GitHub *project* page, so the built site lives under
// /<repo>/ rather than the domain root. The dev server and `vite preview`
// serve from the root, so only a real build gets the prefix -- otherwise
// `npm run dev` redirects away from localhost:5173 for no reason.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/Anita-s-Portfolio/" : "/",
  build: { outDir: "dist" },
}));
