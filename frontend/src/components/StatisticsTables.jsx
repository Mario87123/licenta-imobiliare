function StatisticsTables({ statistics }) {
  if (!statistics) {
    return <div className="panel">Se încarcă statisticile...</div>;
  }

  return (
    <div className="panel section-stack">
      <div className="section-heading">
        <h2>Statistici</h2>
        <p>
          Privire de ansamblu asupra distribuției anunțurilor după cartier și
          număr de camere.
        </p>
      </div>

      <div className="section-stack">
        <div className="section-heading">
          <h3>Analiză pe cartiere</h3>
          <p>Zonele sunt ordonate pe baza anunțurilor agregate din platformă.</p>
        </div>

        <div className="data-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cartier</th>
                <th>Nr. anunțuri</th>
                <th>Preț mediu</th>
                <th>Suprafață medie</th>
                <th>Preț/mp mediu</th>
              </tr>
            </thead>
            <tbody>
              {statistics.by_neighborhood.map((item, index) => (
                <tr key={index}>
                  <td>{item.neighborhood}</td>
                  <td>{item.count_ads}</td>
                  <td>{item.avg_price}</td>
                  <td>{item.avg_surface}</td>
                  <td>{item.avg_price_per_mp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="section-stack">
        <div className="section-heading">
          <h3>Analiză pe camere</h3>
          <p>Comparație rapidă între tipologiile principale de locuințe.</p>
        </div>

        <div className="data-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Camere</th>
                <th>Nr. anunțuri</th>
                <th>Preț mediu</th>
                <th>Suprafață medie</th>
              </tr>
            </thead>
            <tbody>
              {statistics.by_rooms.map((item, index) => (
                <tr key={index}>
                  <td>{item.rooms}</td>
                  <td>{item.count_ads}</td>
                  <td>{item.avg_price}</td>
                  <td>{item.avg_surface}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default StatisticsTables;
