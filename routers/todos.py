from datetime import datetime
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter , Depends
from database import  SessionLocal



router = APIRouter()


class CreateTodoRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    description: Optional[str] = Field(None, min_length=5 , max_length=120)
    priority: int = Field(gt=0, lt=6)
    complete: bool = False
    report: Optional[str] = Field(None, min_length=5 , max_length=200)



def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]