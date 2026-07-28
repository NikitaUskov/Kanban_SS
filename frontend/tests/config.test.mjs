import assert from "node:assert/strict";
import test from "node:test";

import { RuntimeConfigStore, validateRuntimeConfig } from "../assets/js/config.js";

test("runtime config accepts HTTPS API v1", () => {
  const value = validateRuntimeConfig({
    apiBaseUrl: "https://sample.trycloudflare.com/api/v1",
    generatedAt: "2026-07-27T12:00:00Z",
    configVersion: 5,
    appVersion: "1.1.0",
    apiVersion: "v1",
  });
  assert.equal(value.configVersion, 5);
  assert.equal(value.apiBaseUrl, "https://sample.trycloudflare.com/api/v1");
});

test("runtime config rejects non-local HTTP", () => {
  assert.throws(
    () =>
      validateRuntimeConfig({
        apiBaseUrl: "http://example.com/api/v1",
        configVersion: 1,
      }),
    /HTTPS/,
  );
});

test("store reports a changed tunnel without page reload", async () => {
  const responses = [
    {
      apiBaseUrl: "https://first.trycloudflare.com/api/v1",
      configVersion: 1,
    },
    {
      apiBaseUrl: "https://second.trycloudflare.com/api/v1",
      configVersion: 2,
    },
  ];
  const store = new RuntimeConfigStore({
    documentBase: "https://owner.github.io/repository/",
    fetchImpl: async () => ({
      ok: true,
      json: async () => responses.shift(),
    }),
  });
  let changed = null;
  store.subscribe((next, previous) => {
    changed = { next, previous };
  });
  await store.load();
  await store.load();
  assert.equal(changed.previous.configVersion, 1);
  assert.equal(changed.next.configVersion, 2);
});

