from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import text
import re

from app.core.database import SessionLocal
from app.core.security import ALGORITHM, SECRET_KEY, create_access_token, verify_password
from app.models.consultation_request import ConsultationRequest
from app.models.consultation_request_blocked_slot import ConsultationRequestBlockedSlot
from app.models.consultation_request_variant import ConsultationRequestVariant
from app.models.consultation_variant_slot import ConsultationVariantSlot
from app.models.department import Department
from app.models.department_teacher import DepartmentTeacher
from app.models.discipline import Discipline
from app.models.group import Group
from app.models.schedule_slot import ScheduleSlot
from app.models.schedule_slot_teacher import ScheduleSlotTeacher
from app.models.teacher import Teacher
from app.models.teacher_assignment import TeacherAssignment
from app.models.user import User
from app.services.asp_solver import generate_request_variants_via_asp
from app.services.import_service import import_group_schedule, import_structure
from app.models.teacher_extra_group import TeacherExtraGroup
import json
from fastapi import BackgroundTasks
from app.models.import_job import ImportJob
from app.services.department_schedule_sync import run_department_groups_import_job
from app.services.teacher_schedule_sync import run_teacher_groups_import_job
from app.models.consultation_request_group import ConsultationRequestGroup
from app.models.teacher_manual_busy_slot import TeacherManualBusySlot
from app.models.teacher_generation_run import TeacherGenerationRun
from app.models.teacher_generation_run_request import TeacherGenerationRunRequest
from app.models.teacher_generation_run_variant import TeacherGenerationRunVariant
from app.models.teacher_generation_run_variant_slot import TeacherGenerationRunVariantSlot
from app.services.teacher_batch_asp_solver import generate_teacher_batch_variants

app = FastAPI(title="University Consultation Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEEK_TYPE_LABELS = {
    "both": "обе недели",
    "num": "числитель",
    "den": "знаменатель",
}
WEEK_PREFERENCE_LABELS = {
    "any": "любое",
    "both": "обе недели",
    "num": "числитель",
    "den": "знаменатель",
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str):
    db = SessionLocal()
    try:
        credentials_exception = HTTPException(
            status_code=401,
            detail="Could not validate credentials",
        )

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id is None:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise credentials_exception

        return user
    finally:
        db.close()

def pair_number_to_time_range(pair_number: int) -> str:
    mapping = {
        1: "08:30–10:00",
        2: "10:10–11:40",
        3: "11:50–13:20",
        4: "14:05–15:35",
        5: "15:45–17:15",
        6: "17:25–18:55",
        7: "19:05–20:35",
    }
    return mapping.get(pair_number, f"{pair_number} пара")

@app.get("/departments/my/approved-consultations-table")
def get_my_department_approved_consultations_table(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department responsible can access this endpoint")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .filter(ConsultationRequest.status == "approved")
            .order_by(ConsultationRequest.id.desc())
            .all()
        )

        rows = []

        for request in requests:
            teacher = db.query(Teacher).filter(Teacher.id == request.teacher_id).first()
            discipline = (
                db.query(Discipline).filter(Discipline.id == request.discipline_id).first()
                if request.discipline_id is not None
                else None
            )

            selected_slots = build_selected_batch_slots_for_request(db, request.id)
            if not selected_slots:
                continue

            for slot in selected_slots:
                rows.append(
                    {
                        "teacher_full_name": teacher.full_name if teacher else "Преподаватель",
                        "discipline_name": discipline.full_name if discipline else "Консультация",
                        "day": slot["day_label"],
                        "week_type": slot["week_type_label"],
                        "time": pair_number_to_time_range(slot["pair_number"]),
                        "audience": request.preferred_audience or "",
                    }
                )

        return {
            "rows": rows
        }
    finally:
        db.close()

def build_teacher_assignments(db, teacher_id: int):
    assignments = (
        db.query(TeacherAssignment)
        .filter(TeacherAssignment.teacher_id == teacher_id)
        .all()
    )

    result = []
    for assignment in assignments:
        group = db.query(Group).filter(Group.id == assignment.group_id).first()
        discipline = db.query(Discipline).filter(Discipline.id == assignment.discipline_id).first()

        result.append(
            {
                "group": {
                    "id": group.id,
                    "uuid": group.uuid,
                    "name": group.name,
                } if group else None,
                "discipline": {
                    "id": discipline.id,
                    "full_name": discipline.full_name,
                    "abbr": discipline.abbr,
                } if discipline else None,
                "act_type": assignment.act_type,
                "source": assignment.source,
            }
        )
    return result

def build_teacher_extra_groups(db, teacher_id: int):
    links = (
        db.query(TeacherExtraGroup)
        .filter(TeacherExtraGroup.teacher_id == teacher_id)
        .all()
    )

    result = []
    for link in links:
        group = db.query(Group).filter(Group.id == link.group_id).first()
        if not group:
            continue

        result.append(
            {
                "id": group.id,
                "uuid": group.uuid,
                "name": group.name,
                "department_id": group.department_id,
                "source": link.source,
            }
        )

    return result

def build_request_slot_violation_reasons(
    request: ConsultationRequest,
    slot_day: int,
    slot_pair: int,
):
    reasons = []

    if request.avoid_first_pair and slot_pair == 1:
        reasons.append("поставлена первой парой")

    if request.avoid_last_pair and slot_pair == 7:
        reasons.append("поставлена последней парой")

    if request.preferred_day is not None and slot_day != request.preferred_day:
        reasons.append("не соответствует предпочитаемому дню")

    if request.excluded_day is not None and slot_day == request.excluded_day:
        reasons.append("попадает в исключённый день")

    return reasons

@app.post("/departments/my/consultation-requests/{request_id}/approve")
def approve_department_consultation_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department responsible can approve requests")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if request.status not in {"submitted_for_approval", "approved"}:
            raise HTTPException(
                status_code=400,
                detail="Only requests submitted for approval can be approved",
            )

        request.status = "approved"
        db.commit()

        return {"status": "success"}
    finally:
        db.close()

