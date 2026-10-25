import { useState, type FormEvent } from "react";
import { LoaderCircle, TriangleAlert } from "lucide-react";
import {
  api,
  useData,
  useDebounce,
  type City,
  type Municipality,
  type MunicipalitySearch,
} from "./api";

const UFS =
  "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(
    " ",
  );

export function MunicipalityForm({
  close,
  done,
}: {
  close: () => void;
  done: (id: string) => void;
}) {
  const [uf, setUf] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Municipality | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refreshWarning, setRefreshWarning] = useState("");
  const term = query.trim();
  const debounced = useDebounce(term);
  const path =
    uf && debounced.length >= 2
      ? `/municipalities?${new URLSearchParams({ uf, q: debounced })}`
      : null;
  const lookup = useData<MunicipalitySearch>(path, revision);
  const results =
    lookup.data?.uf === uf && lookup.data.query === term ? lookup.data : null;
  const searching = Boolean(
    uf && term.length >= 2 && (term !== debounced || lookup.loading),
  );
  const lookupError = term === debounced && path ? lookup.error : "";

  const refreshCatalog = async () => {
    setBusy(true);
    setError("");
    setSelected(null);
    try {
      const info = await api<{ warning: string | null }>(
        "/municipalities/refresh",
        "POST",
      );
      setRefreshWarning(info.warning || "");
      setRevision((value) => value + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      const city = await api<City>("/cities", "POST", selected);
      done(city.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const warning = results?.warning || refreshWarning;
  return (
    <form onSubmit={submit} className="form">
      <p className="muted">
        Selecione a UF e pesquise o município. O código será preenchido a partir
        do catálogo oficial do IBGE.
      </p>
      <label>
        UF
        <select
          required
          value={uf}
          disabled={busy}
          onChange={(e) => {
            setUf(e.target.value);
            setQuery("");
            setSelected(null);
            setError("");
          }}
        >
          <option value="">Selecione a UF</option>
          {UFS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        Buscar município
        <input
          value={query}
          disabled={!uf || busy}
          maxLength={100}
          autoComplete="off"
          placeholder={
            uf ? "Digite o nome ou código IBGE" : "Selecione primeiro a UF"
          }
          onChange={(e) => {
            setQuery(e.target.value);
            setSelected(null);
            setError("");
          }}
        />
      </label>
      {uf && term.length < 2 && (
        <p className="muted">Digite pelo menos 2 caracteres para pesquisar.</p>
      )}
      {searching && (
        <p className="municipality-status" role="status">
          <LoaderCircle size={16} className="spin" /> Pesquisando municípios…
        </p>
      )}
      {!searching && results && (
        <>
          <p className="municipality-status" role="status">
            {results.total
              ? `${results.total} município(s) encontrado(s). Selecione um resultado.`
              : "Nenhum município encontrado nessa UF."}
          </p>
          {results.items.length > 0 && (
            <fieldset className="municipality-results">
              <legend>Resultados da busca</legend>
              {results.items.map((item) => (
                <label className="municipality-option" key={item.id}>
                  <input
                    type="radio"
                    name="municipality"
                    value={item.id}
                    checked={selected?.id === item.id}
                    disabled={busy}
                    onChange={() => {
                      setSelected(item);
                      setError("");
                    }}
                  />
                  <span>
                    <strong>
                      {item.name} / {item.uf}
                    </strong>
                    <small>IBGE {item.id}</small>
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          {results.total > results.items.length && (
            <p className="muted">
              Mostrando {results.items.length} resultados. Refine a busca para
              encontrar seu município.
            </p>
          )}
        </>
      )}
      <div className="catalog-tools">
        <span>
          {results
            ? `Catálogo ${results.source === "cache" ? "local do " : "do "}IBGE · ${new Date(results.fetched_at).toLocaleString("pt-BR")}`
            : "Fonte: IBGE"}
        </span>
        <button
          type="button"
          className="text-button"
          disabled={busy || searching}
          onClick={() => void refreshCatalog()}
        >
          Atualizar catálogo
        </button>
      </div>
      {warning && (
        <div className="notice warning" role="status">
          <TriangleAlert size={18} />
          <span>{warning}</span>
        </div>
      )}
      <div className="form-grid">
        <label>
          Município selecionado
          <input
            readOnly
            value={selected?.name || ""}
            placeholder="Selecione um resultado"
          />
        </label>
        <label>
          Código IBGE
          <input
            readOnly
            value={selected?.id || ""}
            placeholder="Preenchido automaticamente"
          />
        </label>
      </div>
      {(error || lookupError) && (
        <div className="notice danger" role="alert">
          <TriangleAlert size={18} />
          <span>{error || lookupError}</span>
        </div>
      )}
      <div className="form-actions">
        <button type="button" className="button secondary" onClick={close}>
          Cancelar
        </button>
        <button
          type="submit"
          className="button primary"
          disabled={busy || !selected}
        >
          {busy && <LoaderCircle size={16} className="spin" />}Cadastrar
          município
        </button>
      </div>
    </form>
  );
}
