const API_URL = import.meta.env.VITE_API_URL;

export async function loginRequest(username, password) {
  const body = new URLSearchParams();
  body.append("username", username);
  body.append("password", password);

  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  if (!response.ok) {
    throw new Error("Неверный логин или пароль");
  }

  return response.json();
}

export async function getMe(token) {
  const response = await fetch(
    `${API_URL}/users/me?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    throw new Error("Не удалось получить профиль");
  }

  return response.json();
}

export async function getAvailableDepartments(token) {
  const response = await fetch(
    `${API_URL}/users/me/available-departments?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить кафедры";
    throw new Error(detail);
  }

  return response.json();
}

export async function selectDepartmentForMe(token, departmentId) {
  const response = await fetch(
    `${API_URL}/users/me/select-department?token=${encodeURIComponent(
      token
    )}&department_id=${departmentId}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось выбрать кафедру";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyAssignments(token) {
  const response = await fetch(
    `${API_URL}/users/me/assignments?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить назначения";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyConsultationRequests(token) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить заявки";
    throw new Error(detail);
  }

  return response.json();
}

export async function createMyConsultationRequest(
  token,
  groupIds,
  disciplineId,
  consultationsCount,
  preferredAudience,
  avoidDayWithoutClasses,
  avoidFirstPair,
  avoidLastPair,
  preferredDay,
  excludedDay,
  weekPreference,
  blockedSlots
) {
  const params = new URLSearchParams();

  params.set("token", token);
  params.set("group_ids", groupIds.join(","));
  params.set("consultations_count", String(consultationsCount));
  params.set("avoid_day_without_classes", String(avoidDayWithoutClasses));
  params.set("avoid_first_pair", String(avoidFirstPair));
  params.set("avoid_last_pair", String(avoidLastPair));
  params.set("week_preference", weekPreference || "both");

  if (disciplineId !== null && disciplineId !== undefined && disciplineId !== "") {
    params.set("discipline_id", String(disciplineId));
  }

  if (preferredAudience !== null && preferredAudience !== undefined && preferredAudience.trim() !== "") {
    params.set("preferred_audience", preferredAudience.trim());
  }

  if (preferredDay !== null && preferredDay !== undefined && preferredDay !== "") {
    params.set("preferred_day", String(preferredDay));
  }

  if (excludedDay !== null && excludedDay !== undefined && excludedDay !== "") {
    params.set("excluded_day", String(excludedDay));
  }

  if (blockedSlots && blockedSlots.length > 0) {
    params.set("blocked_slots", blockedSlots.join(","));
  }

  const response = await fetch(
    `${API_URL}/users/me/consultation-requests?${params.toString()}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail =
      errorData?.detail
        ? typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
        : "Не удалось создать заявку";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyConsultationRequestDetails(token, requestId) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests/${requestId}?token=${encodeURIComponent(
      token
    )}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить заявку";
    throw new Error(detail);
  }

  return response.json();
}

export async function generateVariantsForMyRequest(token, requestId) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests/${requestId}/generate-variants?token=${encodeURIComponent(
      token
    )}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось сгенерировать варианты";
    throw new Error(detail);
  }

  return response.json();
}

export async function selectVariantForMyRequest(token, requestId, variantId) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests/${requestId}/select-variant/${variantId}?token=${encodeURIComponent(
      token
    )}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось выбрать вариант";
    throw new Error(detail);
  }

  return response.json();
}

export async function getVariantPreview(token, requestId, variantId) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests/${requestId}/variants/${variantId}/preview?token=${encodeURIComponent(
      token
    )}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить preview варианта";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyManualBusySlots(token) {
  const response = await fetch(
    `${API_URL}/users/me/manual-busy-slots?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось загрузить ручную занятость";
    throw new Error(detail);
  }

  return response.json();
}

export async function createMyManualBusySlot(
  token,
  day,
  pairNumber,
  weekType,
  title,
  comment
) {
  const params = new URLSearchParams();
  params.set("token", token);
  params.set("day", String(day));
  params.set("pair_number", String(pairNumber));
  params.set("week_type", weekType);
  params.set("title", title?.trim() || "Лабораторная");

  if (comment && comment.trim() !== "") {
    params.set("comment", comment.trim());
  }

  const response = await fetch(
    `${API_URL}/users/me/manual-busy-slots?${params.toString()}`,
    { method: "POST" }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail =
      errorData?.detail
        ? typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
        : "Не удалось добавить занятый слот";
    throw new Error(detail);
  }

  return response.json();
}

export async function deleteMyManualBusySlot(token, slotId) {
  const response = await fetch(
    `${API_URL}/users/me/manual-busy-slots/${slotId}?token=${encodeURIComponent(token)}`,
    { method: "DELETE" }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось удалить занятый слот";
    throw new Error(detail);
  }

  return response.json();
}


