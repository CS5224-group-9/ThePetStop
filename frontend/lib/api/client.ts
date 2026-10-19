export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}
type Options = {
  baseUrl?: string;
  getToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
  fetcher?: typeof fetch;
};
type RequestOptions = Omit<RequestInit, "body"> & {
  auth?: boolean;
  json?: unknown;
  body?: BodyInit | null;
};
export function validateServiceUrl(value: string) {
  const url = new URL(value);
  if (
    url.username ||
    url.password ||
    (url.protocol !== "https:" &&
      !(
        url.protocol === "http:" &&
        ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
      ))
  )
    throw new ApiError(
      503,
      "invalid_configuration",
      "This service is not securely configured.",
    );
  return url;
}
export function createApiClient(options: Options) {
  const fetcher = options.fetcher ?? ((...args) => fetch(...args));
  async function request<T>(
    path: string,
    settings: RequestOptions = {},
  ): Promise<T> {
    if (!options.baseUrl)
      throw new ApiError(
        503,
        "not_configured",
        "This service is not available yet. Please try again later.",
      );
    const base = validateServiceUrl(options.baseUrl.replace(/\/?$/, "/"));
    const url = new URL(path.replace(/^\//, ""), base);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname))
      throw new ApiError(
        400,
        "invalid_url",
        "The service returned an invalid link.",
      );
    const { auth = false, json, signal, ...init } = settings;
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (json !== undefined) headers.set("Content-Type", "application/json");
    if (auth) {
      const token = await options.getToken?.();
      if (!token) {
        options.onUnauthorized?.();
        throw new ApiError(
          401,
          "authentication_required",
          "Sign in to continue.",
        );
      }
      headers.set("Authorization", `Bearer ${token}`);
    }
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const timeout = setTimeout(abort, 20000);
    try {
      const response = await fetcher(url.href, {
        ...init,
        headers,
        body: json === undefined ? init.body : JSON.stringify(json),
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        referrerPolicy: "no-referrer",
        signal: controller.signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (response.status === 401 && auth) options.onUnauthorized?.();
        const defaults: Record<number, string> = {
          401: "Your session has ended. Please sign in again.",
          403: "You do not have permission to perform this action.",
          404: "This record could not be found.",
          409: "This item changed. Refresh and try again.",
          429: "Too many requests. Please wait and try again.",
        };
        throw new ApiError(
          response.status,
          body?.error?.code ?? "request_failed",
          defaults[response.status] ??
            (typeof body?.error?.message === "string" && response.status < 500
              ? body.error.message
              : "Unable to complete the request. Please try again."),
          body?.error?.details ?? {},
        );
      }
      if (response.status === 204) return undefined as T;
      if (!response.headers.get("content-type")?.includes("application/json"))
        throw new ApiError(
          502,
          "invalid_response",
          "The service returned an unexpected response.",
        );
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (signal?.aborted)
        throw new DOMException("Request cancelled", "AbortError");
      throw new ApiError(
        0,
        "network_error",
        controller.signal.aborted
          ? "The request timed out. Please try again."
          : "Unable to reach the service. Check your connection and try again.",
      );
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
    }
  }
  async function list<T>(
    path: string,
    settings: RequestOptions = {},
  ): Promise<T[]> {
    const rows: T[] = [];
    const visited = new Set<string>();
    let next: string | null = path;
    while (next) {
      if (visited.has(next) || visited.size >= 100)
        throw new ApiError(
          502,
          "invalid_pagination",
          "The service returned an invalid result list.",
        );
      visited.add(next);
      const page: { results: T[]; next: string | null } = await request(
        next,
        settings,
      );
      if (!Array.isArray(page.results))
        throw new ApiError(
          502,
          "invalid_response",
          "The service returned an unexpected result list.",
        );
      rows.push(...page.results);
      next = page.next;
    }
    return rows;
  }
  return { request, list };
}
let getToken: () => Promise<string | null> = async () => null;
let unauthorized = () => {};
export function configureAuthorization(
  tokenProvider: typeof getToken,
  onUnauthorized: () => void,
) {
  getToken = tokenProvider;
  unauthorized = onUnauthorized;
}
export const api = createApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  getToken: () => getToken(),
  onUnauthorized: () => unauthorized(),
});
// Signed object-storage URLs are never sent an application Authorization header.
export async function transferPrivateFile(url: string, init: RequestInit = {}) {
  validateServiceUrl(url);
  const headers = new Headers(init.headers);
  headers.delete("Authorization");
  headers.delete("Proxy-Authorization");
  headers.delete("Cookie");
  const response = await fetch(url, {
    ...init,
    headers,
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    referrerPolicy: "no-referrer",
  });
  if (!response.ok)
    throw new ApiError(
      response.status,
      "file_transfer_failed",
      "The file transfer failed. Please try again.",
    );
  return response;
}
