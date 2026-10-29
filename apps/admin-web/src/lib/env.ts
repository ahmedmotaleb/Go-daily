import "server-only";

/** Server-side configuration. Never import this from client components. */
export const env = {
  apiUrl: (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  cookieSecure:
    (process.env.SESSION_COOKIE_SECURE ??
      (process.env.NODE_ENV === "production" ? "true" : "false")) === "true",
};
