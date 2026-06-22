import { useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Popup,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import api from "../api/api";

const DEFAULT_MAP_CENTER = [45.759, 21.2197];
const DEFAULT_MAP_ZOOM = 12;
let hasCompletedInitialMapFit = false;

function getGeoDataBounds(geoData) {
  if (!geoData?.features?.length) {
    return [];
  }

  const allPoints = [];

  geoData.features.forEach((feature) => {
    const geometry = feature.geometry;

    if (!geometry) return;

    if (geometry.type === "Polygon") {
      geometry.coordinates[0].forEach(([lng, lat]) => {
        allPoints.push([lat, lng]);
      });
    }

    if (geometry.type === "MultiPolygon") {
      geometry.coordinates.forEach((polygon) => {
        polygon[0].forEach(([lng, lat]) => {
          allPoints.push([lat, lng]);
        });
      });
    }
  });

  return allPoints;
}

function fitMapToGeoData(map, geoData) {
  const bounds = getGeoDataBounds(geoData);

  if (!bounds.length) {
    map.setView(DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM);
    return;
  }

  map.fitBounds(bounds, { padding: [30, 30] });
}

function FitMapToBounds({ geoData }) {
  const map = useMap();

  useEffect(() => {
    if (!geoData || hasCompletedInitialMapFit) {
      return;
    }

    fitMapToGeoData(map, geoData);
    hasCompletedInitialMapFit = true;
  }, [geoData, map]);

  return null;
}

function MapController({ onMapReady }) {
  const map = useMap();

  useEffect(() => {
    onMapReady(map);
  }, [map, onMapReady]);

  return null;
}


function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }

  return Number(value).toLocaleString("ro-RO");
}

function normalizeNeighborhoodKey(value) {
  const normalized = String(value || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  const aliases = {
    cetatii: "cetate",
    cetate: "cetate",
  };

  return aliases[normalized] || normalized;
}

function truncateText(text, max = 70) {
  if (!text) return "";
  if (text.length <= max) return text;
  return `${text.slice(0, max).trim()}...`;
}

function hashString(input) {
  const text = String(input || "");
  let hash = 0;

  for (let i = 0; i < text.length; i += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }

  return Math.abs(hash);
}

function seededRandom(seed) {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

function ringArea(ring) {
  let area = 0;

  for (let i = 0; i < ring.length - 1; i += 1) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[i + 1];
    area += x1 * y2 - x2 * y1;
  }

  return Math.abs(area / 2);
}

function pointInRing(point, ring) {
  const [x, y] = point;
  let inside = false;

  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];

    const intersect =
      yi > y !== yj > y &&
      x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1e-12) + xi;

    if (intersect) inside = !inside;
  }

  return inside;
}

function getCandidateRings(feature) {
  if (!feature?.geometry) return [];

  const geometry = feature.geometry;

  if (geometry.type === "Polygon") {
    return [geometry.coordinates[0]];
  }

  if (geometry.type === "MultiPolygon") {
    return geometry.coordinates.map((polygon) => polygon[0]);
  }

  return [];
}

function getLargestRing(feature) {
  const rings = getCandidateRings(feature);
  if (!rings.length) return null;

  return [...rings].sort((a, b) => ringArea(b) - ringArea(a))[0];
}

function getBoundingBox(ring) {
  const lngs = ring.map(([lng]) => lng);
  const lats = ring.map(([, lat]) => lat);

  return {
    minLng: Math.min(...lngs),
    maxLng: Math.max(...lngs),
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
  };
}

function getRingCentroid(ring) {
  let sumLng = 0;
  let sumLat = 0;

  ring.forEach(([lng, lat]) => {
    sumLng += lng;
    sumLat += lat;
  });

  return [sumLng / ring.length, sumLat / ring.length];
}

function generateStablePointInFeature(feature, seedValue) {
  const ring = getLargestRing(feature);
  if (!ring) return null;

  const bbox = getBoundingBox(ring);
  const baseSeed = hashString(seedValue);

  for (let attempt = 0; attempt < 80; attempt += 1) {
    const lngSeed = baseSeed + attempt * 17.13;
    const latSeed = baseSeed + attempt * 31.71;

    const lng =
      bbox.minLng + seededRandom(lngSeed) * (bbox.maxLng - bbox.minLng);
    const lat =
      bbox.minLat + seededRandom(latSeed) * (bbox.maxLat - bbox.minLat);

    if (pointInRing([lng, lat], ring)) {
      return [lat, lng];
    }
  }

  const [fallbackLng, fallbackLat] = getRingCentroid(ring);
  return [fallbackLat, fallbackLng];
}

