export const EXPECTED_API_VERSION = "v1";
export const FRONTEND_VERSION = "1.0.0";

export function validateRuntimeConfig(value) {
  if (!value || typeof value !== "object") {
    throw new Error("runtime-config.json не содержит объект");
  }
  const apiBaseUrl = String(value.apiBaseUrl || "").replace(/\/+$/, "");
  let parsed;
  try {
    parsed = new URL(apiBaseUrl);
  } catch {
    throw new Error("apiBaseUrl не является URL");
  }
  const isLocalHttp =
    parsed.protocol === "http:" &&
    (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost");
  if (parsed.protocol !== "https:" && !isLocalHttp) {
    throw new Error("apiBaseUrl должен использовать HTTPS; HTTP допустим только локально");
  }
  if (!apiBaseUrl.endsWith("/api/v1")) {
    throw new Error("apiBaseUrl должен оканчиваться на /api/v1");
  }
  const configVersion = Number(value.configVersion);
  if (!Number.isInteger(configVersion) || configVersion < 1) {
    throw new Error("configVersion должен быть положительным целым числом");
  }
  return {
    apiBaseUrl,
    generatedAt: value.generatedAt ? String(value.generatedAt) : null,
    configVersion,
    appVersion: value.appVersion ? String(value.appVersion) : null,
    apiVersion: value.apiVersion ? String(value.apiVersion) : EXPECTED_API_VERSION,
  };
}

export class RuntimeConfigStore {
  constructor({
    fetchImpl = globalThis.fetch,
    documentBase = globalThis.document?.baseURI || "http://localhost/",
  } = {}) {
    this.fetchImpl = fetchImpl;
    this.url = new URL("runtime-config.json", documentBase);
    this.current = null;
    this.listeners = new Set();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async load() {
    const requestUrl = new URL(this.url);
    requestUrl.searchParams.set("ts", String(Date.now()));
    const response = await this.fetchImpl(requestUrl, {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) {
      throw new Error(`runtime-config.json: HTTP ${response.status}`);
    }
    const next = validateRuntimeConfig(await response.json());
    const previous = this.current;
    this.current = next;
    if (
      previous &&
      (previous.configVersion !== next.configVersion ||
        previous.apiBaseUrl !== next.apiBaseUrl)
    ) {
      for (const listener of this.listeners) {
        listener(next, previous);
      }
    }
    return next;
  }
}

