import { Alert } from "@/components/ui/alert";
import { NOTICES, type NoticeCode } from "@/lib/notices";

export function Notice({ code }: { code: string | string[] | undefined }) {
  if (typeof code !== "string" || !(code in NOTICES)) return null;
  return (
    <Alert tone="success" className="mb-4">
      {NOTICES[code as NoticeCode]}
    </Alert>
  );
}
