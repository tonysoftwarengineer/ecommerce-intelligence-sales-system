import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(frontendRoot, "..");
const apiPort = process.env.E2E_API_PORT ?? "8000";
const frontendPort = process.env.E2E_FRONTEND_PORT ?? "5173";
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const frontendBaseUrl = `http://127.0.0.1:${frontendPort}`;
const apiPython = process.env.E2E_PYTHON ?? (
  process.env.CI ? "python3" : path.join(projectRoot, ".venv", "bin", "python")
);

// Never reuse a server that happens to be running: a stale one silently tests old
// code. If a port is busy the run fails loudly instead. Opt in with
// E2E_REUSE_SERVER=1 when you deliberately want to test against your own dev server.
const reuseExistingServer = process.env.E2E_REUSE_SERVER === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
  ],
  use: {
    baseURL: frontendBaseUrl,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: (
        `${JSON.stringify(apiPython)} -m uvicorn api.main:app --host 127.0.0.1 ` +
        `--port ${apiPort} ` +
        "--lifespan off"
      ),
      cwd: projectRoot,
      env: {
        RAG_RETRIEVAL_BACKEND: "tfidf",
        RAG_RELEVANCE_THRESHOLD: "0.12",
        RAG_ANSWER_PROVIDER: "fake",
      },
      url: `${apiBaseUrl}/api/v1/health`,
      reuseExistingServer,
      timeout: 30_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      cwd: frontendRoot,
      env: { VITE_API_URL: apiBaseUrl },
      url: frontendBaseUrl,
      reuseExistingServer,
      timeout: 30_000,
    },
  ],
});
