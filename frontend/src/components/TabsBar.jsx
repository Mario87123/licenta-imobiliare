function TabsBar({ activeTab, onChange, isAdmin = false }) {
  const tabs = [
    { key: "ads", label: "Anunțuri" },
    { key: "favorites", label: "Favorite" },
    { key: "estimator", label: "Estimator" },
    { key: "statistics", label: "Statistici" },
    { key: "jobs", label: "Joburi" },
    { key: "map", label: "Hartă" },
  ];

  if (isAdmin) {
    tabs.push({ key: "admin", label: "Admin" });
  }

  return (
    <div className="tabs-shell">
      <div className="tabs-bar">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={activeTab === tab.key ? "tab active-tab" : "tab"}
            onClick={() => onChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default TabsBar;
