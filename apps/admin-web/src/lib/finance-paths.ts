export type FinanceResource = "fuel" | "expenses" | "revenue" | "statements" | "maintenance";

/** Admin pages of each reviewable financial record type. */
export const FINANCE_PAGE: Record<FinanceResource, string> = {
  fuel: "/finance/fuel",
  expenses: "/finance/expenses",
  revenue: "/finance/revenue",
  statements: "/finance/ride-hailing",
  maintenance: "/maintenance/records",
};
