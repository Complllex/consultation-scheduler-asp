export const DAY_LABELS = {
  1: "Понедельник",
  2: "Вторник",
  3: "Среда",
  4: "Четверг",
  5: "Пятница",
  6: "Суббота",
};

export const STATUS_LABELS = {
  ready_for_generation: "Готова к подбору",
  variants_generated: "Варианты сгенерированы",
  selected_by_teacher: "Вариант выбран",
  submitted_to_department: "Отправлена на согласование",
  approved: "Утверждена",
  rejected: "Отклонена",
};

export function getStatusLabel(status) {
  switch (status) {
    case "ready_for_generation":
      return "Готова к генерации";
    case "submitted_for_approval":
      return "Отправлено на согласование";
    case "approved":
      return "Утверждена";
    case "rejected":
      return "Отклонена";
    default:
      return status;
  }
}

export function getStatusClass(status) {
  switch (status) {
    case "approved":
      return "status-approved";
    case "rejected":
      return "status-rejected";
    case "submitted_for_approval":
      return "status-pending";
    default:
      return "";
  }
}