from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path
from starlette import status

from models import Project, User, TodoCategory, UserProject
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

class CategoryRequest(BaseModel):
    name: str = Field(min_length=5, max_length=40)




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




