import re

from app.core.database import SessionLocal
from app.core.security import get_password_hash

from app.models.user import User
from app.models.department import Department
from app.models.teacher import Teacher


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


def find_department(db, department_input: str):
    value = department_input.strip()
    if not value:
        return None

    department = db.query(Department).filter(Department.uuid == value).first()
    if department:
        return department

    department = db.query(Department).filter(Department.abbr == value).first()
    if department:
        return department

    return None


def main():
    db = SessionLocal()

    try:
        login = input("Login: ").strip()
        password = input("Password: ").strip()
        full_name = input("Full name: ").strip()
        role = input("Role (teacher / department_responsible / admin): ").strip()

        if role not in {"teacher", "department_responsible", "admin"}:
            print("Invalid role")
            return

        existing_user = db.query(User).filter(User.login == login).first()
        if existing_user:
            print("User with this login already exists")
            return

        teacher_id = None
        department_id = None
        resolved_full_name = full_name

        if role == "teacher":
            teacher = find_teacher_by_full_name(db, full_name)
            if not teacher:
                print("Teacher with this full name was not found.")
                print("First import schedules where this teacher appears.")
                return

            teacher_id = teacher.id
            resolved_full_name = teacher.full_name
            print(f"Teacher matched automatically: {teacher.full_name} (id={teacher.id})")

        elif role == "department_responsible":
            department_input = input("Department abbr or uuid: ").strip()
            department = find_department(db, department_input)
            if not department:
                print("Department not found")
                return

            department_id = department.id
            print(f"Department matched: {department.abbr} — {department.name} (id={department.id})")

        user = User(
            login=login,
            password_hash=get_password_hash(password),
            full_name=resolved_full_name,
            role=role,
            teacher_id=teacher_id,
            department_id=department_id,
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print("User created successfully:")
        print(f"  id={user.id}")
        print(f"  login={user.login}")
        print(f"  full_name={user.full_name}")
        print(f"  role={user.role}")
        print(f"  teacher_id={user.teacher_id}")
        print(f"  department_id={user.department_id}")

    finally:
        db.close()


if __name__ == "__main__":
    main()