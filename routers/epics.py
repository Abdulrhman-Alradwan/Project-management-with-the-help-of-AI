from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal
from .auth import get_current_user , check_project_permission
from fastapi import status, HTTPException, Path
from models import Epic, Project, Task, UserProject

router = APIRouter(
    prefix='/epic',
    tags=['epic']
)




class CreateEpicRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)


class UpdateEpicRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)

class AddTaskToEpicRequest(BaseModel):
    task_id: int = Field(gt=0)

def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()





db_dependency = Annotated[Session , Depends(get_db)]
user_dependency = Annotated[dict , Depends(get_current_user)]





@router.post("/{project_id}", status_code=status.HTTP_201_CREATED)
async def create_epic(
    user: user_dependency,
    db: db_dependency,
    epic_request: CreateEpicRequest,
    project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من أن المستخدم لديه صلاحية في المشروع (مالك أو مدير)
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can create epics'
        )

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # إنشاء الـ Epic الجديد
    epic_model = Epic(
        name=epic_request.name,
        project_id=project_id
    )

    db.add(epic_model)
    db.commit()
    db.refresh(epic_model)

    return {
        "message": "Epic created successfully",
        "epic_id": epic_model.id,
        "project_id": project_id
    }


@router.put("/{epic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_epic_name(
    user: user_dependency,
    db: db_dependency,
    epic_request: UpdateEpicRequest,
    epic_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # البحث عن الـ Epic المطلوب
    epic = db.query(Epic).filter(Epic.id == epic_id).first()
    if not epic:
        raise HTTPException(status_code=404, detail='Epic not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير للمشروع)
    if not check_project_permission(db, user.get('id'), epic.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can update epics'
        )

    # تحديث اسم الـ Epic
    epic.name = epic_request.name
    db.commit()


@router.put("/{epic_id}/tasks", status_code=status.HTTP_200_OK)
async def add_task_to_epic(
    user: user_dependency,
    db: db_dependency,
    request: AddTaskToEpicRequest,
    epic_id: int = Path(gt=0)):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    epic = db.query(Epic).filter(Epic.id == epic_id).first()
    if not epic:
        raise HTTPException(status_code=404, detail='Epic not found')

    # التحقق من وجود المهمة
    task = db.query(Task).filter(Task.id == request.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المهمة تنتمي لنفس المشروع الخاص بالepic
    if task.project_id != epic.project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Task does not belong to the same project as the epic'
        )

    # التحقق من أن المهمة ليست مضافَة إلى أي epic آخر
    if task.epic_id is not None and task.epic_id != epic_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Task is already assigned to another epic'
        )

    # التحقق من أن المهمة ليست مضافَة بالفعل إلى نفس الepic
    if task.epic_id == epic_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Task is already assigned to this epic'
        )

    # التحقق من صلاحيات المستخدم (أنه مدير أو مالك المشروع)
    if not check_project_permission(db, user.get('id'), epic.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or managers can modify epics'
        )

    # تعيين الepic للمهمة
    task.epic_id = epic_id
    db.commit()

    return {"message": "Task added to epic successfully"}


@router.delete("/tasks/{task_id}/epic", status_code=status.HTTP_200_OK)
async def remove_task_from_epic(
    user: user_dependency,
    db: db_dependency,
    task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المهمة لديها epic
    if not task.epic_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Task is not associated with any epic'
        )

    # التحقق من صلاحيات المستخدم (أنه مدير أو مالك المشروع)
    if not check_project_permission(db, user.get('id'), task.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or managers can modify epics'
        )

    # إزالة المهمة من الepic
    task.epic_id = None
    db.commit()

    return {"message": "Task removed from epic successfully"}


@router.get("/project/{project_id}", status_code=status.HTTP_200_OK)
async def get_epics_by_project(
        user: user_dependency,
        db: db_dependency,
        project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من صلاحيات المستخدم (عضو في المشروع)
    is_member = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == project_id
    ).first()

    if not is_member and project.owner_id != user.get('id'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # جلب جميع الـ Epics الخاصة بالمشروع
    epics = db.query(Epic).filter(Epic.project_id == project_id).all()

    # تحويل النتيجة إلى تنسيق مناسب
    epics_list = []
    for epic in epics:
        epic_data = {
            "id": epic.id,
            "name": epic.name,
            "project_id": epic.project_id,
            "task_count": len(epic.tasks)  # عدد المهام في الepic
        }
        epics_list.append(epic_data)

    return {"epics": epics_list}


@router.get("/{epic_id}/tasks-summary", status_code=status.HTTP_200_OK)
async def get_task_names_and_status_in_epic(
        user: user_dependency,
        db: db_dependency,
        epic_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود الملحمة
    epic = db.query(Epic).filter(Epic.id == epic_id).first()
    if not epic:
        raise HTTPException(status_code=404, detail='Epic not found')

    # التحقق من الصلاحيات
    is_member = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == epic.project_id
    ).first()

    if not is_member and epic.project.owner_id != user.get('id'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # جلب أسماء وحالات المهام
    tasks = db.query(Task.name, Task.status).filter(Task.epic_id == epic_id).all()

    return {
        "epic_id": epic_id,
        "epic_name": epic.name,
        "tasks": [{"name": task.name, "status": task.status} for task in tasks]
    }


@router.delete("/{epic_id}", status_code=status.HTTP_200_OK)
async def delete_epic(
    user: user_dependency,
    db: db_dependency,
    epic_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # البحث عن الepic المطلوبة
    epic = db.query(Epic).filter(Epic.id == epic_id).first()
    if not epic:
        raise HTTPException(status_code=404, detail='Epic not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), epic.project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can delete epics'
        )

    # جلب جميع المهام المرتبطة بالepic
    tasks = db.query(Task).filter(Task.epic_id == epic_id).all()

    # إزالة ارتباط المهام بالepic أولاً
    for task in tasks:
        task.epic_id = None
        db.add(task)

    # حذف الepic
    db.delete(epic)
    db.commit()

    return {
        "message": "Epic deleted successfully",
        "disassociated_tasks_count": len(tasks)
    }
