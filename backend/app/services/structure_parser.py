from typing import Any


def walk_structure_tree(
    node: dict[str, Any],
    faculty_context: dict[str, Any] | None = None,
    department_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    departments: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []

    node_type = node.get("nodeType")
    children = node.get("children", []) or []

    current_faculty = faculty_context
    current_department = department_context

    if node_type == "faculty":
        current_faculty = {
            "name": node.get("name"),
            "abbr": node.get("abbr"),
            "uuid": node.get("uuid"),
        }

    if node_type == "department":
        current_department = {
            "name": node.get("name"),
            "abbr": node.get("abbr"),
            "uuid": node.get("uuid"),
            "faculty_name": current_faculty.get("name") if current_faculty else None,
            "faculty_abbr": current_faculty.get("abbr") if current_faculty else None,
        }
        departments.append(current_department)

    if node_type == "group":
        groups.append(
            {
                "name": node.get("abbr"),
                "uuid": node.get("uuid"),
                "course": node.get("course"),
                "semester": node.get("semester"),
                "department_uuid": current_department.get("uuid") if current_department else None,
            }
        )

    for child in children:
        child_departments, child_groups = walk_structure_tree(
            child,
            faculty_context=current_faculty,
            department_context=current_department,
        )
        departments.extend(child_departments)
        groups.extend(child_groups)

    return departments, groups