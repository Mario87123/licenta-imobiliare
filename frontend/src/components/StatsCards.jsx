function StatsCards({ statistics, adsCount }) {
  if (!statistics) {
    return (
      <div className="stats-grid">
        <div className="stat-card stat-card--featured">
          <span className="stat-label">Piața locală</span>
          <strong className="stat-value">Se încarcă...</strong>
          <span className="stat-note">
            Pregătim indicatorii principali ai pieței rezidențiale.
          </span>
        </div>
      </div>
    );
  }

  const duplicateGroups = statistics.duplicates?.duplicate_groups || 0;

  const avgPrice =
    statistics.by_neighborhood?.length > 0
      ? Math.round(
          statistics.by_neighborhood.reduce(
            (acc, item) => acc + (item.avg_price || 0),
            0
          ) / statistics.by_neighborhood.length
        )
      : 0;

  return (
    <div className="stats-grid">
      <div className="stat-card stat-card--featured">
        <span className="stat-label">Indicator principal</span>
        <strong className="stat-value">
          {avgPrice.toLocaleString("ro-RO")} EUR
        </strong>
        <span className="stat-note">
          Preț mediu estimat pe baza cartierelor detectate în setul curent de
          date.
        </span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Total afișate</span>
        <strong className="stat-value">{adsCount}</strong>
        <span className="stat-note">Rezultatele vizibile după filtrare.</span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Total în bază</span>
        <strong className="stat-value">{statistics.total_ads}</strong>
        <span className="stat-note">Anunțuri colectate și stocate local.</span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Duplicate probabile</span>
        <strong className="stat-value">{duplicateGroups}</strong>
        <span className="stat-note">
          Grupuri cross-source marcate fără ștergere automată.
        </span>
      </div>
    </div>
  );
}

export default StatsCards;
