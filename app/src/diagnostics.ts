import usDiagnosticsRaw from "./diagnostics-us.json";
import ukDiagnosticsRaw from "./diagnostics-uk.json";
import type { BenchData, CountryCode } from "./types";

function withCountry(
  country: CountryCode,
  payload: Omit<BenchData, "country">
): BenchData {
  return {
    country,
    ...payload,
    scenarios: Object.fromEntries(
      Object.entries(payload.scenarios).map(([scenarioId, scenario]) => [
        scenarioId,
        {
          ...scenario,
          country,
        },
      ])
    ),
  };
}

export const DIAGNOSTICS_BY_COUNTRY: Record<CountryCode, BenchData> = {
  us: withCountry("us", usDiagnosticsRaw as unknown as Omit<BenchData, "country">),
  uk: withCountry("uk", ukDiagnosticsRaw as unknown as Omit<BenchData, "country">),
};
