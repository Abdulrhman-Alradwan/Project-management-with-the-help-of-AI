from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from database import  SessionLocal
from models import PriorityEnum, DependencyType, Project, User, Task, TaskStatus, TaskInfo, UserProject, RoleEnum
from routers.auth import get_current_user, check_project_permission

router = APIRouter(
    prefix='/task',
    tags=['task']
)




def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]
user_dependency = Annotated[dict , Depends(get_current_user)]



class CreateTaskRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    worker_id: Optional[int] = None
    dependent_on: Optional[int] = None
    dependency_type: Optional[DependencyType] = DependencyType.NONE
    priority: Optional[PriorityEnum] = PriorityEnum.MEDIUM


@router.post("/{project_id}", status_code=status.HTTP_201_CREATED)
async def create_task(
        user: user_dependency,
        db: db_dependency,
        task_request: CreateTaskRequest,
        project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من صلاحيات المستخدم
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can create tasks'
        )

    # التحقق من وجود العامل وانه عضو في المشروع
    if task_request.worker_id:
        worker = db.query(User).filter(User.id == task_request.worker_id).first()
        if not worker:
            raise HTTPException(status_code=404, detail='User not found')

        if worker.role != RoleEnum.User.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Worker must be of type User'
            )

        is_member = db.query(UserProject).filter(
            UserProject.user_id == task_request.worker_id,
            UserProject.project_id == project_id
        ).first()
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Assigned worker is not a member of this project'
            )

    # التحقق من المهمة التابعة
    if task_request.dependent_on:
        dependent_task = db.query(Task).filter(Task.id == task_request.dependent_on).first()
        if not dependent_task:
            raise HTTPException(status_code=404, detail='Dependent task not found')
        if dependent_task.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Dependent task must be in the same project'
            )

    # إنشاء المهمة مع التحويل الصحيح للـ Enum
    task = Task(
        name=task_request.name,
        status=TaskStatus.NOT_AVAILABLE.value,
        project_id=project_id,
        worker_id=task_request.worker_id,
        dependent_on=task_request.dependent_on,
        dependency_type=task_request.dependency_type.value if task_request.dependency_type else None,
        priority=task_request.priority.value.lower() if task_request.priority else PriorityEnum.MEDIUM.value.lower(),
        create_date=datetime.now(timezone.utc)
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    # إنشاء سجل المهمة
    task_info = TaskInfo(
        task_num=task.id,
        update_date=datetime.now(timezone.utc),
        task_status=TaskStatus.NOT_AVAILABLE.value
    )
    db.add(task_info)
    db.commit()

    return {
        "message": "Task created successfully",
        "task_id": task.id,
        "status": task.status,
        "worker_id": task.worker_id,
        "priority": task.priority
    }
