export const publicTextChangeFields = [
  "title",
  "location_text",
  "city",
  "region",
  "country_code",
  "workplace_type",
  "employment_type",
] as const;

export type PublicTextChangeField = (typeof publicTextChangeFields)[number];
export type PublicChangeType = "added" | "removed" | "modified";
export type PublicSalaryValue = {
  min: string | null;
  max: string | null;
  currency: string | null;
  period: string | null;
};
export type PublicJobTextChange = {
  field: PublicTextChangeField;
  change_type: PublicChangeType;
  old_value: string | null;
  new_value: string | null;
};
export type PublicJobSalaryChange = {
  field: "salary";
  change_type: PublicChangeType;
  old_value: PublicSalaryValue | null;
  new_value: PublicSalaryValue | null;
};
export type PublicJobDescriptionChange = {
  field: "description";
  change_type: PublicChangeType;
};
export type PublicJobChange =
  | PublicJobTextChange
  | PublicJobSalaryChange
  | PublicJobDescriptionChange;
export type PublicJobChangeGroup = {
  observed_at: string;
  changes: PublicJobChange[];
};
export type PublicJobChangesResponse = {
  job_id: string;
  items: PublicJobChangeGroup[];
  limit: number;
};
