import { useEffect, useState } from "react";
import { api, type AssetSummary, type Finding } from "./api";
import { healthScore, worst } from "./ui";

export interface FleetAsset extends AssetSummary {
  findings: Finding[];
  health: number;
  severity: ReturnType<typeof worst>;
  diagnoses: number;
}

export function useFleet() {
  const [assets, setAssets] = useState<FleetAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const list = await api.assets();
        const full = await Promise.all(
          list.map(async (a) => {
            const findings = await api.findings(a.unit).catch(() => [] as Finding[]);
            const sevs = findings.map((f) => f.severity);
            return {
              ...a,
              findings,
              health: healthScore(sevs),
              severity: worst(sevs),
              diagnoses: findings.filter((f) => f.origin === "diagnosed").length,
            };
          }),
        );
        if (alive) setAssets(full);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return { assets, error };
}
