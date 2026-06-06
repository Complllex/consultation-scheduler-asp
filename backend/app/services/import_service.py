import httpx
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.discipline import Discipline
from app.models.group import Group
from app.models.schedule_slot import ScheduleSlot
from app.models.schedule_slot_teacher import ScheduleSlotTeacher
from app.models.teacher import Teacher
from app.models.teacher_assignment import TeacherAssignment
from app.services.schedule_parser import parse_schedule_entries
from app.services.structure_parser import walk_structure_tree

STRUCTURE_URL = "https://lks.bmstu.ru/lks-back/api/v1/structure"
GROUP_SCHEDULE_URL_TEMPLATE = "https://lks.bmstu.ru/lks-back/api/v1/schedules/groups/{group_uuid}/public"


def upsert_department(db: Session, department_data: dict) -> Department:
    department = (
        db.query(Department)
        .filter(Department.uuid == department_data["uuid"])
        .first()
    )

    if department:
        department.name = department_data["name"]
        department.abbr = department_data["abbr"]
        department.faculty_name = department_data.get("faculty_name")
        department.faculty_abbr = department_data.get("faculty_abbr")
    else:
        department = Department(
            uuid=department_data["uuid"],
            name=department_data["name"],
            abbr=department_data["abbr"],
            faculty_name=department_data.get("faculty_name"),
            faculty_abbr=department_data.get("faculty_abbr"),
        )
        db.add(department)
        db.flush()

    return department


def upsert_group(db: Session, group_data: dict, department_id: int | None) -> Group:
    group = db.query(Group).filter(Group.uuid == group_data["uuid"]).first()

    if group:
        group.name = group_data["name"]
        group.course = group_data.get("course")
        group.semester = group_data.get("semester")
        group.department_id = department_id
    else:
        group = Group(
            uuid=group_data["uuid"],
            name=group_data["name"],
            course=group_data.get("course"),
            semester=group_data.get("semester"),
            department_id=department_id,
        )
        db.add(group)
        db.flush()

    return group


def upsert_teacher(db: Session, teacher_data: dict) -> Teacher:
    teacher = db.query(Teacher).filter(Teacher.uuid == teacher_data["uuid"]).first()

    if teacher:
        teacher.last_name = teacher_data["last_name"]
        teacher.first_name = teacher_data["first_name"]
        teacher.middle_name = teacher_data.get("middle_name")
        teacher.full_name = teacher_data["full_name"]
    else:
        teacher = Teacher(
            uuid=teacher_data["uuid"],
            last_name=teacher_data["last_name"],
            first_name=teacher_data["first_name"],
            middle_name=teacher_data.get("middle_name"),
            full_name=teacher_data["full_name"],
        )
        db.add(teacher)
        db.flush()

    return teacher


def upsert_discipline(db: Session, discipline_data: dict) -> Discipline:
    discipline = (
        db.query(Discipline)
        .filter(Discipline.full_name == discipline_data["full_name"])
        .filter(Discipline.abbr == discipline_data.get("abbr"))
        .first()
    )

    if discipline:
        discipline.short_name = discipline_data.get("short_name")
    else:
        discipline = Discipline(
            full_name=discipline_data["full_name"],
            short_name=discipline_data.get("short_name"),
            abbr=discipline_data.get("abbr"),
        )
        db.add(discipline)
        db.flush()

    return discipline


def ensure_teacher_assignment(
    db: Session,
    teacher_id: int,
    group_id: int,
    discipline_id: int,
    act_type: str | None,
) -> TeacherAssignment:
    assignment = (
        db.query(TeacherAssignment)
        .filter(TeacherAssignment.teacher_id == teacher_id)
        .filter(TeacherAssignment.group_id == group_id)
        .filter(TeacherAssignment.discipline_id == discipline_id)
        .filter(TeacherAssignment.act_type == act_type)
        .first()
    )

    if not assignment:
        assignment = TeacherAssignment(
            teacher_id=teacher_id,
            group_id=group_id,
            discipline_id=discipline_id,
            act_type=act_type,
            source="base_schedule",
        )
        db.add(assignment)
        db.flush()

    return assignment


