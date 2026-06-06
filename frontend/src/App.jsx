import { useEffect, useState } from "react";
import { getMe, getMyAssignments, loginRequest } from "./api";
import AdminPanel from "./components/AdminPanel";
import DepartmentResponsiblePanel from "./components/DepartmentResponsiblePanel";
import LoginForm from "./components/LoginForm";
import MyAssignments from "./components/MyAssignments";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [user, setUser] = useState(null);
  const [assignmentsData, setAssignmentsData] = useState(null);

  const [loading, setLoading] = useState(false);
  const [pageLoading, setPageLoading] = useState(false);
  const [error, setError] = useState("");

  const loadUserData = async (currentToken) => {
    setPageLoading(true);
    setError("");

    try {
      const me = await getMe(currentToken);
      setUser(me);

      if (me.role === "teacher") {
        const assignments = await getMyAssignments(currentToken);
        setAssignmentsData(assignments);
      } else {
        setAssignmentsData({ assignments: [] });
      }
    } catch (err) {
      setError(err.message || "Ошибка загрузки данных");
      handleLogout();
    } finally {
      setPageLoading(false);
    }
  };

  useEffect(() => {
    if (token) {
      loadUserData(token);
    }
  }, [token]);

  const handleLogin = async (login, password) => {
    setLoading(true);
    setError("");

    try {
      const result = await loginRequest(login, password);
      localStorage.setItem("token", result.access_token);
      setToken(result.access_token);
    } catch (err) {
      setError(err.message || "Ошибка входа");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken("");
    setUser(null);
    setAssignmentsData(null);
  };

  if (!token) {
    return (
      <div className="app-shell">
        <LoginForm onLogin={handleLogin} loading={loading} error={error} />
      </div>
    );
  }

  if (pageLoading || !user || !assignmentsData) {
    return (
      <div className="app-shell">
        <div className="card">
          <h1>Загрузка...</h1>
          <p className="muted">Получаем данные пользователя</p>
        </div>
      </div>
    );
  }

  if (user.role === "admin") {
    return (
      <div className="app-shell">
        <AdminPanel user={user} token={token} onLogout={handleLogout} />
      </div>
    );
  }

  if (user.role === "teacher") {
    return (
      <div className="app-shell">
        <MyAssignments
          user={user}
          setUser={setUser}
          data={assignmentsData}
          token={token}
          onLogout={handleLogout}
          refreshTeacherData={() => loadUserData(token)}
        />
      </div>
    );
  }

  if (user.role === "department_responsible") {
    return (
      <div className="app-shell">
        <DepartmentResponsiblePanel
          user={user}
          token={token}
          onLogout={handleLogout}
        />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="card">
        <h1>Неизвестная роль</h1>
        <p className="muted">
          Для пользователя задана неподдерживаемая роль: {user.role}
        </p>
        <button onClick={handleLogout}>Выйти</button>
      </div>
    </div>
  );
}