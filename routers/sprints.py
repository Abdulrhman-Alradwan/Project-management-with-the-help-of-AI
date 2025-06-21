from typing import Annotated
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal
from .auth import get_current_user , check_project_permission
from fastapi import status, HTTPException, Path
from models import Epic, Project, SprintDuration, Sprint

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

    # التحقق من عدم وجود sprint نشط
    if db.query(Sprint).filter(
            Sprint.project_id == project_id,
            Sprint.is_active == True,
            Sprint.is_completed == False
    ).first():
        raise HTTPException(status_code=400, detail='Active sprint already exists')

    # إنشاء Sprint (بدون إطلاق)
    sprint = Sprint(
        name=sprint_request.name,
        duration=sprint_request.duration,
        project_id=project_id
    )
    db.add(sprint)
    db.commit()

    return {
        "message": "Sprint created (pending launch)",
        "sprint_id": sprint.id,
        "status": "DRAFT"
    }