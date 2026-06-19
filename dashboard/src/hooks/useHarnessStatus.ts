import { useEffect, useState } from "react";
import type { HarnessStatusResponse } from "@/types/slopgate";

const HARNESS_STATUS_TIMEOUT_MS = 12000;
const API_BASE = window.location.origin + import.meta.env.BASE_URL.replace(/\/$/, "");
const HARNESS_ENDPOINT = `${API_BASE}/api/harness/status`;

export interface HarnessStatusState {
  status: HarnessStatusResponse | null;
  loading: boolean;
  error: string | null;
}

export function useHarnessStatus(): HarnessStatusState {
  const [status, setStatus] = useState<HarnessStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HARNESS_STATUS_TIMEOUT_MS);
    let cancelled = false;

    setLoading(true);
    fetch(HARNESS_ENDPOINT, { signal: controller.signal })
      .then(async (response) => {
        const body = (await response.json()) as HarnessStatusResponse;
        if (!response.ok || body.error) {
          throw new Error(body.error ?? `HTTP ${response.status}`);
        }
        return body;
      })
      .then((body) => {
        if (cancelled) return;
        setStatus(body);
        setError(null);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : String(exc));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  return { status, loading, error };
}
