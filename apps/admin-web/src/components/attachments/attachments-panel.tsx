import { FileText, ImageIcon } from "lucide-react";
import { deleteAttachmentAction, uploadAttachmentAction } from "@/app/(app)/attachments/actions";
import { ActionForm } from "@/components/forms/action-form";
import { TextField } from "@/components/forms/fields";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Attachment, AttachmentOwner } from "@/lib/attachment-types";
import { formatDateTime, formatNumber } from "@/lib/format";
import { FileField } from "./file-field";

function size(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${formatNumber((bytes / (1024 * 1024)).toFixed(1))} م.ب`
    : `${formatNumber(Math.max(1, Math.round(bytes / 1024)))} ك.ب`;
}

/**
 * Receipts, statements and invoices for one record. Files open through
 * /files/[id], which checks the session; nothing is publicly reachable.
 */
export async function AttachmentsPanel({
  ownerType,
  ownerId,
  returnPath,
  canWrite,
  locked,
  title = "المرفقات",
}: {
  ownerType: AttachmentOwner;
  ownerId: string;
  returnPath: string;
  canWrite: boolean;
  /** Approved/voided records: evidence can no longer be added or removed. */
  locked: boolean;
  title?: string;
}) {
  const items = await api.get<Attachment[]>("/attachments", {
    owner_type: ownerType,
    owner_id: ownerId,
  });
  return (
    <Card>
      <CardHeader
        title={title}
        description={locked ? "السجل معتمد أو ملغي: المرفقات محفوظة كإثبات ولا تُعدّل" : undefined}
      />
      <CardBody className="space-y-4">
        {items.length === 0 ? (
          <p className="text-sm text-ink-muted">لا توجد مرفقات.</p>
        ) : (
          <ul className="divide-y divide-line">
            {items.map((a) => {
              const Icon = a.content_type === "application/pdf" ? FileText : ImageIcon;
              return (
                <li
                  key={a.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Icon className="size-4 shrink-0 text-ink-muted" aria-hidden="true" />
                    {a.deleted_at ? (
                      <span className="truncate text-ink-muted line-through">
                        {a.original_filename}
                      </span>
                    ) : (
                      <a
                        href={`/files/${a.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="truncate font-medium text-forest-700 hover:underline"
                      >
                        {a.original_filename}
                      </a>
                    )}
                    <span className="ltr-nums text-xs text-ink-muted">{size(a.size_bytes)}</span>
                  </span>
                  <span className="text-xs text-ink-muted">
                    {a.uploaded_by?.full_name ?? "—"} · {formatDateTime(a.created_at)}
                  </span>
                  {a.deleted_at ? (
                    <Badge>محذوف: {a.delete_reason}</Badge>
                  ) : canWrite && !locked ? (
                    <details className="w-full">
                      <summary className="cursor-pointer text-xs text-danger">حذف المرفق</summary>
                      <ActionForm
                        action={deleteAttachmentAction.bind(null, a.id, returnPath)}
                        submitLabel="حذف"
                        variant="danger"
                        confirm="يُخفى الملف من السجل ويبقى محفوظًا مع السبب. متابعة؟"
                        className="mt-2 max-w-sm"
                      >
                        <TextField name="reason" label="السبب" required />
                      </ActionForm>
                    </details>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {canWrite && !locked ? (
          <ActionForm
            action={uploadAttachmentAction.bind(null, ownerType, ownerId, returnPath)}
            submitLabel="رفع"
            variant="secondary"
            className="border-t border-line pt-4"
          >
            <FileField />
          </ActionForm>
        ) : null}
      </CardBody>
    </Card>
  );
}
