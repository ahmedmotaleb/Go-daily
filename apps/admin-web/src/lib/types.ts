import type { Role } from "@go-daily/shared";

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type User = {
  id: string;
  full_name: string;
  phone: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CurrentUser = User & { permissions: string[] };

export type LoginResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: CurrentUser;
};
