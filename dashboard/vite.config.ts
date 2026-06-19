import path from "node:path";
import react from "@vitejs/plugin-react-swc";
import { componentTagger } from "lovable-tagger";
import { defineConfig } from "vite";

const VENDOR_CHUNKS: Array<[string, string[]]> = [
  ["nivo", ["/node_modules/@nivo/"]],
  ["recharts", ["/node_modules/recharts/"]],
  ["d3", ["/node_modules/d3-"]],
  ["radix-ui", ["/node_modules/@radix-ui/"]],
  ["react-core", ["/node_modules/react/", "/node_modules/react-dom/", "/node_modules/react-router-dom/"]],
  ["query", ["/node_modules/@tanstack/"]],
];

function dashboardManualChunk(id: string): string | undefined {
  const normalizedId = id.replaceAll("\\", "/");
  for (const [chunkName, prefixes] of VENDOR_CHUNKS) {
    if (prefixes.some((prefix) => normalizedId.includes(prefix))) {
      return chunkName;
    }
  }
  if (normalizedId.includes("/node_modules/")) {
    return "vendor";
  }
  return undefined;
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 18835,
    allowedHosts: ["airbox"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18834",
        changeOrigin: true,
        ws: false,
      },
    },
    hmr: {
      overlay: false,
    },
  },
  plugins: [react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: dashboardManualChunk,
      },
    },
  },
}));
