import { useEffect, useState } from "react";
import api from "../api/api";

function AuthPanel({
  initialMode = "login",
  initialResetToken = "",
  onAuthSuccess,
  onClose,
  message,
}) {
  const [mode, setMode] = useState(initialMode);
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
    resetToken: initialResetToken,
  });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    setMode(initialMode);
    setForm((prev) => ({ ...prev, resetToken: initialResetToken }));
  }, [initialMode, initialResetToken]);

  const handleChange = (event) => {
    setForm((prev) => ({ ...prev, [event.target.name]: event.target.value }));
  };

  const changeMode = (nextMode) => {
    setMode(nextMode);
    setError("");
    setInfo("");
  };

  const handleAuthSubmit = async () => {
    if (mode === "register") {
      await api.post("/auth/register", {
        name: form.name,
        email: form.email,
        password: form.password,
      });
    }

    const response = await api.post("/auth/login", {
      email: form.email,
      password: form.password,
    });

    localStorage.setItem("authToken", response.data.token);
    localStorage.setItem("currentUser", JSON.stringify(response.data.user));
    onAuthSuccess(response.data.user);
  };

  const handlePasswordResetRequest = async () => {
    const response = await api.post("/auth/password-reset/request", {
      email: form.email,
    });

    setInfo(
      `Dacă adresa există, vei primi un link valabil ${response.data.expires_in_minutes} de minute. Verifică și folderul Spam.`
    );
  };

  const handlePasswordResetConfirm = async () => {
    if (form.password !== form.confirmPassword) {
      setError("Parolele introduse nu coincid.");
      return;
    }

    await api.post("/auth/password-reset/confirm", {
      token: form.resetToken,
      password: form.password,
    });

    setForm((prev) => ({
      ...prev,
      password: "",
      confirmPassword: "",
      resetToken: "",
    }));
    window.history.replaceState({}, "", window.location.pathname);
    setInfo("Parola a fost resetată. Te poți autentifica folosind parola nouă.");
    setMode("login");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setInfo("");
    setIsSubmitting(true);

    try {
      if (mode === "forgot") {
        await handlePasswordResetRequest();
      } else if (mode === "reset") {
        await handlePasswordResetConfirm();
      } else {
        await handleAuthSubmit();
      }
    } catch (err) {
      setError(
        err.response?.data?.detail || "Operațiunea nu a putut fi finalizată."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const titleByMode = {
    login: "Logare cont",
    register: "Creează cont",
    forgot: "Resetare parolă",
    reset: "Parolă nouă",
  };

  const submitLabelByMode = {
    login: "Autentificare",
    register: "Creează cont",
    forgot: "Trimite linkul",
    reset: "Salvează parola nouă",
  };

  const defaultMessage =
    mode === "forgot"
      ? "Introdu adresa de e-mail asociată contului pentru a primi linkul de resetare."
      : mode === "reset"
        ? "Alege o parolă nouă pentru contul tău."
        : "Autentifică-te pentru a salva anunțuri și pentru a folosi funcțiile asociate contului.";

  return (
    <div className="auth-modal-backdrop" role="presentation">
      <section
        className="auth-card auth-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
      >
        <button
          className="auth-close-btn"
          type="button"
          aria-label="Închide"
          onClick={onClose}
        >
          x
        </button>

        <span className="workspace-label">Acces platformă</span>
        <h1 id="auth-dialog-title">{titleByMode[mode]}</h1>
        <p>
          {message && mode !== "forgot" && mode !== "reset"
            ? message
            : defaultMessage}
        </p>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "register" && (
            <label className="field">
              <span>Nume</span>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                required
              />
            </label>
          )}

          {mode !== "reset" && (
            <label className="field">
              <span>E-mail</span>
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
              />
            </label>
          )}

          {mode === "reset" && (
            <input name="resetToken" type="hidden" value={form.resetToken} />
          )}

          {mode !== "forgot" && (
            <label className="field">
              <span>{mode === "reset" ? "Parola nouă" : "Parola"}</span>
              <input
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                required
                minLength={6}
              />
            </label>
          )}

          {mode === "reset" && (
            <label className="field">
              <span>Confirmă parola</span>
              <input
                name="confirmPassword"
                type="password"
                value={form.confirmPassword}
                onChange={handleChange}
                required
                minLength={6}
              />
            </label>
          )}

          {error && <p className="auth-error">{error}</p>}
          {info && <p className="auth-info">{info}</p>}

          <button className="primary-btn" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Se procesează..." : submitLabelByMode[mode]}
          </button>
        </form>

        {mode === "login" && (
          <button
            className="auth-forgot"
            type="button"
            onClick={() => changeMode("forgot")}
          >
            Ai uitat parola?
          </button>
        )}

        {mode === "reset" && (
          <button
            className="auth-forgot"
            type="button"
            onClick={() => changeMode("forgot")}
          >
            Trimite alt link
          </button>
        )}

        <button
          className="auth-switch"
          type="button"
          onClick={() => changeMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login"
            ? "Nu ai cont? Creează unul"
            : mode === "register"
              ? "Ai deja cont? Autentifică-te"
              : "Înapoi la autentificare"}
        </button>
      </section>
    </div>
  );
}

export default AuthPanel;
