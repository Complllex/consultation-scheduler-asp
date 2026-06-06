import { useEffect, useRef, useState } from "react";
import {
  getHealthTables,
  getImportJobStatus,
  importDepartmentGroupsByUuid,
  importStructure,
  importTeacherGroupsByUuid,
} from "../api";

export default function AdminPanel({ user, token, onLogout }) {
  const [teacherUuid, setTeacherUuid] = useState("");
  const [departmentUuid, setDepartmentUuid] = useState("");
  const [health, setHealth] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [currentJob, setCurrentJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const pollingRef = useRef(null);

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const startPollingJob = (jobId) => {
    stopPolling();

    const poll = async () => {
      try {
        const status = await getImportJobStatus(token, jobId);
        setCurrentJob(status);

        if (status.status === "done" || status.status === "failed") {
          stopPolling();
          setLastResult(status.result || status);

          if (status.status === "done") {
            setSuccessMessage("Импорт завершён");
          } else {
            setError(status.message || "Импорт завершился с ошибкой");
          }
        }
      } catch (err) {
        stopPolling();
        setError(err.message || "Ошибка проверки статуса задачи");
      }
    };

    poll();
    pollingRef.current = setInterval(poll, 1500);
  };

  useEffect(() => {
    return () => stopPolling();
  }, []);

  const handleImportStructure = async () => {
    setLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await importStructure();
      setLastResult(result);
      setSuccessMessage("Структура университета успешно импортирована");
    } catch (err) {
      setError(err.message || "Ошибка импорта структуры");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadHealth = async () => {
    setLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await getHealthTables();
      setHealth(result);
      setLastResult(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки статистики");
    } finally {
      setLoading(false);
    }
  };

  const handleImportTeacherGroups = async () => {
    if (!teacherUuid.trim()) {
      setError("Введите UUID преподавателя");
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMessage("");
    setCurrentJob(null);

    try {
      const result = await importTeacherGroupsByUuid(token, teacherUuid.trim());
      setSuccessMessage("Задача импорта по преподавателю запущена");
      startPollingJob(result.job_id);
    } catch (err) {
      setError(err.message || "Ошибка импорта групп преподавателя");
    } finally {
      setLoading(false);
    }
  };

  const handleImportDepartmentGroups = async () => {
    if (!departmentUuid.trim()) {
      setError("Введите UUID кафедры");
      return;
    }

    setLoading(true);
    setError("");
    setSuccessMessage("");
    setCurrentJob(null);

    try {
      const result = await importDepartmentGroupsByUuid(token, departmentUuid.trim());
      setSuccessMessage("Задача импорта кафедры запущена");
      startPollingJob(result.job_id);
    } catch (err) {
      setError(err.message || "Ошибка импорта расписаний кафедры");
    } finally {
      setLoading(false);
    }
  };

  const progressPercent =
    currentJob && currentJob.total_groups > 0
      ? Math.round((currentJob.processed_groups / currentJob.total_groups) * 100)
      : 0;

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1>Админ-панель</h1>
          <p className="muted">{user.full_name}</p>
        </div>

        <button onClick={onLogout}>Выйти</button>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Быстрые действия</h2>
            <p className="muted">Служебные операции для заполнения и синхронизации данных</p>
          </div>
        </div>

        <div className="request-actions">
          <button onClick={handleImportStructure} disabled={loading}>
            Импортировать структуру
          </button>

          <button onClick={handleLoadHealth} disabled={loading}>
            Обновить статистику БД
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Импорт по преподавателю</h2>
            <p className="muted">
              Найдёт все группы, где встречается преподаватель, и импортирует их расписания
            </p>
          </div>
        </div>

        <div className="department-select-row">
          <input
            value={teacherUuid}
            onChange={(e) => setTeacherUuid(e.target.value)}
            placeholder="UUID преподавателя"
          />
          <button onClick={handleImportTeacherGroups} disabled={loading}>
            Импортировать
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Импорт по кафедре</h2>
            <p className="muted">
              Импортирует расписания всех групп кафедры из уже загруженной структуры
            </p>
          </div>
        </div>

        <div className="department-select-row">
          <input
            value={departmentUuid}
            onChange={(e) => setDepartmentUuid(e.target.value)}
            placeholder="UUID кафедры"
          />
          <button onClick={handleImportDepartmentGroups} disabled={loading}>
            Импортировать
          </button>
        </div>
      </div>

      {error ? <div className="error mb16">{error}</div> : null}
      {successMessage ? <div className="success mb16">{successMessage}</div> : null}

      {currentJob ? (
        <div className="card">
          <h2>Текущая задача импорта</h2>

          <div className="info-grid">
            <div>
              <span className="label">Тип</span>
              <span>{currentJob.job_type}</span>
            </div>
            <div>
              <span className="label">Статус</span>
              <span>{currentJob.status}</span>
            </div>
            <div>
              <span className="label">Цель</span>
              <span>{currentJob.target_uuid}</span>
            </div>
            <div>
              <span className="label">Сообщение</span>
              <span>{currentJob.message || "—"}</span>
            </div>
          </div>

          <div className="progress-block">
            <div className="progress-meta">
              <span>Обработано: {currentJob.processed_groups} / {currentJob.total_groups}</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          <div className="info-grid">
            <div>
              <span className="label">Найдено</span>
              <span>{currentJob.matched_groups}</span>
            </div>
            <div>
              <span className="label">Импортировано</span>
              <span>{currentJob.imported_groups}</span>
            </div>
            <div>
              <span className="label">Ошибки</span>
              <span>{currentJob.error_count}</span>
            </div>
            <div>
              <span className="label">Job ID</span>
              <span>{currentJob.id}</span>
            </div>
          </div>
        </div>
      ) : null}

      {health ? (
        <div className="card">
          <h2>Статистика БД</h2>
          <div className="info-grid">
            {Object.entries(health).map(([key, value]) => (
              <div key={key}>
                <span className="label">{key}</span>
                <span>{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {lastResult ? (
        <div className="card">
          <h2>Последний результат</h2>
          <pre className="result-pre">{JSON.stringify(lastResult, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}