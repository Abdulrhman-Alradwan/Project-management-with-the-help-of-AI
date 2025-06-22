import asyncio
from datetime import timedelta, datetime, timezone, time
from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal
from .auth import get_current_user , check_project_permission
from fastapi import status, HTTPException, Path
from models import Epic, Project, SprintDuration, Sprint, Task, TaskStatus, TaskInfo

router = APIRouter(
    prefix='/sprint',
    tags=['sprint']
)



class CreateSprintRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    duration: SprintDuration



def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]
user_dependency = Annotated[dict , Depends(get_current_user)]


async def check_sprint_expiration(db: Session):
    while True:
        try:
            current_time = datetime.now(timezone.utc)

            # البحث عن الـ Sprints النشطة المنتهية
            expired_sprints = db.query(Sprint).filter(
                and_(
                    Sprint.is_active == True,
                    Sprint.end_date <= current_time
                )
            ).all()

            for sprint in expired_sprints:
                # تحديث حالة الـ Sprint
                sprint.is_active = False
                sprint.is_completed = True

                # جلب المهام غير المكتملة
                incomplete_tasks = db.query(Task).filter(
                    and_(
                        Task.sprint_id == sprint.id,
                        Task.status != TaskStatus.COMPLETE
                    )
                ).all()

                # إزالة المهام غير المكتملة من الـ Sprint
                for task in incomplete_tasks:
                    task.sprint_id = None

                db.commit()

        except Exception as e:
            # تسجيل الأخطاء (يمكنك استخدام logging هنا)
            print(f"Error in sprint expiration check: {e}")

        # الانتظار لمدة 30 دقيقة
        await asyncio.sleep(120)  # 1800 ثانية = 30 دقيقة





@router.post("/{project_id}", status_code=status.HTTP_201_CREATED)
async def create_sprint(
        user: user_dependency,
        db: db_dependency,
        sprint_request: CreateSprintRequest,
        project_id: int = Path(gt=0)
):
    # التحقق من الصلاحيات
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(status_code=403, detail='Only managers or owners can create sprints')

    # التحقق من وجود مشروع Sprint غير منتهٍ (سواء كان نشطاً أو لا)
    existing_uncompleted_sprint = db.query(Sprint).filter(
        Sprint.project_id == project_id,
        Sprint.is_completed == False
    ).first()

    if existing_uncompleted_sprint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Cannot create new sprint. There is an uncompleted sprint (ID: {existing_uncompleted_sprint.id}) in this project'
        )

    # إنشاء Sprint جديد
    sprint = Sprint(
        name=sprint_request.name,
        duration=sprint_request.duration,
        project_id=project_id,
        is_active=False,  # غير نشط عند الإنشاء
        is_completed=False  # غير مكتمل عند الإنشاء
    )
    db.add(sprint)
    db.commit()

    return {
        "message": "Sprint created successfully (pending launch)",
        "sprint_id": sprint.id,
        "status": "DRAFT"
    }



class UpdateSprintNameRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)

@router.put("/{sprint_id}/name", status_code=status.HTTP_200_OK)
async def update_sprint_name(
    user: user_dependency,
    db: db_dependency,
    name_request: UpdateSprintNameRequest,
    sprint_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # البحث عن الـ Sprint المطلوب
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail='Sprint not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير للمشروع)
    if not check_project_permission(db, user.get('id'), sprint.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can update sprints'
        )

    # التحقق من أن الـ Sprint ليس في حالة مكتملة
    if sprint.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Cannot update name of a completed sprint'
        )

    # تحديث اسم الـ Sprint
    sprint.name = name_request.name
    db.commit()

    return {"message": "Sprint name updated successfully"}



class AddTaskToSprintRequest(BaseModel):
    task_id: int = Field(gt=0, description="Task ID to be added")

