import { Fragment, useMemo, useState } from "react";

function matchesWeekType(itemWeekType, selectedWeekTab) {
  if (itemWeekType === "both") return true;
  if (selectedWeekTab === "num") return itemWeekType === "num";
  if (selectedWeekTab === "den") return itemWeekType === "den";
  return false;
}

export default function FinalScheduleGrid({ data }) {
  const [selectedWeekTab, setSelectedWeekTab] = useState("num");

  const filteredGrid = useMemo(() => {
    return (data?.grid || []).map((day) => ({
      ...day,
      rows: (day.rows || []).map((row) => ({
        ...row,
        items: (row.items || []).filter((item) =>
          matchesWeekType(item.week_type, selectedWeekTab)
        ),
      })),
    }));
  }, [data?.grid, selectedWeekTab]);

  const filteredApprovedConsultations = useMemo(() => {
    return (data?.approved_consultations || []).filter((item) =>
      matchesWeekType(item.week_type, selectedWeekTab)
    );
  }, [data?.approved_consultations, selectedWeekTab]);

  return (
    <div className="preview-wrapper">
      <div className="card inner-card">
        <h3>Моё утверждённое расписание</h3>

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
            <span>Утверждённые консультации</span>
          </div>
          <div className="legend-item">
            <span className="legend-box" style={{ background: "#fff7ed", border: "1px solid #fdba74" }}></span>
            <span>Ручная занятость</span>
          </div>
        </div>
      </div>

      <div className="card inner-card">
        <h3>
          Расписание — {selectedWeekTab === "num" ? "числитель" : "знаменатель"}
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
                          <div className="slot-pill-meta">
                            {item.week_type_label}
                            {item.discipline_name
                              ? ` • ${item.discipline_name}`
                              : item.act_type && item.act_type !== "consultation"
                              ? ` • ${item.act_type}`
                              : ""}
                          </div>
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
          Утверждённые консультации —{" "}
          {selectedWeekTab === "num" ? "числитель" : "знаменатель"}
        </h3>

        {filteredApprovedConsultations.length === 0 ? (
          <p className="muted">На этой неделе утверждённых консультаций нет</p>
        ) : (
          <div className="requests-list">
            {filteredApprovedConsultations.map((slot, index) => (
              <div
                className="request-card compact-request-card"
                key={`${slot.request_id}-${slot.day}-${slot.pair_number}-${slot.week_type}-${index}`}
              >
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

                <div>
                  <span className="label">Группы</span>
                  <div>{slot.groups_label || "—"}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}