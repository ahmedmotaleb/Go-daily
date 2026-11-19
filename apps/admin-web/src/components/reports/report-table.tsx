import { Table, TD, TH, THead, TR } from "@/components/ui/table";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "@/lib/format";
import type { ReportColumn, ReportTable } from "@/lib/report-types";

function cell(value: unknown, column: ReportColumn) {
  if (value === null || value === undefined || value === "") return "—";
  switch (column.type) {
    case "money":
      return formatMoney(value as string);
    case "number":
    case "minutes":
    case "km":
      return formatNumber(value as number | string);
    case "date":
      return formatDate(value as string);
    case "datetime":
      return formatDateTime(value as string);
    default:
      return String(value);
  }
}

const NUMERIC = new Set(["money", "number", "minutes", "km"]);

/** Generic report table with an optional totals row (sums of the rows shown in full). */
export function ReportTableView({ table, limit }: { table: ReportTable; limit?: number }) {
  const rows = limit ? table.rows.slice(0, limit) : table.rows;
  const hasTotals = Object.keys(table.totals).length > 0;
  return (
    <Table>
      <THead>
        <tr>
          {table.columns.map((c) => (
            <TH key={c.key}>{c.label}</TH>
          ))}
        </tr>
      </THead>
      <tbody>
        {rows.map((r, i) => (
          <TR key={i}>
            {table.columns.map((c) => (
              <TD
                key={c.key}
                className={
                  NUMERIC.has(c.type) || c.type.startsWith("date")
                    ? "ltr-nums whitespace-nowrap"
                    : undefined
                }
              >
                {cell(r[c.key], c)}
              </TD>
            ))}
          </TR>
        ))}
        {hasTotals && table.rows.length > 0 ? (
          <tr className="border-t-2 border-line bg-forest-50 font-bold">
            {table.columns.map((c, i) => (
              <td key={c.key} className="ltr-nums px-4 py-2.5 text-sm whitespace-nowrap">
                {i === 0 ? "الإجمالي" : c.key in table.totals ? cell(table.totals[c.key], c) : ""}
              </td>
            ))}
          </tr>
        ) : null}
      </tbody>
    </Table>
  );
}
