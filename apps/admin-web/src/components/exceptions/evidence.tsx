import Link from "next/link";
import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { EVIDENCE_KEYS, EVIDENCE_VALUES, SUBJECT_PATH } from "@/lib/exception-labels";
import { FINANCE_PAGE } from "@/lib/finance-paths";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATETIME = /^\d{4}-\d{2}-\d{2}T/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

type Row = Record<string, unknown>;

function label(key: string) {
  return EVIDENCE_KEYS[key] ?? key;
}

/** Where an id inside the evidence points to, if anywhere. */
function href(key: string, value: string, row: Row, kind: unknown): string | null {
  if (!UUID.test(value)) return null;
  if (key.endsWith("shift_id")) return `/shifts/${value}`;
  if (key === "statement_id") return `${FINANCE_PAGE.statements}/${value}`;
  if (key === "attachment_id") return `/files/${value}`;
  if (key === "owner_id" && typeof row.owner_type === "string") {
    const base = SUBJECT_PATH[row.owner_type];
    return base ? `${base}/${value}` : null;
  }
  if (key === "id" && (kind === "fuel" || kind === "expense")) {
    return `${kind === "fuel" ? FINANCE_PAGE.fuel : FINANCE_PAGE.expenses}/${value}`;
  }
  return null;
}

function Value({ k, v, row, kind }: { k: string; v: unknown; row: Row; kind: unknown }) {
  if (v === null || v === undefined || v === "") return <>—</>;
  if (typeof v === "boolean") return <>{v ? "نعم" : "لا"}</>;
  if (typeof v === "number") return <span className="ltr-nums">{formatNumber(v)}</span>;
  if (Array.isArray(v)) {
    return <>{v.length ? v.map((x) => EVIDENCE_VALUES[String(x)] ?? String(x)).join("، ") : "—"}</>;
  }
  if (typeof v === "string") {
    const target = href(k, v, row, kind);
    if (target) {
      return (
        <Link href={target} className="text-forest-700 hover:underline" prefetch={false}>
          عرض
        </Link>
      );
    }
    if (DATETIME.test(v)) return <span className="ltr-nums">{formatDateTime(v)}</span>;
    if (DATE.test(v)) return <span className="ltr-nums">{formatDate(v)}</span>;
    return <>{EVIDENCE_VALUES[v] ?? v}</>;
  }
  return <>{JSON.stringify(v)}</>;
}

function isRowList(v: unknown): v is Row[] {
  return Array.isArray(v) && v.length > 0 && v.every((x) => x !== null && typeof x === "object");
}

function isObject(v: unknown): v is Row {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/**
 * Renders the facts a rule used, as recorded. Lists of periods or records
 * become tables; ids become links to the record.
 */
export function Evidence({ evidence }: { evidence: Row }) {
  const kind = evidence.kind;
  const scalars = Object.entries(evidence).filter(([, v]) => !isRowList(v) && !isObject(v));
  const tables = Object.entries(evidence).filter(([, v]) => isRowList(v)) as [string, Row[]][];
  const groups = Object.entries(evidence).filter(([, v]) => isObject(v)) as [string, Row][];
  return (
    <div className="space-y-4">
      {scalars.length ? (
        <dl className="divide-y divide-line text-sm">
          {scalars.map(([k, v]) => (
            <div key={k} className="flex flex-wrap justify-between gap-2 py-2">
              <dt className="text-ink-muted">{label(k)}</dt>
              <dd className="font-medium">
                <Value k={k} v={v} row={evidence} kind={kind} />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {tables.map(([k, rows]) => {
        const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
        return (
          <div key={k}>
            <h4 className="mb-2 text-sm font-semibold">{label(k)}</h4>
            <Table>
              <THead>
                <tr>
                  {columns.map((c) => (
                    <TH key={c}>{label(c)}</TH>
                  ))}
                </tr>
              </THead>
              <tbody>
                {rows.map((r, i) => (
                  <TR key={i}>
                    {columns.map((c) => (
                      <TD key={c}>
                        <Value k={c} v={r[c]} row={r} kind={kind} />
                      </TD>
                    ))}
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>
        );
      })}
      {groups.map(([k, group]) => (
        <div key={k}>
          <h4 className="mb-2 text-sm font-semibold">{label(k)}</h4>
          <dl className="divide-y divide-line text-sm">
            {Object.entries(group).map(([gk, gv]) => (
              <div key={gk} className="flex flex-wrap justify-between gap-2 py-2">
                <dt className="text-ink-muted">{EVIDENCE_VALUES[gk] ?? gk}</dt>
                <dd className="font-medium">
                  {isObject(gv) ? (
                    Object.entries(gv)
                      .map(([a, b]) => `${label(a)}: ${String(b)}`)
                      .join(" · ")
                  ) : (
                    <Value k={gk} v={gv} row={group} kind={kind} />
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
