import json

import httpx
from sqlalchemy.orm import Session

from app.models.group import Group
from app.models.import_job import ImportJob
from app.services.import_service import import_group_schedule

BASE_URL = "https://lks.bmstu.ru/lks-back/api/v1"


def teacher_exists_in_schedule_payload(schedule_data: dict, teacher_uuid: str) -> bool:
    schedule_items = schedule_data.get("data", {}).get("schedule", [])

    for item in schedule_items:
        teachers = item.get("teachers", [])
        for teacher in teachers:
            if teacher.get("uuid") == teacher_uuid:
                return True

    return False


def run_teacher_groups_import_job(job_id: int, teacher_uuid: str):
    from app.core.database import SessionLocal

    db: Session = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.message = "Подготовка списка групп"
        db.commit()

        groups = db.query(Group).order_by(Group.name).all()

        job.total_groups = len(groups)
        job.processed_groups = 0
        job.matched_groups = 0
        job.imported_groups = 0
        job.error_count = 0
        job.message = "Сканирование расписаний групп"
        db.commit()

        matched_groups = []
        imported_groups = []
        errors = []

        with httpx.Client(timeout=20.0) as client:
            for index, group in enumerate(groups, start=1):
                url = f"{BASE_URL}/schedules/groups/{group.uuid}/public"

                try:
                    response = client.get(url)
                    response.raise_for_status()
                    payload = response.json()

                    if teacher_exists_in_schedule_payload(payload, teacher_uuid):
                        matched_groups.append(
                            {
                                "id": group.id,
                                "uuid": group.uuid,
                                "name": group.name,
                            }
                        )

                        job.matched_groups = len(matched_groups)
                        job.message = f"Импорт расписания группы {group.name}"
                        db.commit()

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
            "teacher_uuid": teacher_uuid,
            "scanned_groups": len(groups),
            "matched_groups_count": len(matched_groups),
            "imported_groups_count": len(imported_groups),
            "matched_groups": matched_groups,
            "imported_groups": imported_groups,
            "errors": errors,
        }

        job.status = "done"
        job.message = "Импорт по преподавателю завершён"
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