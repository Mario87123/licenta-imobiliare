import { useEffect, useRef, useState } from "react";
import AccountMenu from "./AccountMenu";
import CrawlerControls from "./CrawlerControls";
import TabsBar from "./TabsBar";

function Header({
  onStartCrawler,
  onCancelCrawler,
  crawlMode,
  onCrawlModeChange,
  crawlSource,
  onCrawlSourceChange,
  currentJob,
  activeTab,
  onTabChange,
  currentUser,
  onLogout,
  onOpenAuth,
  onShowFavorites,
}) {
  const [openMenu, setOpenMenu] = useState(null);
  const menuRef = useRef(null);
  const isCrawlerOpen = openMenu === "crawler";
  const isAccountOpen = openMenu === "account";

  useEffect(() => {
    if (!openMenu) {
      return;
    }

    const handleOutsideClick = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpenMenu(null);
      }
    };

    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setOpenMenu(null);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [openMenu]);

  const toggleMenu = (menuName) => {
    setOpenMenu((prev) => (prev === menuName ? null : menuName));
  };

  return (
    <header className={`header-shell ${isCrawlerOpen ? "header-shell-open" : ""}`}>
      <div className="header-utility-bar">
        <span>Monitorizare locală pentru piața rezidențială din Timișoara</span>
      </div>

      <header className="header">
        <div className="header-inner header-main-row">
          <div className="header-brand-block">
            <div className="brand-mark" />

            <div className="brand-copy">
              <span className="brand-kicker">Radar rezidențial</span>
              <h1 className="brand-title">Imobiliare Timișoara</h1>
            </div>
          </div>

          <div className="header-primary-links">
            <TabsBar
              activeTab={activeTab}
              onChange={onTabChange}
              isAdmin={currentUser?.role === "admin"}
            />
          </div>

          <div className="header-actions-inline" ref={menuRef}>
            <AccountMenu
              currentUser={currentUser}
              isOpen={isAccountOpen}
              onToggle={() => toggleMenu("account")}
              onClose={() => setOpenMenu(null)}
              onOpenAuth={onOpenAuth}
              onLogout={onLogout}
              onShowFavorites={onShowFavorites}
            />

            <button
              className="header-menu-btn"
              type="button"
              aria-expanded={isCrawlerOpen}
              aria-label={isCrawlerOpen ? "Închide panoul" : "Deschide panoul"}
              onClick={() => toggleMenu("crawler")}
            >
              <svg
                className="header-menu-icon"
                viewBox="0 0 24 24"
                aria-hidden="true"
                focusable="false"
              >
                <rect x="4.5" y="5" width="15" height="14" rx="3" />
                <path d="M10 5v14" />
                <path d="M13.5 9h2.8" />
                <path d="M13.5 12h4" />
                <path d="M13.5 15h2.8" />
              </svg>
            </button>

            <div
              className={`header-crawler-dropdown ${
                isCrawlerOpen ? "header-crawler-dropdown-visible" : ""
              }`}
              aria-hidden={!isCrawlerOpen}
            >
              <span className="header-panel-label">Crawler</span>

              <CrawlerControls
                onStartCrawler={onStartCrawler}
                onCancelCrawler={onCancelCrawler}
                crawlMode={crawlMode}
                onCrawlModeChange={onCrawlModeChange}
                crawlSource={crawlSource}
                onCrawlSourceChange={onCrawlSourceChange}
                currentJob={currentJob}
                sourceSelectId="header-crawl-source"
                modeSelectId="header-crawl-mode"
              />
            </div>
          </div>
        </div>
      </header>
    </header>
  );
}

export default Header;