@app.get("/users/me/generation-runs/{run_id}/variants/{variant_id}/preview")
def get_my_generation_run_variant_preview(
    run_id: int,
    variant_id: int,
    token: str = Query(...),
):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can view generation run preview")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        run = (
            db.query(TeacherGenerationRun)
            .filter(TeacherGenerationRun.id == run_id)
            .filter(TeacherGenerationRun.teacher_id == current_user.teacher_id)
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")

        variant = (
            db.query(TeacherGenerationRunVariant)
            .filter(TeacherGenerationRunVariant.id == variant_id)
            .filter(TeacherGenerationRunVariant.run_id == run.id)
            .first()
        )
        if not variant:
            raise HTTPException(status_code=404, detail="Generation run variant not found")

        teacher = db.query(Teacher).filter(Teacher.id == current_user.teacher_id).first()

        teacher_schedule_rows = (
            db.query(ScheduleSlot)
            .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
            .filter(ScheduleSlotTeacher.teacher_id == current_user.teacher_id)
            .all()
        )

        manual_busy_slots = (
            db.query(TeacherManualBusySlot)
            .filter(TeacherManualBusySlot.teacher_id == current_user.teacher_id)
            .all()
        )

        variant_slots = (
            db.query(TeacherGenerationRunVariantSlot)
            .filter(TeacherGenerationRunVariantSlot.run_variant_id == variant.id)
            .order_by(
                TeacherGenerationRunVariantSlot.request_id,
                TeacherGenerationRunVariantSlot.day,
                TeacherGenerationRunVariantSlot.pair_number,
            )
            .all()
        )

        discipline_ids = {
            slot.discipline_id
            for slot in teacher_schedule_rows
            if slot.discipline_id is not None
        }

        linked_requests = (
            db.query(TeacherGenerationRunRequest)
            .filter(TeacherGenerationRunRequest.run_id == run.id)
            .all()
        )

        request_map = {}
        request_groups_map = {}
        request_discipline_map = {}

        for link in linked_requests:
            request = (
                db.query(ConsultationRequest)
                .filter(ConsultationRequest.id == link.request_id)
                .first()
            )
            if not request:
                continue

            request_map[request.id] = request
            request_groups_map[request.id] = build_request_groups(db, request.id)

            if request.discipline_id is not None:
                discipline_ids.add(request.discipline_id)

        disciplines = (
            db.query(Discipline)
            .filter(Discipline.id.in_(discipline_ids))
            .all()
            if discipline_ids
            else []
        )
        discipline_map = {discipline.id: discipline for discipline in disciplines}

        for request_id, request in request_map.items():
            request_discipline_map[request_id] = discipline_map.get(request.discipline_id)

        unique_teacher_schedule_slots = []
        seen_schedule_keys = set()

        for schedule_slot in teacher_schedule_rows:
            slot_discipline = discipline_map.get(schedule_slot.discipline_id)

            dedup_key = (
                schedule_slot.day,
                schedule_slot.pair_number,
                schedule_slot.week_type,
                schedule_slot.discipline_id,
                schedule_slot.act_type,
                schedule_slot.start_time,
                schedule_slot.end_time,
            )

            if dedup_key in seen_schedule_keys:
                continue

            seen_schedule_keys.add(dedup_key)

            unique_teacher_schedule_slots.append(
                {
                    "day": schedule_slot.day,
                    "pair_number": schedule_slot.pair_number,
                    "week_type": schedule_slot.week_type,
                    "week_type_label": get_week_type_label(schedule_slot.week_type),
                    "act_type": schedule_slot.act_type,
                    "discipline_name": slot_discipline.full_name if slot_discipline else "Занятие",
                }
            )

        unique_manual_busy_slots = []
        seen_manual_keys = set()

        for slot in manual_busy_slots:
            key = (slot.day, slot.pair_number, slot.week_type, slot.title, slot.comment)
            if key in seen_manual_keys:
                continue

            seen_manual_keys.add(key)

            unique_manual_busy_slots.append(
                {
                    "day": slot.day,
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "week_type_label": get_week_type_label(slot.week_type),
                    "title": slot.title,
                    "comment": slot.comment,
                }
            )

        grouped_variant_slots = {}
        for slot in variant_slots:
            grouped_variant_slots.setdefault(slot.request_id, []).append(slot)

        summary_requests = []

        grid = []
        for day in range(1, 7):
            day_rows = []
            for pair_number in range(1, 8):
                items = []

                for schedule_slot in unique_teacher_schedule_slots:
                    if schedule_slot["day"] == day and schedule_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "existing_class",
                                "label": schedule_slot["discipline_name"],
                                "week_type": schedule_slot["week_type"],
                                "week_type_label": schedule_slot["week_type_label"],
                                "act_type": schedule_slot["act_type"],
                            }
                        )

                for busy_slot in unique_manual_busy_slots:
                    if busy_slot["day"] == day and busy_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "manual_busy",
                                "label": busy_slot["title"],
                                "week_type": busy_slot["week_type"],
                                "week_type_label": busy_slot["week_type_label"],
                                "act_type": "manual_busy",
                            }
                        )

                for request_id, request_slots in grouped_variant_slots.items():
                    for slot in request_slots:
                        if slot.day == day and slot.pair_number == pair_number:
                            groups = request_groups_map.get(request_id, [])
                            groups_label = ", ".join([g["name"] for g in groups]) if groups else "Группа"
                            discipline = request_discipline_map.get(request_id)
                            violation_reasons = build_request_slot_violation_reasons(
                                request=request_map[request_id],
                                slot_day=slot.day,
                                slot_pair=slot.pair_number,
                            )
                            items.append(
                                {
                                    "type": "consultation",
                                    "label": f"Консультация: {groups_label}",
                                    "week_type": slot.week_type,
                                    "week_type_label": get_week_type_label(slot.week_type),
                                    "act_type": "consultation",
                                    "discipline_name": discipline.full_name if discipline else "Консультация",
                                    "is_preference_violation": len(violation_reasons) > 0,
                                    "violation_reasons": violation_reasons,
                                }
                            )

                day_rows.append(
                    {
                        "day": day,
                        "day_label": DAY_LABELS[day],
                        "pair_number": pair_number,
                        "items": items,
                    }
                )

            grid.append(
                {
                    "day": day,
                    "day_label": DAY_LABELS[day],
                    "rows": day_rows,
                }
            )

        for request_id, request_slots in grouped_variant_slots.items():
            groups = request_groups_map.get(request_id, [])
            discipline = request_discipline_map.get(request_id)
            summary_requests.append(
                {
                    "request_id": request_id,
                    "groups": groups,
                    "groups_label": ", ".join([g["name"] for g in groups]) if groups else "Группа",
                    "discipline": {
                        "id": discipline.id,
                        "full_name": discipline.full_name,
                        "abbr": discipline.abbr,
                    } if discipline else None,
                    "slots": [
                        {
                            "day": slot.day,
                            "day_label": DAY_LABELS[slot.day],
                            "pair_number": slot.pair_number,
                            "week_type": slot.week_type,
                            "week_type_label": get_week_type_label(slot.week_type),
                            "violation_reasons": build_request_slot_violation_reasons(
                                request=request_map[request_id],
                                slot_day=slot.day,
                                slot_pair=slot.pair_number,
                            ),
                        }
                        for slot in request_slots
                    ],
                }
            )

        return {
            "teacher": {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
            } if teacher else None,
            "run": {
                "id": run.id,
                "status": run.status,
                "comment": run.comment,
            },
            "variant": {
                "id": variant.id,
                "variant_number": variant.variant_number,
                "status": variant.status,
                "comment": variant.comment,
            },
            "summary": {
                "requests": summary_requests,
            },
            "grid": grid,
        }
    finally:
        db.close()

@app.post("/departments/my/consultation-requests/{request_id}/reject")
def reject_department_consultation_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department responsible can reject requests")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if request.status not in {"submitted_for_approval", "rejected"}:
            raise HTTPException(
                status_code=400,
                detail="Only requests submitted for approval can be rejected",
            )

        request.status = "rejected"
        db.commit()

        return {"status": "success"}
    finally:
        db.close()

@app.get("/departments/my/consultation-requests")
def get_my_department_consultation_requests(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department responsible can access this endpoint")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .filter(ConsultationRequest.status.in_(["submitted_for_approval", "approved", "rejected"]))
            .order_by(ConsultationRequest.id.desc())
            .all()
        )

        result = []
        for request in requests:
            teacher = db.query(Teacher).filter(Teacher.id == request.teacher_id).first()
            item = build_request_details(db, request)
            item["teacher"] = {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
            } if teacher else None
            result.append(item)

        return result
    finally:
        db.close()

def build_request_details(db, request):
    groups = build_request_groups(db, request.id)

    discipline = (
        db.query(Discipline).filter(Discipline.id == request.discipline_id).first()
        if request.discipline_id is not None
        else None
    )

    blocked_slots = (
        db.query(ConsultationRequestBlockedSlot)
        .filter(ConsultationRequestBlockedSlot.request_id == request.id)
        .order_by(
            ConsultationRequestBlockedSlot.day,
            ConsultationRequestBlockedSlot.pair_number,
            ConsultationRequestBlockedSlot.week_type,
        )
        .all()
    )

    variants = (
        db.query(ConsultationRequestVariant)
        .filter(ConsultationRequestVariant.request_id == request.id)
        .order_by(ConsultationRequestVariant.variant_number)
        .all()
    )

    selected_variant = None
    if request.selected_variant_id:
        selected_variant = (
            db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.id == request.selected_variant_id)
            .first()
        )

    variant_items = []
    for variant in variants:
        slots = (
            db.query(ConsultationVariantSlot)
            .filter(ConsultationVariantSlot.variant_id == variant.id)
            .order_by(
                ConsultationVariantSlot.day,
                ConsultationVariantSlot.pair_number,
                ConsultationVariantSlot.week_type,
            )
            .all()
        )

        slot_items = []
        for slot in slots:
            violation_reasons = build_variant_slot_violation_reasons(
                request=request,
                slot_day=slot.day,
                slot_pair=slot.pair_number,
            )

            slot_items.append(
                {
                    "day": slot.day,
                    "day_label": DAY_LABELS.get(slot.day, str(slot.day)),
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "week_type_label": get_week_type_label(slot.week_type),
                    "violation_reasons": violation_reasons,
                    "is_preference_violation": len(violation_reasons) > 0,
                }
            )

        variant_items.append(
            {
                "id": variant.id,
                "variant_number": variant.variant_number,
                "status": variant.status,
                "score": variant.score,
                "comment": variant.comment,
                "slots": slot_items,
            }
        )

    blocked_slot_items = [
        {
            "id": slot.id,
            "day": slot.day,
            "day_label": DAY_LABELS.get(slot.day, str(slot.day)),
            "pair_number": slot.pair_number,
            "week_type": slot.week_type,
            "week_type_label": get_week_type_label(slot.week_type),
        }
        for slot in blocked_slots
    ]
    selected_batch_slots = build_selected_batch_slots_for_request(db, request.id)

    return {
        "id": request.id,
        "status": request.status,
        "consultations_count": request.consultations_count,
        "preferred_audience": request.preferred_audience,
        "avoid_day_without_classes": request.avoid_day_without_classes,
        "avoid_first_pair": request.avoid_first_pair,
        "avoid_last_pair": request.avoid_last_pair,
        "preferred_day": request.preferred_day,
        "excluded_day": request.excluded_day,
        "week_preference": request.week_preference,
        "selected_batch_slots": selected_batch_slots,
        "week_preference_label": WEEK_PREFERENCE_LABELS.get(
            request.week_preference, request.week_preference
        ),
        "groups": groups,
        "discipline": {
            "id": discipline.id,
            "full_name": discipline.full_name,
            "abbr": discipline.abbr,
        } if discipline else None,
        "blocked_slots": blocked_slot_items,
        "variants": variant_items,
        "selected_variant_id": request.selected_variant_id,
        "selected_variant_number": selected_variant.variant_number if selected_variant else None,
        "created_at": str(request.created_at) if request.created_at else None,
        "updated_at": str(request.updated_at) if request.updated_at else None,
    }

