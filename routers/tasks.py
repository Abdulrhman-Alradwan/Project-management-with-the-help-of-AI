from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from database import  SessionLocal
from models import PriorityEnum, DependencyType, Project, User, Task, TaskStatus, TaskInfo, UserProject, RoleEnum, \
    Sprint, Comment, Reply
from routers.auth import get_current_user, check_project_permission
from routers.sprints import check_dependency_status

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


def check_ss_dependency(db: Session, task: Task) -> bool:
    """
    التحقق من إمكانية بدء المهمة بناءً على اعتمادية SS
    """
    if not task.dependent_on:
        return True

    # جلب المهمة المعتمدة عليها
    dependency_task = db.query(Task).filter(Task.id == task.dependent_on).first()

    if not dependency_task:
        return False

    # الحالات المسموحة: in_progress, testing, feedback, complete
    allowed_statuses = [
        TaskStatus.IN_PROGRESS,
        TaskStatus.TESTING,
        TaskStatus.FEEDBACK,
        TaskStatus.COMPLETE
    ]

    return dependency_task.status in allowed_statuses


def check_fs_dependency(db: Session, task: Task) -> bool:
    """
    التحقق من إمكانية بدء المهمة بناءً على اعتمادية FS
    """
    if not task.dependent_on:
        return True

    # جلب المهمة المعتمدة عليها
    dependency_task = db.query(Task).filter(Task.id == task.dependent_on).first()

    if not dependency_task:
        return False

    # يجب أن تكون المهمة المعتمدة عليها مكتملة
    return dependency_task.status == TaskStatus.COMPLETE


def check_dependent_tasks(db: Session, completed_task_id: int):
    """
    تحقق من المهام التي تعتمد على المهمة المكتملة وتحديث حالتها إذا لزم الأمر
    """
    # البحث عن المهام التي تعتمد على هذه المهمة
    dependent_tasks = db.query(Task).filter(Task.dependent_on == completed_task_id).all()

    for task in dependent_tasks:
        # إذا كانت الاعتمادية من نوع FS وتحققت الشروط
        if task.dependency_type == DependencyType.FS:
            # يمكن تغيير حالة المهمة إلى AVAILABLE إذا كانت في حالة WAIT
            if task.status == TaskStatus.WAIT:
                task.status = TaskStatus.AVAILABLE

                # تسجيل التغيير في task_info
                current_time = datetime.now(timezone.utc)
                task_info = TaskInfo(
                    task_num=task.id,
                    update_date=current_time,
                    task_status=TaskStatus.AVAILABLE.value
                )
                db.add(task_info)

    db.commit()


def check_ss_dependent_tasks(db: Session, started_task_id: int):
    """
    تحقق من المهام التي تعتمد على المهمة التي بدأت (من نوع SS) وتحديث حالتها إذا لزم الأمر
    """
    # البحث عن المهام التي تعتمد على هذه المهمة ونوع الاعتمادية SS
    dependent_tasks = db.query(Task).filter(
        Task.dependent_on == started_task_id,
        Task.dependency_type == DependencyType.SS
    ).all()

    for task in dependent_tasks:
        # يمكن تغيير حالة المهمة إلى AVAILABLE إذا كانت في حالة WAIT
        if task.status == TaskStatus.WAIT:
            task.status = TaskStatus.AVAILABLE

            # تسجيل التغيير في task_info
            current_time = datetime.now(timezone.utc)
            task_info = TaskInfo(
                task_num=task.id,
                update_date=current_time,
                task_status=TaskStatus.AVAILABLE.value
            )
            db.add(task_info)

    db.commit()


def check_circular_dependency(db: Session, task_id: int, dependency_id: int) -> bool:
    """
    التحقق من وجود اعتمادية دائرية
    """
    current = dependency_id
    visited = set()

    while current:
        # إذا وصلنا إلى المهمة الأصلية، فهناك اعتمادية دائرية
        if current == task_id:
            return True

        # إذا وصلنا إلى مهمة تم زيارتها سابقاً
        if current in visited:
            return True

        visited.add(current)

        # جلب المهمة التالية في السلسلة
        next_task = db.query(Task).filter(Task.id == current).first()
        if not next_task or not next_task.dependent_on:
            break

        current = next_task.dependent_on

    return False



class CreateTaskRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    worker_id: Optional[int] = None
    dependent_on: Optional[int] = None
    dependency_type: Optional[DependencyType] = DependencyType.NONE
    priority: Optional[PriorityEnum] = PriorityEnum.MEDIUM


class UpdateTaskNameRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)

class UpdateTaskDependencyRequest(BaseModel):
    dependent_on: Optional[int] = Field(None, gt=0, description="ID of the task this task depends on")
    dependency_type: Optional[DependencyType] = Field(DependencyType.NONE, description="Type of dependency")

class AssignTaskRequest(BaseModel):
    user_id: int = Field(gt=0, description="ID of the user to assign the task to")

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


@router.put("/start/{task_id}", status_code=status.HTTP_200_OK)
async def start_task(
        user: user_dependency,
        db: db_dependency,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المستخدم هو العامل المسند إليه المهمة
    if task.worker_id != user.get('id'):
        raise HTTPException(
            status_code=403,
            detail='Only assigned worker can start this task'
        )

    # التحقق من أن الحالة الحالية تسمح بالبدء (available أو feedback)
    if task.status not in [TaskStatus.AVAILABLE, TaskStatus.FEEDBACK]:
        raise HTTPException(
            status_code=400,
            detail='Task must be in available or feedback status to start'
        )

    # التحقق من أن المهمة في sprint نشط
    if not task.sprint_id:
        raise HTTPException(
            status_code=400,
            detail='Task is not in any sprint'
        )

    sprint = db.query(Sprint).filter(Sprint.id == task.sprint_id).first()
    if not sprint or not sprint.is_active:
        raise HTTPException(
            status_code=400,
            detail='Task is not in an active sprint'
        )

    # التحقق من الاعتماديات حسب النوع
    """if task.dependency_type == DependencyType.SS:
        if not check_ss_dependency(db, task):
            raise HTTPException(
                status_code=400,
                detail='Cannot start task: dependent task has not started yet'
            )

    elif task.dependency_type == DependencyType.FS:
        if not check_fs_dependency(db, task):
            raise HTTPException(
                status_code=400,
                detail='Cannot start task: dependent task is not complete'
            )"""

    # تغيير حالة المهمة
    task.status = TaskStatus.IN_PROGRESS

    # تسجيل التغيير في task_info
    current_time = datetime.now(timezone.utc)
    task_info = TaskInfo(
        task_num=task_id,
        update_date=current_time,
        task_status=TaskStatus.IN_PROGRESS.value
    )
    db.add(task_info)
    db.commit()

    # التحقق من تأثير بدء المهمة على المهام المعتمدة عليها من نوع SS
    check_ss_dependent_tasks(db, task_id)

    return {
        "message": "Task started successfully",
        "task_id": task_id,
        "new_status": TaskStatus.IN_PROGRESS.value
    }


@router.put("/mark-testing/{task_id}", status_code=status.HTTP_200_OK)
async def mark_task_as_testing(
        user: user_dependency,
        db: db_dependency,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المستخدم هو العامل المسند إليه المهمة
    if task.worker_id != user.get('id'):
        raise HTTPException(
            status_code=403,
            detail='Only assigned worker can mark task as testing'
        )

    # التحقق من أن الحالة الحالية هي IN_PROGRESS
    if task.status != TaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail='Task must be in progress to mark as testing'
        )

    # التحقق من أن المهمة في sprint نشط
    if not task.sprint_id:
        raise HTTPException(
            status_code=400,
            detail='Task is not in any sprint'
        )

    sprint = db.query(Sprint).filter(Sprint.id == task.sprint_id).first()
    if not sprint or not sprint.is_active:
        raise HTTPException(
            status_code=400,
            detail='Task is not in an active sprint'
        )

    # تغيير حالة المهمة
    task.status = TaskStatus.TESTING

    # تسجيل التغيير في task_info
    current_time = datetime.now(timezone.utc)
    task_info = TaskInfo(
        task_num=task_id,
        update_date=current_time,
        task_status=TaskStatus.TESTING.value
    )
    db.add(task_info)
    db.commit()

    return {
        "message": "Task marked for testing",
        "task_id": task_id,
        "new_status": TaskStatus.TESTING.value
    }


@router.put("/mark-feedback/{task_id}", status_code=status.HTTP_200_OK)
async def mark_task_as_feedback(
        user: user_dependency,
        db: db_dependency,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # التحقق من أن المستخدم له دور Tester
    if user.get('role') != RoleEnum.Tester.value:
        raise HTTPException(
            status_code=403,
            detail='Only testers can mark tasks as feedback'
        )

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن الحالة الحالية هي TESTING
    if task.status != TaskStatus.TESTING:
        raise HTTPException(
            status_code=400,
            detail='Task must be in testing status to mark as feedback'
        )

    # التحقق من أن المهمة في sprint نشط
    if not task.sprint_id:
        raise HTTPException(
            status_code=400,
            detail='Task is not in any sprint'
        )

    sprint = db.query(Sprint).filter(Sprint.id == task.sprint_id).first()
    if not sprint or not sprint.is_active:
        raise HTTPException(
            status_code=400,
            detail='Task is not in an active sprint'
        )

    # تغيير حالة المهمة
    task.status = TaskStatus.FEEDBACK

    # تسجيل التغيير في task_info
    current_time = datetime.now(timezone.utc)
    task_info = TaskInfo(
        task_num=task_id,
        update_date=current_time,
        task_status=TaskStatus.FEEDBACK.value
    )
    db.add(task_info)
    db.commit()

    return {
        "message": "Task marked for feedback",
        "task_id": task_id,
        "new_status": TaskStatus.FEEDBACK.value
    }


@router.put("/mark-complete/{task_id}", status_code=status.HTTP_200_OK)
async def mark_task_as_complete(
        user: user_dependency,
        db: db_dependency,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # التحقق من أن المستخدم له دور Tester
    if user.get('role') != RoleEnum.Tester.value:
        raise HTTPException(
            status_code=403,
            detail='Only testers can mark tasks as complete'
        )

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن الحالة الحالية هي TESTING
    if task.status != TaskStatus.TESTING:
        raise HTTPException(
            status_code=400,
            detail='Task must be in testing status to mark as complete'
        )

    # التحقق من أن المهمة في sprint نشط
    if not task.sprint_id:
        raise HTTPException(
            status_code=400,
            detail='Task is not in any sprint'
        )

    sprint = db.query(Sprint).filter(Sprint.id == task.sprint_id).first()
    if not sprint or not sprint.is_active:
        raise HTTPException(
            status_code=400,
            detail='Task is not in an active sprint'
        )

    # تغيير حالة المهمة
    task.status = TaskStatus.COMPLETE

    # تسجيل التغيير في task_info
    current_time = datetime.now(timezone.utc)
    task_info = TaskInfo(
        task_num=task_id,
        update_date=current_time,
        task_status=TaskStatus.COMPLETE.value
    )
    db.add(task_info)
    db.commit()

    # التحقق من تأثير إكمال المهمة على المهام المعتمدة عليها
    check_dependent_tasks(db, task_id)

    return {
        "message": "Task marked as complete",
        "task_id": task_id,
        "new_status": TaskStatus.COMPLETE.value
    }


@router.put("/{task_id}/name", status_code=status.HTTP_200_OK)
async def update_task_name(
    user: user_dependency,
    db: db_dependency,
    update_request: UpdateTaskNameRequest,
    task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), task.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project owner or assigned managers can update task name'
        )

    # تحديث اسم المهمة
    task.name = update_request.name
    db.commit()

    return {"message": "Task name updated successfully"}


@router.put("/{task_id}/dependency", status_code=status.HTTP_200_OK)
async def update_task_dependency(
        user: user_dependency,
        db: db_dependency,
        update_request: UpdateTaskDependencyRequest,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من صلاحيات المستخدم
    if not check_project_permission(db, user.get('id'), task.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project owner or assigned managers can update task dependencies'
        )

    # التحقق من المهمة المعتمدة عليها
    if update_request.dependent_on:
        dependency_task = db.query(Task).filter(Task.id == update_request.dependent_on).first()
        if not dependency_task:
            raise HTTPException(status_code=404, detail='Dependency task not found')

        # التحقق من أن المهمة في نفس المشروع
        if dependency_task.project_id != task.project_id:
            raise HTTPException(
                status_code=400,
                detail='Dependency task must be in the same project'
            )

        # التحقق من عدم وجود اعتمادية دائرية
        if check_circular_dependency(db, task_id, update_request.dependent_on):
            raise HTTPException(
                status_code=400,
                detail='Circular dependency detected'
            )

    # تحديث الاعتمادية
    task.dependent_on = update_request.dependent_on
    task.dependency_type = update_request.dependency_type.value if update_request.dependency_type else None

    # تحديث حالة المهمة بناءً على الاعتمادية الجديدة فقط إذا كانت في سباق نشط
    if task.sprint_id:
        sprint = db.query(Sprint).filter(Sprint.id == task.sprint_id).first()
        if sprint and sprint.is_active:
            if task.dependent_on:
                if check_dependency_status(db, task):
                    task.status = TaskStatus.AVAILABLE
                else:
                    task.status = TaskStatus.WAIT
            else:
                task.status = TaskStatus.NOT_AVAILABLE

    # تسجيل تغيير الحالة
    current_time = datetime.now(timezone.utc)
    task_info = TaskInfo(
        task_num=task_id,
        update_date=current_time,
        task_status=task.status.value
    )
    db.add(task_info)

    db.commit()

    return {"message": "Task dependency updated successfully"}


@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_task(
        user: user_dependency,
        db: db_dependency,
        task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من صلاحيات المستخدم
    if not check_project_permission(db, user.get('id'), task.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project owner or assigned managers can delete tasks'
        )

    # جلب جميع المهام التي تعتمد على هذه المهمة
    dependent_tasks = db.query(Task).filter(Task.dependent_on == task_id).all()

    # فك ارتباط المهام المعتمدة
    for dep_task in dependent_tasks:
        dep_task.dependent_on = None

        # إذا كانت المهمة في سباق نشط، تحديث حالتها
        if dep_task.sprint_id:
            sprint = db.query(Sprint).filter(Sprint.id == dep_task.sprint_id).first()
            if sprint and sprint.is_active:
                dep_task.status = TaskStatus.AVAILABLE

                # تسجيل تغيير الحالة
                current_time = datetime.now(timezone.utc)
                task_info = TaskInfo(
                    task_num=dep_task.id,
                    update_date=current_time,
                    task_status=TaskStatus.AVAILABLE.value
                )
                db.add(task_info)

    # حذف سجلات TaskInfo المرتبطة بالمهمة الأصلية
    db.query(TaskInfo).filter(TaskInfo.task_num == task_id).delete()

    # حذف التعليقات والردود المرتبطة بالمهمة الأصلية
    comments = db.query(Comment).filter(Comment.task_id == task_id).all()
    for comment in comments:
        db.query(Reply).filter(Reply.comment_id == comment.id).delete()
    db.query(Comment).filter(Comment.task_id == task_id).delete()

    # إذا كانت المهمة في سباق، فك ارتباطها
    if task.sprint_id:
        task.sprint_id = None

    # حذف المهمة نفسها
    db.delete(task)
    db.commit()

    return {
        "message": "Task deleted successfully",
        "task_id": task_id,
        "project_id": task.project_id,
        "dependencies_removed": len(dependent_tasks)
    }

@router.put("/{task_id}/assign", status_code=status.HTTP_200_OK)
async def assign_task_to_user(
    user: user_dependency,
    db: db_dependency,
    assign_request: AssignTaskRequest,
    task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication required')

    # جلب المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), task.project_id):
        raise HTTPException(
            status_code=403,
            detail='Only project owner or assigned managers can assign tasks'
        )

    # جلب المستخدم المراد إسناد المهمة إليه
    assignee = db.query(User).filter(User.id == assign_request.user_id).first()
    if not assignee:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من أن المستخدم المراد إسناد المهمة له له دور "User"
    if assignee.role != RoleEnum.User.value:
        raise HTTPException(
            status_code=400,
            detail='Task can only be assigned to users with "User" role'
        )

    # التحقق من أن المستخدم عضو في المشروع
    is_member = db.query(UserProject).filter(
        UserProject.user_id == assign_request.user_id,
        UserProject.project_id == task.project_id
    ).first()
    if not is_member:
        raise HTTPException(
            status_code=400,
            detail='Assigned user is not a member of this project'
        )

    # تحديث المهمة بإسنادها للمستخدم
    task.worker_id = assign_request.user_id
    db.commit()

    return {
        "message": "Task assigned successfully",
        "task_id": task_id,
        "assigned_to": {
            "user_id": assign_request.user_id,
            "username": assignee.username
        }
    }


