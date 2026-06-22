function formatValue(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return value;
}

function getStatusClass(status) {
  switch (status) {
    case "done":
      return "job-badge job-badge-success";
    case "running":
      return "job-badge job-badge-running";
    case "pending":
      return "job-badge job-badge-pending";
    case "cancelling":
      return "job-badge job-badge-warning";
    case "cancelled":
      return "job-badge job-badge-muted";
    case "failed":
      return "job-badge job-badge-danger";
    default:
      return "job-badge job-badge-muted";
  }
}

function getSourceClass(source) {
  switch (source) {
    case "olx":
      return "job-pill job-pill-olx";
    case "storia":
      return "job-pill job-pill-storia";
    case "imobiliare":
      return "job-pill job-pill-imobiliare";
    default:
      return "job-pill job-pill-neutral";
  }
}

function getModeLabel(mode) {
  switch (mode) {
    case "quick_refresh":
      return "Quick refresh";
    case "deep_crawl":
      return "Deep crawl";
    case "backfill":
      return "Backfill";
    default:
      return mode || "-";
  }
}

function JobsPanel({ jobs }) {
  return (
    <div className="panel section-stack">
      <div className="section-heading">
        <h2>Joburi crawler</h2>
        <p>
          Monitorizare tehnică a sincronizărilor și a actualizărilor de date.
        </p>
      </div>

      {jobs.length === 0 ? (
        <div className="empty-state">
          <h3>Nu există joburi disponibile</h3>
          <p>
            În momentul de față nu există execuții înregistrate pentru crawler.
          </p>
        </div>
      ) : (
        <div className="jobs-list">
          {jobs.map((job) => (
            <article key={job.id} className="job-card">
              <div className="job-card-top">
                <div className="job-card-title-row">
                  <strong className="job-card-id">Job #{job.id}</strong>
                  <span className={getStatusClass(job.status)}>{job.status}</span>
                </div>

                <div className="job-card-pills">
                  <span className={getSourceClass(job.source)}>
                    {(job.source || "-").toUpperCase()}
                  </span>
                  <span className="job-pill job-pill-neutral">
                    {getModeLabel(job.mode)}
                  </span>
                </div>
              </div>

              <div className="job-metrics-grid">
                <div className="job-metric">
                  <span className="job-metric-label">Pagini</span>
                  <strong className="job-metric-value">
                    {formatValue(job.pages_discovered)} / {formatValue(job.max_pages)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Descoperite</span>
                  <strong className="job-metric-value">
                    {formatValue(job.ads_discovered)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Procesate</span>
                  <strong className="job-metric-value">
                    {formatValue(job.ads_processed)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Inserate</span>
                  <strong className="job-metric-value">
                    {formatValue(job.ads_inserted)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Actualizate</span>
                  <strong className="job-metric-value">
                    {formatValue(job.ads_updated)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Blocate</span>
                  <strong className="job-metric-value">
                    {formatValue(job.blocked_count)}
                  </strong>
                </div>

                <div className="job-metric">
                  <span className="job-metric-label">Erori</span>
                  <strong className="job-metric-value">
                    {formatValue(job.error_count)}
                  </strong>
                </div>
              </div>

              <div className="job-message-box">
                <span className="job-message-label">Mesaj job</span>
                <p className="job-message-text">{job.message || "-"}</p>
              </div>

              <div className="job-time-row">
                <div>
                  <span className="job-time-label">Pornit</span>
                  <strong className="job-time-value">{job.started_at}</strong>
                </div>

                <div>
                  <span className="job-time-label">Finalizat</span>
                  <strong className="job-time-value">{job.finished_at || "-"}</strong>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

export default JobsPanel;
