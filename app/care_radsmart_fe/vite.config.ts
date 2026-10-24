import federation from "@originjs/vite-plugin-federation";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    federation({
      name: "care_radsmart",
      filename: "remoteEntry.js",
      // `./manifest` is the ONLY thing the host can import. It is also the only
      // guaranteed load-time hook for side-effectful registrations.
      exposes: { "./manifest": "./src/manifest.tsx" },
      // The host shares these, so the plugin uses its router, query client and toasts.
      shared: ["react", "react-dom", "react-i18next", "@tanstack/react-query", "raviger", "sonner"],
    }),
    tailwindcss(),
    react(),
  ],
  build: {
    target: "esnext",
    minify: true,
    // Remote CSS is not auto-injected by the host; don't depend on packages shipping their own.
    cssCodeSplit: false,
    modulePreload: { polyfill: false },
    rollupOptions: {
      external: [],
      input: { main: "./index.html" },
      output: { format: "esm" },
    },
  },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  preview: {
    port: 19102,
    host: "127.0.0.1",
    strictPort: true,
    cors: true,
    allowedHosts: true,
  },
});
