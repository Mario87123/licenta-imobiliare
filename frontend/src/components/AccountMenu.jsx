function AccountMenu({
  currentUser,
  isOpen,
  onToggle,
  onClose,
  onOpenAuth,
  onLogout,
  onShowFavorites,
}) {
  const openAuth = (mode) => {
    onClose();
    onOpenAuth(mode);
  };

  const showFavorites = () => {
    onClose();
    onShowFavorites();
  };

  const logout = () => {
    onClose();
    onLogout();
  };

  return (
    <div className="account-menu">
      <button
        className={isOpen ? "account-menu-btn account-menu-btn-open" : "account-menu-btn"}
        type="button"
        aria-expanded={isOpen}
        onClick={onToggle}
      >
        <span>Contul meu</span>
      </button>

      <div
        className={`account-dropdown ${
          isOpen ? "account-dropdown-visible" : ""
        }`}
        aria-hidden={!isOpen}
      >
        {currentUser ? (
          <>
            <div className="account-summary">
              <span>{currentUser.role === "admin" ? "Administrator" : "Utilizator"}</span>
              <strong>{currentUser.name}</strong>
              <small>{currentUser.email}</small>
            </div>

            <button type="button" onClick={showFavorites}>
              Anunțuri salvate
            </button>

            <button type="button" onClick={logout}>
              Delogare
            </button>
          </>
        ) : (
          <>
            <div className="account-summary">
              <span>Acces opțional</span>
              <strong>Nu ești logat</strong>
              <small>Poți vizualiza site-ul, dar ai nevoie de cont pentru favorite.</small>
            </div>

            <button type="button" onClick={() => openAuth("login")}>
              Logare
            </button>

            <button type="button" onClick={() => openAuth("register")}>
              Înregistrare
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default AccountMenu;
