import { useEffect, useMemo, useState } from "react";
import api from "../api/api";
import Header from "../components/Header";
import AuthPanel from "../components/AuthPanel";
import CrawlerControls from "../components/CrawlerControls";
import FiltersSidebar from "../components/FiltersSidebar";
import StatsCards from "../components/StatsCards";
import AdsGrid from "../components/AdsGrid";
import JobsPanel from "../components/JobsPanel";
import StatisticsTables from "../components/StatisticsTables";
import AdminStatsPanel from "../components/AdminStatsPanel";
import MapPlaceholder from "../components/MapPlaceholder";
import PriceEstimator from "../components/PriceEstimator";

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("currentUser"));
  } catch {
    return null;
  }
}

function Dashboard() {
  const [currentUser, setCurrentUser] = useState(readStoredUser);
  const [ads, setAds] = useState([]);
  const [favorites, setFavorites] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [statistics, setStatistics] = useState(null);
  const [adminStatistics, setAdminStatistics] = useState(null);
  const [dataAudit, setDataAudit] = useState(null);
  const [activeTab, setActiveTab] = useState("ads");
  const [crawlMode, setCrawlMode] = useState("quick_refresh");
  const [crawlSource, setCrawlSource] = useState("olx");
  const [authModal, setAuthModal] = useState(null);

  const [filters, setFilters] = useState({
    neighborhood: "",
    rooms: "",
    min_price: "",
    max_price: "",
    min_surface: "",
    max_surface: "",
    source: "",
  });

  const favoriteIds = useMemo(
    () => new Set(favorites.map((ad) => ad.id)),
    [favorites]
  );

  const filteredFavorites = useMemo(() => {
    return favorites.filter((ad) => {
      const matchesNeighborhood =
        !filters.neighborhood ||
        (ad.neighborhood || "")
          .toLowerCase()
          .includes(filters.neighborhood.toLowerCase());

      const matchesSource =
        !filters.source ||
        (ad.source || "").toLowerCase().includes(filters.source.toLowerCase());

      const matchesRooms =
        !filters.rooms || Number(ad.rooms) === Number(filters.rooms);

      const matchesMinPrice =
        !filters.min_price || Number(ad.price_eur || 0) >= Number(filters.min_price);

      const matchesMaxPrice =
        !filters.max_price || Number(ad.price_eur || 0) <= Number(filters.max_price);

      const matchesMinSurface =
        !filters.min_surface ||
        Number(ad.surface_mp || 0) >= Number(filters.min_surface);

      const matchesMaxSurface =
        !filters.max_surface ||
        Number(ad.surface_mp || 0) <= Number(filters.max_surface);

      return (
        matchesNeighborhood &&
        matchesSource &&
        matchesRooms &&
        matchesMinPrice &&
        matchesMaxPrice &&
        matchesMinSurface &&
        matchesMaxSurface
      );
    });
  }, [favorites, filters]);

  const fetchAds = async (customFilters = filters) => {
    try {
      const params = {};

      Object.keys(customFilters).forEach((key) => {
        if (customFilters[key] !== "") {
          params[key] = customFilters[key];
        }
      });

      const res = await api.get("/ads", { params });
      setAds(res.data);
    } catch (error) {
      console.error("Eroare la ads:", error);
    }
  };

  const fetchFavorites = async () => {
    if (!currentUser) {
      return;
    }

    try {
      const res = await api.get("/favorites");
      setFavorites(res.data.items || []);
    } catch (error) {
      console.error("Eroare la favorite:", error);
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await api.get("/crawl/jobs");
      setJobs(res.data);
      return res.data;
    } catch (error) {
      console.error("Eroare la jobs:", error);
      return [];
    }
  };

  const fetchStatistics = async () => {
    try {
      const res = await api.get("/statistics");
      setStatistics(res.data);
    } catch (error) {
      console.error("Eroare la statistics:", error);
    }
  };

  const fetchAdminStatistics = async () => {
    if (currentUser?.role !== "admin") {
      return;
    }

    try {
      const res = await api.get("/admin/statistics");
      setAdminStatistics(res.data);
    } catch (error) {
      console.error("Eroare la admin statistics:", error);
    }
  };

  const fetchDataAudit = async () => {
    try {
      const res = await api.get("/audit/data-quality");
      setDataAudit(res.data);
    } catch (error) {
      console.error("Eroare la audit date:", error);
    }
  };

  const currentJob = useMemo(() => {
    return (
      jobs.find((job) =>
        ["pending", "running", "cancelling"].includes(job.status)
      ) || null
    );
  }, [jobs]);

  const startCrawler = async () => {
    if (currentJob) {
      return;
    }

    try {
      await api.post("/crawl/start", null, {
        params: {
          source: crawlSource,
          mode: crawlMode,
        },
      });

      await fetchJobs();
    } catch (error) {
      console.error("Eroare la crawler:", error);
    }
  };

  const cancelCrawler = async () => {
    if (!currentJob || currentJob.status !== "running") {
      return;
    }

    try {
      await api.post(`/crawl/jobs/${currentJob.id}/cancel`);
      await fetchJobs();
    } catch (error) {
      console.error("Eroare la cancel crawler:", error);
    }
  };

  const handleAuthSuccess = (user) => {
    setCurrentUser(user);
    setAuthModal(null);
    fetchFavorites();
    fetchAdminStatistics();
  };

  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (error) {
      console.error("Eroare la logout:", error);
    }

    localStorage.removeItem("authToken");
    localStorage.removeItem("currentUser");
    setCurrentUser(null);
    setFavorites([]);
    setAdminStatistics(null);
    if (activeTab === "admin" || activeTab === "favorites") {
      setActiveTab("ads");
    }
  };

  const toggleFavorite = async (ad) => {
    if (!currentUser) {
      setAuthModal({
        mode: "register",
        message:
          "Pentru a salva anunțuri la favorite trebuie să ai un cont. Înregistrează-te sau loghează-te pentru a păstra anunțurile salvate.",
      });
      return;
    }

    try {
      if (favoriteIds.has(ad.id)) {
        await api.delete(`/favorites/${ad.id}`);
        setFavorites((prev) => prev.filter((item) => item.id !== ad.id));
      } else {
        await api.post(`/favorites/${ad.id}`);
        await fetchFavorites();
      }
    } catch (error) {
      console.error("Eroare la favorite:", error);
    }
  };

  useEffect(() => {
    fetchAds();
    fetchJobs();
    fetchStatistics();
    fetchDataAudit();
  }, []);

  useEffect(() => {
    if (!currentUser) {
      setFavorites([]);
      setAdminStatistics(null);
      return;
    }

    fetchFavorites();
    fetchAdminStatistics();
  }, [currentUser]);

  useEffect(() => {
    if (!currentJob) {
      return;
    }

    const interval = setInterval(async () => {
      const latestJobs = await fetchJobs();
      const stillActive = latestJobs.find((job) => job.id === currentJob.id);

      if (
        !stillActive ||
        ["done", "failed", "cancelled"].includes(stillActive.status)
      ) {
        fetchAds();
        if (currentUser) {
          fetchFavorites();
        }
        fetchStatistics();
        fetchAdminStatistics();
        fetchDataAudit();
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [currentJob]);

  const handleFilterChange = (e) => {
    const numericLimits = {
      rooms: { min: 1, max: 10, integer: true },
      min_price: { min: 0 },
      max_price: { min: 0 },
      min_surface: { min: 0, max: 500 },
      max_surface: { min: 0, max: 500 },
    };

    const limit = numericLimits[e.target.name];
    let value = e.target.value;

    if (limit && value !== "") {
      let numericValue = Number(value);

      if (Number.isNaN(numericValue)) {
        numericValue = limit.min;
      }

      if (limit.integer) {
        numericValue = Math.floor(numericValue);
      }

      if (numericValue < limit.min) {
        numericValue = limit.min;
      }

      if (limit.max !== undefined && numericValue > limit.max) {
        numericValue = limit.max;
      }

      value = String(numericValue);
    }

    setFilters((prev) => ({
      ...prev,
      [e.target.name]: value,
    }));
  };

  const applyFilters = () => {
    const normalizedFilters = { ...filters };

    if (
      normalizedFilters.min_price !== "" &&
      normalizedFilters.max_price !== "" &&
      Number(normalizedFilters.min_price) > Number(normalizedFilters.max_price)
    ) {
      normalizedFilters.max_price = normalizedFilters.min_price;
    }

    if (
      normalizedFilters.min_surface !== "" &&
      normalizedFilters.max_surface !== "" &&
      Number(normalizedFilters.min_surface) > Number(normalizedFilters.max_surface)
    ) {
      normalizedFilters.max_surface = normalizedFilters.min_surface;
    }

    setFilters(normalizedFilters);

    if (activeTab === "favorites") {
      return;
    }

    fetchAds(normalizedFilters);
  };

  const resetFilters = () => {
    const reset = {
      neighborhood: "",
      rooms: "",
      min_price: "",
      max_price: "",
      min_surface: "",
      max_surface: "",
      source: "",
    };

    setFilters(reset);

    if (activeTab === "favorites") {
      return;
    }

    fetchAds(reset);
  };

  const handleNeighborhoodSelectFromMap = (neighborhood) => {
    const updatedFilters = {
      ...filters,
      neighborhood,
    };

    setFilters(updatedFilters);
    fetchAds(updatedFilters);
  };

  const clearNeighborhoodFromMap = () => {
    const updatedFilters = {
      ...filters,
      neighborhood: "",
    };

    setFilters(updatedFilters);
    fetchAds(updatedFilters);
  };

  const neighborhoodsCount = statistics?.by_neighborhood?.length || 0;
  const shouldShowFilters = ["ads", "favorites", "map"].includes(activeTab);

  return (
    <div className="app-shell">
      <Header
        onStartCrawler={startCrawler}
        onCancelCrawler={cancelCrawler}
        crawlMode={crawlMode}
        onCrawlModeChange={setCrawlMode}
        crawlSource={crawlSource}
        onCrawlSourceChange={setCrawlSource}
        adsCount={ads.length}
        neighborhoodsCount={neighborhoodsCount}
        jobsCount={jobs.length}
        currentJob={currentJob}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        currentUser={currentUser}
        onLogout={handleLogout}
        onOpenAuth={(mode) => setAuthModal({ mode })}
        onShowFavorites={() => setActiveTab("favorites")}
      />

      <div
        className={`dashboard-layout ${
          shouldShowFilters ? "" : "dashboard-layout-full"
        } ${activeTab === "map" ? "dashboard-layout-map" : ""} ${
          activeTab === "favorites" ? "dashboard-layout-favorites" : ""
        }`}
      >
        {shouldShowFilters && (
          <aside className="sidebar">
            <FiltersSidebar
              filters={filters}
              onChange={handleFilterChange}
              onApply={applyFilters}
              onReset={resetFilters}
            />
          </aside>
        )}

        <main className="main-content">
          <section className="workspace-header">
            <span className="workspace-label">Panou de analiză</span>

            <div className="workspace-title-row">
              <div>
                <h2 className="workspace-title">Observatorul pieței rezidențiale</h2>
                <p className="workspace-note">
                  Monitorizează anunțurile agregate, compară zonele și urmărește
                  rapid dinamica locală a pieței din Timișoara.
                </p>
              </div>

              <span className="workspace-chip">
                {ads.length} anunțuri în selecția curentă
              </span>
            </div>
          </section>

          <StatsCards statistics={statistics} adsCount={ads.length} />

          {activeTab === "ads" && (
            <section className="panel dashboard-crawler-panel">
              <CrawlerControls
                onStartCrawler={startCrawler}
                onCancelCrawler={cancelCrawler}
                crawlMode={crawlMode}
                onCrawlModeChange={setCrawlMode}
                crawlSource={crawlSource}
                onCrawlSourceChange={setCrawlSource}
                currentJob={currentJob}
                sourceSelectId="dashboard-crawl-source"
                modeSelectId="dashboard-crawl-mode"
              />
            </section>
          )}

          {activeTab === "ads" && (
            <AdsGrid ads={ads} favoriteIds={favoriteIds} onToggleFavorite={toggleFavorite} />
          )}

          {activeTab === "favorites" && (
            currentUser ? (
              <AdsGrid
                ads={filteredFavorites}
                favoriteIds={favoriteIds}
                onToggleFavorite={toggleFavorite}
                title="Anunțuri favorite"
                subtitle={`${filteredFavorites.length} din ${favorites.length} anunțuri salvate corespund filtrelor curente.`}
                emptyTitle="Nu există favorite pentru filtrele curente"
                emptyText="Modifică filtrele sau salvează alte anunțuri din secțiunea Anunțuri."
              />
            ) : (
              <div className="panel empty-state">
                <h3>Ai nevoie de cont pentru anunțuri salvate</h3>
                <p>
                  Site-ul poate fi vizualizat fără cont, dar lista de favorite
                  este disponibilă doar după logare sau înregistrare.
                </p>
                <button
                  className="primary-btn"
                  type="button"
                  onClick={() => setAuthModal({ mode: "register" })}
                >
                  Creează cont
                </button>
              </div>
            )
          )}

          {activeTab === "estimator" && (
            <PriceEstimator statistics={statistics} />
          )}
          {activeTab === "jobs" && <JobsPanel jobs={jobs} />}
          {activeTab === "statistics" && (
            <StatisticsTables statistics={statistics} />
          )}
          {activeTab === "admin" && currentUser.role === "admin" && (
            <AdminStatsPanel statistics={adminStatistics} dataAudit={dataAudit} />
          )}
          {activeTab === "map" && (
            <MapPlaceholder
              ads={ads}
              filters={filters}
              selectedNeighborhood={filters.neighborhood}
              onSelectNeighborhood={handleNeighborhoodSelectFromMap}
              onClearNeighborhood={clearNeighborhoodFromMap}
            />
          )}
        </main>
      </div>

      {authModal && (
        <AuthPanel
          initialMode={authModal.mode}
          message={authModal.message}
          onAuthSuccess={handleAuthSuccess}
          onClose={() => setAuthModal(null)}
        />
      )}
    </div>
  );
}

export default Dashboard;
