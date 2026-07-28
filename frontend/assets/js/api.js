export class ApiError extends Error {
  constructor(status, code, message, details = {}, requestId = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export class TokenStore {
  constructor() {
    this.accessKey = "kanban.accessToken";
    this.accessExpiresKey = "kanban.accessExpiresAt";
    this.refreshKey = "kanban.refreshToken";
  }

  get accessToken() {
    return sessionStorage.getItem(this.accessKey);
  }

  get refreshToken() {
    return localStorage.getItem(this.refreshKey);
  }

  get accessExpiresAt() {
    return Number(sessionStorage.getItem(this.accessExpiresKey) || 0);
  }

  setPair(pair) {
    sessionStorage.setItem(this.accessKey, pair.access_token);
    sessionStorage.setItem(
      this.accessExpiresKey,
      String(Date.now() + Number(pair.expires_in) * 1000),
    );
    localStorage.setItem(this.refreshKey, pair.refresh_token);
  }

  clear() {
    sessionStorage.removeItem(this.accessKey);
    sessionStorage.removeItem(this.accessExpiresKey);
    localStorage.removeItem(this.refreshKey);
  }
}

export class ApiClient {
  constructor(configStore, callbacks = {}) {
    this.configStore = configStore;
    this.tokens = new TokenStore();
    this.callbacks = callbacks;
    this.refreshPromise = null;
    this.refreshTimer = null;
    this.compatible = true;
  }

  get baseUrl() {
    const value = this.configStore.current?.apiBaseUrl;
    if (!value) throw new Error("API URL ещё не загружен");
    return value;
  }

  setCompatible(value) {
    this.compatible = Boolean(value);
  }

  scheduleRefresh() {
    window.clearTimeout(this.refreshTimer);
    const delay = Math.max(1_000, this.tokens.accessExpiresAt - Date.now() - 60_000);
    this.refreshTimer = window.setTimeout(() => {
      this.refresh().catch(() => this.callbacks.onUnauthorized?.());
    }, delay);
  }

  async parseError(response) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // Empty or non-JSON infrastructure response.
    }
    const error = body?.error || {};
    return new ApiError(
      response.status,
      error.code || `HTTP_${response.status}`,
      error.message || `Ошибка сервера: HTTP ${response.status}`,
      error.details || {},
      error.requestId || response.headers.get("X-Request-ID"),
    );
  }

  async rawRequest(path, options = {}, retryOn401 = true) {
    const method = options.method || "GET";
    if (!this.compatible && !["GET", "HEAD"].includes(method)) {
      throw new ApiError(
        409,
        "API_VERSION_INCOMPATIBLE",
        "Версии интерфейса и API несовместимы. Дождитесь обновления GitHub Pages",
      );
    }
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (this.tokens.accessToken && options.auth !== false) {
      headers.set("Authorization", `Bearer ${this.tokens.accessToken}`);
    }
    headers.set("X-Request-ID", crypto.randomUUID());
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        cache: method === "GET" ? "no-store" : "default",
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
      this.callbacks.onConnected?.();
    } catch (error) {
      this.callbacks.onUnavailable?.(error);
      throw new ApiError(0, "NETWORK_ERROR", "Сервер недоступен. Выполняется переподключение");
    }
    if (
      response.status === 401 &&
      retryOn401 &&
      options.auth !== false &&
      this.tokens.refreshToken
    ) {
      await this.refresh();
      return this.rawRequest(path, options, false);
    }
    if (!response.ok) throw await this.parseError(response);
    if (response.status === 204) return null;
    return response.json();
  }

  request(path, options = {}) {
    return this.rawRequest(path, options, true);
  }

  async login(username, password) {
    const pair = await this.rawRequest(
      "/auth/login",
      { method: "POST", auth: false, body: { username, password } },
      false,
    );
    this.tokens.setPair(pair);
    this.scheduleRefresh();
    return pair;
  }

  async refresh() {
    if (this.refreshPromise) return this.refreshPromise;
    const refreshToken = this.tokens.refreshToken;
    if (!refreshToken) {
      this.tokens.clear();
      throw new ApiError(401, "REFRESH_MISSING", "Требуется повторный вход");
    }
    this.refreshPromise = (async () => {
      let response;
      try {
        response = await fetch(`${this.baseUrl}/auth/refresh`, {
          method: "POST",
          cache: "no-store",
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": crypto.randomUUID(),
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch (error) {
        this.callbacks.onUnavailable?.(error);
        throw new ApiError(0, "NETWORK_ERROR", "Сервер недоступен");
      }
      if (!response.ok) {
        this.tokens.clear();
        throw await this.parseError(response);
      }
      const pair = await response.json();
      this.tokens.setPair(pair);
      this.scheduleRefresh();
      return pair;
    })();
    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
  }

  async logout() {
    const refreshToken = this.tokens.refreshToken;
    try {
      if (refreshToken && this.tokens.accessToken) {
        await this.request("/auth/logout", {
          method: "POST",
          body: { refresh_token: refreshToken },
        });
      }
    } finally {
      this.tokens.clear();
      window.clearTimeout(this.refreshTimer);
    }
  }
}

