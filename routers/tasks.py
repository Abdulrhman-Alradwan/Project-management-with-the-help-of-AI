from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal




router = APIRouter()





class CreateTaskRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    deadline: Optional[datetime] = None
    status: str = Field(default='available')
    dependent_on: Optional[int] = None
    dependency_type: str = Field(default='None')
    comments: Optional[str] = Field(None, min_length=5)



def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]