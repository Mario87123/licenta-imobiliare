import { useEffect, useMemo, useState } from "react";
import api from "../api/api";

const INITIAL_FORM = {
  neighborhood: "",
  city: "Timisoara",
  surface_mp: "",
  rooms: "",
  floor: "",
  total_floors: "",
  year_built: "",
  partitioning: "",
};

function formatCurrency(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return `${Number(value).toLocaleString("ro-RO")} EUR`;
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }

  return Number(value).toLocaleString("ro-RO");
}

function formatConfidence(value) {
  switch (value) {
    case "high":
      return "Ridicată";
    case "medium":
      return "Medie";
    case "low":
      return "Scăzută";
    default:
      return value || "-";
  }
}

function getSourceBadgeClass(source) {
  const normalizedSource = (source || "").toLowerCase();

  if (normalizedSource === "storia") {
    return "badge source-badge source-badge-storia";
  }

  if (normalizedSource === "imobiliare") {
    return "badge source-badge source-badge-imobiliare";
  }

  if (normalizedSource === "olx") {
    return "badge source-badge source-badge-olx";
  }

  return "badge source-badge";
}

function buildPayload(form) {
  const payload = {
    neighborhood: form.neighborhood.trim(),
    city: form.city.trim() || "Timisoara",
    surface_mp: Number(form.surface_mp),
    rooms: Number(form.rooms),
  };

  ["floor", "total_floors", "year_built"].forEach((key) => {
    if (form[key] !== "") {
      payload[key] = Number(form[key]);
    }
  });

  if (form.partitioning.trim()) {
    payload.partitioning = form.partitioning.trim();
  }

  return payload;
}