DAY_LABELS = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
}

WEEK_TYPE_LABELS = {
    "both": "обе недели",
    "num": "числитель",
    "den": "знаменатель",
}

def build_teacher_generation_run_requests(db, run_id: int):
    links = (
        db.query(TeacherGenerationRunRequest)
        .filter(TeacherGenerationRunRequest.run_id == run_id)
        .all()
    )

    result = []
    for link in links:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == link.request_id)
            .first()
        )
        if not request:
            continue

        result.append(build_request_details(db, request))

    return result


def build_teacher_generation_run_variants(db, run_id: int):
    variants = (
        db.query(TeacherGenerationRunVariant)
        .filter(TeacherGenerationRunVariant.run_id == run_id)
        .order_by(TeacherGenerationRunVariant.variant_number)
        .all()
    )

    result = []
    for variant in variants:
        slots = (
            db.query(TeacherGenerationRunVariantSlot)
            .filter(TeacherGenerationRunVariantSlot.run_variant_id == variant.id)
            .order_by(
                TeacherGenerationRunVariantSlot.request_id,
                TeacherGenerationRunVariantSlot.day,
                TeacherGenerationRunVariantSlot.pair_number,
            )
            .all()
        )

        grouped = {}
        for slot in slots:
            grouped.setdefault(slot.request_id, []).append(
                {
                    "day": slot.day,
                    "day_label": DAY_LABELS.get(slot.day, str(slot.day)),
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "week_type_label": get_week_type_label(slot.week_type),
                }
            )

        request_items = []
        for request_id, request_slots in grouped.items():
            request = (
                db.query(ConsultationRequest)
                .filter(ConsultationRequest.id == request_id)
                .first()
            )
            if not request:
                continue

            groups = build_request_groups(db, request.id)
            discipline = (
                db.query(Discipline).filter(Discipline.id == request.discipline_id).first()
                if request.discipline_id is not None
                else None
            )

            request_items.append(
                {
                    "request_id": request.id,
                    "groups": groups,
                    "groups_label": ", ".join([g["name"] for g in groups]) if groups else "Группа",
                    "discipline": {
                        "id": discipline.id,
                        "full_name": discipline.full_name,
                        "abbr": discipline.abbr,
                    } if discipline else None,
                    "preferred_audience": request.preferred_audience,
                    "slots": request_slots,
                }
            )

        result.append(
            {
                "id": variant.id,
                "variant_number": variant.variant_number,
                "score": variant.score,
                "comment": variant.comment,
                "status": variant.status,
                "requests": request_items,
            }
        )

    return result

def build_request_groups(db, request_id: int):
    links = (
        db.query(ConsultationRequestGroup)
        .filter(ConsultationRequestGroup.request_id == request_id)
        .all()
    )

    groups = []
    for link in links:
        group = db.query(Group).filter(Group.id == link.group_id).first()
        if not group:
            continue

        groups.append(
            {
                "id": group.id,
                "uuid": group.uuid,
                "name": group.name,
                "department_id": group.department_id,
            }
        )

    return groups

def get_week_type_label(value: str) -> str:
    return WEEK_TYPE_LABELS.get(value, value)

def normalize_full_name(value: str) -> str:
    if not value:
        return ""

    value = value.strip().lower()
    value = value.replace("ё", "е")
    value = re.sub(r"\s+", " ", value)
    return value


def find_teacher_by_full_name(db, full_name: str):
    normalized_target = normalize_full_name(full_name)
    if not normalized_target:
        return None

    teachers = db.query(Teacher).all()
    for teacher in teachers:
        if normalize_full_name(teacher.full_name) == normalized_target:
            return teacher

    return None

def build_variant_slot_violation_reasons(request: ConsultationRequest, slot_day: int, slot_pair: int):
    reasons = []

    if request.avoid_first_pair and slot_pair == 1:
        reasons.append("первая пара")

    if request.avoid_last_pair and slot_pair == 7:
        reasons.append("последняя пара")

    if request.excluded_day is not None and slot_day == request.excluded_day:
        reasons.append("исключённый день")

    return reasons

@app.get("/")
def root():
    return {"message": "Backend is running"}


@app.get("/health/db")
def check_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    finally:
        db.close()


@app.get("/health/tables")
def check_tables():
    db = SessionLocal()
    try:
        return {
            "departments": db.query(Department).count(),
            "groups": db.query(Group).count(),
            "teachers": db.query(Teacher).count(),
            "disciplines": db.query(Discipline).count(),
            "schedule_slots": db.query(ScheduleSlot).count(),
            "teacher_assignments": db.query(TeacherAssignment).count(),
            "department_teachers": db.query(DepartmentTeacher).count(),
            "consultation_requests": db.query(ConsultationRequest).count(),
            "consultation_request_blocked_slots": db.query(ConsultationRequestBlockedSlot).count(),
            "consultation_request_variants": db.query(ConsultationRequestVariant).count(),
            "consultation_variant_slots": db.query(ConsultationVariantSlot).count(),
            "users": db.query(User).count(),
        }
    finally:
        db.close()


@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.login == form_data.username).first()
        if not user or not verify_password(form_data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect login or password")

        access_token = create_access_token(data={"sub": str(user.id)})

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }
    finally:
        db.close()


@app.get("/users/me")
def get_me(token: str = Query(...)):
    user = get_current_user(token)
    return {
        "id": user.id,
        "login": user.login,
        "full_name": user.full_name,
        "role": user.role,
        "teacher_id": user.teacher_id,
        "department_id": user.department_id,
        "is_active": user.is_active,
    }

