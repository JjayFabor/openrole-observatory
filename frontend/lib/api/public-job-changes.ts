import "server-only";
import { ApiClient, ApiError } from "./client";
import { isRecord, isTimestamp, isUuid } from "./validation";
import {
  publicTextChangeFields,
  type PublicChangeType,
  type PublicJobChange,
  type PublicJobChangeGroup,
  type PublicJobChangesResponse,
  type PublicSalaryValue,
} from "./public-job-changes-types";

export const PUBLIC_JOB_CHANGES_LIMIT = 10;

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}
function isNullableDecimal(value: unknown): value is string | null {
  return (
    value === null ||
    (typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value))
  );
}
function isSalary(value: unknown): value is PublicSalaryValue | null {
  if (value === null) return true;
  return (
    isRecord(value) &&
    isNullableDecimal(value.min) &&
    isNullableDecimal(value.max) &&
    isNullableString(value.currency) &&
    isNullableString(value.period) &&
    [value.min, value.max, value.currency, value.period].some(
      (part) => part !== null,
    )
  );
}
function projectSalary(
  value: PublicSalaryValue | null,
): PublicSalaryValue | null {
  return value === null
    ? null
    : {
        min: value.min,
        max: value.max,
        currency: value.currency,
        period: value.period,
      };
}
function isChangeType(value: unknown): value is PublicChangeType {
  return value === "added" || value === "removed" || value === "modified";
}
function parseChange(value: unknown): PublicJobChange | null {
  if (!isRecord(value) || !isChangeType(value.change_type)) return null;
  if (value.field === "description")
    return { field: "description", change_type: value.change_type };
  if (value.field === "salary") {
    if (
      !isSalary(value.old_value) ||
      !isSalary(value.new_value) ||
      (value.old_value === null && value.new_value === null)
    )
      return null;
    return {
      field: "salary",
      change_type: value.change_type,
      old_value: projectSalary(value.old_value),
      new_value: projectSalary(value.new_value),
    };
  }
  const field = publicTextChangeFields.find(
    (candidate) => candidate === value.field,
  );
  if (
    !field ||
    !isNullableString(value.old_value) ||
    !isNullableString(value.new_value)
  )
    return null;
  return {
    field,
    change_type: value.change_type,
    old_value: value.old_value,
    new_value: value.new_value,
  };
}
function isObservationTimestamp(value: unknown): value is string {
  if (!isTimestamp(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  return (
    year >= 1 &&
    month >= 1 &&
    month <= 12 &&
    day >= 1 &&
    day <= new Date(Date.UTC(year, month, 0)).getUTCDate()
  );
}
function parseGroup(value: unknown): PublicJobChangeGroup | null {
  if (
    !isRecord(value) ||
    !isObservationTimestamp(value.observed_at) ||
    !Array.isArray(value.changes) ||
    value.changes.length === 0 ||
    value.changes.length > 9
  )
    return null;
  const changes = value.changes.map(parseChange);
  if (!changes.every((change): change is PublicJobChange => change !== null))
    return null;
  if (new Set(changes.map((change) => change.field)).size !== changes.length)
    return null;
  return { observed_at: value.observed_at, changes };
}

export async function listPublicJobChanges(
  jobId: string,
  client = new ApiClient(),
): Promise<PublicJobChangesResponse> {
  if (!isUuid(jobId)) throw new ApiError(0, "INVALID_JOB_ID");
  const { status, body } = await client.getJson(
    `/api/v1/public/jobs/${jobId}/changes?limit=${PUBLIC_JOB_CHANGES_LIMIT}`,
  );
  if (
    status !== 200 ||
    !isRecord(body) ||
    !isUuid(body.job_id) ||
    body.job_id.toLowerCase() !== jobId.toLowerCase() ||
    body.limit !== PUBLIC_JOB_CHANGES_LIMIT ||
    !Array.isArray(body.items) ||
    body.items.length > PUBLIC_JOB_CHANGES_LIMIT
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  const items = body.items.map(parseGroup);
  if (
    !items.every((group): group is PublicJobChangeGroup => group !== null) ||
    items.some(
      (group, index) =>
        index > 0 &&
        Date.parse(group.observed_at) >
          Date.parse(items[index - 1].observed_at),
    )
  ) {
    throw new ApiError(status, "INVALID_RESPONSE");
  }
  return { job_id: body.job_id, items, limit: body.limit };
}
