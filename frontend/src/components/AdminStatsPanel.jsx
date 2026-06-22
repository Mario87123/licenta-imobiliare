import DataAuditPanel from "./DataAuditPanel";

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return Number(value).toLocaleString("ro-RO");
}

function formatCurrency(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return `${Number(value).toLocaleString("ro-RO")} EUR`;
}

function AdminStatsPanel({ statistics, dataAudit }) {
  if (!statistics) {
    return <div className="panel">Se încarcă statisticile administrative...</div>;
  }

  return (
    <div className="panel section-stack admin-panel">
      <div className="section-heading">
        <span className="workspace-label">Admin</span>
        <h2>Statistici administrative</h2>
        <p>
          Indicatori pentru monitorizarea platformei: utilizatori, favorite,
          distribuția anunțurilor și prețurile pe zone sau suprafețe.
        </p>
      </div>

      <div className="admin-metrics-grid">
        <article className="admin-metric-card">
          <span>Utilizatori</span>
          <strong>{formatNumber(statistics.users?.total_users)}</strong>
          <small>Conturi create în platformă</small>
        </article>

        <article className="admin-metric-card">
          <span>Favorite</span>
          <strong>{formatNumber(statistics.users?.total_favorites)}</strong>
          <small>Anunțuri salvate de utilizatori</small>
        </article>

        <article className="admin-metric-card">
          <span>Anunțuri active</span>
          <strong>{formatNumber(statistics.ads?.active_ads)}</strong>
          <small>{formatNumber(statistics.ads?.inactive_ads)} inactive</small>
        </article>

        <article className="admin-metric-card">
          <span>Preț/mp mediu</span>
          <strong>{formatCurrency(statistics.ads?.avg_price_per_mp)}</strong>
          <small>Calculat pe baza anunțurilor valide</small>
        </article>
      </div>

      <div className="audit-two-column">
        <section className="audit-section">
          <div className="section-heading">
            <h3>Distribuția prețurilor pe cartiere</h3>
            <p>Top cartiere după numărul de anunțuri active.</p>
          </div>

          <div className="data-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Cartier</th>
                  <th>Anunțuri</th>
                  <th>Preț mediu</th>
                  <th>Preț/mp</th>
                </tr>
              </thead>
              <tbody>
                {statistics.price_by_neighborhood?.map((item) => (
                  <tr key={item.neighborhood}>
                    <td>{item.neighborhood}</td>
                    <td>{formatNumber(item.count_ads)}</td>
                    <td>{formatCurrency(item.avg_price)}</td>
                    <td>{formatCurrency(item.avg_price_per_mp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="audit-section">
          <div className="section-heading">
            <h3>Distribuția prețurilor după suprafață</h3>
            <p>Grupe de suprafață utilă folosite pentru analiză rapidă.</p>
          </div>

          <div className="data-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Suprafață</th>
                  <th>Anunțuri</th>
                  <th>Preț mediu</th>
                  <th>Preț/mp</th>
                </tr>
              </thead>
              <tbody>
                {statistics.price_by_surface?.map((item) => (
                  <tr key={item.surface_bucket}>
                    <td>{item.surface_bucket}</td>
                    <td>{formatNumber(item.count_ads)}</td>
                    <td>{formatCurrency(item.avg_price)}</td>
                    <td>{formatCurrency(item.avg_price_per_mp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <div className="audit-two-column">
        <section className="audit-section">
          <div className="section-heading">
            <h3>Anunțuri după sursă</h3>
            <p>Volumul de date colectat din fiecare platformă.</p>
          </div>

          <div className="audit-list">
            {statistics.by_source?.map((item) => (
              <div className="audit-list-item" key={item.source || "unknown"}>
                <strong>{item.source || "-"}</strong>
                <span>{formatNumber(item.count_ads)} anunțuri</span>
              </div>
            ))}
          </div>
        </section>

        <section className="audit-section">
          <div className="section-heading">
            <h3>Joburi după status</h3>
            <p>Sumar pentru execuțiile crawlerelor.</p>
          </div>

          <div className="audit-list">
            {statistics.jobs_by_status?.map((item) => (
              <div className="audit-list-item" key={item.status || "unknown"}>
                <strong>{item.status || "-"}</strong>
                <span>{formatNumber(item.count_jobs)} joburi</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="section-heading">
        <span className="workspace-label">Audit administrativ</span>
        <h2>Controlul calității datelor</h2>
        <p>
          Această zonă este destinată administratorului și grupează problemele
          tehnice ale datelor colectate: câmpuri lipsă, URL-uri ignorate,
          outlieri și statusul modelului ML.
        </p>
      </div>

      <DataAuditPanel audit={dataAudit} />
    </div>
  );
}

export default AdminStatsPanel;
