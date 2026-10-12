import type { SourceRead } from "../lib/api/types";
import { sourceHealth } from "./fixtures";

export function sourceRead(overrides: Partial<SourceRead> = {}): SourceRead {
  const health = sourceHealth();
  return {
    ...health,
    company: {
      id: health.company_id,
      name: "Example Company",
      domain: "example.test",
      careers_url: "https://example.test/careers",
    },
    ...overrides,
  };
}
