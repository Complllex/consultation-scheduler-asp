from app.core.database import SessionLocal
from app.models.teacher import Teacher
from app.models.user import User
from app.models.department import Department

def main():
    db = SessionLocal()

    login = input("User login: ").strip()
    teacher_uuid = input("Teacher UUID: ").strip()

    user = db.query(User).filter(User.login == login).first()
    if not user:
        print("User not found")
        db.close()
        return

    teacher = db.query(Teacher).filter(Teacher.uuid == teacher_uuid).first()
    if not teacher:
        print("Teacher not found")
        db.close()
        return

    user.teacher_id = teacher.id
    db.commit()
    db.close()

    print("User linked to teacher successfully")


if __name__ == "__main__":
    main()