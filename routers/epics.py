from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal
from .auth import get_current_user , check_project_permission
from fastapi import status, HTTPException, Path
from models import Epic, Project





router = APIRouter(
    prefix='/epic',
    tags=['epic']
)




class CreateEpicRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)


class UpdateEpicRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)



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


