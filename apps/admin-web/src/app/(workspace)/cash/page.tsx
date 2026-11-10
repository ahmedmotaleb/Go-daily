import clsx from "clsx";
import { Camera, MessageSquareText, Receipt } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { CancelCollection } from "@/components/cash/cancel-collection";
import { CollectDialog } from "@/components/cash/collect-dialog";
import { DateJump } from "@/components/tracking/date-jump";
import { WorkspaceBar } from "@/components/tracking/workspace-bar";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import { can, requirePermission } from "@/lib/auth";
import { closeoutSummary, egp, lineNotDeducted, lineValue, rowStatus } from "@/lib/cash";
import type { BoardRow, CashBoard, Closeout } from "@/lib/cash-types";
import { formatLongDate, formatNumber } from "@/lib/format";
import { cairoToday, spDate } from "@/lib/search";
import { collectCashAction, voidCollectionAction } from "./actions";

export const metadata: Metadata = { title: "تحصيل نقدية السائقين" };

const TIME = new Intl.DateTimeFormat("ar-EG-u-nu-latn", {
  timeZone: "Africa/Cairo",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function Stat({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "hero" | "success" | "danger" | "default";
}) {
  const hero = tone === "hero";
  return (
    <div
      className={clsx(
        "flex flex-col gap-1.5 rounded-[18px] p-[18px]",
        hero ? "bg-primary text-white" : "border border-line bg-surface",
      )}
    >
      <span className={clsx("text-[13px]", hero ? "text-[#c9d6d0]" : "text-ink-soft")}>
        {label}
      </span>
      <span
        className={clsx(
          "text-[28px] leading-tight font-bold",
          tone === "success" && "text-success",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </span>
      <span className={clsx("text-xs", hero ? "text-lime-400" : "text-ink-muted")}>{sub}</span>
    </div>
  );
}

function Cell({
  label,
  value,
  strong,
  struck,
}: {
  label: string;
  value: string;
  strong?: boolean;
  struck?: boolean;
}) {
  return (
    <div
      className={clsx(
        "flex flex-col gap-0.5 rounded-[10px] px-2.5 py-2",
        strong ? "bg-[#eef4f0]" : "bg-neutral-50",
      )}
    >
      <span className={clsx("text-[11px]", strong ? "text-primary" : "text-ink-muted")}>
        {label}
      </span>
      <span
        className={clsx(
          "text-sm",
          strong ? "font-bold text-primary" : "font-semibold",
          struck && "text-danger line-through decoration-2",
        )}
      >
        {value}
      </span>
      {struck ? (
        <span className="text-[10px] font-semibold text-danger">مرفوض — على السائق</span>
      ) : null}
    </div>
  );
}

function CloseoutBody({ c }: { c: Closeout }) {
  const line = (key: string) => c.lines.find((l) => l.key === key);
  const note = [c.maintenance_note, c.notes].filter(Boolean).join(" — ");
  return (
    <div className="flex min-w-0 flex-[3_1_520px] flex-col gap-2.5">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        <Cell
          label={c.collection_booked ? "التحصيل" : "التحصيل (نقل ذكي)"}
          value={egp(c.collection_amount)}
          strong={false}
        />
        {(["gas", "gasoline", "toll", "maintenance"] as const).map((key) => {
          const l = line(key);
          const label =
            key === "gas"
              ? "غاز"
              : key === "gasoline"
                ? "بنزين"
                : key === "toll"
                  ? "الكارتة"
                  : "صيانة / زيت";
          return <Cell key={key} label={label} value={lineValue(l)} struck={lineNotDeducted(l)} />;
        })}
        <Cell label="صافي للتسليم" value={egp(c.net_amount)} strong />
      </div>
      <div className="flex flex-wrap gap-2">
        {note ? (
          <span className="flex items-center gap-1.5 rounded-full border border-line bg-neutral-50 px-2.5 py-1 text-xs text-ink-soft">
            <MessageSquareText className="size-3.5" aria-hidden="true" />
            ملاحظة السائق: {note}
          </span>
        ) : null}
        {c.receipt_attachment_ids.map((id, i) => (
          <a
            key={id}
            href={`/files/${id}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs font-semibold text-primary hover:bg-neutral-50"
          >
            <Receipt className="size-3.5" aria-hidden="true" />
            إيصال الوقود{c.receipt_attachment_ids.length > 1 ? ` ${i + 1}` : ""}
          </a>
        ))}
      </div>
    </div>
  );
}

function Row({
  row,
  canCollect,
  dayLabel,
}: {
  row: BoardRow;
  canCollect: boolean;
  dayLabel: string;
}) {
  const c = row.closeout;
  const status = rowStatus(row);
  const vehicle = row.vehicle?.plate_number ?? "بدون سيارة";
  const info =
    row.kind === "DAY_OFF"
      ? `اليوم إجازة · سجّلها ${row.day_off?.source === "DRIVER_APP" ? "السائق" : "المكتب"} ${
          row.day_off ? TIME.format(new Date(row.day_off.created_at)) : ""
        }${row.day_off?.note ? ` · ملاحظة: ${row.day_off.note}` : ""}`
      : row.kind === "OPEN_SHIFT"
        ? `الوردية ما زالت مفتوحة منذ ${row.started_at ? TIME.format(new Date(row.started_at)) : "—"} — التقفيل والمعاملات تُسجَّل في آخر اليوم`
        : row.kind === "ENDED_NOT_CLOSED"
          ? "انتهت الوردية بدون تقفيل — يمكن للمكتب إدخال التقفيل من الإيصالات"
          : "";
  return (
    <article className="flex flex-wrap items-center gap-x-7 gap-y-4 rounded-[18px] border border-line bg-surface px-5 py-[18px]">
      <div className="flex flex-[1_1_200px] flex-col gap-1">
        <span className="text-base font-bold">{row.driver.full_name}</span>
        <span className="text-[13px] text-ink-soft">
          {vehicle}
          {row.operation_label
            ? ` · ${row.operation_label}`
            : row.kind === "DAY_OFF"
              ? " · إجازة"
              : ""}
        </span>
        {c ? (
          <>
            <span className="mt-1 flex items-center gap-1.5 text-xs text-primary">
              <Camera className="size-3.5" aria-hidden="true" />
              {c.start_odometer_photo_id ? (
                <a
                  href={`/files/${c.start_odometer_photo_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="font-semibold underline-offset-2 hover:underline"
                >
                  صورة العداد عند البدء
                </a>
              ) : (
                <span className="text-ink-muted">بدون صورة عداد</span>
              )}
            </span>
            <span className="text-xs text-ink-soft">
              العداد {c.start_odometer_km !== null ? formatNumber(c.start_odometer_km) : "—"} ←{" "}
              {formatNumber(c.end_odometer_km)} كم
            </span>
          </>
        ) : null}
      </div>

      {c ? (
        <CloseoutBody c={c} />
      ) : (
        <div className="flex-[3_1_520px] text-sm text-ink-soft">{info}</div>
      )}

      <div className="flex flex-[1_1_210px] flex-col items-stretch gap-2">
        <Badge tone={status.tone} dot className="self-start">
          {status.label}
        </Badge>
        {c ? (
          <span
            className={clsx(
              "text-[13px] font-semibold",
              c.status === "PARTIAL" ? "text-danger" : "text-ink-soft",
            )}
          >
            {closeoutSummary(c)}
          </span>
        ) : Number(row.outstanding) > 0 ? (
          <span className="text-[13px] font-semibold text-danger">
            متبقي من أيام سابقة {egp(row.outstanding)} ج.م
          </span>
        ) : null}
        {c && canCollect && Number(c.remaining) > 0 ? (
          <CollectDialog
            action={collectCashAction.bind(null, row.driver.id, c.id)}
            driverName={row.driver.full_name}
            subtitle={`${vehicle} · ${dayLabel}`}
            net={c.net_amount}
            carried={c.carried_before}
            collected={c.collected}
            totalDue={c.remaining}
          />
        ) : null}
        {c?.collections.map((x) => (
          <div
            key={x.id}
            className="flex flex-col gap-1 rounded-[10px] bg-neutral-50 px-2.5 py-2 text-xs"
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-semibold">اتحصّل {egp(x.amount)} ج.م</span>
              <span className="ltr-nums text-ink-muted">
                {TIME.format(new Date(x.collected_at))}
              </span>
            </span>
            {x.collected_by ? (
              <span className="text-ink-muted">سجّله {x.collected_by.full_name}</span>
            ) : null}
            {x.note ? <span className="text-ink-soft">«{x.note}»</span> : null}
            {canCollect ? (
              <CancelCollection action={voidCollectionAction.bind(null, x.id)} />
            ) : null}
          </div>
        ))}
      </div>
    </article>
  );
}

export default async function CashPage({ searchParams }: PageProps<"/cash">) {
  const user = await requirePermission("cash:read");
  const canCollect = can(user, "cash:collect");
  const sp = await searchParams;
  const day = spDate(sp, "date") ?? cairoToday();
  const board = await api.get<CashBoard>("/cash/board", { day });
  const dayLabel = formatLongDate(`${day}T12:00:00Z`);

  return (
    <>
      <WorkspaceBar title="تحصيل نقدية السائقين">
        <DateJump value={day} basePath="/cash" />
      </WorkspaceBar>
      <main
        id="main"
        className="mx-auto flex w-full max-w-[1280px] flex-col gap-[22px] px-4 pt-7 pb-12 sm:px-6"
      >
        <section
          aria-label="ملخص اليوم"
          className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3.5"
        >
          <Stat
            label="صافي مستحق اليوم"
            value={`${egp(board.net_due)} ج.م`}
            sub={`من ${formatNumber(board.closeouts)} تقفيلات مُرسلة`}
            tone="hero"
          />
          <Stat
            label="تم تحصيله"
            value={`${egp(board.collected)} ج.م`}
            sub="مسجّل بواسطة المدير"
            tone="success"
          />
          <Stat
            label="لم يُحصَّل بعد"
            value={`${egp(board.open_balance)} ج.م`}
            sub="يشمل متبقيات أيام سابقة"
            tone={Number(board.open_balance) > 0 ? "danger" : "default"}
          />
          <Stat
            label="إجازات · ورديات مفتوحة"
            value={`${formatNumber(board.day_offs)} · ${formatNumber(board.open_shifts)}`}
            sub="لا تحتاج تحصيل الآن"
          />
        </section>

        <section aria-labelledby="rows-title" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="rows-title" className="text-lg font-bold">
              تقفيلات اليوم
            </h2>
            <span className="text-[13px] text-ink-muted">{dayLabel}</span>
          </div>
          {board.rows.length === 0 ? (
            <EmptyState
              title="لا توجد تقفيلات أو ورديات في هذا اليوم"
              description="تظهر هنا تقفيلات السائقين عند إرسالها من التطبيق، والإجازات والورديات المفتوحة."
            />
          ) : (
            board.rows.map((row) => (
              <Row
                key={`${row.kind}-${row.closeout?.id ?? row.day_off?.id ?? row.shift_id}`}
                row={row}
                canCollect={canCollect}
                dayLabel={dayLabel}
              />
            ))
          )}
          <p className="text-xs text-ink-muted">
            الصافي = التحصيل − (غاز + بنزين + الكارتة + الصيانة). البنود التي يرفضها المكتب لا تُخصم
            وتصبح على السائق. اعتماد كل بند يتم من صفحات الوقود والمصروفات والإيرادات.{" "}
            <Link href="/finance/revenue" className="font-semibold text-primary hover:underline">
              الإيرادات
            </Link>
          </p>
        </section>
      </main>
    </>
  );
}
