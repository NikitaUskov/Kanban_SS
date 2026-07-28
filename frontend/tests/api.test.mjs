import assert from "node:assert/strict";
import test from "node:test";

import { ApiClient, ApiError, TokenStore } from "../assets/js/api.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("token store splits access and refresh storage and clears both", () => {
  globalThis.sessionStorage = new MemoryStorage();
  globalThis.localStorage = new MemoryStorage();
  const store = new TokenStore();
  store.setPair({
    access_token: "access",
    refresh_token: "refresh",
    expires_in: 100,
  });
  assert.equal(sessionStorage.getItem("kanban.accessToken"), "access");
  assert.equal(localStorage.getItem("kanban.refreshToken"), "refresh");
  store.clear();
  assert.equal(store.accessToken, null);
  assert.equal(store.refreshToken, null);
});

test("one refresh is attempted after 401 and original request is retried", async () => {
  globalThis.sessionStorage = new MemoryStorage();
  globalThis.localStorage = new MemoryStorage();
  globalThis.window = {
    clearTimeout() {},
    setTimeout() {
      return 1;
    },
  };
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    if (calls.length === 1) {
      return jsonResponse(
        { error: { code: "TOKEN_EXPIRED", message: "Истёк" } },
        401,
      );
    }
    if (calls.length === 2) {
      return jsonResponse({
        access_token: "new-access",
        refresh_token: "new-refresh",
        expires_in: 43_200,
      });
    }
    return jsonResponse({ items: [] });
  };

  const client = new ApiClient({
    current: { apiBaseUrl: "https://api.example.test/api/v1" },
  });
  client.tokens.setPair({
    access_token: "old-access",
    refresh_token: "old-refresh",
    expires_in: 1,
  });
  const result = await client.request("/boards");
  assert.deepEqual(result, { items: [] });
  assert.equal(calls.length, 3);
  assert.equal(client.tokens.accessToken, "new-access");
  assert.equal(client.tokens.refreshToken, "new-refresh");
});

test("network failure returns a safe reconnecting error", async () => {
  globalThis.sessionStorage = new MemoryStorage();
  globalThis.localStorage = new MemoryStorage();
  let unavailable = false;
  globalThis.fetch = async () => {
    throw new TypeError("socket details must not be exposed");
  };
  const client = new ApiClient(
    { current: { apiBaseUrl: "https://api.example.test/api/v1" } },
    { onUnavailable: () => { unavailable = true; } },
  );
  await assert.rejects(
    client.request("/health", { auth: false }),
    (error) =>
      error instanceof ApiError &&
      error.code === "NETWORK_ERROR" &&
      !error.message.includes("socket"),
  );
  assert.equal(unavailable, true);
});
