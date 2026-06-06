import httpx
from sqlalchemy.orm import Session

from app.models.group import Group
from app.services.import_service import import_group_schedule

BASE_URL = "https://lks.bmstu.ru/lks-back/api/v1"


def sync_department_groups_by_uuid(db: Session, department_uuid: str) -> dict:
    groups = (
        db.query(Group)
        .filter(Group.department_id.in_(
            db.query(Group.department_id)
            .filter(False)
        ))
        .all()
    )

    from app.models.department import Department

    department = db.query(Department).filter(Department.uuid == department_uuid).first()
    if not department:
        raise ValueError("Department not found")

    groups = (
        db.query(Group)
        .filter(Group.department_id == department.id)
        .order_by(Group.name)
        .all()
    )

    scanned_groups = 0
    imported_groups = []
    errors = []

    with httpx.Client(timeout=20.0) as client:
        for group in groups:
            scanned_groups += 1
            url = f"{BASE_URL}/schedules/groups/{group.uuid}/public"

            try:
                response = client.get(url)
                response.raise_for_status()

                import_group_schedule(db, group.uuid)

                imported_groups.append(
                    {
                        "id": group.id,
                        "uuid": group.uuid,
                        "name": group.name,
                    }
                )
            except Exception as e:
                errors.append(
                    {
                        "group_id": group.id,
                        "group_uuid": group.uuid,
                        "group_name": group.name,
                        "error": str(e),
                    }
                )

    return {
        "department_uuid": department_uuid,
        "department_name": department.name,
        "scanned_groups": scanned_groups,
        "imported_groups_count": len(imported_groups),
        "imported_groups": imported_groups,
        "errors": errors,
    }