from database import Base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from datetime import datetime , timezone



class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True , index=True)
    first_name = Column(String,nullable=False)
    last_name = Column(String,nullable=False)
    email = Column(String,unique=True)
    hashed_password = Column(String,nullable=False)
    role = Column(String,nullable=False)
    job_title = Column(String,nullable=True)
    username = Column(String,unique=True,nullable=False)
    gender = Column(String,nullable=False)
    age = Column(Integer,nullable=False)


class Project(Base):
    __tablename__ = 'project'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc),nullable=False)
    end_date = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    description = Column(String,nullable=True)
    complete = Column(Boolean , default=False)
    owner_id = Column(Integer, ForeignKey('user.id'), nullable=False)

class TodoCategory(Base):
    __tablename__ = 'todo_category'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    teamleader_id = Column(Integer, ForeignKey('user.id'))
    project_id = Column(Integer, ForeignKey('project.id'))

    __table_args__ = (
        UniqueConstraint('teamleader_id', 'project_id', name='_user_project_todo_uc'),
    )


class Todo(Base):
    __tablename__ = 'todo'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc))
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    description = Column(String,nullable=True)
    priority = Column(Integer,nullable=False)
    complete = Column(Boolean , default=False)
    report = Column(String,nullable=True)
    project_id = Column(Integer, ForeignKey('project.id'))
    teamleader_id = Column(Integer, ForeignKey('user.id'))
    category_id = Column(Integer, ForeignKey('todo_category.id'))

    """__table_args__ = (
        UniqueConstraint('organizer_id', 'project_id', name='_user_project_todo_uc'),
    )"""



class Task(Base):
    __tablename__ = 'task'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String,nullable=False)
    create_date = Column(DateTime, default=datetime.now(timezone.utc))
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    deadline = Column(DateTime, nullable=True)
    task_number = Column(Integer, nullable=False, default=1)
    status = Column(String,default='available')
    dependent_on = Column(Integer,nullable=True)
    dependency_type = Column(String, default='None')
    comments = Column(String, nullable=True)
    todo_id = Column(Integer, ForeignKey('todo.id'))
    worker_id = Column(Integer, ForeignKey('user.id'))


class UserProject(Base):
    __tablename__ = 'user_project'

    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    project_id = Column(Integer, ForeignKey('project.id'), primary_key=True)












