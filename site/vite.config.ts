import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Published as a GitHub *user* site (repo `anita-huangz.github.io`), which
// serves from the domain root -- so no path prefix, in dev or in the build.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "dist" },
});
