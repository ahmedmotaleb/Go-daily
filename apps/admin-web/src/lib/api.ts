import "server-only";
import { redirect } from "next/navigation";
import { env } from "./env";
import { getSessionToken } from "./session";

export type ApiErrorBody = {
  code: string;
  message: string;
  details?: {
    fields?: { loc: string[]; msg: string; type: string }[];
    [key: string]: unknown;
  };
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorBody,
  ) {
    super(body.message);
    this.name = "ApiError";
  }

  get code(): string {
    return this.body.code;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  /** Skip the session token (login). */
  anonymous?: boolean;
  /** Return null on 404 instead of throwing. */
  allow404?: boolean;
};

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${env.apiUrl}/api/v1${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "")
      url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // Correlates this call with the API's log line; shown to the user on server errors.
  const requestId = crypto.randomUUID().replaceAll("-", "");
  const headers: Record<string, string> = { Accept: "application/json", "X-Request-ID": requestId };
  if (!options.anonymous) {
    const token = await getSessionToken();
    if (!token) redirect("/login");
    headers.Authorization = `Bearer ${token}`;
  }
  const isForm = options.body instanceof FormData;
  if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body:
        options.body === undefined
          ? undefined
          : isForm
            ? (options.body as FormData)
            : JSON.stringify(options.body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(503, {
      code: "api_unreachable",
      message: "تعذر الاتصال بالخادم، حاول مرة أخرى",
    });
  }

  if (res.status === 401 && !options.anonymous) {
    // Session ended (expired, revoked, account disabled): clear the cookie and re-login.
    redirect("/auth/clear");
  }
  if (res.status === 404 && options.allow404) return null as T;

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    // e.g. an HTML 502 page from a proxy; treated as an error without a body.
    if (res.ok)
      throw new ApiError(502, { code: "bad_response", message: "رد غير متوقع من الخادم" });
  }
  if (!res.ok) {
    const body = (data as { error?: ApiErrorBody } | null)?.error ?? {
      code: "http_error",
      message: "حدث خطأ غير متوقع",
    };
    if (res.status >= 500) {
      body.message = `${body.message} (رمز المتابعة: ${requestId.slice(0, 12)})`;
    }
    throw new ApiError(res.status, body);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query, opts?: Omit<RequestOptions, "method" | "query">) =>
    request<T>(path, { ...opts, query }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...opts, method: "POST", body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  /** Multipart upload (the browser's file is forwarded as is). */
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};