@app.get("/users/me/available-departments")
def get_available_departments_for_me(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access departments list")

    db = SessionLocal()
    try:
        departments = db.query(Department).order_by(Department.abbr).all()

        return [
            {
                "id": department.id,
                "uuid": department.uuid,
                "abbr": department.abbr,
                "name": department.name,
            }
            for department in departments
        ]
    finally:
        db.close()

def build_selected_batch_slots_for_request(db, request_id: int):
    selected_variant = (
        db.query(TeacherGenerationRunVariant)
        .join(
            TeacherGenerationRun,
            TeacherGenerationRun.id == TeacherGenerationRunVariant.run_id,
        )
        .join(
            TeacherGenerationRunRequest,
            TeacherGenerationRunRequest.run_id == TeacherGenerationRun.id,
        )
        .filter(TeacherGenerationRunRequest.request_id == request_id)
        .filter(TeacherGenerationRunVariant.status == "selected")
        .order_by(TeacherGenerationRunVariant.id.desc())
        .first()
    )

    if not selected_variant:
        return []

    slots = (
        db.query(TeacherGenerationRunVariantSlot)
        .filter(TeacherGenerationRunVariantSlot.run_variant_id == selected_variant.id)
        .filter(TeacherGenerationRunVariantSlot.request_id == request_id)
        .order_by(
            TeacherGenerationRunVariantSlot.day,
            TeacherGenerationRunVariantSlot.pair_number,
            TeacherGenerationRunVariantSlot.week_type,
        )
        .all()
    )

    return [
        {
            "day": slot.day,
            "day_label": DAY_LABELS.get(slot.day, str(slot.day)),
            "pair_number": slot.pair_number,
            "week_type": slot.week_type,
            "week_type_label": get_week_type_label(slot.week_type),
        }
        for slot in slots
    ]

@app.post("/users/me/generation-runs")
def create_my_generation_run(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can create generation runs")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        active_requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .filter(ConsultationRequest.status == "ready_for_generation")
            .order_by(ConsultationRequest.id.asc())
            .all()
        )

        if not active_requests:
            raise HTTPException(
                status_code=400,
                detail="No active requests available for batch generation",
            )

        run = TeacherGenerationRun(
            teacher_id=current_user.teacher_id,
            status="running",
            comment=f"Создано заявок: {len(active_requests)}",
        )
        db.add(run)
        db.flush()

        for request in active_requests:
            db.add(
                TeacherGenerationRunRequest(
                    run_id=run.id,
                    request_id=request.id,
                )
            )

        db.flush()

        variants_count = generate_teacher_batch_variants(
            db=db,
            run_id=run.id,
            max_variants=3,
        )

        db.refresh(run)

        return {
            "status": "success",
            "run_id": run.id,
            "requests_count": len(active_requests),
            "variants_count": variants_count,
        }
    finally:
        db.close()

@app.get("/users/me/generation-runs")
def get_my_generation_runs(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access generation runs")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        runs = (
            db.query(TeacherGenerationRun)
            .filter(TeacherGenerationRun.teacher_id == current_user.teacher_id)
            .order_by(TeacherGenerationRun.id.desc())
            .all()
        )

        return [
            {
                "id": run.id,
                "status": run.status,
                "comment": run.comment,
                "created_at": str(run.created_at) if run.created_at else None,
                "updated_at": str(run.updated_at) if run.updated_at else None,
            }
            for run in runs
        ]
    finally:
        db.close()

@app.get("/users/me/generation-runs/{run_id}")
def get_my_generation_run_details(run_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access generation run details")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        run = (
            db.query(TeacherGenerationRun)
            .filter(TeacherGenerationRun.id == run_id)
            .filter(TeacherGenerationRun.teacher_id == current_user.teacher_id)
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")

        requests = build_teacher_generation_run_requests(db, run.id)
        variants = build_teacher_generation_run_variants(db, run.id)

        return {
            "id": run.id,
            "status": run.status,
            "comment": run.comment,
            "created_at": str(run.created_at) if run.created_at else None,
            "updated_at": str(run.updated_at) if run.updated_at else None,
            "requests": requests,
            "variants": variants,
        }
    finally:
        db.close()

@app.post("/users/me/generation-runs/{run_id}/variants/{variant_id}/select")
def select_my_generation_run_variant(run_id: int, variant_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can select generation run variant")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        run = (
            db.query(TeacherGenerationRun)
            .filter(TeacherGenerationRun.id == run_id)
            .filter(TeacherGenerationRun.teacher_id == current_user.teacher_id)
            .first()
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")

        selected_variant = (
            db.query(TeacherGenerationRunVariant)
            .filter(TeacherGenerationRunVariant.id == variant_id)
            .filter(TeacherGenerationRunVariant.run_id == run.id)
            .first()
        )
        if not selected_variant:
            raise HTTPException(status_code=404, detail="Generation run variant not found")

        all_variants = (
            db.query(TeacherGenerationRunVariant)
            .filter(TeacherGenerationRunVariant.run_id == run.id)
            .all()
        )

        for variant in all_variants:
            if variant.id == selected_variant.id:
                variant.status = "selected"
            else:
                variant.status = "discarded"

        linked_requests = (
            db.query(TeacherGenerationRunRequest)
            .filter(TeacherGenerationRunRequest.run_id == run.id)
            .all()
        )

        for link in linked_requests:
            request = (
                db.query(ConsultationRequest)
                .filter(ConsultationRequest.id == link.request_id)
                .first()
            )
            if request:
                request.status = "submitted_for_approval"

        run.status = "selected"
        run.comment = f"Выбран общий вариант #{selected_variant.variant_number}"

        db.commit()

        return {
            "status": "success",
            "run_id": run.id,
            "selected_variant_id": selected_variant.id,
            "selected_variant_number": selected_variant.variant_number,
        }
    finally:
        db.close()

@app.post("/admin/import/teacher-groups-by-uuid/{teacher_uuid}")
def import_teacher_groups_by_uuid(
    teacher_uuid: str,
    background_tasks: BackgroundTasks,
    token: str = Query(...),
):
    current_user = get_current_user(token)

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can run this import")

    db = SessionLocal()
    try:
        job = ImportJob(
            job_type="teacher_groups",
            target_uuid=teacher_uuid,
            status="pending",
            message="Задача создана",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        background_tasks.add_task(run_teacher_groups_import_job, job.id, teacher_uuid)

        return {
            "status": "accepted",
            "job_id": job.id,
            "job_type": job.job_type,
            "target_uuid": job.target_uuid,
        }
    finally:
        db.close()

@app.post("/admin/import/department-groups-by-uuid/{department_uuid}")
def import_department_groups_by_uuid(
    department_uuid: str,
    background_tasks: BackgroundTasks,
    token: str = Query(...),
):
    current_user = get_current_user(token)

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can run this import")

    db = SessionLocal()
    try:
        job = ImportJob(
            job_type="department_groups",
            target_uuid=department_uuid,
            status="pending",
            message="Задача создана",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        background_tasks.add_task(run_department_groups_import_job, job.id, department_uuid)

        return {
            "status": "accepted",
            "job_id": job.id,
            "job_type": job.job_type,
            "target_uuid": job.target_uuid,
        }
    finally:
        db.close()

@app.get("/admin/import-jobs/{job_id}")
def get_import_job_status(job_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin can view import jobs")

    db = SessionLocal()
    try:
        job = db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found")

        result_data = None
        if job.result_json:
            try:
                result_data = json.loads(job.result_json)
            except Exception:
                result_data = job.result_json

        return {
            "id": job.id,
            "job_type": job.job_type,
            "target_uuid": job.target_uuid,
            "status": job.status,
            "total_groups": job.total_groups,
            "processed_groups": job.processed_groups,
            "matched_groups": job.matched_groups,
            "imported_groups": job.imported_groups,
            "error_count": job.error_count,
            "message": job.message,
            "result": result_data,
            "created_at": str(job.created_at) if job.created_at else None,
            "updated_at": str(job.updated_at) if job.updated_at else None,
        }
    finally:
        db.close()

@app.get("/users/me/available-department-groups")
def get_available_department_groups_for_me(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access department groups")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="Teacher user must choose department first")

    db = SessionLocal()
    try:
        assignment_group_ids = {
            group_id
            for (group_id,) in db.query(TeacherAssignment.group_id)
            .filter(TeacherAssignment.teacher_id == current_user.teacher_id)
            .distinct()
            .all()
        }

        extra_group_ids = {
            group_id
            for (group_id,) in db.query(TeacherExtraGroup.group_id)
            .filter(TeacherExtraGroup.teacher_id == current_user.teacher_id)
            .distinct()
            .all()
        }

        already_attached_ids = assignment_group_ids | extra_group_ids

        groups = (
            db.query(Group)
            .filter(Group.department_id == current_user.department_id)
            .order_by(Group.name)
            .all()
        )

        return [
            {
                "id": group.id,
                "uuid": group.uuid,
                "name": group.name,
                "department_id": group.department_id,
                "already_added": group.id in already_attached_ids,
            }
            for group in groups
        ]
    finally:
        db.close()

@app.post("/users/me/add-extra-group/{group_id}")
def add_extra_group_for_me(group_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can add extra groups")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="Teacher user must choose department first")

    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        if group.department_id != current_user.department_id:
            raise HTTPException(
                status_code=400,
                detail="You can add only groups of your department",
            )

        existing_assignment = (
            db.query(TeacherAssignment)
            .filter(TeacherAssignment.teacher_id == current_user.teacher_id)
            .filter(TeacherAssignment.group_id == group.id)
            .first()
        )
        if existing_assignment:
            return {"status": "already_exists_in_assignments"}

        existing_link = (
            db.query(TeacherExtraGroup)
            .filter(TeacherExtraGroup.teacher_id == current_user.teacher_id)
            .filter(TeacherExtraGroup.group_id == group.id)
            .first()
        )
        if existing_link:
            return {"status": "already_exists"}

        link = TeacherExtraGroup(
            teacher_id=current_user.teacher_id,
            group_id=group.id,
            source="manual_department_access",
        )
        db.add(link)
        db.commit()

        return {"status": "success"}
    finally:
        db.close()

@app.post("/users/me/select-department")
def select_department_for_me(token: str = Query(...), department_id: int = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can select department")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

        user.department_id = department.id
        db.commit()

        return {
            "status": "success",
            "department": {
                "id": department.id,
                "uuid": department.uuid,
                "abbr": department.abbr,
                "name": department.name,
            },
        }
    finally:
        db.close()

@app.get("/users/me/assignments")
def get_my_assignments(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access assignments")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        teacher = db.query(Teacher).filter(Teacher.id == current_user.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Linked teacher not found")

        return {
            "teacher": {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
                "last_name": teacher.last_name,
                "first_name": teacher.first_name,
                "middle_name": teacher.middle_name,
            },
            "assignments": build_teacher_assignments(db, teacher.id),
            "extra_groups": build_teacher_extra_groups(db, teacher.id),
        }
    finally:
        db.close()


@app.post("/users/me/consultation-requests")
def create_my_consultation_request(
    token: str = Query(...),
    group_ids: str = Query(...),  # например "12,15,18"
    discipline_id: int | None = Query(default=None),
    consultations_count: int = Query(...),
    preferred_audience: str | None = Query(default=None),
    avoid_day_without_classes: bool = Query(default=False),
    avoid_first_pair: bool = Query(default=False),
    avoid_last_pair: bool = Query(default=False),
    preferred_day: int | None = Query(default=None),
    excluded_day: int | None = Query(default=None),
    week_preference: str = Query(default="both"),
    blocked_slots: str = Query(default=""),
):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can create consultation requests")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="Teacher user must choose department first")

    if consultations_count <= 0:
        raise HTTPException(status_code=400, detail="consultations_count must be greater than 0")

    if preferred_day is not None and preferred_day not in {1, 2, 3, 4, 5, 6}:
        raise HTTPException(status_code=400, detail="preferred_day must be between 1 and 6")

    if excluded_day is not None and excluded_day not in {1, 2, 3, 4, 5, 6}:
        raise HTTPException(status_code=400, detail="excluded_day must be between 1 and 6")

    if preferred_day is not None and excluded_day is not None and preferred_day == excluded_day:
        raise HTTPException(status_code=400, detail="preferred_day and excluded_day cannot be the same")

    if week_preference not in {"both", "num", "den"}:
        raise HTTPException(
            status_code=400,
            detail="week_preference must be one of: both, num, den",
        )

    raw_group_ids = [item.strip() for item in group_ids.split(",") if item.strip()]
    if not raw_group_ids:
        raise HTTPException(status_code=400, detail="At least one group_id is required")

    try:
        parsed_group_ids = sorted({int(item) for item in raw_group_ids})
    except ValueError:
        raise HTTPException(status_code=400, detail="group_ids must contain integers only")

    db = SessionLocal()
    try:
        assignment_group_ids = {
            group_id
            for (group_id,) in db.query(TeacherAssignment.group_id)
            .filter(TeacherAssignment.teacher_id == current_user.teacher_id)
            .distinct()
            .all()
        }

        extra_group_ids = {
            group_id
            for (group_id,) in db.query(TeacherExtraGroup.group_id)
            .filter(TeacherExtraGroup.teacher_id == current_user.teacher_id)
            .distinct()
            .all()
        }

        accessible_group_ids = assignment_group_ids | extra_group_ids

        for parsed_group_id in parsed_group_ids:
            if parsed_group_id not in accessible_group_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"This teacher has no access to group_id={parsed_group_id}",
                )

        # Если указана дисциплина, она должна быть дисциплиной преподавателя где-либо
        if discipline_id is not None:
            discipline_allowed = (
                db.query(TeacherAssignment)
                .filter(TeacherAssignment.teacher_id == current_user.teacher_id)
                .filter(TeacherAssignment.discipline_id == discipline_id)
                .first()
            )
            if not discipline_allowed:
                raise HTTPException(
                    status_code=400,
                    detail="discipline_id must belong to one of teacher's existing assignments",
                )

        request = ConsultationRequest(
            teacher_id=current_user.teacher_id,
            user_id=current_user.id,
            department_id=current_user.department_id,
            discipline_id=discipline_id,
            consultations_count=consultations_count,
            preferred_audience=preferred_audience.strip() if preferred_audience else None,
            avoid_day_without_classes=avoid_day_without_classes,
            avoid_first_pair=avoid_first_pair,
            avoid_last_pair=avoid_last_pair,
            preferred_day=preferred_day,
            excluded_day=excluded_day,
            week_preference=week_preference,
            status="ready_for_generation",
        )
        db.add(request)
        db.flush()

        for parsed_group_id in parsed_group_ids:
            request_group = ConsultationRequestGroup(
                request_id=request.id,
                group_id=parsed_group_id,
            )
            db.add(request_group)

        if blocked_slots.strip():
            raw_items = [item.strip() for item in blocked_slots.split(",") if item.strip()]
            for raw_item in raw_items:
                try:
                    day_str, pair_str, week_type = raw_item.split(":")
                    day = int(day_str)
                    pair_number = int(pair_str)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid blocked slot format: {raw_item}. Use day:pair:weektype",
                    )

                if day not in {1, 2, 3, 4, 5, 6}:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid day in blocked slot: {raw_item}",
                    )

                if pair_number not in {1, 2, 3, 4, 5, 6, 7}:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid pair_number in blocked slot: {raw_item}",
                    )

                if week_type not in {"both", "num", "den"}:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid week_type in blocked slot: {raw_item}",
                    )

                blocked_slot = ConsultationRequestBlockedSlot(
                    request_id=request.id,
                    day=day,
                    pair_number=pair_number,
                    week_type=week_type,
                )
                db.add(blocked_slot)

        db.commit()
        db.refresh(request)

        return {
            "status": "success",
            "request_id": request.id,
        }
    finally:
        db.close()


@app.get("/users/me/consultation-requests")
def get_my_consultation_requests(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access consultation requests")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .order_by(ConsultationRequest.id.desc())
            .all()
        )

        return [build_request_details(db, request) for request in requests]
    finally:
        db.close()


@app.get("/users/me/consultation-requests/{request_id}")
def get_my_consultation_request_details(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access consultation requests")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        return build_request_details(db, request)
    finally:
        db.close()

@app.get("/users/me/manual-busy-slots")
def get_my_manual_busy_slots(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access manual busy slots")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        slots = (
            db.query(TeacherManualBusySlot)
            .filter(TeacherManualBusySlot.teacher_id == current_user.teacher_id)
            .order_by(
                TeacherManualBusySlot.day,
                TeacherManualBusySlot.pair_number,
                TeacherManualBusySlot.week_type,
            )
            .all()
        )

        return [
            {
                "id": slot.id,
                "day": slot.day,
                "day_label": DAY_LABELS.get(slot.day, str(slot.day)),
                "pair_number": slot.pair_number,
                "week_type": slot.week_type,
                "week_type_label": get_week_type_label(slot.week_type),
                "title": slot.title,
                "comment": slot.comment,
            }
            for slot in slots
        ]
    finally:
        db.close()

@app.post("/users/me/manual-busy-slots")
def create_my_manual_busy_slot(
    token: str = Query(...),
    day: int = Query(...),
    pair_number: int = Query(...),
    week_type: str = Query(...),
    title: str = Query(default="Лабораторная"),
    comment: str | None = Query(default=None),
):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can create manual busy slots")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    if day not in {1, 2, 3, 4, 5, 6}:
        raise HTTPException(status_code=400, detail="day must be between 1 and 6")

    if pair_number not in {1, 2, 3, 4, 5, 6, 7}:
        raise HTTPException(status_code=400, detail="pair_number must be between 1 and 7")

    if week_type not in {"both", "num", "den"}:
        raise HTTPException(status_code=400, detail="week_type must be one of: both, num, den")

    db = SessionLocal()
    try:
        slot = TeacherManualBusySlot(
            teacher_id=current_user.teacher_id,
            day=day,
            pair_number=pair_number,
            week_type=week_type,
            title=title.strip() if title else "Лабораторная",
            comment=comment.strip() if comment else None,
        )
        db.add(slot)
        db.commit()
        db.refresh(slot)

        return {
            "status": "success",
            "slot_id": slot.id,
        }
    finally:
        db.close()

@app.delete("/users/me/manual-busy-slots/{slot_id}")
def delete_my_manual_busy_slot(slot_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can delete manual busy slots")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        slot = (
            db.query(TeacherManualBusySlot)
            .filter(TeacherManualBusySlot.id == slot_id)
            .filter(TeacherManualBusySlot.teacher_id == current_user.teacher_id)
            .first()
        )
        if not slot:
            raise HTTPException(status_code=404, detail="Manual busy slot not found")

        db.delete(slot)
        db.commit()

        return {"status": "success"}
    finally:
        db.close()

@app.delete("/users/me/consultation-requests/{request_id}")
def delete_my_consultation_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can delete requests")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if request.status == "approved":
            raise HTTPException(status_code=400, detail="Approved request cannot be deleted")

        variant_ids = [
            variant.id
            for variant in db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.request_id == request.id)
            .all()
        ]

        if variant_ids:
            db.query(ConsultationVariantSlot).filter(
                ConsultationVariantSlot.variant_id.in_(variant_ids)
            ).delete(synchronize_session=False)

        db.query(ConsultationRequestVariant).filter(
            ConsultationRequestVariant.request_id == request.id
        ).delete(synchronize_session=False)

        db.query(ConsultationRequestBlockedSlot).filter(
            ConsultationRequestBlockedSlot.request_id == request.id
        ).delete(synchronize_session=False)

        db.query(ConsultationRequestGroup).filter(
            ConsultationRequestGroup.request_id == request.id
        ).delete(synchronize_session=False)

        db.query(TeacherGenerationRunRequest).filter(
            TeacherGenerationRunRequest.request_id == request.id
        ).delete(synchronize_session=False)

        db.delete(request)
        db.commit()

        return {"status": "success", "request_id": request_id}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@app.post("/users/me/consultation-requests/{request_id}/generate-variants")
def generate_variants_for_my_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can generate variants")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if request.status in {"approved", "rejected"}:
            raise HTTPException(
                status_code=400,
                detail="Request is already finalized and cannot be changed",
            )

        old_variants = (
            db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.request_id == request.id)
            .all()
        )

        old_variant_ids = [variant.id for variant in old_variants]
        if old_variant_ids:
            db.query(ConsultationVariantSlot).filter(
                ConsultationVariantSlot.variant_id.in_(old_variant_ids)
            ).delete(synchronize_session=False)

        db.query(ConsultationRequestVariant).filter(
            ConsultationRequestVariant.request_id == request.id
        ).delete(synchronize_session=False)

        generated_variants = generate_request_variants_via_asp(
            db=db,
            request_id=request.id,
            max_variants=3,
        )

        if not generated_variants:
            raise HTTPException(
                status_code=400,
                detail="Не удалось построить ни одного допустимого варианта по заданным ограничениям",
            )

        for variant_data in generated_variants:
            variant = ConsultationRequestVariant(
                request_id=request.id,
                variant_number=variant_data.variant_number,
                status="generated",
                score=None,
                comment=variant_data.comment,
            )
            db.add(variant)
            db.flush()

            for slot_data in variant_data.slots:
                slot = ConsultationVariantSlot(
                    variant_id=variant.id,
                    day=slot_data["day"],
                    pair_number=slot_data["pair_number"],
                    week_type=slot_data["week_type"],
                )
                db.add(slot)

        request.status = "variants_generated"
        request.selected_variant_id = None

        db.commit()

        return {
            "status": "success",
            "request_id": request.id,
            "variants_generated": len(generated_variants),
        }
    finally:
        db.close()


@app.post("/users/me/consultation-requests/{request_id}/select-variant/{variant_id}")
def select_variant_for_my_request(request_id: int, variant_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can select variant")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if request.status in {"approved", "rejected"}:
            raise HTTPException(
                status_code=400,
                detail="Request is already finalized and cannot be changed",
            )

        variant = (
            db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.id == variant_id)
            .filter(ConsultationRequestVariant.request_id == request.id)
            .first()
        )
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        all_variants = (
            db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.request_id == request.id)
            .all()
        )

        for item in all_variants:
            item.status = "discarded"

        variant.status = "selected"
        request.selected_variant_id = variant.id
        request.status = "selected_by_teacher"

        db.commit()

        return {
            "status": "success",
            "request_id": request.id,
            "selected_variant_id": variant.id,
        }
    finally:
        db.close()

@app.get("/users/me/consultation-requests/{request_id}/variants/{variant_id}/preview")
def get_variant_preview_for_my_request(request_id: int, variant_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can view variant preview")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        variant = (
            db.query(ConsultationRequestVariant)
            .filter(ConsultationRequestVariant.id == variant_id)
            .filter(ConsultationRequestVariant.request_id == request.id)
            .first()
        )
        if not variant:
            raise HTTPException(status_code=404, detail="Variant not found")

        teacher = db.query(Teacher).filter(Teacher.id == current_user.teacher_id).first()
        groups = build_request_groups(db, request.id)
        discipline = (
            db.query(Discipline).filter(Discipline.id == request.discipline_id).first()
            if request.discipline_id is not None
            else None
        )

        teacher_schedule_rows = (
            db.query(ScheduleSlot)
            .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
            .filter(ScheduleSlotTeacher.teacher_id == current_user.teacher_id)
            .all()
        )

        manual_busy_slots = (
            db.query(TeacherManualBusySlot)
            .filter(TeacherManualBusySlot.teacher_id == current_user.teacher_id)
            .all()
        )

        variant_slots = (
            db.query(ConsultationVariantSlot)
            .filter(ConsultationVariantSlot.variant_id == variant.id)
            .order_by(ConsultationVariantSlot.day, ConsultationVariantSlot.pair_number)
            .all()
        )

        discipline_ids = {
            slot.discipline_id
            for slot in teacher_schedule_rows
            if slot.discipline_id is not None
        }

        disciplines = (
            db.query(Discipline)
            .filter(Discipline.id.in_(discipline_ids))
            .all()
            if discipline_ids
            else []
        )
        discipline_map = {item.id: item for item in disciplines}

        unique_teacher_schedule_slots = []
        seen_schedule_keys = set()

        for schedule_slot in teacher_schedule_rows:
            slot_discipline = discipline_map.get(schedule_slot.discipline_id)

            dedup_key = (
                schedule_slot.day,
                schedule_slot.pair_number,
                schedule_slot.week_type,
                schedule_slot.discipline_id,
                schedule_slot.act_type,
                schedule_slot.start_time,
                schedule_slot.end_time,
            )

            if dedup_key in seen_schedule_keys:
                continue

            seen_schedule_keys.add(dedup_key)

            unique_teacher_schedule_slots.append(
                {
                    "day": schedule_slot.day,
                    "pair_number": schedule_slot.pair_number,
                    "week_type": schedule_slot.week_type,
                    "week_type_label": get_week_type_label(schedule_slot.week_type),
                    "act_type": schedule_slot.act_type,
                    "discipline_name": slot_discipline.full_name if slot_discipline else "Занятие",
                }
            )

        unique_manual_busy_slots = []
        seen_manual_keys = set()

        for slot in manual_busy_slots:
            key = (slot.day, slot.pair_number, slot.week_type, slot.title, slot.comment)
            if key in seen_manual_keys:
                continue
            seen_manual_keys.add(key)

            unique_manual_busy_slots.append(
                {
                    "day": slot.day,
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "week_type_label": get_week_type_label(slot.week_type),
                    "title": slot.title,
                    "comment": slot.comment,
                }
            )

        unique_variant_slots = []
        seen_variant_keys = set()

        for variant_slot in variant_slots:
            dedup_key = (
                variant_slot.day,
                variant_slot.pair_number,
                variant_slot.week_type,
            )

            if dedup_key in seen_variant_keys:
                continue

            seen_variant_keys.add(dedup_key)
            unique_variant_slots.append(variant_slot)

        grid = []
        for day in range(1, 7):
            day_rows = []
            for pair_number in range(1, 8):
                items = []

                for schedule_slot in unique_teacher_schedule_slots:
                    if schedule_slot["day"] == day and schedule_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "existing_class",
                                "label": schedule_slot["discipline_name"],
                                "week_type": schedule_slot["week_type"],
                                "week_type_label": schedule_slot["week_type_label"],
                                "act_type": schedule_slot["act_type"],
                                "is_preference_violation": False,
                                "violation_reasons": [],
                            }
                        )

                for busy_slot in unique_manual_busy_slots:
                    if busy_slot["day"] == day and busy_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "manual_busy",
                                "label": busy_slot["title"],
                                "week_type": busy_slot["week_type"],
                                "week_type_label": busy_slot["week_type_label"],
                                "act_type": "manual_busy",
                                "is_preference_violation": False,
                                "violation_reasons": [],
                            }
                        )

                for variant_slot in unique_variant_slots:
                    if variant_slot.day == day and variant_slot.pair_number == pair_number:
                        violation_reasons = build_variant_slot_violation_reasons(
                            request=request,
                            slot_day=variant_slot.day,
                            slot_pair=variant_slot.pair_number,
                        )

                        items.append(
                            {
                                "type": "consultation",
                                "label": f"Консультация: {', '.join([g['name'] for g in groups]) if groups else 'Группа'}",
                                "week_type": variant_slot.week_type,
                                "week_type_label": get_week_type_label(variant_slot.week_type),
                                "act_type": "consultation",
                                "is_preference_violation": len(violation_reasons) > 0,
                                "violation_reasons": violation_reasons,
                            }
                        )

                day_rows.append(
                    {
                        "day": day,
                        "day_label": DAY_LABELS[day],
                        "pair_number": pair_number,
                        "items": items,
                    }
                )

            grid.append(
                {
                    "day": day,
                    "day_label": DAY_LABELS[day],
                    "rows": day_rows,
                }
            )

        all_variant_slots_summary = []
        total_violations = 0

        for variant_slot in unique_variant_slots:
            violation_reasons = build_variant_slot_violation_reasons(
                request=request,
                slot_day=variant_slot.day,
                slot_pair=variant_slot.pair_number,
            )
            total_violations += len(violation_reasons)

            all_variant_slots_summary.append(
                {
                    "day": variant_slot.day,
                    "day_label": DAY_LABELS[variant_slot.day],
                    "pair_number": variant_slot.pair_number,
                    "week_type": variant_slot.week_type,
                    "week_type_label": get_week_type_label(variant_slot.week_type),
                    "violation_reasons": violation_reasons,
                }
            )

        return {
            "request": {
                "id": request.id,
                "status": request.status,
                "consultations_count": request.consultations_count,
                "preferred_audience": request.preferred_audience,
                "avoid_day_without_classes": request.avoid_day_without_classes,
                "avoid_first_pair": request.avoid_first_pair,
                "avoid_last_pair": request.avoid_last_pair,
                "preferred_day": request.preferred_day,
                "excluded_day": request.excluded_day,
                "week_preference": request.week_preference,
                "week_preference_label": WEEK_PREFERENCE_LABELS.get(
                    request.week_preference, request.week_preference
                ),
                "groups": groups,
                "discipline": {
                    "id": discipline.id,
                    "full_name": discipline.full_name,
                    "abbr": discipline.abbr,
                } if discipline else None,
            },
            "teacher": {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
            } if teacher else None,
            "variant": {
                "id": variant.id,
                "variant_number": variant.variant_number,
                "status": variant.status,
                "comment": variant.comment,
            },
            "summary": {
                "total_consultations": len(unique_variant_slots),
                "total_preference_violations": total_violations,
                "slots": all_variant_slots_summary,
            },
            "grid": grid,
        }
    finally:
        db.close()

