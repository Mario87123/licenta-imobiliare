function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return Number(value).toLocaleString("ro-RO");
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return `${Number(value).toLocaleString("ro-RO")}%`;
}

function formatCurrency(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return `${Number(value).toLocaleString("ro-RO")} EUR`;
}

function getReadinessLabel(status) {
  switch (status) {
    case "good":
      return "Pregătit";
    case "warning":
      return "Necesită verificare";
    case "critical":
      return "Necesită curățare";
    default:
      return "Necunoscut";
  }
}

function getIssueClass(severity) {
  switch (severity) {
    case "critical":
      return "audit-issue audit-issue-critical";
    case "warning":
      return "audit-issue audit-issue-warning";
    default:
      return "audit-issue audit-issue-info";
  }
}

function DataAuditPanel({ audit }) {
  if (!audit) {
    return (
      <div className="audit-panel">
        <div className="empty-state">
          <h3>Se încarcă auditul datelor</h3>
          <p>Calculăm indicatorii de calitate pentru baza curentă.</p>
        </div>
      </div>
    );
  }

  const missingEntries = Object.entries(audit.quality?.missing || {});
  const sourceRows = audit.distribution?.by_source || [];
  const cityRows = audit.distribution?.by_city || [];
  const outliers = audit.outliers?.price_per_mp || [];
  const ignoredRows = audit.crawler?.ignored_by_reason || [];
  const latestJobs = audit.crawler?.latest_jobs || [];
  const mlMetrics = audit.ml?.metrics || {};

  return (
    <div className="audit-panel">
      <div className="audit-hero">
        <div>
          <span className="workspace-label">Audit pre-hosting</span>
          <h3>Sănătatea datelor colectate</h3>
          <p>
            Raport rapid pentru verificarea bazei înainte de demo, hosting sau
            antrenarea finală a modelului ML.
          </p>
        </div>

        <div className={`audit-score audit-score-${audit.readiness?.status}`}>
          <span>Scor pregătire</span>
          <strong>{formatNumber(audit.readiness?.score)}</strong>
          <small>{getReadinessLabel(audit.readiness?.status)}</small>
        </div>
      </div>

      <div className="audit-metrics-grid">
        <div className="audit-metric-card">
          <span>Anunțuri active</span>
          <strong>{formatNumber(audit.summary?.active_ads)}</strong>
          <small>{formatNumber(audit.summary?.inactive_ads)} inactive</small>
        </div>

        <div className="audit-metric-card">
          <span>Pregătite pentru estimator</span>
          <strong>{formatNumber(audit.summary?.estimator_ready_ads)}</strong>
          <small>{formatPercent(audit.summary?.estimator_ready_percent)} din bază</small>
        </div>

        <div className="audit-metric-card">
          <span>Duplicate respinse</span>
          <strong>{formatNumber(audit.duplicates?.rejected_duplicates)}</strong>
          <small>{formatNumber(audit.duplicates?.duplicate_groups)} grupuri detectate</small>
        </div>

        <div className="audit-metric-card">
          <span>Model ML</span>
          <strong>{audit.ml?.is_trained ? "Antrenat" : "Neantrenat"}</strong>
          <small>
            {audit.ml?.is_trained
              ? `${formatNumber(audit.ml.training_samples)} anunțuri`
              : "Antrenează după crawl-ul final"}
          </small>
        </div>
      </div>

      <div className="audit-section">
        <div className="section-heading">
          <h3>Probleme găsite</h3>
          <p>Ordinea este orientativă: critical, warning, apoi info.</p>
        </div>

        {audit.issues?.length ? (
          <div className="audit-issues-list">
            {audit.issues.map((issue) => (
              <article className={getIssueClass(issue.severity)} key={issue.code}>
                <div>
                  <span>{issue.severity}</span>
                  <strong>{issue.title}</strong>
                  <p>{issue.detail}</p>
                </div>
                {issue.count !== null && issue.count !== undefined && (
                  <b>{formatNumber(issue.count)}</b>
                )}
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <h3>Nu sunt probleme evidente</h3>
            <p>Datele arată bine pentru un demo sau pentru o rulare finală.</p>
          </div>
        )}
      </div>

      <div className="audit-section">
        <div className="section-heading">
          <h3>Câmpuri lipsă</h3>
          <p>Indicatori care pot afecta harta, comparabilele și estimatorul.</p>
        </div>

        <div className="audit-quality-grid">
          {missingEntries.map(([key, item]) => (
            <div className="audit-quality-card" key={key}>
              <span>{key.replaceAll("_", " ")}</span>
              <strong>{formatNumber(item.count)}</strong>
              <small>{formatPercent(item.percent)}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="audit-two-column">
        <div className="audit-section">
          <div className="section-heading">
            <h3>Surse</h3>
            <p>Distribuția anunțurilor active pe platforme.</p>
          </div>

          <div className="data-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Sursă</th>
                  <th>Anunțuri</th>
                  <th>Preț mediu</th>
                  <th>Preț/mp</th>
                </tr>
              </thead>
              <tbody>
                {sourceRows.map((item) => (
                  <tr key={item.source || "unknown"}>
                    <td>{item.source || "-"}</td>
                    <td>{formatNumber(item.count_ads)}</td>
                    <td>{formatCurrency(item.avg_price)}</td>
                    <td>{formatCurrency(item.avg_price_per_mp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="audit-section">
          <div className="section-heading">
            <h3>Orașe / localități</h3>
            <p>Util pentru verificarea zonelor din jurul Timișoarei.</p>
          </div>

          <div className="data-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Localitate</th>
                  <th>Anunțuri</th>
                </tr>
              </thead>
              <tbody>
                {cityRows.map((item) => (
                  <tr key={item.city || "unknown"}>
                    <td>{item.city || "-"}</td>
                    <td>{formatNumber(item.count_ads)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="audit-two-column">
        <div className="audit-section">
          <div className="section-heading">
            <h3>Outlieri preț/mp</h3>
            <p>
              Sub {formatNumber(audit.summary?.price_per_mp_low_threshold)} EUR/mp sau
              peste {formatNumber(audit.summary?.price_per_mp_high_threshold)} EUR/mp.
            </p>
          </div>

          <div className="audit-list">
            {outliers.length ? (
              outliers.slice(0, 8).map((item) => (
                <a
                  className="audit-list-item"
                  href={item.url}
                  key={item.id}
                  rel="noreferrer"
                  target="_blank"
                >
                  <strong>{item.neighborhood || "-"}</strong>
                  <span>{formatCurrency(item.price_per_mp)} / mp</span>
                  <small>{item.source || "-"} - {formatCurrency(item.price_eur)}</small>
                </a>
              ))
            ) : (
              <p className="audit-muted">Nu există outlieri după pragurile curente.</p>
            )}
          </div>
        </div>

        <div className="audit-section">
          <div className="section-heading">
            <h3>URL-uri ignorate</h3>
            <p>Top motive pentru care crawlerul a sărit anunțuri.</p>
          </div>

          <div className="audit-list">
            {ignoredRows.length ? (
              ignoredRows.slice(0, 8).map((item) => (
                <div className="audit-list-item" key={`${item.source}-${item.reason}`}>
                  <strong>{item.reason || "-"}</strong>
                  <span>{formatNumber(item.count)}</span>
                  <small>{item.source || "-"}</small>
                </div>
              ))
            ) : (
              <p className="audit-muted">Nu există URL-uri ignorate.</p>
            )}
          </div>
        </div>
      </div>

      <div className="audit-two-column">
        <div className="audit-section">
          <div className="section-heading">
            <h3>Joburi recente</h3>
            <p>Ultimele execuții crawler și rezultat sumar.</p>
          </div>

          <div className="audit-list">
            {latestJobs.map((job) => (
              <div className="audit-list-item" key={job.id}>
                <strong>Job #{job.id} - {job.source}</strong>
                <span>{job.status}</span>
                <small>
                  procesate {formatNumber(job.ads_processed)}, inserate{" "}
                  {formatNumber(job.ads_inserted)}, erori {formatNumber(job.error_count)}
                </small>
              </div>
            ))}
          </div>
        </div>

        <div className="audit-section">
          <div className="section-heading">
            <h3>Model ML</h3>
            <p>Statusul modelului folosit pentru estimarea prețului.</p>
          </div>

          <div className="audit-ml-card">
            <strong>{audit.ml?.is_trained ? "Model antrenat" : "Model neantrenat"}</strong>
            <span>
              {audit.ml?.is_trained
                ? `Antrenat pe ${formatNumber(audit.ml.training_samples)} anunțuri`
                : audit.ml?.message || "Nu există model salvat."}
            </span>
            {audit.ml?.is_trained && (
              <div className="audit-quality-grid">
                <div className="audit-quality-card">
                  <span>MAE</span>
                  <strong>{formatCurrency(mlMetrics.mae)}</strong>
                </div>
                <div className="audit-quality-card">
                  <span>MAPE</span>
                  <strong>{formatPercent(mlMetrics.mape)}</strong>
                </div>
                <div className="audit-quality-card">
                  <span>RMSE</span>
                  <strong>{formatCurrency(mlMetrics.rmse)}</strong>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default DataAuditPanel;
