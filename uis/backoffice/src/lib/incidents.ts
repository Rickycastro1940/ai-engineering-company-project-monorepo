/** Brasaland incident manager values. Keep in step with packages/shared/incident_rules.py. */

export const INCIDENT_BRANCHES = [
  { value: "central", label: "Central (Medellín / Miami)" },
  { value: "medellin_centro", label: "Medellín Centro" },
  { value: "medellin_laureles", label: "Medellín Laureles" },
  { value: "medellin_envigado", label: "Medellín Envigado" },
  { value: "medellin_bello", label: "Medellín Bello" },
  { value: "medellin_itagui", label: "Medellín Itagüí" },
  { value: "bogota_chapinero", label: "Bogotá Chapinero" },
  { value: "bogota_usaquen", label: "Bogotá Usaquén" },
  { value: "cali_granada", label: "Cali Granada" },
  { value: "barranquilla_norte", label: "Barranquilla Norte" },
  { value: "miami_doral", label: "Miami Doral" },
  { value: "miami_hialeah", label: "Miami Hialeah" },
  { value: "miami_kendall", label: "Miami Kendall" },
  { value: "orlando_international", label: "Orlando International Drive" },
  { value: "fort_lauderdale", label: "Fort Lauderdale" },
] as const;

export const INCIDENT_CATEGORIES = [
  { value: "equipment_failure", label: "Equipment failure" },
  { value: "supply_issue", label: "Supply issue" },
  { value: "customer_complaint", label: "Customer complaint" },
  { value: "staff_issue", label: "Staff issue" },
  { value: "facility_issue", label: "Facility issue" },
  { value: "pos_system", label: "POS system" },
  { value: "delivery_issue", label: "Delivery issue" },
  { value: "other", label: "Other" },
] as const;

export const INCIDENT_STATUSES = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "discarded", label: "Discarded" },
] as const;

export const INCIDENT_ORIGINS = [
  { value: "customer", label: "Customer" },
  { value: "branch", label: "Branch" },
  { value: "internal", label: "Internal" },
] as const;

export const STATUS_TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded"],
  resolved: [],
  discarded: [],
};

export type Incident = {
  id: string;
  title: string;
  description: string;
  category: string;
  status: string;
  origin: string;
  branch: string;
  created_at: string;
  updated_at: string;
};

export type IncidentSummary = {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
};

export type IncidentDraft = {
  title: string;
  description: string;
  category: string;
  status: string;
  origin: string;
  branch: string;
};

export function labelFor(options: ReadonlyArray<{ value: string; label: string }>, value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

export function validateIncidentDraft(draft: IncidentDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!draft.title.trim()) {
    errors.title = "Enter a short title.";
  } else if (draft.title.trim().length > 120) {
    errors.title = "Keep the title to 120 characters or fewer.";
  }
  if (!draft.description.trim()) {
    errors.description = "Describe what happened.";
  }
  if (!INCIDENT_CATEGORIES.some((option) => option.value === draft.category)) {
    errors.category = "Choose a category from the list.";
  }
  if (!INCIDENT_STATUSES.some((option) => option.value === draft.status)) {
    errors.status = "Choose a valid status.";
  }
  if (!INCIDENT_ORIGINS.some((option) => option.value === draft.origin)) {
    errors.origin = "Choose where this report came from.";
  }
  if (!INCIDENT_BRANCHES.some((option) => option.value === draft.branch)) {
    errors.branch = "Choose the branch for this incident.";
  }
  return errors;
}
