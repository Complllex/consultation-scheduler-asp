from typing import Any


def map_week_type(api_week: str) -> str:
    mapping = {
        "all": "both",
        "ch": "num",
        "zn": "den",
    }
    return mapping.get(api_week, "both")


def build_teacher_full_name(teacher_data: dict[str, Any]) -> str:
    last_name = teacher_data.get("lastName", "").strip()
    first_name = teacher_data.get("firstName", "").strip()
    middle_name = teacher_data.get("middleName", "").strip()

    parts = [last_name, first_name, middle_name]
    return " ".join(part for part in parts if part)


def parse_schedule_entries(schedule_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed_entries: list[dict[str, Any]] = []

    for entry in schedule_data:
        discipline = entry.get("discipline") or {}
        teachers = entry.get("teachers") or []

        parsed_entries.append(
            {
                "day": entry.get("day"),
                "pair_number": entry.get("time"),
                "week_type": map_week_type(entry.get("week")),
                "start_time": entry.get("startTime"),
                "end_time": entry.get("endTime"),
                "act_type": discipline.get("actType"),
                "discipline": {
                    "full_name": discipline.get("fullName"),
                    "short_name": discipline.get("shortName"),
                    "abbr": discipline.get("abbr"),
                }
                if discipline
                else None,
                "is_vuc": (discipline.get("abbr") == "ВУЦ" or discipline.get("fullName") == "ВУЦ"),
                "teachers": [
                    {
                        "uuid": teacher.get("uuid"),
                        "last_name": teacher.get("lastName"),
                        "first_name": teacher.get("firstName"),
                        "middle_name": teacher.get("middleName"),
                        "full_name": build_teacher_full_name(teacher),
                    }
                    for teacher in teachers
                    if teacher.get("uuid")
                ],
            }
        )

    return parsed_entries