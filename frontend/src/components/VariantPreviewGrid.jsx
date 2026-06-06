import { Fragment, useMemo, useState } from "react";

function matchesWeekType(itemWeekType, selectedWeekTab) {
  if (itemWeekType === "both") return true;
  if (selectedWeekTab === "num") return itemWeekType === "num";
  if (selectedWeekTab === "den") return itemWeekType === "den";
  return false;
}

function buildSummaryRows(previewData) {
  if (Array.isArray(previewData?.summary?.slots)) {
    return previewData.summary.slots.map((slot) => ({
      requestLabel:
        previewData?.request?.groups?.length > 0
          ? previewData.request.groups.map((g) => g.name).join(", ")
          : previewData?.request?.group?.name || "Группа",
      disciplineLabel:
        previewData?.request?.discipline?.full_name || "Консультация",
      ...slot,
    }));
  }

  if (Array.isArray(previewData?.summary?.requests)) {
    return previewData.summary.requests.flatMap((requestItem) =>
      (requestItem.slots || []).map((slot) => ({
        requestLabel: requestItem.groups_label || "Группа",
        disciplineLabel: requestItem.discipline?.full_name || "Консультация",
        ...slot,
      }))
    );
  }

  return [];
}

export default function VariantPreviewGrid({ previewData }) {
  const [selectedWeekTab, setSelectedWeekTab] = useState("num");

  const filteredGrid = useMemo(() => {
    return (previewData?.grid || []).map((day) => ({
      ...day,
      rows: (day.rows || []).map((row) => ({
        ...row,
        items: (row.items || []).filter((item) =>
          matchesWeekType(item.week_type, selectedWeekTab)
        ),
      })),
    }));
  }, [previewData?.grid, selectedWeekTab]);

  const filteredSummaryRows = useMemo(() => {
    return buildSummaryRows(previewData).filter((item) =>
      matchesWeekType(item.week_type, selectedWeekTab)
    );
  }, [previewData, selectedWeekTab]);

  const headerTitle = previewData?.request
    ? `Вариант ${previewData?.variant?.variant_number ?? ""}`.trim()
    : `Общий вариант ${previewData?.variant?.variant_number ?? ""}`.trim();

  return (
    <div className="preview-wrapper">
      <div className="card inner-card">
        <h3>{headerTitle}</h3>

        <p className="muted" style={{ marginBottom: 12 }}>
          {previewData?.teacher?.full_name || "Преподаватель"}
        </p>

        <div className="week-tabs">
          <button
            type="button"
            className={`week-tab-button ${selectedWeekTab === "num" ? "week-tab-button-active" : ""}`}
            onClick={() => setSelectedWeekTab("num")}
          >
            Числитель
          </button>

          <button
            type="button"
            className={`week-tab-button ${selectedWeekTab === "den" ? "week-tab-button-active" : ""}`}
            onClick={() => setSelectedWeekTab("den")}
          >
            Знаменатель
          </button>
        </div>

        <div className="legend-row">
          <div className="legend-item">
            <span className="legend-box existing-class-box"></span>
            <span>Существующие занятия</span>
          </div>
          <div className="legend-item">
            <span className="legend-box consultation-box"></span>
            <span>Консультации</span>
          </div>
          <div className="legend-item">
            <span className="legend-box" style={{ background: "#fff7ed", border: "1px solid #fdba74" }}></span>
            <span>Ручная занятость</span>
          </div>
        </div>
      </div>

      <div className="card inner-card">
        <h3>
          Preview — {selectedWeekTab === "num" ? "числитель" : "знаменатель"}
        </h3>

        <div className="schedule-grid-table">
          <div className="schedule-grid-header schedule-grid-cell">Пара</div>
          {filteredGrid.map((day) => (
            <div
              key={`header-${day.day}`}
              className="schedule-grid-header schedule-grid-cell"
            >
              {day.day_label}
            </div>
          ))}

          {[1, 2, 3, 4, 5, 6, 7].map((pairNumber) => (
            <Fragment key={`pair-row-${pairNumber}`}>
              <div className="schedule-grid-pair schedule-grid-cell">
                {pairNumber} пара
              </div>

              {filteredGrid.map((day) => {
                const row = (day.rows || []).find(
                  (item) => item.pair_number === pairNumber
                );

                return (
                  <div
                    key={`${day.day}-${pairNumber}`}
                    className="schedule-grid-cell schedule-grid-slot"
                  >
                    {row?.items?.length ? (
                      row.items.map((item, index) => (
                        <div
                          key={`${day.day}-${pairNumber}-${item.type}-${index}`}
                          className={
                            item.type === "consultation" ||
                            item.type === "approved_consultation"
                              ? "slot-pill consultation-pill"
                              : item.type === "manual_busy"
                              ? "slot-pill"
                              : "slot-pill existing-class-pill"
                          }
                          style={
                            item.type === "manual_busy"
                              ? {
                                  background: "#fff7ed",
                                  border: "1px solid #fdba74",
                                }
                              : undefined
                          }
                        >
                          <div className="slot-pill-title">{item.label}</div>

                          {(item.discipline_name || item.week_type_label) ? (
                            <div className="slot-pill-meta">
                              {item.week_type_label || ""}
                              {item.discipline_name
                                ? `${item.week_type_label ? " • " : ""}${item.discipline_name}`
                                : ""}
                            </div>
                          ) : null}

                          {Array.isArray(item.violation_reasons) &&
                          item.violation_reasons.length > 0 ? (
                            <div
                              style={{
                                color: "#b91c1c",
                                fontSize: 12,
                                marginTop: 6,
                              }}
                            >
                              {item.violation_reasons.join("; ")}
                            </div>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div className="empty-slot">—</div>
                    )}
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="card inner-card">
        <h3>
          Сводка по консультациям —{" "}
          {selectedWeekTab === "num" ? "числитель" : "знаменатель"}
        </h3>

        {filteredSummaryRows.length === 0 ? (
          <p className="muted">На этой неделе консультаций нет</p>
        ) : (
          <div className="requests-list">
            {filteredSummaryRows.map((slot, index) => (
              <div
                className="request-card compact-request-card"
                key={`${slot.requestLabel}-${slot.day}-${slot.pair_number}-${slot.week_type}-${index}`}
              >
                <div>
                  <span className="label">Группы</span>
                  <div>{slot.requestLabel}</div>
                </div>

                <div>
                  <span className="label">Дисциплина</span>
                  <div>{slot.disciplineLabel}</div>
                </div>

                <div>
                  <span className="label">День</span>
                  <div>{slot.day_label}</div>
                </div>

                <div>
                  <span className="label">Пара</span>
                  <div>{slot.pair_number}</div>
                </div>

                <div>
                  <span className="label">Неделя</span>
                  <div>{slot.week_type_label}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}