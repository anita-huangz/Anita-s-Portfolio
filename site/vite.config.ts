import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Published as a GitHub *user* site (repo `anita-huangz.github.io`), which
// serves from the domain root -- so no path prefix, in dev or in the build.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    // The large chunks are lazily-imported demo *data*, not code: the price
    // file is fetched only when someone opens the backtest. Warning at 500 kB
    // would flag that by design on every build.
    chunkSizeWarningLimit: 800,
  },
});
