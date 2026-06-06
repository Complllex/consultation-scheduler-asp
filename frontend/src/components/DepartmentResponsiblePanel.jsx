import { useEffect, useState } from "react";
import {
  approveDepartmentConsultationRequest,
  getMyDepartmentApprovedConsultationsTable,
  getMyDepartmentConsultationRequests,
  rejectDepartmentConsultationRequest,
} from "../api";
import { getStatusClass, getStatusLabel } from "../utils";
import Modal from "./Modal";

export default function DepartmentResponsiblePanel({ user, token, onLogout }) {
  const [consultationRequests, setConsultationRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [approvedTableData, setApprovedTableData] = useState([]);
  const [loadingApprovedTable, setLoadingApprovedTable] = useState(false);
  const [isApprovedTableOpen, setIsApprovedTableOpen] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError("");

    try {
      const requests = await getMyDepartmentConsultationRequests(token);
      setConsultationRequests(requests);
    } catch (err) {
      setError(err.message || "Ошибка загрузки заявок кафедры");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token]);

  const handleApprove = async (requestId) => {
    setActionLoadingId(`approve_${requestId}`);
    setError("");
    setSuccessMessage("");

    try {
      await approveDepartmentConsultationRequest(token, requestId);
      await loadData();
      setSuccessMessage("Заявка утверждена");
    } catch (err) {
      setError(err.message || "Ошибка подтверждения заявки");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReject = async (requestId) => {
    setActionLoadingId(`reject_${requestId}`);
    setError("");
    setSuccessMessage("");

    try {
      await rejectDepartmentConsultationRequest(token, requestId);
      await loadData();
      setSuccessMessage("Заявка отклонена");
    } catch (err) {
      setError(err.message || "Ошибка отклонения заявки");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleOpenApprovedTable = async () => {
    setLoadingApprovedTable(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await getMyDepartmentApprovedConsultationsTable(token);
      setApprovedTableData(result.rows || []);
      setIsApprovedTableOpen(true);
    } catch (err) {
      setError(err.message || "Ошибка загрузки таблицы утверждённых консультаций");
    } finally {
      setLoadingApprovedTable(false);
    }
  };

  const handleCopyApprovedTable = async () => {
    if (!approvedTableData.length) {
      setError("Нет данных для копирования");
      return;
    }

    const header = [
      "ФИО",
      "Название дисциплины",
      "День",
      "Недели",
      "Время",
      "Аудитория",
    ];

    const lines = [
      header.join("\t"),
      ...approvedTableData.map((row) =>
        [
          row.teacher_full_name || "",
          row.discipline_name || "",
          row.day || "",
          row.week_type || "",
          row.time || "",
          row.audience || "",
        ].join("\t")
      ),
    ];

    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setSuccessMessage("Таблица скопирована в буфер обмена");
    } catch {
      setError("Не удалось скопировать таблицу");
    }
  };

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1>Кабинет ответственного кафедры</h1>
          <p className="muted">{user.full_name}</p>
        </div>

        <div className="request-actions">
          <button onClick={handleOpenApprovedTable} disabled={loadingApprovedTable}>
            {loadingApprovedTable
              ? "Загружаем..."
              : "Таблица утверждённых консультаций"}
          </button>
          <button onClick={onLogout}>Выйти</button>
        </div>
      </div>

      {error ? <div className="error mb16">{error}</div> : null}
      {successMessage ? <div className="success mb16">{successMessage}</div> : null}

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Заявки на согласование</h2>
            <p className="muted">
              Отображаются заявки, отправленные преподавателями на согласование
            </p>
          </div>
        </div>

        {loading ? (
          <p className="muted">Загрузка заявок...</p>
        ) : consultationRequests.length === 0 ? (
          <p className="muted">Пока нет заявок на согласование</p>
        ) : (
          <div className="requests-list">
            {consultationRequests.map((item) => {
              const selectedSlots = Array.isArray(item.selected_batch_slots)
                ? item.selected_batch_slots
                : [];

              const groupsLabel =
                item.groups?.length > 0
                  ? item.groups.map((group) => group.name).join(", ")
                  : "—";

              return (
                <div
                  className={`request-card polished-request-card ${getStatusClass(
                    item.status
                  )}`}
                  key={item.id}
                >
                  <div className="request-card-inner">
                    <div className="request-main-row request-main-row-wide">
                      <div>
                        <span className="label">Преподаватель</span>
                        <div>{item.teacher?.full_name || "—"}</div>
                      </div>

                      <div>
                        <span className="label">Группы</span>
                        <div>{groupsLabel}</div>
                      </div>

                      <div>
                        <span className="label">Дисциплина</span>
                        <div>{item.discipline?.full_name || "Консультация"}</div>
                      </div>

                      <div>
                        <span className="label">Статус</span>
                        <div className="status-badge">{getStatusLabel(item.status)}</div>
                      </div>
                    </div>

                    <div className="request-main-row request-main-row-wide">
                      <div>
                        <span className="label">Желаемая аудитория</span>
                        <div>{item.preferred_audience || "—"}</div>
                      </div>
                    </div>

                    <div className="expanded-section">
                      <span className="label">Выбранные консультации</span>

                      {selectedSlots.length === 0 ? (
                        <div className="muted">
                          Преподаватель ещё не выбрал общий вариант
                        </div>
                      ) : (
                        <div className="variants-list">
                          <div className="variant-card variant-card-selected">
                            <div className="variant-header">
                              <div>
                                <strong>Итоговые слоты</strong>
                                <div className="muted">
                                  Выбраны преподавателем в общем варианте
                                </div>
                              </div>
                              <div className="variant-status">Выбрано</div>
                            </div>

                            <div className="variant-slots">
                              {selectedSlots.map((slot, index) => (
                                <div className="variant-slot" key={index}>
                                  {slot.day_label}, {slot.pair_number} пара
                                  {slot.week_type_label
                                    ? `, ${slot.week_type_label}`
                                    : ""}
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="request-actions request-actions-spaced">
                      <button
                        onClick={() => handleApprove(item.id)}
                        disabled={
                          actionLoadingId === `approve_${item.id}` ||
                          item.status === "approved"
                        }
                      >
                        {item.status === "approved"
                          ? "Уже утверждена"
                          : actionLoadingId === `approve_${item.id}`
                          ? "Подтверждаем..."
                          : "Принять"}
                      </button>

                      <button
                        onClick={() => handleReject(item.id)}
                        disabled={
                          actionLoadingId === `reject_${item.id}` ||
                          item.status === "rejected"
                        }
                      >
                        {item.status === "rejected"
                          ? "Уже отклонена"
                          : actionLoadingId === `reject_${item.id}`
                          ? "Отклоняем..."
                          : "Отклонить"}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        isOpen={isApprovedTableOpen}
        title="Таблица утверждённых консультаций"
        onClose={() => setIsApprovedTableOpen(false)}
      >
        <div className="request-actions" style={{ marginBottom: 16 }}>
          <button onClick={handleCopyApprovedTable}>
            Скопировать таблицу
          </button>
        </div>

        {!approvedTableData.length ? (
          <p className="muted">Нет утверждённых консультаций</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="approved-table">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Название дисциплины</th>
                  <th>День</th>
                  <th>Недели</th>
                  <th>Время</th>
                  <th>Аудитория</th>
                </tr>
              </thead>
              <tbody>
                {approvedTableData.map((row, index) => (
                  <tr key={index}>
                    <td>{row.teacher_full_name}</td>
                    <td>{row.discipline_name}</td>
                    <td>{row.day}</td>
                    <td>{row.week_type}</td>
                    <td>{row.time}</td>
                    <td>{row.audience || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </div>
  );
}