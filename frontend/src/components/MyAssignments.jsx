import { useEffect, useMemo, useState } from "react";
import {
  createMyConsultationRequest,
  deleteMyConsultationRequest,
  generateVariantsForMyRequest,
  getAvailableDepartments,
  getMyConsultationRequests,
  getMyFinalSchedule,
  getVariantPreview,
  selectDepartmentForMe,
  selectVariantForMyRequest,
  addExtraGroupForMe,
  getAvailableDepartmentGroups,
  getMyManualBusySlots,
  createMyManualBusySlot,
  deleteMyManualBusySlot,
  createMyGenerationRun,
  getMyGenerationRuns,
  getMyGenerationRunDetails,
  selectMyGenerationRunVariant,
  getMyGenerationRunVariantPreview,
} from "../api";
import { DAY_LABELS, getStatusClass, getStatusLabel } from "../utils";
import FinalScheduleGrid from "./FinalScheduleGrid";
import Modal from "./Modal";
import VariantPreviewGrid from "./VariantPreviewGrid";

const DAYS = [
  { value: 1, label: "Понедельник" },
  { value: 2, label: "Вторник" },
  { value: 3, label: "Среда" },
  { value: 4, label: "Четверг" },
  { value: 5, label: "Пятница" },
  { value: 6, label: "Суббота" },
];

const PAIRS = [1, 2, 3, 4, 5, 6, 7];

