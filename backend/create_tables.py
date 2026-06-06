from app.core.database import Base, engine
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
from app.models.teacher_extra_group import TeacherExtraGroup
from app.models.import_job import ImportJob
from app.models.consultation_request_group import ConsultationRequestGroup
from app.models.teacher_manual_busy_slot import TeacherManualBusySlot
from app.models.teacher_generation_run import TeacherGenerationRun
from app.models.teacher_generation_run_request import TeacherGenerationRunRequest
from app.models.teacher_generation_run_variant import TeacherGenerationRunVariant
from app.models.teacher_generation_run_variant_slot import TeacherGenerationRunVariantSlot

def main():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully")


if __name__ == "__main__":
    main()