@router.post("/{sprint_id}/tasks", status_code=status.HTTP_200_OK)
async def add_task_to_sprint(
    user: user_dependency,
    db: db_dependency,
    request: AddTaskToSprintRequest,
    sprint_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # البحث عن الsprint
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail='Sprint not found')

    # البحث عن المهمة
    task = db.query(Task).filter(Task.id == request.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المهمة تنتمي لنفس مشروع الsprint
    if task.project_id != sprint.project_id:
        raise HTTPException(
            status_code=400,
            detail='Task does not belong to the same project as the sprint'
        )

    # التحقق من صلاحيات المستخدم (مدير أو مالك المشروع)
    if not check_project_permission(db, user.get('id'), sprint.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project manager or owner can add tasks to sprint'
        )

    # التحقق من أن الsprint غير مكتمل
    if sprint.is_completed:
        raise HTTPException(
            status_code=400,
            detail='Cannot add tasks to a completed sprint'
        )

    # التحقق من أن حالة المهمة ليست complete
    if task.status == TaskStatus.COMPLETE:
        raise HTTPException(
            status_code=400,
            detail='Cannot add completed tasks to sprint'
        )

    # إضافة المهمة للsprint
    task.sprint_id = sprint_id
    db.commit()

    return {
        "message": "Task added to sprint successfully",
        "sprint_id": sprint_id,
        "task_id": task.id,
        "task_name": task.name
    }


@router.post("/{sprint_id}/launch", status_code=status.HTTP_200_OK)
async def launch_sprint(
        user: user_dependency,
        db: db_dependency,
        sprint_id: int = Path(gt=0)
):
    # التحقق من توثيق المستخدم
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب الـ Sprint المطلوب
    sprint = db.query(Sprint).filter(Sprint.id == sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail='Sprint not found')

    # التحقق من الصلاحيات (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), sprint.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project manager or owner can launch sprints'
        )

    # التحقق من أن الـ Sprint غير منتهٍ أو نشط مسبقاً
    if sprint.is_active or sprint.is_completed:
        raise HTTPException(
            status_code=400,
            detail='Sprint is already active or completed'
        )

    # جلب مهام الـ Sprint
    tasks = db.query(Task).filter(Task.sprint_id == sprint_id).all()

    # التحقق من أن الـ Sprint يحتوي على 5 مهام على الأقل
    if len(tasks) <= 5:
        raise HTTPException(
            status_code=400,
            detail='Sprint must contain at least 5 tasks'
        )

    # التحقق من أن جميع المهام مسندة لمستخدم
    unassigned_tasks = [task for task in tasks if task.worker_id is None]
    if unassigned_tasks:
        unassigned_ids = [task.id for task in unassigned_tasks]
        raise HTTPException(
            status_code=400,
            detail=f'Unassigned tasks found: {unassigned_ids}'
        )

    current_time = datetime.now(timezone.utc)

    # تحديث جميع المهام
    for task in tasks:
        # تغيير حالة المهمة إلى available
        task.status = TaskStatus.AVAILABLE

        # تسجيل التغيير في task_info
        task_info = TaskInfo(
            task_num=task.id,
            update_date=current_time,
            task_status=TaskStatus.AVAILABLE.value
        )
        db.add(task_info)

    # حساب وقت الانتهاء بناءً على المدة
    duration_mapping = {
        SprintDuration.ONE_WEEK: timedelta(weeks=1),
        SprintDuration.TWO_WEEKS: timedelta(weeks=2),
        SprintDuration.THREE_WEEKS: timedelta(weeks=3),
        SprintDuration.FOUR_WEEKS: timedelta(weeks=4)
    }

    # يجب أن نستخدم القيمة الفعلية للـ duration
    duration_delta = duration_mapping[sprint.duration]  # بدون قيمة افتراضية

    sprint.start_date = current_time
    sprint.end_date = current_time + duration_delta
    sprint.is_active = True

    db.commit()

    return {
        "message": "Sprint launched successfully",
        "start_date": sprint.start_date.isoformat(),
        "end_date": sprint.end_date.isoformat()
    }