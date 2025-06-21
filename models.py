from database import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import validates , relationship
from datetime import datetime, timezone
import re  # لاستخدام التعابير النمطية للتحقق من صيغة الإيميل
from enum import Enum as PyEnum



class RoleEnum(str ,PyEnum):
    Manager = "Manager"
    Tester = "Tester"
    User = "User"

class GenderEnum(str, PyEnum):
    Male = "Male"
    Female = "Female"

class PriorityEnum(str, PyEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class SprintDuration(PyEnum):
    ONE_WEEK = "1week"
    TWO_WEEKS = "2weeks"
    THREE_WEEKS = "3weeks"
    FOUR_WEEKS = "4weeks"


class TaskStatus(str, PyEnum):
    NOT_AVAILABLE = "not available"
    AVAILABLE = "available"
    WAIT = "wait"
    COMPLETE = "complete"
    TESTING = "testing"
    IN_PROGRESS = "in progress"
    FEEDBACK = "feedback"

class DependencyType(str, PyEnum):
    NONE = "None"
    FS = "FS"  # Finish-to-Start
    SS = "SS"  # Start-to-Start




class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True , index=True)
    first_name = Column(String,nullable=False)
    last_name = Column(String,nullable=False)
    profile_picture = Column(String, nullable=True)
    email = Column(String,unique=True,nullable=False)
    hashed_password = Column(String,nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    job_title = Column(String,nullable=True)
    username = Column(String,unique=True,nullable=False)
    gender = Column(Enum(GenderEnum), nullable=False)
    age = Column(Integer,nullable=False)

    owned_projects = relationship("Project", back_populates="owner")
    projects = relationship("UserProject", back_populates="user")
    tasks = relationship("Task", back_populates="worker")




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

    owner = relationship("User", back_populates="owned_projects")
    users = relationship("UserProject", back_populates="project")
    tasks = relationship("Task", back_populates="project")
    sprints = relationship("Sprint", back_populates="project")
    epics = relationship("Epic", back_populates="project")



class Task(Base):
    __tablename__ = 'task'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc))
    """start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)"""
    status = Column(Enum(TaskStatus), default=TaskStatus.NOT_AVAILABLE)
    dependent_on = Column(Integer,nullable=True)
    dependency_type = Column(Enum(DependencyType), default=DependencyType.NONE)
    comments = Column(String, nullable=True)
    priority = Column(Enum(PriorityEnum), nullable=False, default=PriorityEnum.MEDIUM)
    worker_id = Column(Integer, ForeignKey('user.id'),nullable=True)
    sprint_id = Column(Integer , ForeignKey('sprint.id'),nullable=True)
    project_id = Column(Integer, ForeignKey('project.id'),nullable=False)
    epic_id = Column(Integer,ForeignKey('epic.id'),default=None)

    worker = relationship("User", back_populates="tasks")
    project = relationship("Project", back_populates="tasks")
    sprint = relationship("Sprint", back_populates="tasks")
    epic = relationship("Epic", back_populates="tasks")
    info = relationship("TaskInfo", back_populates="task", uselist=False)

class TaskInfo(Base):
    __tablename__ = 'task_info'

    id = Column(Integer, primary_key=True, index=True)
    task_num = Column(Integer,ForeignKey('task.id'))
    update_date = Column(DateTime, nullable=True)
    task_status = Column(String,nullable=False)


    task = relationship("Task", back_populates="info")


class Sprint(Base):
    __tablename__ = 'sprint'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    duration = Column(Enum(SprintDuration), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))  # وقت الإنشاء
    start_date = Column(DateTime, nullable=True)  # null حتى يتم الإطلاق
    end_date = Column(DateTime, nullable=True)  # null حتى يتم الإطلاق
    is_active = Column(Boolean, default=False)  # يصبح True عند الإطلاق
    is_completed = Column(Boolean, default=False)
    project_id = Column(Integer, ForeignKey('project.id'), nullable=False)

    project = relationship("Project", back_populates="sprints")
    tasks = relationship("Task", back_populates="sprint")


class Epic(Base):
    __tablename__ = 'epic'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    project_id = Column(Integer, ForeignKey('project.id'),nullable=False)

    project = relationship("Project", back_populates="epics")
    tasks = relationship("Task", back_populates="epic")




class UserProject(Base):
    __tablename__ = 'user_project'

    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    project_id = Column(Integer, ForeignKey('project.id'), primary_key=True)

    user = relationship("User", back_populates="projects")
    project = relationship("Project", back_populates="users")












