import AdCard from "./AdCard";

function AdsGrid({
  ads,
  favoriteIds = new Set(),
  onToggleFavorite,
  title = "Anunțuri filtrate",
  subtitle,
  emptyTitle = "Nu există rezultate pentru selecția curentă",
  emptyText = "Încearcă un interval de preț mai larg, modifică suprafața sau elimină unul dintre filtre pentru a descoperi mai multe anunțuri.",
}) {
  const safeAds = Array.isArray(ads) ? ads : [];

  if (safeAds.length === 0) {
    return (
      <div className="panel empty-state">
        <h3>{emptyTitle}</h3>
        <p>{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="section-stack">
      <div className="results-bar">
        <div>
          <h3 className="results-title">{title}</h3>
          <p className="results-subtitle">
            {subtitle || `${safeAds.length} rezultate pregătite pentru analiză și comparație.`}
          </p>
        </div>

        <span className="workspace-chip">Sortare vizuală: cele mai recente</span>
      </div>

      <div className="ads-grid-panel">
        <div className="ads-grid">
          {safeAds.map((ad) => (
            <AdCard
              key={ad.id}
              ad={ad}
              isFavorite={favoriteIds.has(ad.id)}
              onToggleFavorite={onToggleFavorite}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default AdsGrid;
