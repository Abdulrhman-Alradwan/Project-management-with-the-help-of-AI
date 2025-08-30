from datetime import timezone, datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from starlette import status
from models import Project, User, UserProject, RoleEnum, Task, TaskStatus
from database import  SessionLocal
from .auth import get_current_user , check_project_permission



router = APIRouter(
    prefix='/project',
    tags=['project']
)


class ProjectRequest(BaseModel):
    name: str = Field(min_length=5 , max_length=40)
    description: Optional[str] = Field(None, min_length=5 , max_length=120)
    complete: bool = False

class AddUserToProjectRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)

class LeaveProjectRequest(BaseModel):
    new_owner_id: Optional[int] = Field(None, gt=0, description="Required if the user is the owner")


class UpdateUserStoryPointsRequest(BaseModel):
    story_points: int = Field(ge=0, le=100, description="Story points must be between 0 and 100")


def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]
user_dependency = Annotated[dict , Depends(get_current_user)]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(user: user_dependency,
                        db: db_dependency,
                        project_request: ProjectRequest):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    if user.get('role') != RoleEnum.Manager.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only users with Manager role can create projects'
        )

    # إنشاء المشروع مع تحديد المالك
    project_model = Project(
        **project_request.model_dump(),
        owner_id=user.get('id')
    )

    db.add(project_model)
    db.commit()
    db.refresh(project_model)  # ضروري للحصول على الـ ID

    # إنشاء العلاقة بشكل صحيح مع كلا المعرفين
    user_project = UserProject(
        user_id=user.get('id'),
        project_id=project_model.id  # هنا نضيف معرف المشروع
    )
    db.add(user_project)
    db.commit()

    return {"message": "Project created successfully", "project_id": project_model.id}


@router.put("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_project_name(
    user: user_dependency,
    db: db_dependency,
    project_name: str = Query(..., min_length=5, max_length=40),
    project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    project_model = db.query(Project).filter(Project.id == project_id).first()
    if not project_model:
        raise HTTPException(status_code=404, detail='Project not found')

    # استدعاء دالة التحقق من الصلاحيات
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can update the project'
        )

    project_model.name = project_name
    db.commit()


@router.post("/{project_id}/users", status_code=status.HTTP_201_CREATED)
async def add_user_to_project(
        user: user_dependency,
        db: db_dependency,
        add_user_request: AddUserToProjectRequest,
        project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من أن المستخدم الحالي هو مالك المشروع
    if user.get('id') != project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner can add users to the project'
        )

    # البحث عن المستخدم المراد إضافته
    user_to_add = db.query(User).filter(User.username == add_user_request.username).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من عدم وجود العلاقة بالفعل
    existing_association = db.query(UserProject).filter(
        UserProject.user_id == user_to_add.id,
        UserProject.project_id == project_id
    ).first()

    if existing_association:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User is already associated with this project'
        )

    # التحقق من وجود مدير آخر في المشروع (بخلاف المالك الحالي)
    if user_to_add.role == RoleEnum.Manager.value:
        # البحث عن أي مدير آخر في المشروع
        other_managers = db.query(User).join(UserProject).filter(
            UserProject.project_id == project_id,
            User.role == RoleEnum.Manager.value,
            User.id != user.get('id')  # استثناء المالك الحالي
        ).count()

        if other_managers > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Project already has a manager. Cannot add another manager.'
            )

    # إنشاء العلاقة الجديدة
    new_association = UserProject(
        user_id=user_to_add.id,
        project_id=project_id,
        story_points=40  # القيمة الافتراضية
    )

    db.add(new_association)

    # إذا كان المستخدم المضاف مديراً، نقوم بنقل الملكية إليه تلقائياً
    if user_to_add.role == RoleEnum.Manager.value:
        project.owner_id = user_to_add.id
        message = f"Manager {add_user_request.username} added to project and ownership transferred successfully"
    else:
        message = f"User {add_user_request.username} added to project successfully"

    db.commit()

    return {"message": message}


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_200_OK)
async def remove_member_from_project(
        user: user_dependency,
        db: db_dependency,
        project_id: int = Path(gt=0),
        user_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من وجود المستخدم المراد إزالته
    member_to_remove = db.query(User).filter(User.id == user_id).first()
    if not member_to_remove:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من أن المستخدم المراد إزالته عضو في المشروع
    user_project = db.query(UserProject).filter(
        UserProject.project_id == project_id,
        UserProject.user_id == user_id
    ).first()

    if not user_project:
        raise HTTPException(
            status_code=400,
            detail='User is not a member of this project'
        )

    # التحقق من صلاحيات المستخدم الحالي (مالك المشروع فقط يمكنه الإزالة)
    if user.get('id') != project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner can remove members'
        )

    # منع إزالة المالك من مشروعه
    if user_id == project.owner_id:
        raise HTTPException(
            status_code=400,
            detail='Project owner cannot be removed'
        )

    # جلب جميع المهام المخصصة لهذا العضو في المشروع
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.worker_id == user_id
    ).all()

    # فك ارتباط المهام بالعضو
    for task in tasks:
        task.worker_id = None


    # إزالة العضو من المشروع
    db.delete(user_project)
    db.commit()

    return {
        "message": "Member removed from project successfully",
        "project_id": project_id,
        "user_id": user_id,
        "tasks_unassigned": len(tasks)
    }