function generateDistributedPointsInFeature(feature, seedValues) {
  const ring = getLargestRing(feature);
  if (!ring || !seedValues.length) return [];

  const bbox = getBoundingBox(ring);
  const totalPoints = seedValues.length;
  const gridDensity = Math.max(12, Math.ceil(totalPoints * 2.4));
  const cols = Math.max(3, Math.ceil(Math.sqrt(gridDensity)));
  const rows = Math.max(3, Math.ceil(gridDensity / cols));
  const lngStep = (bbox.maxLng - bbox.minLng) / (cols + 1);
  const latStep = (bbox.maxLat - bbox.minLat) / (rows + 1);
  const candidates = [];
  const featureSeed = hashString(
    feature?.properties?.name || feature?.properties?.cartier || "neighborhood"
  );

  for (let row = 1; row <= rows; row += 1) {
    for (let col = 1; col <= cols; col += 1) {
      const cellSeed = featureSeed + row * 101 + col * 271;
      const lngJitter = (seededRandom(cellSeed) - 0.5) * lngStep * 0.55;
      const latJitter = (seededRandom(cellSeed + 37.9) - 0.5) * latStep * 0.55;
      const lng = bbox.minLng + col * lngStep + lngJitter;
      const lat = bbox.minLat + row * latStep + latJitter;

      if (pointInRing([lng, lat], ring)) {
        candidates.push({
          position: [lat, lng],
          rank: seededRandom(cellSeed + 73.3),
        });
      }
    }
  }

  const orderedCandidates = candidates.sort((a, b) => a.rank - b.rank);

  return seedValues.map((seedValue, index) => {
    const candidate = orderedCandidates[index];
    if (candidate) return candidate.position;

    return generateStablePointInFeature(feature, `${seedValue}-${index}`);
  });
}

