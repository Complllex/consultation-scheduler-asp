import { useState } from "react";

export default function LoginForm({ onLogin, loading, error }) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    onLogin(login, password);
  };

  return (
    <div className="card">
      <h1>Вход в систему</h1>
      <p className="muted">Введите логин и пароль преподавателя или администратора</p>

      <form onSubmit={handleSubmit} className="form">
        <label>
          Логин
          <input
            type="text"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            placeholder="Например: fomin"
            required
          />
        </label>

        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Введите пароль"
            required
          />
        </label>

        {error ? <div className="error">{error}</div> : null}

        <button type="submit" disabled={loading}>
          {loading ? "Входим..." : "Войти"}
        </button>
      </form>
    </div>
  );
}