function PriceEstimator({ statistics }) {
  const [form, setForm] = useState(INITIAL_FORM);
  const [result, setResult] = useState(null);
  const [mlResult, setMlResult] = useState(null);
  const [mlStatus, setMlStatus] = useState(null);
  const [error, setError] = useState("");
  const [mlError, setMlError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTrainingMl, setIsTrainingMl] = useState(false);

  const neighborhoodOptions = useMemo(() => {
    return statistics?.by_neighborhood?.map((item) => item.neighborhood) || [];
  }, [statistics]);

  const fetchMlStatus = async () => {
    try {
      const response = await api.get("/ml/status");
      setMlStatus(response.data);
    } catch (err) {
      console.error("Eroare la status ML:", err);
    }
  };

  useEffect(() => {
    fetchMlStatus();
  }, []);

  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setMlError("");
    setResult(null);
    setMlResult(null);

    if (!form.neighborhood.trim()) {
      setError("Alege sau introdu un cartier.");
      return;
    }

    if (!form.surface_mp || !form.rooms) {
      setError("Suprafața și numărul de camere sunt obligatorii.");
      return;
    }

    try {
      setIsLoading(true);
      const payload = buildPayload(form);
      const response = await api.post("/estimate", payload);

      if (response.data?.error) {
        setError(response.data.error);
        return;
      }

      setResult(response.data);

      try {
        const mlResponse = await api.post("/estimate/ml", payload);

        if (mlResponse.data?.error) {
          setMlError(mlResponse.data.error);
        } else {
          setMlResult(mlResponse.data);
        }
      } catch (mlErr) {
        console.error("Eroare la estimator ML:", mlErr);
        setMlError("Estimarea ML nu este disponibilă momentan.");
      }
    } catch (err) {
      console.error("Eroare la estimator:", err);
      setError("Nu am putut calcula estimarea. Verifică backend-ul și datele introduse.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setResult(null);
    setMlResult(null);
    setError("");
    setMlError("");
  };

  const handleTrainMl = async () => {
    setMlError("");

    try {
      setIsTrainingMl(true);
      const response = await api.post("/ml/train");
      setMlStatus({
        is_trained: response.data.status === "trained",
        ...response.data,
      });

      if (response.data.status !== "trained") {
        setMlError(response.data.message || "Modelul ML nu a putut fi antrenat.");
      }
    } catch (err) {
      console.error("Eroare la antrenarea ML:", err);
      setMlError("Nu am putut antrena modelul ML.");
    } finally {
      setIsTrainingMl(false);
    }
  };

  return (
    <section className="panel estimator-shell">
      <div className="estimator-heading">
        <div>
          <span className="workspace-label">Estimator preț</span>
          <h2>Estimează valoarea apartamentului tău</h2>
          <p>
            Introdu caracteristicile apartamentului, iar aplicația compară datele
            cu anunțurile active din bază și calculează un interval realist.
          </p>
        </div>

        <div className="ml-training-strip estimator-training-card">
          <div>
            <span>Model ML</span>
            <strong>
              {mlStatus?.is_trained
                ? `Antrenat pe ${mlStatus.training_samples} anunțuri`
                : "Neantrenat încă"}
            </strong>
          </div>

          <button
            className="secondary-btn"
            type="button"
            onClick={handleTrainMl}
            disabled={isTrainingMl}
          >
            {isTrainingMl ? "Antrenez..." : "Antrenează ML"}
          </button>

          {mlError && <p className="estimator-warning">{mlError}</p>}
        </div>
      </div>

      <div className="estimator-layout">
        <form className="estimator-form" onSubmit={handleSubmit}>
          <div className="estimator-card-heading">
            <span>Date apartament</span>
            <strong>Completează estimarea</strong>
          </div>

          <div className="estimator-form-section">
            <span className="estimator-section-label">Date obligatorii</span>
            <div className="field">
              <label htmlFor="estimate-neighborhood">Cartier</label>
              <input
                id="estimate-neighborhood"
                name="neighborhood"
                list="estimate-neighborhoods"
                value={form.neighborhood}
                onChange={handleChange}
                placeholder="Ex: Soarelui"
              />
              <datalist id="estimate-neighborhoods">
                {neighborhoodOptions.map((neighborhood) => (
                  <option key={neighborhood} value={neighborhood} />
                ))}
              </datalist>
            </div>

            <div className="field-row">
              <div className="field">
                <label htmlFor="estimate-surface">Suprafață utilă</label>
                <input
                  id="estimate-surface"
                  name="surface_mp"
                  type="number"
                  min="10"
                  max="500"
                  value={form.surface_mp}
                  onChange={handleChange}
                  placeholder="Ex: 54"
                />
              </div>

              <div className="field">
                <label htmlFor="estimate-rooms">Camere</label>
                <input
                  id="estimate-rooms"
                  name="rooms"
                  type="number"
                  min="1"
                  max="10"
                  value={form.rooms}
                  onChange={handleChange}
                  placeholder="Ex: 2"
                />
              </div>
            </div>
          </div>

          <div className="estimator-form-section estimator-form-section-muted">
            <span className="estimator-section-label">Detalii opționale</span>
            <div className="field-row">
              <div className="field">
                <label htmlFor="estimate-floor">Etaj</label>
                <input
                  id="estimate-floor"
                  name="floor"
                  type="number"
                  min="-2"
                  max="60"
                  value={form.floor}
                  onChange={handleChange}
                  placeholder="Ex: 1"
                />
              </div>

              <div className="field">
                <label htmlFor="estimate-total-floors">Total etaje</label>
                <input
                  id="estimate-total-floors"
                  name="total_floors"
                  type="number"
                  min="1"
                  max="60"
                  value={form.total_floors}
                  onChange={handleChange}
                  placeholder="Ex: 4"
                />
              </div>
            </div>

            <div className="field-row">
              <div className="field">
                <label htmlFor="estimate-year">An construcție</label>
                <input
                  id="estimate-year"
                  name="year_built"
                  type="number"
                  min="1850"
                  max="2035"
                  value={form.year_built}
                  onChange={handleChange}
                  placeholder="Ex: 1980"
                />
              </div>

              <div className="field">
                <label htmlFor="estimate-partitioning">Compartimentare</label>
                <input
                  id="estimate-partitioning"
                  name="partitioning"
                  value={form.partitioning}
                  onChange={handleChange}
                  placeholder="Ex: decomandat"
                />
              </div>
            </div>
          </div>

          {error && <p className="estimator-error">{error}</p>}

          <div className="estimator-actions">
            <button className="primary-btn" type="submit" disabled={isLoading}>
              {isLoading ? "Calculez..." : "Calculează estimarea"}
            </button>

            <button className="secondary-btn" type="button" onClick={handleReset}>
              Resetează
            </button>
          </div>
        </form>

        <div className="estimator-result-panel">
          {!result ? (
            <div className="estimator-empty">
              <span className="estimator-empty-kicker">Estimare automată</span>
              <h3>Estimarea va apărea aici</h3>
              <p>
                Pentru un rezultat bun, completează cel puțin cartierul,
                suprafața și numărul de camere.
              </p>
            </div>
          ) : (
            <>
              <div className="estimator-result-heading">
                <span className="workspace-label">Rezultat estimare</span>
                <h3>Interval și comparație</h3>
              </div>

              {mlResult && (
                <div className="ml-estimate-card ml-estimate-card-primary">
                  <div className="estimate-card-header">
                    <span className="estimator-empty-kicker">Preț estimat</span>
                    <span className={`confidence-pill confidence-${mlResult.estimate.confidence}`}>
                      Încredere {formatConfidence(mlResult.estimate.confidence)}
                    </span>
                  </div>

                  <strong>{formatCurrency(mlResult.estimate.estimated_price)}</strong>
                  <span>
                    Interval realist între {formatCurrency(mlResult.estimate.low_estimate)} și{" "}
                    {formatCurrency(mlResult.estimate.high_estimate)}
                  </span>

                  <div className="ml-estimate-meta">
                    <small>
                      {formatNumber(mlResult.estimate.estimated_price_per_mp)} EUR/mp
                    </small>
                    <small>Model ML antrenat pe datele colectate</small>
                  </div>
                </div>
              )}

              <div className="statistical-estimate-card">
                <div className="estimate-card-header">
                  <span className="estimator-empty-kicker">
                    {mlResult ? "Comparație statistică" : "Preț estimat"}
                  </span>
                  <span className={`confidence-pill confidence-${result.estimate.confidence}`}>
                    Încredere {formatConfidence(result.estimate.confidence)}
                  </span>
                </div>

                <div className="estimate-hero">
                  <span>Valoare estimată</span>
                  <strong>{formatCurrency(result.estimate.estimated_price)}</strong>
                  <small>
                    Interval realist între {formatCurrency(result.estimate.low_estimate)} și{" "}
                    {formatCurrency(result.estimate.high_estimate)}
                  </small>
                </div>

                <div className="estimate-metrics">
                  <div>
                    <span>Preț/mp estimat</span>
                    <strong>
                      {formatNumber(result.estimate.estimated_price_per_mp)} EUR/mp
                    </strong>
                  </div>

                  <div>
                    <span>Anunțuri comparabile</span>
                    <strong>{result.estimate.sample_size}</strong>
                  </div>

                  <div>
                    <span>Cartier</span>
                    <strong>{result.input.neighborhood}</strong>
                  </div>
                </div>
              </div>

              <div className="estimate-market-summary">
                <h3>Context piață</h3>
                <div className="market-summary-grid">
                  <div>
                    <span>Cartier</span>
                    <strong>{result.market_summary.same_neighborhood.count}</strong>
                    <small>
                      mediana{" "}
                      {formatNumber(result.market_summary.same_neighborhood.median_price_per_mp)} EUR/mp
                    </small>
                  </div>

                  <div>
                    <span>Oraș</span>
                    <strong>{result.market_summary.same_city.count}</strong>
                    <small>
                      mediana {formatNumber(result.market_summary.same_city.median_price_per_mp)} EUR/mp
                    </small>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {result?.comparables?.length > 0 && (
        <div className="estimate-comparables">
          <div className="results-header">
            <div>
              <h3 className="results-title">Anunțuri comparabile</h3>
              <p className="results-subtitle">
                Cele mai apropiate anunțuri folosite pentru estimarea statistică.
              </p>
            </div>
          </div>

          <div className="comparables-grid">
            {result.comparables.map((ad) => (
              <article className="comparable-card" key={ad.id}>
                <div className="comparable-top">
                  <span className={getSourceBadgeClass(ad.source)}>
                    {ad.source || "-"}
                  </span>
                  <strong>{formatCurrency(ad.price_eur)}</strong>
                </div>

                <h4>{ad.title}</h4>

                <div className="ad-specs">
                  <span className="ad-spec-pill">{formatNumber(ad.surface_mp)} mp</span>
                  <span className="ad-spec-pill">{formatNumber(ad.rooms)} camere</span>
                  <span className="ad-spec-pill">
                    {formatNumber(ad.price_per_mp)} EUR/mp
                  </span>
                </div>

                <p>
                  {ad.neighborhood || "-"} - scor similaritate{" "}
                  {formatNumber(ad.similarity_score)}
                </p>

                <a className="link-btn comparable-link" href={ad.url} target="_blank" rel="noreferrer">
                  Vezi anunțul
                </a>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default PriceEstimator;