export default function MyAssignments({
  user,
  setUser,
  data,
  token,
  onLogout,
  refreshTeacherData,
}) {
  const [consultationsCount, setConsultationsCount] = useState(1);
  const [selectedGroupIds, setSelectedGroupIds] = useState([]);
  const [selectedDisciplineId, setSelectedDisciplineId] = useState("");
  const [preferredAudience, setPreferredAudience] = useState("");

  const [avoidDayWithoutClasses, setAvoidDayWithoutClasses] = useState(false);
  const [avoidFirstPair, setAvoidFirstPair] = useState(false);
  const [avoidLastPair, setAvoidLastPair] = useState(false);
  const [preferredDay, setPreferredDay] = useState("");
  const [excludedDay, setExcludedDay] = useState("");
  const [weekPreference, setWeekPreference] = useState("both");
  const [blockedSlots, setBlockedSlots] = useState([]);

  const [requests, setRequests] = useState([]);
  const [loadingRequests, setLoadingRequests] = useState(false);
  const [creating, setCreating] = useState(false);
  const [expandedRequestId, setExpandedRequestId] = useState(null);

  const [previewData, setPreviewData] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const [finalScheduleData, setFinalScheduleData] = useState(null);
  const [loadingFinalSchedule, setLoadingFinalSchedule] = useState(false);
  const [isFinalScheduleOpen, setIsFinalScheduleOpen] = useState(false);

  const [actionLoading, setActionLoading] = useState(false);

  const [departments, setDepartments] = useState([]);
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(
    user.department_id ? String(user.department_id) : ""
  );
  const [loadingDepartments, setLoadingDepartments] = useState(false);
  const [savingDepartment, setSavingDepartment] = useState(false);

  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [availableDepartmentGroups, setAvailableDepartmentGroups] = useState([]);
  const [selectedExtraGroupId, setSelectedExtraGroupId] = useState("");
  const [loadingExtraGroups, setLoadingExtraGroups] = useState(false);
  const [addingExtraGroup, setAddingExtraGroup] = useState(false);

  const [manualBusySlots, setManualBusySlots] = useState([]);
  const [loadingManualBusySlots, setLoadingManualBusySlots] = useState(false);
  const [creatingManualBusySlot, setCreatingManualBusySlot] = useState(false);
  const [deletingManualBusySlotId, setDeletingManualBusySlotId] = useState(null);

  const [manualBusyDay, setManualBusyDay] = useState("1");
  const [manualBusyPair, setManualBusyPair] = useState("1");
  const [manualBusyWeekType, setManualBusyWeekType] = useState("both");
  const [manualBusyTitle, setManualBusyTitle] = useState("Лабораторная");
  const [manualBusyComment, setManualBusyComment] = useState("");

  const [generationRuns, setGenerationRuns] = useState([]);
  const [loadingGenerationRuns, setLoadingGenerationRuns] = useState(false);
  const [creatingGenerationRun, setCreatingGenerationRun] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState(null);
  const [runDetailsMap, setRunDetailsMap] = useState({});
  const [loadingRunDetailsId, setLoadingRunDetailsId] = useState(null);
  const [selectingRunVariantId, setSelectingRunVariantId] = useState(null);

  const availableGroups = useMemo(() => {
    const map = new Map();

    const assignments = data.assignments || [];
    const extraGroups = data.extra_groups || [];

    for (const item of assignments) {
      const group = item.group;
      if (!group?.id) continue;

      if (!map.has(group.id)) {
        map.set(group.id, {
          id: group.id,
          uuid: group.uuid,
          name: group.name,
          source: "assignment",
        });
      }
    }

    for (const group of extraGroups) {
      if (!group?.id) continue;

      if (!map.has(group.id)) {
        map.set(group.id, {
          id: group.id,
          uuid: group.uuid,
          name: group.name,
          source: group.source || "extra_group",
        });
      }
    }

    return Array.from(map.values()).sort((a, b) =>
      a.name.localeCompare(b.name, "ru")
    );
  }, [data.assignments, data.extra_groups]);

  const availableDisciplines = useMemo(() => {
    const map = new Map();
    const assignments = data.assignments || [];

    for (const item of assignments) {
      const discipline = item.discipline;
      if (!discipline?.id) continue;

      if (!map.has(discipline.id)) {
        map.set(discipline.id, {
          id: discipline.id,
          full_name: discipline.full_name,
          abbr: discipline.abbr,
        });
      }
    }

    return Array.from(map.values()).sort((a, b) =>
      a.full_name.localeCompare(b.full_name, "ru")
    );
  }, [data.assignments]);

  const myGroups = useMemo(() => {
    return availableGroups;
  }, [availableGroups]);

  const selectedGroupsMeta = useMemo(() => {
    const ids = new Set(selectedGroupIds.map(Number));
    return availableGroups.filter((group) => ids.has(group.id));
  }, [availableGroups, selectedGroupIds]);

  const hasExtraGroupSelected = selectedGroupsMeta.some(
    (group) => group.source === "extra_group" || group.source === "manual_department_access"
  );

  const toggleBlockedSlot = (day, pairNumber) => {
    const key = `${day}:${pairNumber}:both`;

    setBlockedSlots((prev) => {
      if (prev.includes(key)) {
        return prev.filter((item) => item !== key);
      }
      return [...prev, key];
    });
  };

  const isBlocked = (day, pairNumber) => {
    return blockedSlots.includes(`${day}:${pairNumber}:both`);
  };

  const loadAvailableDepartmentGroups = async () => {
    if (!user.department_id) {
      setAvailableDepartmentGroups([]);
      return;
    }

    setLoadingExtraGroups(true);
    try {
      const result = await getAvailableDepartmentGroups(token);
      setAvailableDepartmentGroups(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки групп кафедры");
    } finally {
      setLoadingExtraGroups(false);
    }
  };

  const loadRequests = async () => {
    setLoadingRequests(true);
    setError("");

    try {
      const result = await getMyConsultationRequests(token);
      setRequests(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки заявок");
    } finally {
      setLoadingRequests(false);
    }
  };

  const loadDepartments = async () => {
    setLoadingDepartments(true);

    try {
      const result = await getAvailableDepartments(token);
      setDepartments(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки кафедр");
    } finally {
      setLoadingDepartments(false);
    }
  };

  const loadManualBusySlots = async () => {
    setLoadingManualBusySlots(true);
    try {
      const result = await getMyManualBusySlots(token);
      setManualBusySlots(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки ручной занятости");
    } finally {
      setLoadingManualBusySlots(false);
    }
  };

  const handleOpenGenerationVariantPreview = async (runId, variantId) => {
    setLoadingPreview(true);
    setError("");

    try {
      const result = await getMyGenerationRunVariantPreview(token, runId, variantId);
      setPreviewData(result);
      setIsPreviewOpen(true);
    } catch (err) {
      setError(err.message || "Ошибка загрузки preview общего варианта");
    } finally {
      setLoadingPreview(false);
    }
  };

  const loadGenerationRuns = async () => {
    setLoadingGenerationRuns(true);
    try {
      const result = await getMyGenerationRuns(token);
      setGenerationRuns(result);
    } catch (err) {
      setError(err.message || "Ошибка загрузки общих генераций");
    } finally {
      setLoadingGenerationRuns(false);
    }
  };

  useEffect(() => {
    loadRequests();
    loadDepartments();
    loadAvailableDepartmentGroups();
    loadManualBusySlots();
    loadGenerationRuns();
  }, [token, user.department_id]);

  const loadVariantPreview = async (requestId, variantId) => {
    setLoadingPreview(true);
    setError("");

    try {
      const result = await getVariantPreview(token, requestId, variantId);
      setPreviewData(result);
      setIsPreviewOpen(true);
    } catch (err) {
      setError(err.message || "Ошибка загрузки preview");
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleOpenFinalSchedule = async () => {
    setLoadingFinalSchedule(true);
    setError("");

    try {
      const result = await getMyFinalSchedule(token);
      setFinalScheduleData(result);
      setIsFinalScheduleOpen(true);
    } catch (err) {
      setError(err.message || "Ошибка загрузки расписания");
    } finally {
      setLoadingFinalSchedule(false);
    }
  };

  const handleSaveDepartment = async () => {
    if (!selectedDepartmentId) {
      setError("Выберите кафедру");
      return;
    }

    setSavingDepartment(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await selectDepartmentForMe(token, Number(selectedDepartmentId));
      setUser((prev) => ({
        ...prev,
        department_id: result.department.id,
      }));
      setSuccessMessage(`Кафедра сохранена: ${result.department.abbr}`);
    } catch (err) {
      setError(err.message || "Ошибка сохранения кафедры");
    } finally {
      setSavingDepartment(false);
    }
  };

  const handleCreateRequest = async (e) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    if (!selectedGroupIds.length) {
      setError("Выберите хотя бы одну группу");
      return;
    }

    if (!user.department_id) {
      setError("Сначала выберите свою кафедру");
      return;
    }

    if (!consultationsCount || Number(consultationsCount) <= 0) {
      setError("Укажите корректное количество консультаций");
      return;
    }

    const normalizedPreferredDay = preferredDay ? Number(preferredDay) : null;
    const normalizedExcludedDay = excludedDay ? Number(excludedDay) : null;

    if (
      normalizedPreferredDay !== null &&
      normalizedExcludedDay !== null &&
      normalizedPreferredDay === normalizedExcludedDay
    ) {
      setError("Предпочтительный и исключённый день не могут совпадать");
      return;
    }

    let normalizedDisciplineId = selectedDisciplineId
      ? Number(selectedDisciplineId)
      : null;

    if (hasExtraGroupSelected) {
      normalizedDisciplineId = null;
    }

    setCreating(true);

    try {
      const result = await createMyConsultationRequest(
        token,
        selectedGroupIds.map(Number),
        normalizedDisciplineId,
        Number(consultationsCount),
        preferredAudience,
        avoidDayWithoutClasses,
        avoidFirstPair,
        avoidLastPair,
        normalizedPreferredDay,
        normalizedExcludedDay,
        weekPreference,
        blockedSlots
      );

      setSuccessMessage("Заявка успешно создана");
      setConsultationsCount(1);
      setSelectedGroupIds([]);
      setSelectedDisciplineId("");
      setPreferredAudience("");
      setAvoidDayWithoutClasses(false);
      setAvoidFirstPair(false);
      setAvoidLastPair(false);
      setWeekPreference("both");
      setPreferredDay("");
      setExcludedDay("");
      setBlockedSlots([]);

      await refreshTeacherData();
      await loadRequests();
      setExpandedRequestId(result.request_id);
    } catch (err) {
      setError(err.message || "Ошибка создания заявки");
    } finally {
      setCreating(false);
    }
  };

  const handleAddExtraGroup = async () => {
    if (!selectedExtraGroupId) {
      setError("Выберите группу кафедры");
      return;
    }

    setAddingExtraGroup(true);
    setError("");
    setSuccessMessage("");

    try {
      await addExtraGroupForMe(token, Number(selectedExtraGroupId));
      setSelectedExtraGroupId("");
      setSuccessMessage("Группа добавлена");

      await refreshTeacherData();
      await loadAvailableDepartmentGroups();
    } catch (err) {
      setError(err.message || "Ошибка добавления группы");
    } finally {
      setAddingExtraGroup(false);
    }
  };

  const handleCreateManualBusySlot = async (e) => {
    e.preventDefault();
    setError("");
    setSuccessMessage("");

    try {
      setCreatingManualBusySlot(true);
      await createMyManualBusySlot(
        token,
        Number(manualBusyDay),
        Number(manualBusyPair),
        manualBusyWeekType,
        manualBusyTitle,
        manualBusyComment
      );

      setSuccessMessage("Занятый слот добавлен");
      setManualBusyDay("1");
      setManualBusyPair("1");
      setManualBusyWeekType("both");
      setManualBusyTitle("Лабораторная");
      setManualBusyComment("");

      await loadManualBusySlots();
    } catch (err) {
      setError(err.message || "Ошибка добавления занятого слота");
    } finally {
      setCreatingManualBusySlot(false);
    }
  };

  const handleDeleteManualBusySlot = async (slotId) => {
    setError("");
    setSuccessMessage("");

    try {
      setDeletingManualBusySlotId(slotId);
      await deleteMyManualBusySlot(token, slotId);
      setSuccessMessage("Занятый слот удалён");
      await loadManualBusySlots();
    } catch (err) {
      setError(err.message || "Ошибка удаления занятого слота");
    } finally {
      setDeletingManualBusySlotId(null);
    }
  };

  const handleGenerateVariants = async (requestId) => {
    setActionLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      await generateVariantsForMyRequest(token, requestId);
      await loadRequests();
      setExpandedRequestId(requestId);
      setSuccessMessage("Варианты успешно сгенерированы");
    } catch (err) {
      setError(err.message || "Ошибка генерации вариантов");
    } finally {
      setActionLoading(false);
    }
  };

  const handleSelectVariant = async (requestId, variantId) => {
    setActionLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      await selectVariantForMyRequest(token, requestId, variantId);
      await loadRequests();
      await loadVariantPreview(requestId, variantId);
      setExpandedRequestId(requestId);
      setSuccessMessage("Вариант успешно выбран");
    } catch (err) {
      setError(err.message || "Ошибка выбора варианта");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteRequest = async (requestId) => {
    setActionLoading(true);
    setError("");
    setSuccessMessage("");

    try {
      await deleteMyConsultationRequest(token, requestId);
      await loadRequests();
      if (expandedRequestId === requestId) {
        setExpandedRequestId(null);
      }
      setSuccessMessage("Заявка удалена");
    } catch (err) {
      setError(err.message || "Ошибка удаления заявки");
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateGenerationRun = async () => {
    setCreatingGenerationRun(true);
    setError("");
    setSuccessMessage("");

    try {
      const result = await createMyGenerationRun(token);
      setSuccessMessage(
        `Общая генерация выполнена. Заявок: ${result.requests_count}, вариантов: ${result.variants_count}`
      );
      await loadGenerationRuns();
      if (result.run_id) {
        setExpandedRunId(result.run_id);
        await handleExpandRun(result.run_id, true);
      }
    } catch (err) {
      setError(err.message || "Ошибка общей генерации");
    } finally {
      setCreatingGenerationRun(false);
    }
  };

  const handleExpandRun = async (runId, forceOpen = false) => {
    if (!forceOpen && expandedRunId === runId) {
      setExpandedRunId(null);
      return;
    }

    setExpandedRunId(runId);

    if (runDetailsMap[runId]) {
      return;
    }

    try {
      setLoadingRunDetailsId(runId);
      const result = await getMyGenerationRunDetails(token, runId);
      setRunDetailsMap((prev) => ({
        ...prev,
        [runId]: result,
      }));
    } catch (err) {
      setError(err.message || "Ошибка загрузки деталей общей генерации");
    } finally {
      setLoadingRunDetailsId(null);
    }
  };

  const handleSelectGenerationVariant = async (runId, variantId) => {
    try {
      setSelectingRunVariantId(variantId);
      setError("");
      setSuccessMessage("");

      await selectMyGenerationRunVariant(token, runId, variantId);
      setSuccessMessage("Общий вариант выбран");

      await loadGenerationRuns();
      const result = await getMyGenerationRunDetails(token, runId);
      setRunDetailsMap((prev) => ({
        ...prev,
        [runId]: result,
      }));
      await loadRequests();
    } catch (err) {
      setError(err.message || "Ошибка выбора общего варианта");
    } finally {
      setSelectingRunVariantId(null);
    }
  };

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <h1>Личный кабинет преподавателя</h1>
          <p className="muted">{user.full_name}</p>
        </div>

        <div className="request-actions">
          <button onClick={handleOpenFinalSchedule} disabled={loadingFinalSchedule}>
            {loadingFinalSchedule ? "Загружаем..." : "Моё расписание"}
          </button>
          <button onClick={onLogout}>Выйти</button>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Моя кафедра</h2>
            <p className="muted">Выберите кафедру, к которой вы относитесь</p>
          </div>
        </div>

        <div className="department-select-row">
          <select
            className="select"
            value={selectedDepartmentId}
            onChange={(e) => setSelectedDepartmentId(e.target.value)}
            disabled={loadingDepartments}
          >
            <option value="">Выберите кафедру</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>
                {department.abbr} — {department.name}
              </option>
            ))}
          </select>

          <button onClick={handleSaveDepartment} disabled={savingDepartment}>
            {savingDepartment ? "Сохраняем..." : "Сохранить кафедру"}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Мои группы</h2>
            <p className="muted">Группы, у которых вы ведёте занятия или добавили вручную</p>
          </div>
        </div>

        {myGroups.length === 0 ? (
          <p className="muted">Группы не найдены</p>
        ) : (
          <div className="groups-pills-row">
            {myGroups.map((group) => (
              <span className="group-pill" key={group.id}>
                {group.name}
              </span>
            ))}
          </div>
        )}

        <div className="extra-group-add-row">
          <select
            className="select"
            value={selectedExtraGroupId}
            onChange={(e) => setSelectedExtraGroupId(e.target.value)}
            disabled={loadingExtraGroups || !user.department_id}
          >
            <option value="">
              {user.department_id
                ? "Выберите группу кафедры"
                : "Сначала выберите кафедру"}
            </option>
            {availableDepartmentGroups
              .filter((group) => !group.already_added)
              .map((group) => (
                <option key={group.id} value={group.id}>
                  {group.name}
                </option>
              ))}
          </select>

          <button
            onClick={handleAddExtraGroup}
            disabled={addingExtraGroup || !user.department_id}
          >
            {addingExtraGroup ? "Добавляем..." : "+ Добавить группу"}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Ручная занятость</h2>
            <p className="muted">
              Добавьте лабораторные или другие занятые слоты, которых нет в расписании
            </p>
          </div>
        </div>

        <form onSubmit={handleCreateManualBusySlot} className="form">
          <div className="day-preferences-row">
            <label>
              День
              <select
                className="select"
                value={manualBusyDay}
                onChange={(e) => setManualBusyDay(e.target.value)}
              >
                {DAYS.map((day) => (
                  <option key={day.value} value={day.value}>
                    {day.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Пара
              <select
                className="select"
                value={manualBusyPair}
                onChange={(e) => setManualBusyPair(e.target.value)}
              >
                {PAIRS.map((pair) => (
                  <option key={pair} value={pair}>
                    {pair} пара
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="day-preferences-row">
            <label>
              Неделя
              <select
                className="select"
                value={manualBusyWeekType}
                onChange={(e) => setManualBusyWeekType(e.target.value)}
              >
                <option value="both">Обе недели</option>
                <option value="num">Только числитель</option>
                <option value="den">Только знаменатель</option>
              </select>
            </label>

            <label>
              Название
              <input
                value={manualBusyTitle}
                onChange={(e) => setManualBusyTitle(e.target.value)}
                placeholder="Например: Лабораторная"
              />
            </label>
          </div>

          <label>
            Комментарий
            <input
              value={manualBusyComment}
              onChange={(e) => setManualBusyComment(e.target.value)}
              placeholder="Необязательно"
            />
          </label>

          <button type="submit" disabled={creatingManualBusySlot}>
            {creatingManualBusySlot ? "Добавляем..." : "Добавить занятый слот"}
          </button>
        </form>

        <div className="expanded-section" style={{ marginTop: 20 }}>
          <span className="label">Текущая ручная занятость</span>

          {loadingManualBusySlots ? (
            <div className="muted">Загрузка...</div>
          ) : manualBusySlots.length === 0 ? (
            <div className="muted">Ручная занятость пока не добавлена</div>
          ) : (
            <div className="variants-list">
              {manualBusySlots.map((slot) => (
                <div className="variant-card" key={slot.id}>
                  <div className="variant-header">
                    <div>
                      <strong>{slot.title}</strong>
                      <div className="muted">
                        {slot.day_label}, {slot.pair_number} пара, {slot.week_type_label}
                      </div>
                      {slot.comment ? <div className="muted">{slot.comment}</div> : null}
                    </div>
                  </div>

                  <div className="request-actions">
                    <button
                      onClick={() => handleDeleteManualBusySlot(slot.id)}
                      disabled={deletingManualBusySlotId === slot.id}
                    >
                      {deletingManualBusySlotId === slot.id ? "Удаляем..." : "Удалить"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Новая заявка на консультации</h2>
            <p className="muted">Укажите параметры и предпочтения для подбора вариантов</p>
          </div>
        </div>

        <form onSubmit={handleCreateRequest} className="form">
          <div className="card inner-card">
            <h3>Группы заявки</h3>

            <div className="multi-groups-list">
              {availableGroups.map((group) => {
                const checked = selectedGroupIds.includes(group.id);

                return (
                  <label key={group.id} className="checkbox-card">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedGroupIds((prev) => [...prev, group.id]);
                        } else {
                          setSelectedGroupIds((prev) =>
                            prev.filter((id) => id !== group.id)
                          );
                        }
                      }}
                    />
                    <span>
                      {group.name}
                      {group.source === "extra_group" ||
                      group.source === "manual_department_access"
                        ? " — консультация"
                        : ""}
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="card inner-card">
            <h3>Дисциплина и аудитория</h3>

            <label>
              Дисциплина
              <select
                className="select"
                value={selectedDisciplineId}
                onChange={(e) => setSelectedDisciplineId(e.target.value)}
                disabled={hasExtraGroupSelected}
              >
                <option value="">
                  {hasExtraGroupSelected
                    ? "Для вручную добавленных групп используется просто консультация"
                    : "Выберите дисциплину"}
                </option>
                {!hasExtraGroupSelected &&
                  availableDisciplines.map((discipline) => (
                    <option key={discipline.id} value={discipline.id}>
                      {discipline.full_name}
                    </option>
                  ))}
              </select>
            </label>

            <label>
              Желаемая аудитория
              <input
                value={preferredAudience}
                onChange={(e) => setPreferredAudience(e.target.value)}
                placeholder="Например: 512ю, 402, онлайн"
              />
            </label>
          </div>

          <label>
            Количество консультаций
            <input
              type="number"
              min="1"
              value={consultationsCount}
              onChange={(e) => setConsultationsCount(e.target.value)}
              required
            />
          </label>

          <div className="preferences-grid">
            <label className="checkbox-card">
              <input
                type="checkbox"
                checked={avoidDayWithoutClasses}
                onChange={(e) => setAvoidDayWithoutClasses(e.target.checked)}
              />
              <span>Не ставить в день без занятий</span>
            </label>

            <label className="checkbox-card">
              <input
                type="checkbox"
                checked={avoidFirstPair}
                onChange={(e) => setAvoidFirstPair(e.target.checked)}
              />
              <span>Не ставить первой парой</span>
            </label>

            <label className="checkbox-card">
              <input
                type="checkbox"
                checked={avoidLastPair}
                onChange={(e) => setAvoidLastPair(e.target.checked)}
              />
              <span>Не ставить последней парой</span>
            </label>
          </div>

          <div className="day-preferences-row">
            <label>
              Предпочтительный день
              <select
                className="select"
                value={preferredDay}
                onChange={(e) => setPreferredDay(e.target.value)}
              >
                <option value="">Не выбрано</option>
                {DAYS.map((day) => (
                  <option key={day.value} value={day.value}>
                    {day.label}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Исключить день
              <select
                className="select"
                value={excludedDay}
                onChange={(e) => setExcludedDay(e.target.value)}
              >
                <option value="">Не выбрано</option>
                {DAYS.map((day) => (
                  <option key={day.value} value={day.value}>
                    {day.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label>
            Предпочтение по типу недели
            <select
              className="select"
              value={weekPreference}
              onChange={(e) => setWeekPreference(e.target.value)}
            >
              <option value="both">Обе недели</option>
              <option value="num">Только числитель</option>
              <option value="den">Только знаменатель</option>
            </select>
          </label>

          <div>
            <span className="label">Запрещённые таймслоты</span>
            <div className="blocked-table">
              <div className="blocked-table-header blocked-table-cell">Пара</div>
              {DAYS.map((day) => (
                <div
                  key={`header-${day.value}`}
                  className="blocked-table-header blocked-table-cell"
                >
                  {day.label}
                </div>
              ))}

              {PAIRS.map((pairNumber) => (
                <div key={`row-${pairNumber}`} style={{ display: "contents" }}>
                  <div className="blocked-table-pair blocked-table-cell">
                    {pairNumber}
                  </div>

                  {DAYS.map((day) => (
                    <label
                      key={`${day.value}-${pairNumber}`}
                      className="blocked-table-cell blocked-table-slot"
                    >
                      <input
                        type="checkbox"
                        checked={isBlocked(day.value, pairNumber)}
                        onChange={() => toggleBlockedSlot(day.value, pairNumber)}
                      />
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {error ? <div className="error">{error}</div> : null}
          {successMessage ? <div className="success">{successMessage}</div> : null}

          <button type="submit" disabled={creating}>
            {creating ? "Создаём..." : "Создать заявку"}
          </button>
        </form>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Общая генерация по всем активным заявкам</h2>
            <p className="muted">
              Система подбирает согласованные варианты сразу для всех ваших активных заявок
            </p>
          </div>
        </div>

        <div className="request-actions">
          <button onClick={handleCreateGenerationRun} disabled={creatingGenerationRun}>
            {creatingGenerationRun
              ? "Генерируем..."
              : "Подобрать общий вариант по всем активным заявкам"}
          </button>
        </div>

        <div style={{ marginTop: 20 }}>
          <span className="label">История общих генераций</span>

          {loadingGenerationRuns ? (
            <div className="muted">Загрузка...</div>
          ) : generationRuns.length === 0 ? (
            <div className="muted">Общих генераций пока нет</div>
          ) : (
            <div className="variants-list">
              {generationRuns.map((run) => {
                const details = runDetailsMap[run.id];
                const isExpanded = expandedRunId === run.id;

                return (
                  <div className="variant-card" key={run.id}>
                    <div className="variant-header">
                      <div>
                        <strong>Запуск #{run.id}</strong>
                        <div className="muted">{run.comment || "Без комментария"}</div>
                        <div className="muted">
                          Статус: {run.status} • создан: {run.created_at || "—"}
                        </div>
                      </div>
                    </div>

                    <div className="request-actions">
                      <button onClick={() => handleExpandRun(run.id)}>
                        {isExpanded ? "Скрыть" : "Открыть"}
                      </button>
                    </div>

                    {isExpanded ? (
                      <div className="request-expanded-block">
                        {loadingRunDetailsId === run.id ? (
                          <div className="muted">Загружаем детали...</div>
                        ) : details ? (
                          <>
                            <div className="expanded-section">
                              <span className="label">Заявки, вошедшие в расчёт</span>
                              {details.requests?.length ? (
                                <div className="variants-list">
                                  {details.requests.map((request) => (
                                    <div className="variant-card" key={request.id}>
                                      <div>
                                        <strong>Заявка #{request.id}</strong>
                                      </div>
                                      <div className="muted">
                                        Группы:{" "}
                                        {request.groups?.length
                                          ? request.groups.map((g) => g.name).join(", ")
                                          : "—"}
                                      </div>
                                      <div className="muted">
                                        Тип: {request.discipline?.full_name || "Консультация"}
                                      </div>
                                      <div className="muted">
                                        Аудитория: {request.preferred_audience || "—"}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="muted">Нет заявок</div>
                              )}
                            </div>

                            <div className="expanded-section">
                              <span className="label">Общие варианты</span>

                              {!details.variants || details.variants.length === 0 ? (
                                <div className="muted">Варианты пока не сгенерированы</div>
                              ) : (
                                <div className="variants-list">
                                  {details.variants.map((variant) => (
                                    <div
                                      className={`variant-card ${
                                        variant.status === "selected"
                                          ? "variant-card-selected"
                                          : ""
                                      }`}
                                      key={variant.id}
                                    >
                                      <div className="variant-header">
                                        <div>
                                          <strong>Общий вариант {variant.variant_number}</strong>
                                          <div className="muted">
                                            {variant.comment || "Без комментария"}
                                          </div>
                                        </div>
                                        <div className="variant-status">
                                          {variant.status === "selected"
                                            ? "Выбран"
                                            : variant.status === "discarded"
                                            ? "Отклонён"
                                            : "Доступен"}
                                        </div>
                                      </div>

                                      <div className="variants-list">
                                        {variant.requests?.map((requestVariant) => (
                                          <div className="variant-card" key={requestVariant.request_id}>
                                            <div>
                                              <strong>
                                                Заявка #{requestVariant.request_id}
                                              </strong>
                                            </div>
                                            <div className="muted">
                                              Группы: {requestVariant.groups_label}
                                            </div>
                                            <div className="muted">
                                              Тип:{" "}
                                              {requestVariant.discipline?.full_name ||
                                                "Консультация"}
                                            </div>
                                            <div className="muted">
                                              Аудитория:{" "}
                                              {requestVariant.preferred_audience || "—"}
                                            </div>

                                            <div className="variant-slots">
                                              {requestVariant.slots?.map((slot, idx) => (
                                                <div className="variant-slot" key={idx}>
                                                  {slot.day_label}, {slot.pair_number} пара
                                                  {slot.week_type_label
                                                    ? `, ${slot.week_type_label}`
                                                    : ""}
                                                </div>
                                              ))}
                                            </div>
                                          </div>
                                        ))}
                                      </div>

                                      <div className="request-actions">
                                        <button
                                          onClick={() =>
                                            handleOpenGenerationVariantPreview(run.id, variant.id)
                                          }
                                          disabled={loadingPreview}
                                        >
                                          Показать в сетке
                                        </button>
                                        <button
                                          onClick={() =>
                                            handleSelectGenerationVariant(run.id, variant.id)
                                          }
                                          disabled={
                                            selectingRunVariantId === variant.id ||
                                            variant.status === "selected"
                                          }
                                        >
                                          {variant.status === "selected"
                                            ? "Выбран"
                                            : selectingRunVariantId === variant.id
                                            ? "Выбираем..."
                                            : "Выбрать общий вариант"}
                                        </button>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="muted">Нет данных</div>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="section-header">
          <div>
            <h2>Мои заявки</h2>
            <p className="muted">Все заявки загружаются автоматически</p>
          </div>
        </div>

        {loadingRequests ? (
          <p className="muted">Загрузка заявок...</p>
        ) : requests.length === 0 ? (
          <p className="muted">Заявок пока нет</p>
        ) : (
          <div className="requests-list">
            {requests.map((request) => {
              const isLocked =
                request.status === "approved" ||
                request.status === "rejected" ||
                request.status === "submitted_for_approval";

              return (
                <div
                  className={`request-card polished-request-card ${getStatusClass(
                    request.status
                  )}`}
                  key={request.id}
                >
                  <div className="request-card-inner">
                    <div className="request-main-row">
                      <div>
                        <span className="label">Группы</span>
                        <div>
                          {request.groups?.length
                            ? request.groups.map((group) => group.name).join(", ")
                            : "—"}
                        </div>
                      </div>

                      <div>
                        <span className="label">Тип</span>
                        <div>{request.discipline?.full_name || "Консультация"}</div>
                      </div>

                      <div>
                        <span className="label">Статус</span>
                        <div className="status-badge">
                          {getStatusLabel(request.status)}
                        </div>
                      </div>
                    </div>

                    <div className="request-main-row">
                      <div>
                        <span className="label">Желаемая аудитория</span>
                        <div>{request.preferred_audience || "—"}</div>
                      </div>
                    </div>

                    <div className="request-preferences-line">
                      <span className="mini-pill">
                        Консультаций: {request.consultations_count}
                      </span>
                      <span className="mini-pill">
                        Неделя: {request.week_preference_label || "обе недели"}
                      </span>
                      {request.preferred_audience ? (
                        <span className="mini-pill">
                          аудитория: {request.preferred_audience}
                        </span>
                      ) : null}
                      {request.avoid_day_without_classes ? (
                        <span className="mini-pill">без пустого дня</span>
                      ) : null}
                      {request.avoid_first_pair ? (
                        <span className="mini-pill">не 1 пара</span>
                      ) : null}
                      {request.avoid_last_pair ? (
                        <span className="mini-pill">не последняя</span>
                      ) : null}
                      {request.preferred_day ? (
                        <span className="mini-pill">
                          Желаемый день: {DAY_LABELS[request.preferred_day]}
                        </span>
                      ) : null}
                      {request.excluded_day ? (
                        <span className="mini-pill">
                          исключить: {DAY_LABELS[request.excluded_day]}
                        </span>
                      ) : null}
                    </div>

                    <div className="request-actions">
                      <button
                        onClick={() =>
                          setExpandedRequestId(
                            expandedRequestId === request.id ? null : request.id
                          )
                        }
                      >
                        {expandedRequestId === request.id ? "Скрыть" : "Открыть"}
                      </button>
                      {/*
                      <button
                        onClick={() => handleGenerateVariants(request.id)}
                        disabled={actionLoading || isLocked}
                      >
                        Подобрать варианты
                      </button>
                      */}

                      <button
                        onClick={() => handleDeleteRequest(request.id)}
                        disabled={actionLoading || request.status === "approved"}
                      >
                        Удалить заявку
                      </button>
                    </div>

                    {expandedRequestId === request.id ? (
                      <div className="request-expanded-block">
                        <div className="expanded-section">
                          <span className="label">Запрещённые слоты</span>
                          <div>
                            {!request.blocked_slots || request.blocked_slots.length === 0
                              ? "не заданы"
                              : request.blocked_slots
                                  .map(
                                    (slot) =>
                                      `${DAY_LABELS[slot.day]}, ${slot.pair_number} пара`
                                  )
                                  .join(" • ")}
                          </div>
                        </div>

                        <div className="expanded-section">
                          <span className="label">Локальные варианты</span>

                          {!request.variants || request.variants.length === 0 ? (
                            <div className="muted">Варианты пока не сгенерированы</div>
                          ) : (
                            <div className="variants-list">
                              {request.variants.map((variant) => (
                                <div
                                  className={`variant-card ${
                                    variant.status === "selected"
                                      ? "variant-card-selected"
                                      : ""
                                  }`}
                                  key={variant.id}
                                >
                                  <div className="variant-header">
                                    <div>
                                      <strong>Вариант {variant.variant_number}</strong>
                                      <div className="muted">
                                        {variant.comment || "Без комментария"}
                                      </div>
                                    </div>
                                    <div className="variant-status">
                                      {variant.status === "selected"
                                        ? "Выбран"
                                        : variant.status === "discarded"
                                        ? "Отклонён"
                                        : "Доступен"}
                                    </div>
                                  </div>

                                  <div className="variant-slots">
                                    {variant.slots.map((slot, index) => (
                                      <div className="variant-slot" key={index}>
                                        {DAY_LABELS[slot.day]}, {slot.pair_number} пара
                                        {slot.week_type_label
                                          ? `, ${slot.week_type_label}`
                                          : ""}
                                      </div>
                                    ))}
                                  </div>

                                  <div className="request-actions">
                                    <button
                                      onClick={() =>
                                        loadVariantPreview(request.id, variant.id)
                                      }
                                      disabled={loadingPreview}
                                    >
                                      Показать в сетке
                                    </button>

                                    <button
                                      onClick={() =>
                                        handleSelectVariant(request.id, variant.id)
                                      }
                                      disabled={
                                        actionLoading ||
                                        variant.status === "selected" ||
                                        isLocked
                                      }
                                    >
                                      {variant.status === "selected"
                                        ? "Выбран"
                                        : "Выбрать"}
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        isOpen={isPreviewOpen}
        title="Preview варианта в расписании"
        onClose={() => setIsPreviewOpen(false)}
      >
        {loadingPreview ? (
          <p className="muted">Загружаем preview...</p>
        ) : previewData ? (
          <VariantPreviewGrid previewData={previewData} />
        ) : (
          <p className="muted">Нет данных для preview</p>
        )}
      </Modal>

      <Modal
        isOpen={isFinalScheduleOpen}
        title="Моё расписание"
        onClose={() => setIsFinalScheduleOpen(false)}
      >
        {loadingFinalSchedule ? (
          <p className="muted">Загружаем расписание...</p>
        ) : finalScheduleData ? (
          <FinalScheduleGrid data={finalScheduleData} />
        ) : (
          <p className="muted">Нет данных для расписания</p>
        )}
      </Modal>
    </div>
  );
}