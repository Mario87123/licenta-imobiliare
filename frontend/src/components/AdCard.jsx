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

function AdCard({ ad, isFavorite = false, onToggleFavorite }) {
  return (
    <article className="listing-card">
      <div className="ad-card-top">
        <div className="ad-badges">
          <span className={getSourceBadgeClass(ad.source)}>
            {ad.source || "sursă"}
          </span>

          <span className="ad-location">{ad.neighborhood || "Cartier necunoscut"}</span>

          {ad.duplicate_group_id && (
            <span className="duplicate-badge">
              duplicat {Math.round(ad.duplicate_score || 0)}%
            </span>
          )}
        </div>

        <div className="price-stack">
          <div className="price">
            <span className="price-value">
              {ad.price_eur?.toLocaleString("ro-RO") || "-"} EUR
            </span>
          </div>

          <button
            className={
              isFavorite
                ? "favorite-star-btn favorite-star-btn-active"
                : "favorite-star-btn"
            }
            type="button"
            onClick={() => onToggleFavorite?.(ad)}
            aria-pressed={isFavorite}
            aria-label={isFavorite ? "Elimină de la favorite" : "Adaugă la favorite"}
            title={isFavorite ? "Salvat la favorite" : "Adaugă la favorite"}
          >
            ★
          </button>
        </div>
      </div>

      <h3 className="ad-title">{ad.title}</h3>

      <div className="ad-specs">
        <span className="ad-spec-pill">{ad.surface_mp || "-"} mp</span>
        <span className="ad-spec-pill">{ad.rooms || "-"} camere</span>
        <span className="ad-spec-pill">{ad.partitioning || "-"}</span>
        <span className="ad-spec-pill">Etaj {ad.floor ?? "-"}</span>
      </div>

      <div className="ad-meta-grid ad-meta-grid-compact">
        <div className="ad-meta-item">
          <span>An construcție</span>
          <strong>{ad.year_built ?? "-"}</strong>
        </div>

        <div className="ad-meta-item">
          <span>Zonă</span>
          <strong>{ad.neighborhood || "-"}</strong>
        </div>
      </div>

      <div className="ad-actions-row ad-actions-row-single">
        <a className="link-btn" href={ad.url} target="_blank" rel="noreferrer">
          Vezi anunțul
        </a>
      </div>
    </article>
  );
}

export default AdCard;