@app.get("/users/me/final-schedule")
def get_my_final_schedule(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "teacher":
        raise HTTPException(status_code=403, detail="Only teacher can access final schedule")

    if not current_user.teacher_id:
        raise HTTPException(status_code=400, detail="User is not linked to teacher")

    db = SessionLocal()
    try:
        teacher = db.query(Teacher).filter(Teacher.id == current_user.teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

        teacher_schedule_rows = (
            db.query(ScheduleSlot)
            .join(ScheduleSlotTeacher, ScheduleSlotTeacher.slot_id == ScheduleSlot.id)
            .filter(ScheduleSlotTeacher.teacher_id == current_user.teacher_id)
            .all()
        )

        manual_busy_slots = (
            db.query(TeacherManualBusySlot)
            .filter(TeacherManualBusySlot.teacher_id == current_user.teacher_id)
            .all()
        )

        approved_requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.teacher_id == current_user.teacher_id)
            .filter(ConsultationRequest.status == "approved")
            .all()
        )

        discipline_ids = {
            slot.discipline_id
            for slot in teacher_schedule_rows
            if slot.discipline_id is not None
        }

        for request in approved_requests:
            if request.discipline_id is not None:
                discipline_ids.add(request.discipline_id)

        disciplines = (
            db.query(Discipline)
            .filter(Discipline.id.in_(discipline_ids))
            .all()
            if discipline_ids
            else []
        )
        discipline_map = {discipline.id: discipline for discipline in disciplines}

        unique_teacher_schedule_slots = []
        seen_schedule_keys = set()

        for schedule_slot in teacher_schedule_rows:
            slot_discipline = discipline_map.get(schedule_slot.discipline_id)

            dedup_key = (
                schedule_slot.day,
                schedule_slot.pair_number,
                schedule_slot.week_type,
                schedule_slot.discipline_id,
                schedule_slot.act_type,
                schedule_slot.start_time,
                schedule_slot.end_time,
            )

            if dedup_key in seen_schedule_keys:
                continue

            seen_schedule_keys.add(dedup_key)

            unique_teacher_schedule_slots.append(
                {
                    "day": schedule_slot.day,
                    "pair_number": schedule_slot.pair_number,
                    "week_type": schedule_slot.week_type,
                    "week_type_label": get_week_type_label(schedule_slot.week_type),
                    "act_type": schedule_slot.act_type,
                    "discipline_name": slot_discipline.full_name if slot_discipline else "Занятие",
                }
            )

        unique_manual_busy_slots = []
        seen_manual_keys = set()

        for slot in manual_busy_slots:
            key = (slot.day, slot.pair_number, slot.week_type, slot.title, slot.comment)
            if key in seen_manual_keys:
                continue

            seen_manual_keys.add(key)
            unique_manual_busy_slots.append(
                {
                    "day": slot.day,
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "week_type_label": get_week_type_label(slot.week_type),
                    "title": slot.title,
                    "comment": slot.comment,
                }
            )

        approved_consultations = []
        seen_consultation_keys = set()

        for request in approved_requests:
            groups = build_request_groups(db, request.id)
            selected_slots = build_selected_batch_slots_for_request(db, request.id)
            discipline = discipline_map.get(request.discipline_id)

            group_names = [group["name"] for group in groups]
            groups_label = ", ".join(group_names) if group_names else "Группа"

            for slot in selected_slots:
                consultation_key = (
                    request.id,
                    slot["day"],
                    slot["pair_number"],
                    slot["week_type"],
                    groups_label,
                    discipline.full_name if discipline else None,
                )

                if consultation_key in seen_consultation_keys:
                    continue

                seen_consultation_keys.add(consultation_key)

                approved_consultations.append(
                    {
                        "request_id": request.id,
                        "day": slot["day"],
                        "day_label": slot["day_label"],
                        "pair_number": slot["pair_number"],
                        "week_type": slot["week_type"],
                        "week_type_label": slot["week_type_label"],
                        "groups": groups,
                        "groups_label": groups_label,
                        "discipline_name": discipline.full_name if discipline else "Консультация",
                        "preferred_audience": request.preferred_audience,
                    }
                )

        grid = []
        for day in range(1, 7):
            day_rows = []
            for pair_number in range(1, 8):
                items = []

                for schedule_slot in unique_teacher_schedule_slots:
                    if schedule_slot["day"] == day and schedule_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "existing_class",
                                "label": schedule_slot["discipline_name"],
                                "week_type": schedule_slot["week_type"],
                                "week_type_label": schedule_slot["week_type_label"],
                                "act_type": schedule_slot["act_type"],
                            }
                        )

                for busy_slot in unique_manual_busy_slots:
                    if busy_slot["day"] == day and busy_slot["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "manual_busy",
                                "label": busy_slot["title"],
                                "week_type": busy_slot["week_type"],
                                "week_type_label": busy_slot["week_type_label"],
                                "act_type": "manual_busy",
                                "comment": busy_slot["comment"],
                            }
                        )

                for consultation in approved_consultations:
                    if consultation["day"] == day and consultation["pair_number"] == pair_number:
                        items.append(
                            {
                                "type": "approved_consultation",
                                "label": f"Консультация: {consultation['groups_label']}",
                                "week_type": consultation["week_type"],
                                "week_type_label": consultation["week_type_label"],
                                "act_type": "consultation",
                                "discipline_name": consultation["discipline_name"],
                                "preferred_audience": consultation["preferred_audience"],
                            }
                        )

                day_rows.append(
                    {
                        "day": day,
                        "day_label": DAY_LABELS[day],
                        "pair_number": pair_number,
                        "items": items,
                    }
                )

            grid.append(
                {
                    "day": day,
                    "day_label": DAY_LABELS[day],
                    "rows": day_rows,
                }
            )

        return {
            "teacher": {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
            },
            "approved_consultations": approved_consultations,
            "manual_busy_slots": unique_manual_busy_slots,
            "grid": grid,
        }
    finally:
        db.close()

