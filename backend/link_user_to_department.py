from app.core.database import SessionLocal
from app.models.department import Department
from app.models.user import User
from app.models.department import Department
from app.models.teacher import Teacher

def main():
    db = SessionLocal()

    login = input("User login: ").strip()
    department_id_raw = input("Department ID: ").strip()

    if not department_id_raw.isdigit():
        print("Department ID must be a number")
        db.close()
        return

    department_id = int(department_id_raw)

    user = db.query(User).filter(User.login == login).first()
    if not user:
        print("User not found")
        db.close()
        return

    department = db.query(Department).filter(Department.id == department_id).first()
    if not department:
        print("Department not found")
        db.close()
        return

    user.department_id = department.id
    db.commit()
    db.close()

    print("User linked to department successfully")


if __name__ == "__main__":
    main()