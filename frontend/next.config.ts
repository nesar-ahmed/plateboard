import type { NextConfig } from "next";

// Where the FastAPI backend lives. The rewrite destination is resolved when
// this file is evaluated (build/dev start), so override per environment:
//   API_ORIGIN=http://127.0.0.1:8000 npm run build
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Self-hosted build: `next build` emits a minimal, dependency-trimmed Node
  // server at .next/standalone/server.js - the mode designed for running the
  // frontend as its own process (pm2 / systemd / Docker) behind an nginx
  // reverse proxy. Requires the asset copy step in package.json `postbuild`.
  output: "standalone",

  // `next dev` otherwise (re)generates an AGENTS.md for AI coding agents;
  // this flag makes Next remove the file instead.
  agentRules: false,

  // Forwards /api/* to the backend. Behind nginx this is a no-op (nginx
  // routes /api itself); it exists for hitting the Next server directly:
  // `next dev` locally, or a pm2-only VPS without a /api nginx rule.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },

  reactCompiler: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
