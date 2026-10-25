import { useEffect, useState } from "react";

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    signal,
    headers: { "Content-Type": "application/json", "X-Compras-UI": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: `Erro HTTP ${response.status}` }));
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail.map((d: { msg: string }) => d.msg).join("; ")
        : data.detail,
    );
  }
  return response.json();
}

export function useData<T>(path: string | null, revision = 0, poll = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      setError("");
      return;
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    setLoading(true);
    setError("");
    const load = async () => {
      try {
        const result = await api<T>(path, "GET", undefined, controller.signal);
        if (!controller.signal.aborted) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          if (poll) timer = setTimeout(load, poll);
        }
      }
    };
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [path, revision, poll]);
  return { data, error, loading };
}

export function useDebounce(value: string, delay = 250) {
  const [result, setResult] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setResult(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return result;
}

export interface Coverage {
  status: string;
  message: string;
  records: number;
  unreconciled: number;
  entity_pages: Record<string, number>;
  snapshot_built_at: string;
  start_date?: string;
  end_date?: string;
}
export interface Municipality {
  id: string;
  name: string;
  uf: string;
}
export interface MunicipalitySearch {
  items: Municipality[];
  total: number;
  uf: string;
  query: string;
  source: "ibge" | "cache";
  fetched_at: string;
  warning: string | null;
}
export interface City {
  id: string;
  name: string;
  uf: string;
  has_snapshot: boolean;
  snapshot_at: string | null;
  coverage: Coverage | null;
}
export interface Purchase {
  purchase_key: string;
  family: string;
  published_on: string;
  org_name: string;
  modality: string;
  description: string;
  estimated: number | null;
  awarded: number | null;
  origin_json: string;
  payload_json: string;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Overview {
  metrics: {
    purchases: number;
    estimated: number | null;
    awarded: number | null;
    estimated_known: number;
    awarded_known: number;
    organizations: number;
  };
  monthly: { month: string; purchases: number }[];
  organizations: { org_name: string; purchases: number }[];
  modalities: { modality: string }[];
  orgs: { org_name: string }[];
  coverage: Coverage;
  date_range: { start_date: string | null; end_date: string | null };
}
export interface Run {
  id: string;
  city_id: string;
  city_name: string;
  uf: string;
  status: string;
  created_at: string;
  config: { start_date: string; end_date: string };
  error: string | null;
  result: unknown;
}
export interface Schedule {
  id: string;
  name: string;
  city_name: string;
  frequency: string;
  local_time: string;
  timezone: string;
  next_due: string;
  enabled: number;
  executed: number;
  window_days: number;
  weekday: number | null;
}
export interface RawRecord {
  id: string;
  entity: string;
  payload_json: string;
  origin_json: string;
}
export interface LogEvent {
  id: number;
  created_at: string;
  message: string;
}
export interface ServiceStatus {
  service: string;
  error: string | null;
  free_disk_bytes: number;
  max_workers: number;
}
