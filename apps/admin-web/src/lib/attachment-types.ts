export type AttachmentOwner =
  | "fuel_transaction"
  | "expense"
  | "revenue_entry"
  | "ride_hailing_statement"
  | "maintenance_record"
  | "vehicle";

export type Attachment = {
  id: string;
  owner_type: AttachmentOwner;
  owner_id: string;
  kind: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: { id: string; full_name: string } | null;
  created_at: string;
  deleted_at: string | null;
  delete_reason: string | null;
};

export type UploadResult = {
  attachment: Attachment;
  duplicates: { attachment_id: string; owner_type: AttachmentOwner; owner_id: string }[];
};
