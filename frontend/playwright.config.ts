import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:8765", trace: "retain-on-failure" },
  webServer: {
    command: "../.venv/bin/python ../scripts/web_test_server.py",
    url: "http://127.0.0.1:8765",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
