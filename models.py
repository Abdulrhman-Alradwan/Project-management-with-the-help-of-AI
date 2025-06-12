from database import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import validates
from datetime import datetime, timezone
import re  # لاستخدام التعابير النمطية للتحقق من صيغة الإيميل
from enum import Enum as PyEnum


class RoleEnum(PyEnum):
    MANAGER = "Manager"
    TESTER = "Tester"
    USER = "User"

class GenderEnum(PyEnum):
    MALE = "Male"
    FEMALE = "Female"

class PriorityEnum(PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"




class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True , index=True)
    first_name = Column(String,nullable=False)
    last_name = Column(String,nullable=False)
    email = Column(String,unique=True,nullable=False)
    hashed_password = Column(String,nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    job_title = Column(String,nullable=True)
    username = Column(String,unique=True,nullable=False)
    gender = Column(Enum(GenderEnum), nullable=False)
    age = Column(Integer,nullable=False)

    @validates('email')
    def validate_email(self, key, email):
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            raise ValueError('Invalid email format. Example')
        return email

    @validates('age')
    def validate_age(self, key, age):
        if not (18 <= age <= 74):
            raise ValueError('Age must be between 18 and 75 years')
        return age



class Project(Base):
    __tablename__ = 'project'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc),nullable=False)
    end_date = Column(DateTime, nullable=True)
    description = Column(String,nullable=True)
    complete = Column(Boolean , default=False)
    owner_id = Column(Integer, ForeignKey('user.id'), nullable=False)



class Task(Base):
    __tablename__ = 'task'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    """create_date = Column(DateTime, default=datetime.now(timezone.utc))
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)"""
    status = Column(String,default='not available')
    dependent_on = Column(Integer,nullable=True)
    dependency_type = Column(String, default='None')
    comments = Column(String, nullable=True)
    priority = Column(Enum(PriorityEnum), nullable=False, default=PriorityEnum.MEDIUM)
    worker_id = Column(Integer, ForeignKey('user.id'),nullable=False)
    sprint_id = Column(Integer , ForeignKey('sprint.id'),nullable=True)
    project_id = Column(Integer, ForeignKey('project.id'),nullable=False)
    epic_id = Column(Integer,ForeignKey('epic.id'),default=None)

class TaskInfo(Base):
    __tablename__ = 'task_info'

    id = Column(Integer,ForeignKey('task.id'))
    update_date = Column(DateTime, nullable=True)
    task_status = Column(String,ForeignKey('task.status'),nullable=False)


class Sprint(Base):
    __tablename__ = 'sprint'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc))
    end_date = Column(DateTime, nullable=False)
    done = Column(Boolean , default=False)
    project_id = Column(Integer,ForeignKey('project.id'),nullable=False)


class Epic(Base):
    __tablename__ = 'epic'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey('project.id'),nullable=False)



class UserProject(Base):
    __tablename__ = 'user_project'

    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    project_id = Column(Integer, ForeignKey('project.id'), primary_key=True)












