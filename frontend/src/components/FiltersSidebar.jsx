function FiltersSidebar({ filters, onChange, onApply, onReset }) {
  return (
    <div className="panel filters-panel">
      <div className="filters-heading">
        <h2>Filtre</h2>
        <p>Rafinează rezultatele după zonă, tipologie și intervale relevante.</p>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">Localizare și sursă</span>

        <div className="field">
          <label htmlFor="neighborhood">Cartier</label>
          <input
            id="neighborhood"
            type="text"
            name="neighborhood"
            placeholder="Ex. Girocului"
            value={filters.neighborhood}
            onChange={onChange}
          />
        </div>

        <div className="field">
          <label htmlFor="source">Sursă</label>
          <input
            id="source"
            type="text"
            name="source"
            placeholder="Ex. OLX"
            value={filters.source}
            onChange={onChange}
          />
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">Configurație</span>

        <div className="field">
          <label htmlFor="rooms">Număr camere</label>
          <input
            id="rooms"
            type="number"
            name="rooms"
            min="1"
            max="10"
            step="1"
            placeholder="Ex. 2"
            value={filters.rooms}
            onChange={onChange}
          />
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">Interval preț</span>

        <div className="field-row">
          <div className="field">
            <label htmlFor="min_price">Preț minim</label>
            <input
              id="min_price"
              type="number"
              name="min_price"
              min="0"
              step="1000"
              placeholder="0"
              value={filters.min_price}
              onChange={onChange}
            />
          </div>

          <div className="field">
            <label htmlFor="max_price">Preț maxim</label>
            <input
              id="max_price"
              type="number"
              name="max_price"
              min="0"
              step="1000"
              placeholder="200000"
              value={filters.max_price}
              onChange={onChange}
            />
          </div>
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-group-title">Suprafață utilă</span>

        <div className="field-row">
          <div className="field">
            <label htmlFor="min_surface">Suprafață minimă</label>
            <input
              id="min_surface"
              type="number"
              name="min_surface"
              min="0"
              max="500"
              step="1"
              placeholder="Ex. 20"
              value={filters.min_surface}
              onChange={onChange}
            />
          </div>

          <div className="field">
            <label htmlFor="max_surface">Suprafață maximă</label>
            <input
              id="max_surface"
              type="number"
              name="max_surface"
              min="0"
              max="500"
              step="1"
              placeholder="Ex. 120"
              value={filters.max_surface}
              onChange={onChange}
            />
          </div>
        </div>
      </div>

      <div className="sidebar-actions">
        <button className="primary-btn" onClick={onApply}>
          Aplică filtrele
        </button>
        <button className="secondary-btn" onClick={onReset}>
          Resetează
        </button>
      </div>
    </div>
  );
}

export default FiltersSidebar;