@router.get("/user-projects", status_code=status.HTTP_200_OK)
async def get_user_projects(
        user: user_dependency,
        db: db_dependency
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # جلب جميع المشاريع التي يمتلكها المستخدم
    owned_projects = db.query(Project).filter(Project.owner_id == user.get('id')).all()

    # جلب جميع المشاريع التي يديرها المستخدم (من خلال جدول UserProject)
    managed_projects = (
        db.query(Project)
        .join(UserProject, Project.id == UserProject.project_id)
        .join(User, UserProject.user_id == User.id)
        .filter(
            User.id == user.get('id'),
            User.role == RoleEnum.Manager.value
        )
        .all()
    )

    # دمج النتائج مع إزالة التكرارات
    all_projects = list(set(owned_projects + managed_projects))

    # تحويل النتائج إلى تنسيق مناسب
    projects_list = []
    for project in all_projects:
        # جلب اسم المالك
        owner = db.query(User).filter(User.id == project.owner_id).first()
        owner_name = f"{owner.first_name} {owner.last_name}" if owner else "Unknown"

        # جلب عدد المهام في المشروع
        tasks_count = db.query(Task).filter(Task.project_id == project.id).count()

        projects_list.append({
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": project.create_date,
            "owner_id": project.owner_id,
            "owner_name": owner_name,
            "is_completed": project.complete,
            "tasks_count": tasks_count
        })

    return {"projects": projects_list}

class LeaveProjectRequest(BaseModel):
    new_owner_id: Optional[int] = Field(None, gt=0, description="Required if the user is the owner")



@router.put("/{project_id}/leave", status_code=status.HTTP_200_OK)
async def leave_project(
    user: user_dependency,
    db: db_dependency,
    request: LeaveProjectRequest,
    project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # جلب المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من أن المستخدم عضو في المشروع
    user_project = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == project_id
    ).first()
    if not user_project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # إذا كان المستخدم هو المالك
    if project.owner_id == user.get('id'):
        # يجب تقديم معرف المالك الجديد
        if request.new_owner_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='You must specify a new owner before leaving the project'
            )

        # التحقق من أن المالك الجديد موجود
        new_owner = db.query(User).filter(User.id == request.new_owner_id).first()
        if not new_owner:
            raise HTTPException(status_code=404, detail='New owner not found')

        # التحقق من أن المالك الجديد عضو في المشروع
        new_owner_membership = db.query(UserProject).filter(
            UserProject.user_id == request.new_owner_id,
            UserProject.project_id == project_id
        ).first()
        if not new_owner_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='New owner must be a member of the project'
            )

        # التحقق من أن المالك الجديد ليس المستخدم الحالي
        if request.new_owner_id == user.get('id'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='You cannot transfer ownership to yourself'
            )

        # نقل الملكية
        project.owner_id = request.new_owner_id

    # فك ارتباط المستخدم من المهام المسندة إليه في هذا المشروع
    tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.worker_id == user.get('id')
    ).all()

    for task in tasks:
        task.worker_id = None

    # إزالة المستخدم من المشروع
    db.delete(user_project)
    db.commit()

    return {"message": "You have left the project successfully"}


@router.put("/{project_id}/complete", status_code=status.HTTP_200_OK)
async def complete_project(
    user: user_dependency,
    db: db_dependency,
    project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # جلب المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من الصلاحيات (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can complete the project'
        )

    # التحقق من أن المشروع ليس مكتملاً بالفعل
    if project.complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Project is already completed'
        )

    # التحقق من أن جميع مهام المشروع مكتملة
    incomplete_tasks = db.query(Task).filter(
        Task.project_id == project_id,
        Task.status != TaskStatus.COMPLETE
    ).all()

    if incomplete_tasks:
        incomplete_task_ids = [task.id for task in incomplete_tasks]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Cannot complete project. Incomplete tasks found: {incomplete_task_ids}'
        )

    # تحديث المشروع ليصبح مكتملاً وتسجيل تاريخ الانتهاء
    project.complete = True
    project.end_date = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Project marked as complete",
        "project_id": project_id,
        "end_date": project.end_date
    }

@router.put("/{project_id}/members/{user_id}/story-points", status_code=status.HTTP_200_OK)
async def update_user_story_points(
    user: user_dependency,
    db: db_dependency,
    update_request: UpdateUserStoryPointsRequest,
    project_id: int = Path(gt=0),
    user_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من صلاحيات المستخدم (مالك أو مدير المشروع)
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can update story points'
        )

    # التحقق من وجود المستخدم المراد تعديله
    user_to_update = db.query(User).filter(User.id == user_id).first()
    if not user_to_update:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من أن المستخدم المراد تعديله من نوع "User"
    if user_to_update.role != RoleEnum.User.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Can only assign story points to users with role "User"'
        )

    # التحقق من أن المستخدم عضو في المشروع
    user_project = db.query(UserProject).filter(
        UserProject.user_id == user_id,
        UserProject.project_id == project_id
    ).first()
    if not user_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User is not a member of this project'
        )

    # تحديث story points
    user_project.story_points = update_request.story_points
    db.commit()

    return {
        "message": "User story points updated successfully",
        "project_id": project_id,
        "user_id": user_id,
        "story_points": user_project.story_points
    }