import "server-only";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(
      status
        ? "The backend request could not be completed."
        : "The backend could not be reached.",
    );
    this.name = "ApiError";
  }
}

export function buildApiUrl(baseUrl: string, path: string): URL {
  try {
    const base = new URL(baseUrl);
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password ||
      base.search ||
      base.hash
    ) {
      throw new Error("Invalid API base URL");
    }
    // Endpoint paths are relative to the configured base, including a deployment prefix.
    if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
      throw new Error("Invalid API path");
    }
    const root = `${base.origin}${base.pathname.replace(/\/+$/, "")}/`;
    const url = new URL(path.slice(1), root);
    if (
      url.origin !== base.origin ||
      !url.pathname.startsWith(new URL(root).pathname)
    ) {
      throw new Error("API path escapes configured base");
    }
    return url;
  } catch {
    throw new ApiError(0, "INVALID_CONFIGURATION");
  }
}

function errorCode(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("error" in body))
    return undefined;
  const error = body.error;
  if (typeof error !== "object" || error === null || !("code" in error))
    return undefined;
  return typeof error.code === "string" ? error.code : undefined;
}

type ApiClientOptions = {
  baseUrl?: string;
  fetcher?: typeof fetch;
  timeoutMs?: number;
  mutationTimeoutMs?: number;
};

export class ApiClient {
  private readonly baseUrl: string | undefined;
  private readonly fetcher: typeof fetch;
  private readonly timeoutMs: number;
  private readonly mutationTimeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? process.env.OPENROLE_API_BASE_URL;
    this.fetcher = options.fetcher ?? fetch;
    this.timeoutMs = options.timeoutMs ?? 4000;
    this.mutationTimeoutMs = options.mutationTimeoutMs ?? 300000;
  }

  async getJson(
    path: string,
    acceptedErrorStatuses: readonly number[] = [],
  ): Promise<{ status: number; body: unknown }> {
    return this.requestJson(path, "GET", this.timeoutMs, acceptedErrorStatuses);
  }

  async postJson(path: string): Promise<{ status: number; body: unknown }> {
    return this.requestJson(path, "POST", this.mutationTimeoutMs);
  }

  private async requestJson(
    path: string,
    method: "GET" | "POST",
    timeoutMs: number,
    acceptedErrorStatuses: readonly number[] = [],
  ): Promise<{ status: number; body: unknown }> {
    if (!this.baseUrl) throw new ApiError(0, "INVALID_CONFIGURATION");
    const url = buildApiUrl(this.baseUrl, path);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await this.fetcher(url, {
        method,
        cache: "no-store",
        signal: controller.signal,
      });
      let body: unknown;
      try {
        body = await response.json();
      } catch {
        if (controller.signal.aborted) throw new ApiError(0, "TIMEOUT");
        throw new ApiError(
          response.status,
          response.ok ? "INVALID_RESPONSE" : undefined,
        );
      }
      if (!response.ok && !acceptedErrorStatuses.includes(response.status)) {
        throw new ApiError(response.status, errorCode(body));
      }
      return { status: response.status, body };
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        0,
        controller.signal.aborted ? "TIMEOUT" : "NETWORK_ERROR",
      );
    } finally {
      clearTimeout(timeout);
    }
  }
}