def import_structure(db: Session) -> dict:
    response = httpx.get(STRUCTURE_URL, timeout=60.0)
    response.raise_for_status()

    payload = response.json()
    root_node = payload["data"]

    departments_data, groups_data = walk_structure_tree(root_node)

    department_uuid_to_id: dict[str, int] = {}

    for department_data in departments_data:
        department = upsert_department(db, department_data)
        if department.uuid:
            department_uuid_to_id[department.uuid] = department.id

    for group_data in groups_data:
        department_uuid = group_data.get("department_uuid")
        department_id = department_uuid_to_id.get(department_uuid) if department_uuid else None
        upsert_group(db, group_data, department_id)

    db.commit()

    return {
        "status": "success",
        "departments_count": len(departments_data),
        "groups_count": len(groups_data),
    }


def import_group_schedule(db: Session, group_uuid: str) -> dict:
    group = db.query(Group).filter(Group.uuid == group_uuid).first()
    if not group:
        raise ValueError("Group not found in database")

    url = GROUP_SCHEDULE_URL_TEMPLATE.format(group_uuid=group_uuid)
    response = httpx.get(url, timeout=60.0)
    response.raise_for_status()

    payload = response.json()
    schedule_data = payload["data"]["schedule"]

    parsed_entries = parse_schedule_entries(schedule_data)

    existing_slot_ids = [
        slot_id
        for (slot_id,) in db.query(ScheduleSlot.id)
        .filter(ScheduleSlot.group_id == group.id)
        .all()
    ]

    deleted_teacher_links = 0
    if existing_slot_ids:
        deleted_teacher_links = (
            db.query(ScheduleSlotTeacher)
            .filter(ScheduleSlotTeacher.slot_id.in_(existing_slot_ids))
            .delete(synchronize_session=False)
        )

    deleted_slots = (
        db.query(ScheduleSlot)
        .filter(ScheduleSlot.group_id == group.id)
        .delete(synchronize_session=False)
    )

    deleted_assignments = (
        db.query(TeacherAssignment)
        .filter(TeacherAssignment.group_id == group.id)
        .delete(synchronize_session=False)
    )

    created_slots_count = 0
    linked_teachers_count = 0
    created_assignments_count = 0

    for entry in parsed_entries:
        discipline_id = None
        if entry["discipline"] and entry["discipline"]["full_name"]:
            discipline = upsert_discipline(db, entry["discipline"])
            discipline_id = discipline.id

        slot = ScheduleSlot(
            group_id=group.id,
            day=entry["day"],
            pair_number=entry["pair_number"],
            week_type=entry["week_type"],
            discipline_id=discipline_id,
            act_type=entry["act_type"],
            start_time=entry["start_time"],
            end_time=entry["end_time"],
            source_type="base",
            is_vuc=entry["is_vuc"],
            raw_teacher_count=len(entry["teachers"]),
        )
        db.add(slot)
        db.flush()
        created_slots_count += 1

        for teacher_data in entry["teachers"]:
            teacher = upsert_teacher(db, teacher_data)

            slot_teacher = ScheduleSlotTeacher(
                slot_id=slot.id,
                teacher_id=teacher.id,
            )
            db.add(slot_teacher)
            linked_teachers_count += 1

            if discipline_id is not None:
                before_count = db.query(TeacherAssignment).count()
                ensure_teacher_assignment(
                    db=db,
                    teacher_id=teacher.id,
                    group_id=group.id,
                    discipline_id=discipline_id,
                    act_type=entry["act_type"],
                )
                after_count = db.query(TeacherAssignment).count()
                if after_count > before_count:
                    created_assignments_count += 1

    db.commit()

    return {
        "status": "success",
        "group_uuid": group_uuid,
        "group_name": group.name,
        "deleted_slots": deleted_slots,
        "deleted_teacher_links": deleted_teacher_links,
        "deleted_assignments": deleted_assignments,
        "created_slots": created_slots_count,
        "linked_teachers": linked_teachers_count,
        "created_assignments": created_assignments_count,
    }