export async function importStructure() {
  const response = await fetch(`${API_URL}/import/structure`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error("Не удалось импортировать структуру");
  }

  return response.json();
}

export async function getHealthTables() {
  const response = await fetch(`${API_URL}/health/tables`);

  if (!response.ok) {
    throw new Error("Не удалось получить статистику таблиц");
  }

  return response.json();
}

export async function getMyDepartmentTeachers(token) {
  const response = await fetch(
    `${API_URL}/users/me/department-teachers?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить преподавателей кафедры";
    throw new Error(detail);
  }

  return response.json();
}

export async function deleteMyConsultationRequest(token, requestId) {
  const response = await fetch(
    `${API_URL}/users/me/consultation-requests/${requestId}?token=${encodeURIComponent(token)}`,
    {
      method: "DELETE",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось удалить заявку";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyFinalSchedule(token) {
  const response = await fetch(
    `${API_URL}/users/me/final-schedule?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить расписание";
    throw new Error(detail);
  }

  return response.json();
}

export async function getAvailableDepartmentGroups(token) {
  const response = await fetch(
    `${API_URL}/users/me/available-department-groups?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить группы кафедры";
    throw new Error(detail);
  }

  return response.json();
}

export async function addExtraGroupForMe(token, groupId) {
  const response = await fetch(
    `${API_URL}/users/me/add-extra-group/${groupId}?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось добавить группу";
    throw new Error(detail);
  }

  return response.json();
}

export async function importTeacherGroupsByUuid(token, teacherUuid) {
  const response = await fetch(
    `${API_URL}/admin/import/teacher-groups-by-uuid/${encodeURIComponent(
      teacherUuid
    )}?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось импортировать группы преподавателя";
    throw new Error(detail);
  }

  return response.json();
}

export async function importDepartmentGroupsByUuid(token, departmentUuid) {
  const response = await fetch(
    `${API_URL}/admin/import/department-groups-by-uuid/${encodeURIComponent(
      departmentUuid
    )}?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось импортировать группы кафедры";
    throw new Error(detail);
  }

  return response.json();
}

export async function getImportJobStatus(token, jobId) {
  const response = await fetch(
    `${API_URL}/admin/import-jobs/${jobId}?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось получить статус импорта";
    throw new Error(detail);
  }

  return response.json();
}

export async function createMyGenerationRun(token) {
  const response = await fetch(
    `${API_URL}/users/me/generation-runs?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail =
      errorData?.detail
        ? typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
        : "Не удалось запустить общую генерацию";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyGenerationRuns(token) {
  const response = await fetch(
    `${API_URL}/users/me/generation-runs?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось загрузить общие генерации";
    throw new Error(detail);
  }

  return response.json();
}

export async function getMyGenerationRunDetails(token, runId) {
  const response = await fetch(
    `${API_URL}/users/me/generation-runs/${runId}?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail = errorData?.detail || "Не удалось загрузить детали общей генерации";
    throw new Error(detail);
  }

  return response.json();
}

export async function selectMyGenerationRunVariant(token, runId, variantId) {
  const response = await fetch(
    `${API_URL}/users/me/generation-runs/${runId}/variants/${variantId}/select?token=${encodeURIComponent(token)}`,
    {
      method: "POST",
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail =
      errorData?.detail
        ? typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
        : "Не удалось выбрать общий вариант";
    throw new Error(detail);
  }

  return response.json();
}
export async function getMyDepartmentConsultationRequests(token) {
  const response = await fetch(
    `${API_URL}/departments/my/consultation-requests?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Не удалось загрузить заявки кафедры");
  }

  return response.json();
}

export async function approveDepartmentConsultationRequest(token, requestId) {
  const response = await fetch(
    `${API_URL}/departments/my/consultation-requests/${requestId}/approve?token=${encodeURIComponent(token)}`,
    { method: "POST" }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Не удалось утвердить заявку");
  }

  return response.json();
}

export async function rejectDepartmentConsultationRequest(token, requestId) {
  const response = await fetch(
    `${API_URL}/departments/my/consultation-requests/${requestId}/reject?token=${encodeURIComponent(token)}`,
    { method: "POST" }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Не удалось отклонить заявку");
  }

  return response.json();
}

export async function getMyDepartmentApprovedConsultationsTable(token) {
  const response = await fetch(
    `${API_URL}/departments/my/approved-consultations-table?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(errorData?.detail || "Не удалось загрузить таблицу утверждённых консультаций");
  }

  return response.json();
}

export async function getMyGenerationRunVariantPreview(token, runId, variantId) {
  const response = await fetch(
    `${API_URL}/users/me/generation-runs/${runId}/variants/${variantId}/preview?token=${encodeURIComponent(token)}`
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const detail =
      errorData?.detail
        ? typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail)
        : "Не удалось загрузить preview общего варианта";
    throw new Error(detail);
  }

  return response.json();
}