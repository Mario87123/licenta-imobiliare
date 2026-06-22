const CRAWL_SOURCE_OPTIONS = [
  {
    value: "storia",
    label: "Storia",
    hint: "Sursă mai structurată, utilă pentru anunțuri mai curate și localizare mai clară.",
  },
  {
    value: "imobiliare",
    label: "Imobiliare.ro",
    hint: "Portal imobiliar dedicat, bun pentru completarea datelor din OLX și Storia.",
  },
  {
    value: "olx",
    label: "OLX",
    hint: "Sursă marketplace generalistă, bună pentru volum și monitorizare rapidă.",
  },
];

const CRAWL_MODE_OPTIONS = [
  {
    value: "quick_refresh",
    label: "Actualizare rapidă",
    hint: "Primele pagini, stop rapid dacă găsește duplicate.",
  },
  {
    value: "deep_crawl",
    label: "Crawl extins",
    hint: "Mai multe pagini, bun pentru actualizare serioasă.",
  },
  {
    value: "backfill",
    label: "Backfill istoric",
    hint: "Merge adânc în pagini și aduce anunțuri mai vechi în bază.",
  },
];

function CrawlerControls({
  onStartCrawler,
  onCancelCrawler,
  crawlMode,
  onCrawlModeChange,
  crawlSource,
  onCrawlSourceChange,
  currentJob,
  sourceSelectId = "crawl-source",
  modeSelectId = "crawl-mode",
}) {
  const isJobRunning =
    currentJob &&
    ["pending", "running", "cancelling"].includes(currentJob.status);

  const selectedSource = CRAWL_SOURCE_OPTIONS.find(
    (option) => option.value === crawlSource
  );

  const selectedMode = CRAWL_MODE_OPTIONS.find(
    (option) => option.value === crawlMode
  );

  return (
    <div className="crawl-controls">
      <div className="crawl-field">
        <label className="crawl-select-label" htmlFor={sourceSelectId}>
          Sursă crawler
        </label>

        <select
          id={sourceSelectId}
          className="crawl-select"
          value={crawlSource}
          onChange={(e) => onCrawlSourceChange(e.target.value)}
          disabled={isJobRunning}
        >
          {CRAWL_SOURCE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <p className="crawl-select-hint">{selectedSource?.hint}</p>
      </div>

      <div className="crawl-field">
        <label className="crawl-select-label" htmlFor={modeSelectId}>
          Mod crawler
        </label>

        <select
          id={modeSelectId}
          className="crawl-select"
          value={crawlMode}
          onChange={(e) => onCrawlModeChange(e.target.value)}
          disabled={isJobRunning}
        >
          {CRAWL_MODE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <p className="crawl-select-hint">{selectedMode?.hint}</p>
      </div>

      <div className="crawl-actions-row">
        <button
          className="primary-btn"
          onClick={onStartCrawler}
          disabled={isJobRunning}
        >
          {isJobRunning ? "Crawler în execuție" : "Pornește crawlerul"}
        </button>

        <button
          className="secondary-btn"
          onClick={onCancelCrawler}
          disabled={!currentJob || currentJob.status !== "running"}
        >
          Oprește jobul
        </button>
      </div>

      {currentJob && (
        <div className="crawl-status-box">
          <strong>Job curent:</strong> #{currentJob.id} -{" "}
          {currentJob.source || "-"} - {currentJob.status}
          <br />
          <span>{currentJob.message}</span>
        </div>
      )}
    </div>
  );
}

export default CrawlerControls;
