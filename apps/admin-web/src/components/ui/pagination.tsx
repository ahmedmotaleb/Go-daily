import Link from "next/link";
import { buttonClasses } from "./button";

/** Server-rendered pagination that preserves the current filters. */
export function Pagination({
  page,
  pageSize,
  total,
  basePath,
  params,
}: {
  page: number;
  pageSize: number;
  total: number;
  basePath: string;
  params: Record<string, string | undefined>;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  const href = (p: number) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) sp.set(k, v);
    sp.set("page", String(p));
    return `${basePath}?${sp.toString()}`;
  };
  return (
    <nav
      aria-label="الصفحات"
      className="flex items-center justify-between gap-3 px-4 py-3 text-sm text-ink-muted"
    >
      <span>
        صفحة <span className="ltr-nums">{page}</span> من <span className="ltr-nums">{pages}</span> ({" "}
        <span className="ltr-nums">{total}</span> نتيجة)
      </span>
      <div className="flex gap-2">
        {page > 1 ? (
          <Link className={buttonClasses("secondary", "sm")} href={href(page - 1)}>
            السابق
          </Link>
        ) : null}
        {page < pages ? (
          <Link className={buttonClasses("secondary", "sm")} href={href(page + 1)}>
            التالي
          </Link>
        ) : null}
      </div>
    </nav>
  );
}
