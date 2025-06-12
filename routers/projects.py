from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path
from starlette import status

from models import Project, User, UserProject, RoleEnum
from database import  SessionLocal
from .auth import get_current_user



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
async def create_project(user : user_dependency,
                         db : db_dependency,
                         project_request : ProjectRequest):
    if user is None :
        raise HTTPException(status_code=401, detail='Authentication Failed')

    if user.get('role') != RoleEnum.MANAGER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only users with Manager role can create projects'
        )

    project_model = Project(**project_request.model_dump(),
                            owner_id = user.get('id'))

    db.add(project_model)
    db.commit()

    user_project = UserProject(
        user_id=user.get('id'),
        project_id=project_model.id
    )

    db.add(user_project)
    db.commit()


@router.put("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_project_name(
        user: user_dependency,
        db: db_dependency,
        project_name: str = Field(..., min_length=5, max_length=40),
        project_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')


    if user.get('role') != RoleEnum.MANAGER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only users with Manager role can update projects'
        )

    project_model = db.query(Project).filter(Project.id == project_id).first()

    if project_model is None:
        raise HTTPException(status_code=404, detail='Project not found')


    if project_model.owner_id != user.get('id'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner can update the project'
        )

    project_model.name = project_name
    db.add(project_model)
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

    # التحقق من أن دور المستخدم هو Manager
    if user.get('role') != RoleEnum.MANAGER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only Managers can add users to projects'
        )

    # البحث عن المشروع
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من أن المدير هو مالك المشروع
    if project.owner_id != user.get('id'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only project owner can add users'
        )

    # البحث عن المستخدم المراد إضافته
    user_to_add = db.query(User).filter(User.username == add_user_request.username).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail='User not found')

    # التحقق من أن المستخدم المضاف ليس مديراً
    if user_to_add.role == RoleEnum.MANAGER.value:
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