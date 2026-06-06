import json

import httpx
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.group import Group
from app.models.import_job import ImportJob
from app.services.import_service import import_group_schedule

BASE_URL = "https://lks.bmstu.ru/lks-back/api/v1"


def run_department_groups_import_job(job_id: int, department_uuid: str):
    from app.core.database import SessionLocal

    db: Session = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return

        department = db.query(Department).filter(Department.uuid == department_uuid).first()
        if not department:
            job.status = "failed"
            job.message = "Department not found"
            db.commit()
            return

        job.status = "running"
        job.message = f"Подготовка списка групп кафедры {department.abbr}"
        db.commit()

        groups = (
            db.query(Group)
            .filter(Group.department_id == department.id)
            .order_by(Group.name)
            .all()
        )

        job.total_groups = len(groups)
        job.processed_groups = 0
        job.matched_groups = len(groups)
        job.imported_groups = 0
        job.error_count = 0
        job.message = f"Импорт расписаний кафедры {department.abbr}"
        db.commit()

        imported_groups = []
        errors = []

        with httpx.Client(timeout=20.0) as client:
            for index, group in enumerate(groups, start=1):
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
                    job.imported_groups = len(imported_groups)

                except Exception as e:
                    errors.append(
                        {
                            "group_id": group.id,
                            "group_uuid": group.uuid,
                            "group_name": group.name,
                            "error": str(e),
                        }
                    )
                    job.error_count = len(errors)

                job.processed_groups = index
                job.message = f"Обработано групп: {index} из {len(groups)}"
                db.commit()

        result = {
            "department_uuid": department_uuid,
            "department_name": department.name,
            "department_abbr": department.abbr,
            "scanned_groups": len(groups),
            "imported_groups_count": len(imported_groups),
            "imported_groups": imported_groups,
            "errors": errors,
        }

        job.status = "done"
        job.message = f"Импорт кафедры {department.abbr} завершён"
        job.result_json = json.dumps(result, ensure_ascii=False)
        db.commit()

    except Exception as e:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.message = str(e)
            db.commit()
    finally:
        db.close()