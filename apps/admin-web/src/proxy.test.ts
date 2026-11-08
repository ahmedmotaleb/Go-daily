import { describe, expect, it } from "vitest";
import { contentSecurityPolicy } from "./proxy";

describe("content security policy (U34)", () => {
  const prod = contentSecurityPolicy("abc123", false);
  const directive = (name: string) =>
    prod
      .split("; ")
      .find((d) => d.startsWith(`${name} `))
      ?.slice(name.length + 1) ?? "";

  it("allows only nonced scripts in production", () => {
    expect(directive("script-src")).toBe("'self' 'nonce-abc123' 'strict-dynamic'");
    expect(prod).not.toMatch(/script-src[^;]*unsafe/);
  });

  it("keeps inline styles to attributes only", () => {
    expect(directive("style-src")).toBe("'self' 'nonce-abc123'");
    expect(directive("style-src-attr")).toBe("'unsafe-inline'");
  });

  it("keeps the other restrictions", () => {
    for (const d of [
      "object-src 'none'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ]) {
      expect(prod).toContain(d);
    }
  });

  it("relaxes only for the development server", () => {
    const dev = contentSecurityPolicy("n", true);
    expect(dev).toContain("'unsafe-eval'");
    expect(dev).toContain("style-src 'self' 'unsafe-inline'");
  });
});
