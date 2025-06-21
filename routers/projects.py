from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from starlette import status
from models import Project, User, UserProject, RoleEnum
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

    # التحقق من أن المستخدم هو مدير أو مالك المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # استدعاء دالة التحقق من الصلاحيات
    if not check_project_permission(db, user.get('id'), project_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner or assigned managers can add users to the project'
        )

    # البحث عن المستخدم المراد إضافته
    user_to_add = db.query(User).filter(User.username == add_user_request.username).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من أن المستخدم المضاف ليس مديراً (ما لم يكن المالك نفسه)
    if user_to_add.role == RoleEnum.Manager.value and project.owner_id != user_to_add.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Cannot add another manager to the project'
        )

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

    # إنشاء العلاقة الجديدة
    new_association = UserProject(
        user_id=user_to_add.id,
        project_id=project_id
    )

    db.add(new_association)
    db.commit()

    return {"message": f"User {add_user_request.username} added to project successfully"}