@app.get("/users/me/department-teachers")
def get_my_department_teachers(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department_responsible can access this endpoint")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        department = db.query(Department).filter(Department.id == current_user.department_id).first()
        if not department:
            raise HTTPException(status_code=404, detail="Linked department not found")

        links = (
            db.query(DepartmentTeacher)
            .filter(DepartmentTeacher.department_id == department.id)
            .all()
        )

        teachers_result = []
        for link in links:
            teacher = db.query(Teacher).filter(Teacher.id == link.teacher_id).first()
            if not teacher:
                continue

            teachers_result.append(
                {
                    "teacher": {
                        "id": teacher.id,
                        "uuid": teacher.uuid,
                        "full_name": teacher.full_name,
                    },
                    "assignments": build_teacher_assignments(db, teacher.id),
                }
            )

        return {
            "department": {
                "id": department.id,
                "uuid": department.uuid,
                "abbr": department.abbr,
                "name": department.name,
            },
            "teachers": teachers_result,
        }
    finally:
        db.close()

@app.get("/users/me/department-consultation-requests")
def get_my_department_consultation_requests(token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(
            status_code=403,
            detail="Only department_responsible can access this endpoint",
        )

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        requests = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .filter(ConsultationRequest.status.in_(["selected_by_teacher", "submitted_to_department", "approved", "rejected"]))
            .order_by(ConsultationRequest.id.desc())
            .all()
        )

        result = []
        for request in requests:
            teacher = db.query(Teacher).filter(Teacher.id == request.teacher_id).first()
            request_data = build_request_details(db, request)

            result.append(
                {
                    "teacher": {
                        "id": teacher.id,
                        "uuid": teacher.uuid,
                        "full_name": teacher.full_name,
                    } if teacher else None,
                    "request": request_data,
                }
            )

        return result
    finally:
        db.close()


@app.post("/users/me/department-consultation-requests/{request_id}/approve")
def approve_department_consultation_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(
            status_code=403,
            detail="Only department_responsible can approve requests",
        )

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        if not request.selected_variant_id:
            raise HTTPException(status_code=400, detail="Teacher has not selected a variant yet")

        request.status = "approved"
        db.commit()

        return {"status": "success", "request_id": request.id}
    finally:
        db.close()


@app.post("/users/me/department-consultation-requests/{request_id}/reject")
def reject_department_consultation_request(request_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(
            status_code=403,
            detail="Only department_responsible can reject requests",
        )

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        request = (
            db.query(ConsultationRequest)
            .filter(ConsultationRequest.id == request_id)
            .filter(ConsultationRequest.department_id == current_user.department_id)
            .first()
        )
        if not request:
            raise HTTPException(status_code=404, detail="Request not found")

        request.status = "rejected"
        db.commit()

        return {"status": "success", "request_id": request.id}
    finally:
        db.close()

@app.get("/users/me/available-teachers")
def get_available_teachers_for_department(token: str = Query(...), limit: int = Query(default=200, le=1000)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department_responsible can access this endpoint")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        linked_teacher_ids = {
            teacher_id
            for (teacher_id,) in db.query(DepartmentTeacher.teacher_id)
            .filter(DepartmentTeacher.department_id == current_user.department_id)
            .all()
        }

        teachers = db.query(Teacher).order_by(Teacher.full_name).limit(limit).all()

        result = []
        for teacher in teachers:
            result.append(
                {
                    "id": teacher.id,
                    "uuid": teacher.uuid,
                    "full_name": teacher.full_name,
                    "already_linked": teacher.id in linked_teacher_ids,
                }
            )

        return result
    finally:
        db.close()


@app.post("/users/me/add-teacher/{teacher_id}")
def add_teacher_to_my_department(teacher_id: int, token: str = Query(...)):
    current_user = get_current_user(token)

    if current_user.role != "department_responsible":
        raise HTTPException(status_code=403, detail="Only department_responsible can add teachers")

    if not current_user.department_id:
        raise HTTPException(status_code=400, detail="User is not linked to department")

    db = SessionLocal()
    try:
        department = db.query(Department).filter(Department.id == current_user.department_id).first()
        if not department:
            raise HTTPException(status_code=404, detail="Linked department not found")

        teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

        existing_link = (
            db.query(DepartmentTeacher)
            .filter(DepartmentTeacher.department_id == department.id)
            .filter(DepartmentTeacher.teacher_id == teacher.id)
            .first()
        )
        if existing_link:
            return {"status": "already_exists"}

        link = DepartmentTeacher(
            department_id=department.id,
            teacher_id=teacher.id,
        )
        db.add(link)
        db.commit()

        return {"status": "success"}
    finally:
        db.close()


@app.post("/import/structure")
def run_structure_import():
    db = SessionLocal()
    try:
        result = import_structure(db)
        return result
    finally:
        db.close()


@app.post("/import/group-schedule/{group_uuid}")
def run_group_schedule_import(group_uuid: str):
    db = SessionLocal()
    try:
        result = import_group_schedule(db, group_uuid)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        db.close()


@app.get("/departments")
def get_departments(limit: int = Query(default=20, le=500)):
    db = SessionLocal()
    try:
        departments = db.query(Department).order_by(Department.abbr).limit(limit).all()
        return [
            {
                "id": department.id,
                "uuid": department.uuid,
                "abbr": department.abbr,
                "name": department.name,
                "faculty_abbr": department.faculty_abbr,
                "faculty_name": department.faculty_name,
            }
            for department in departments
        ]
    finally:
        db.close()


@app.get("/groups")
def get_groups(limit: int = Query(default=20, le=1000)):
    db = SessionLocal()
    try:
        groups = db.query(Group).order_by(Group.name).limit(limit).all()
        return [
            {
                "id": group.id,
                "uuid": group.uuid,
                "name": group.name,
                "course": group.course,
                "semester": group.semester,
                "department_id": group.department_id,
            }
            for group in groups
        ]
    finally:
        db.close()


@app.get("/teachers")
def get_teachers(limit: int = Query(default=50, le=500)):
    db = SessionLocal()
    try:
        teachers = db.query(Teacher).order_by(Teacher.full_name).limit(limit).all()
        return [
            {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
                "last_name": teacher.last_name,
                "first_name": teacher.first_name,
                "middle_name": teacher.middle_name,
            }
            for teacher in teachers
        ]
    finally:
        db.close()


@app.get("/disciplines")
def get_disciplines(limit: int = Query(default=50, le=500)):
    db = SessionLocal()
    try:
        disciplines = db.query(Discipline).order_by(Discipline.full_name).limit(limit).all()
        return [
            {
                "id": discipline.id,
                "full_name": discipline.full_name,
                "short_name": discipline.short_name,
                "abbr": discipline.abbr,
            }
            for discipline in disciplines
        ]
    finally:
        db.close()


@app.get("/groups/{group_uuid}/schedule-slots")
def get_group_schedule_slots(group_uuid: str):
    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.uuid == group_uuid).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        slots = (
            db.query(ScheduleSlot)
            .filter(ScheduleSlot.group_id == group.id)
            .order_by(ScheduleSlot.day, ScheduleSlot.pair_number)
            .all()
        )

        result = []

        for slot in slots:
            teacher_links = (
                db.query(ScheduleSlotTeacher, Teacher)
                .join(Teacher, ScheduleSlotTeacher.teacher_id == Teacher.id)
                .filter(ScheduleSlotTeacher.slot_id == slot.id)
                .all()
            )

            teachers = [
                {
                    "id": teacher.id,
                    "uuid": teacher.uuid,
                    "full_name": teacher.full_name,
                }
                for _, teacher in teacher_links
            ]

            discipline = None
            if slot.discipline_id:
                discipline_obj = db.query(Discipline).filter(Discipline.id == slot.discipline_id).first()
                if discipline_obj:
                    discipline = {
                        "id": discipline_obj.id,
                        "full_name": discipline_obj.full_name,
                        "abbr": discipline_obj.abbr,
                        "short_name": discipline_obj.short_name,
                    }

            result.append(
                {
                    "slot_id": slot.id,
                    "day": slot.day,
                    "pair_number": slot.pair_number,
                    "week_type": slot.week_type,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "act_type": slot.act_type,
                    "is_vuc": slot.is_vuc,
                    "raw_teacher_count": slot.raw_teacher_count,
                    "discipline": discipline,
                    "teachers": teachers,
                }
            )

        return {
            "group": {
                "id": group.id,
                "uuid": group.uuid,
                "name": group.name,
            },
            "slots": result,
        }
    finally:
        db.close()


@app.get("/teacher-assignments")
def get_teacher_assignments(limit: int = Query(default=100, le=1000)):
    db = SessionLocal()
    try:
        assignments = db.query(TeacherAssignment).limit(limit).all()

        result = []
        for assignment in assignments:
            teacher = db.query(Teacher).filter(Teacher.id == assignment.teacher_id).first()
            group = db.query(Group).filter(Group.id == assignment.group_id).first()
            discipline = db.query(Discipline).filter(Discipline.id == assignment.discipline_id).first()

            result.append(
                {
                    "id": assignment.id,
                    "teacher": {
                        "id": teacher.id,
                        "uuid": teacher.uuid,
                        "full_name": teacher.full_name,
                    } if teacher else None,
                    "group": {
                        "id": group.id,
                        "uuid": group.uuid,
                        "name": group.name,
                    } if group else None,
                    "discipline": {
                        "id": discipline.id,
                        "full_name": discipline.full_name,
                        "abbr": discipline.abbr,
                    } if discipline else None,
                    "act_type": assignment.act_type,
                    "source": assignment.source,
                }
            )

        return result
    finally:
        db.close()


@app.get("/teachers/{teacher_uuid}/assignments")
def get_assignments_for_teacher(teacher_uuid: str):
    db = SessionLocal()
    try:
        teacher = db.query(Teacher).filter(Teacher.uuid == teacher_uuid).first()
        if not teacher:
            raise HTTPException(status_code=404, detail="Teacher not found")

        return {
            "teacher": {
                "id": teacher.id,
                "uuid": teacher.uuid,
                "full_name": teacher.full_name,
                "last_name": teacher.last_name,
                "first_name": teacher.first_name,
                "middle_name": teacher.middle_name,
            },
            "assignments": build_teacher_assignments(db, teacher.id),
        }
    finally:
        db.close()