function MapPlaceholder({
  ads,
  filters = {},
  onSelectNeighborhood = () => {},
  onClearNeighborhood = () => {},
  selectedNeighborhood = "",
}) {
  const [mapData, setMapData] = useState(null);
  const [geoData, setGeoData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [geoLoading, setGeoLoading] = useState(true);
  const [error, setError] = useState("");
  const [geoError, setGeoError] = useState("");
  const [hoveredNeighborhood, setHoveredNeighborhood] = useState(null);
  const hasLoadedMapDataRef = useRef(false);
  const mapInstanceRef = useRef(null);

  useEffect(() => {
    const loadGeoJson = async () => {
      setGeoLoading(true);
      setGeoError("");

      try {
        const response = await fetch("/geo/timisoara-neighborhoods.geojson");
        if (!response.ok) {
          throw new Error("Fișierul GeoJSON nu a fost găsit.");
        }

        const data = await response.json();
        setGeoData(data);
      } catch (err) {
        console.error("Eroare la încărcarea GeoJSON:", err);
        setGeoError(
          "Nu am putut încărca fișierul geo/timisoara-neighborhoods.geojson."
        );
      } finally {
        setGeoLoading(false);
      }
    };

    loadGeoJson();
  }, []);

  useEffect(() => {
    const fetchMapData = async () => {
      const isInitialLoad = !hasLoadedMapDataRef.current;

      if (isInitialLoad) {
        setLoading(true);
      }

      setError("");

      try {
        const params = {
          min_confidence: "low",
        };

        Object.entries(filters).forEach(([key, value]) => {
          if (key === "neighborhood") {
            return;
          }

          if (value !== "" && value !== null && value !== undefined) {
            params[key] = value;
          }
        });

        const response = await api.get("/map/neighborhoods", { params });
        setMapData(response.data);
        hasLoadedMapDataRef.current = true;
      } catch (err) {
        console.error("Eroare la încărcarea datelor hărții:", err);
        setError("Nu am putut încărca statisticile pentru cartiere.");
      } finally {
        if (isInitialLoad) {
          setLoading(false);
        }
      }
    };

    fetchMapData();
  }, [filters]);

  const statsMap = useMemo(() => {
    const result = new Map();

    (mapData?.items || []).forEach((item) => {
      result.set(normalizeNeighborhoodKey(item.neighborhood), item);
    });

    return result;
  }, [mapData]);

  const selectedNeighborhoodKey = useMemo(
    () => normalizeNeighborhoodKey(selectedNeighborhood),
    [selectedNeighborhood]
  );

  const selectedFeature = useMemo(() => {
    if (!geoData?.features?.length || !selectedNeighborhood) {
      return null;
    }

    return (
      geoData.features.find(
        (feature) =>
          normalizeNeighborhoodKey(feature?.properties?.name) === selectedNeighborhoodKey
      ) || null
    );
  }, [geoData, selectedNeighborhood, selectedNeighborhoodKey]);

  const adMarkers = useMemo(() => {
    if (!selectedFeature || !selectedNeighborhood) {
      return [];
    }

    const neighborhoodAds = ads.filter(
      (ad) => normalizeNeighborhoodKey(ad.neighborhood) === selectedNeighborhoodKey
    );
    const markerPositions = generateDistributedPointsInFeature(
      selectedFeature,
      neighborhoodAds.map((ad) => `${ad.id || ""}-${ad.url || ad.title || ""}`)
    );

    return neighborhoodAds
      .map((ad, index) => {
        return {
          ...ad,
          markerPosition: markerPositions[index],
        };
      })
      .filter((ad) => Array.isArray(ad.markerPosition));
  }, [ads, selectedFeature, selectedNeighborhood, selectedNeighborhoodKey]);

  const totalMappedNeighborhoods = mapData?.total_neighborhoods || 0;
  const topNeighborhood =
    (mapData?.items || []).length > 0
      ? [...mapData.items].sort((a, b) => b.count_ads - a.count_ads)[0]
      : null;

  const resetMapView = () => {
    if (!mapInstanceRef.current || !geoData) {
      return;
    }

    fitMapToGeoData(mapInstanceRef.current, geoData);
  };

  const styleFeature = (feature) => {
    const neighborhoodName = feature?.properties?.name;
    const stat = statsMap.get(normalizeNeighborhoodKey(neighborhoodName));
    const countAds = stat?.count_ads || 0;

    const isSelected = selectedNeighborhoodKey === normalizeNeighborhoodKey(neighborhoodName);
    const isHovered = hoveredNeighborhood === neighborhoodName;

    return {
      color: isSelected ? "#1d2433" : isHovered ? "#6b5f52" : "#ffffff",
      weight: isSelected ? 2.4 : isHovered ? 2 : 1.1,
      fill: true,
      fillColor: isSelected ? "#c7bbb0" : isHovered ? "#d8d0c7" : "#cfc8bf",
      fillOpacity: isSelected ? 0.72 : isHovered ? 0.62 : 0.52,
      interactive: true,
      keyboard: false,
      className: "neighborhood-polygon",
    };
  };

  const onEachFeature = (feature, layer) => {
    const neighborhoodName = feature?.properties?.name;
    const stat = statsMap.get(normalizeNeighborhoodKey(neighborhoodName));

    const tooltipHtml = `
      <div class="map-tooltip">
        <strong>${neighborhoodName || "Cartier"}</strong><br/>
        Anunțuri: ${formatNumber(stat?.count_ads || 0)}<br/>
        Preț mediu: ${formatNumber(stat?.avg_price)} €<br/>
        Suprafață medie: ${formatNumber(stat?.avg_surface)} mp<br/>
        Preț/mp: ${formatNumber(stat?.avg_price_per_mp)} €
      </div>
    `;

    layer.bindTooltip(tooltipHtml, {
      sticky: true,
      direction: "top",
      opacity: 0.96,
      className: "neighborhood-tooltip",
    });

    layer.options.keyboard = false;

    layer.on("add", () => {
      const element = layer.getElement();

      if (!element) {
        return;
      }

      element.setAttribute("tabindex", "-1");
      element.setAttribute("focusable", "false");
      element.style.outline = "none";
    });

    layer.on({
      mouseover: () => setHoveredNeighborhood(neighborhoodName),
      mouseout: () => setHoveredNeighborhood(null),
      click: (event) => {
        event.originalEvent?.preventDefault();
        event.originalEvent?.stopPropagation();

        if (layer.getElement()) {
          layer.getElement().blur?.();
        }

        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }

        console.log("Click pe cartier:", neighborhoodName);
        onSelectNeighborhood(stat?.neighborhood || neighborhoodName);
      },
    });
  };

  return (
    <div className="panel map-shell">
      <div className="section-heading">
        <h2>Harta cartierelor din Timișoara</h2>
        <p>
          Cartiere colorate după volumul de anunțuri, iar pentru cartierul
          selectat apar marker-ele anunțurilor poziționate aproximativ în
          interiorul zonei.
        </p>
      </div>

      {selectedNeighborhood && (
        <div className="map-active-filter">
          <div>
            <strong>Cartier selectat:</strong> {selectedNeighborhood}
          </div>

          <button className="secondary-btn" onClick={onClearNeighborhood}>
            Elimină filtrul de cartier
          </button>
        </div>
      )}

      {loading || geoLoading ? (
        <div className="empty-state">
          <h3>Se încarcă harta</h3>
          <p>Pregătim poligoanele cartierelor și anunțurile mapate.</p>
        </div>
      ) : error || geoError ? (
        <div className="empty-state">
          <h3>Harta nu este disponibilă momentan</h3>
          <p>{error || geoError}</p>
        </div>
      ) : (
        <div className="map-layout">
          <div className="map-stage">
            <div className="map-stage-header">
              <div>
                <h3>Cartiere și anunțuri în interiorul lor</h3>
                <p>
                  Selectează un cartier pentru a vedea anunțurile plasate
                  aproximativ în acea zonă.
                </p>
              </div>

              <div className="map-chip">
                {selectedNeighborhood
                  ? `${adMarkers.length} anunțuri afișate în ${selectedNeighborhood}`
                  : "Selectează un cartier pentru marker-ele anunțurilor"}
              </div>
            </div>

            <div className="map-canvas">
              <button
                type="button"
                className="map-reset-button"
                onClick={resetMapView}
              >
                Reseteaza harta
              </button>

              <MapContainer
                center={DEFAULT_MAP_CENTER}
                zoom={DEFAULT_MAP_ZOOM}
                scrollWheelZoom={false}
                className="leaflet-map"
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <MapController
                  onMapReady={(map) => {
                    mapInstanceRef.current = map;
                  }}
                />

                <FitMapToBounds geoData={geoData} />

                <GeoJSON
                  data={geoData}
                  style={styleFeature}
                  onEachFeature={onEachFeature}
                />

                {adMarkers.map((ad) => (
                  <CircleMarker
                    key={ad.id || ad.url}
                    center={ad.markerPosition}
                    radius={7}
                    pathOptions={{
                      color: "#ffffff",
                      weight: 2,
                      fillColor: "#1d2433",
                      fillOpacity: 0.92,
                    }}
                  >
                    <Tooltip direction="top" offset={[0, -8]} opacity={0.98}>
                      <div className="ad-marker-tooltip">
                        <strong>{truncateText(ad.title, 72)}</strong>
                        <br />
                        Preț: {formatNumber(ad.price_eur)} €
                        <br />
                        Suprafață: {formatNumber(ad.surface_mp)} mp
                        <br />
                        Camere: {formatNumber(ad.rooms)}
                        <br />
                        Sursă: {ad.source || "-"}
                      </div>
                    </Tooltip>

                    <Popup>
                      <div className="map-popup">
                        <strong>{ad.title}</strong>
                        <br />
                        Preț: {formatNumber(ad.price_eur)} €
                        <br />
                        Suprafață: {formatNumber(ad.surface_mp)} mp
                        <br />
                        Camere: {formatNumber(ad.rooms)}
                        <br />
                        Cartier: {ad.neighborhood || "-"}
                        <br />
                        Sursă: {ad.source || "-"}
                        <br />
                        <br />
                        <a
                          className="map-popup-link"
                          href={ad.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Deschide anunțul
                        </a>
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
          </div>

          <aside className="map-sidebar">
            <div className="map-sidecard">
              <span className="stat-label">Cartiere cu date</span>
              <strong className="stat-value">{totalMappedNeighborhoods}</strong>
              <span className="stat-note">
                Cartiere care au cel puțin un anunț valid în filtrul curent.
              </span>
            </div>

            <div className="map-sidecard">
              <span className="stat-label">Anunțuri afișate</span>
              <strong className="stat-value">{ads.length}</strong>
              <span className="stat-note">
                Lista principală și harta sunt conectate prin filtrul de cartier.
              </span>
            </div>

            <div className="map-sidecard">
              <span className="stat-label">Cartier dominant</span>
              <strong className="stat-value map-sidecard-title">
                {topNeighborhood ? topNeighborhood.neighborhood : "-"}
              </strong>
              <span className="stat-note">
                {topNeighborhood
                  ? `${formatNumber(topNeighborhood.count_ads)} anunțuri și preț mediu de ${formatNumber(topNeighborhood.avg_price)} €`
                  : "Încă nu există suficiente date pentru a determina un cartier dominant."}
              </span>
            </div>

            <div className="map-sidecard">
              <span className="stat-label">Notă de poziționare</span>
              <span className="stat-note">
                Marker-ele anunțurilor sunt plasate aproximativ în interiorul
                cartierului, nu la adresa exactă a proprietății.
              </span>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export default MapPlaceholder;
