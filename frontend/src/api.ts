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
  exclusion_reasons?: Record<string, number>;
  entity_pages: Record<string, number>;
  snapshot_built_at: string;
  start_date?: string;
  end_date?: string;
  prior_snapshot?: boolean;
  sources?: Record<string, {
    status: string;
    stages?: Record<string, { status: string; pages: number; records: number }>;
  }>;
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
export interface RecordSource {
  payload_json: string;
  origin_json: string;
}
export interface EvidenceLink {
  status: "confirmed" | "ambiguous" | "missing";
  reason: string;
  evidence: string[];
}
export interface PurchaseDetail {
  purchase: Purchase;
  snapshot: string;
  coverage: Coverage;
  conciliation?: {
    selected_source: string;
    divergences: Record<string, Record<string, string | number | null>>;
    observations: Array<RecordSource & { source: string; entity: string; selected: boolean }>;
  };
  summary: {
    item_records: number;
    result_records: number;
    confirmed_items: number;
    ambiguous_items: number;
    confirmed_results: number;
    ambiguous_results: number;
    results_without_item: number;
  };
}
export interface PurchaseItem extends RecordSource {
  id: string;
  identity_status: "identified" | "unverified";
  description: string;
  item_number: string | null;
  catalog_code: string | null;
  item_type: string | null;
  unit: string | null;
  quantity: number | null;
  estimated_unit_price: number | null;
  budget_sealed?: boolean | null;
  status: string | null;
  purchase_link: EvidenceLink;
  confirmed_results: number;
}
export interface ObservedSupplier {
  name: string;
  identifier: string;
  kind: "cpf" | "cnpj" | "foreign" | null;
  can_open: boolean;
}
export interface ItemResult extends RecordSource {
  id: string;
  identity_status: "identified" | "unverified";
  item_number: string | null;
  sequence: string | null;
  status: string | null;
  cancelled: boolean;
  quantity: number | null;
  unit_price: number | null;
  total: number | null;
  supplier: ObservedSupplier;
  purchase_link: EvidenceLink;
  item_link: EvidenceLink;
  item_record_id: string | null;
}
export interface SupplierRegistration extends RecordSource {
  id: string;
  name: string | null;
  cnae: string | null;
  size: string | null;
  municipality: string | null;
  uf: string | null;
  active: boolean | null;
  eligible: boolean | null;
  identity_conflict: boolean;
  fetched_at: string;
}
export interface SupplierDetail {
  supplier: ObservedSupplier;
  result: ItemResult;
  registration_status: "confirmed" | "ambiguous" | "missing";
  registrations: Page<SupplierRegistration>;
  snapshot: string;
  coverage: Coverage;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface Totals {
  purchases: number;
  estimated: number | null;
  awarded: number | null;
}
export interface Amounts extends Totals {
  estimated_known: number;
  awarded_known: number;
}
// A running Python process can still serve the previous API after the static
// assets are rebuilt. Keep its actual response contract, not invented defaults.
export interface OverviewResponse {
  metrics: Amounts & { organizations: number };
  monthly: (Totals & Partial<Amounts> & { month: string })[];
  organizations: {
    org_name: string;
    purchases: number;
    awarded: number | null;
  }[];
  modalities: { modality: string }[];
  orgs: { org_name: string }[];
  coverage: Coverage;
  date_range: { start_date: string | null; end_date: string | null };
}
export interface Overview extends OverviewResponse {
  metrics: OverviewResponse["metrics"] & {
    organization_known: number;
    modality_known: number;
  };
  monthly: (Amounts & { month: string })[];
  organizations: (Amounts & { org_name: string })[];
  modality_breakdown: (Amounts & { modality: string })[];
  sources: { family: string; purchases: number }[];
  filtered_range: { start_date: string | null; end_date: string | null };
}

export function hasExpandedOverview(data: OverviewResponse): data is Overview {
  const expanded = data as Partial<Overview>;
  const hasAmounts = (row: Partial<Amounts>) =>
    typeof row.estimated_known === "number" &&
    typeof row.awarded_known === "number" &&
    (row.estimated === null || typeof row.estimated === "number") &&
    (row.awarded === null || typeof row.awarded === "number");
  return !!(
    expanded.filtered_range &&
    Array.isArray(expanded.modality_breakdown) &&
    Array.isArray(expanded.sources) &&
    typeof expanded.metrics?.organization_known === "number" &&
    typeof expanded.metrics?.modality_known === "number" &&
    data.monthly.every(hasAmounts) &&
    data.organizations.every(hasAmounts) &&
    expanded.modality_breakdown.every(hasAmounts)
  );
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
  capabilities?: { collection_sources?: string[] };
}
