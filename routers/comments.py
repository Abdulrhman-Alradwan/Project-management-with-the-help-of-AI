from datetime import datetime, timezone
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Path
from starlette import status
from database import SessionLocal
from models import Comment, Reply, User, Task, UserProject, RoleEnum, Project
from routers.auth import get_current_user, check_project_permission

router = APIRouter(
    prefix='/task',
    tags=['task_comments']
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]

class CommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)

class ReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=500)

@router.post("/{task_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment_to_task(
    user: user_dependency,
    db: db_dependency,
    comment_request: CommentRequest,
    task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المستخدم عضو في المشروع
    is_member = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == task.project_id
    ).first()
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # إنشاء التعليق
    comment = Comment(
        content=comment_request.content,
        user_id=user.get('id'),
        task_id=task_id,
        created_at=datetime.now(timezone.utc)
    )

    db.add(comment)
    db.commit()

    return {"message": "Comment added successfully", "comment_id": comment.id}

@router.post("/comments/{comment_id}/replies", status_code=status.HTTP_201_CREATED)
async def add_reply_to_comment(
    user: user_dependency,
    db: db_dependency,
    reply_request: ReplyRequest,
    comment_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود التعليق
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail='Comment not found')

    # التحقق من أن المستخدم عضو في المشروع
    task = db.query(Task).filter(Task.id == comment.task_id).first()
    is_member = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == task.project_id
    ).first()
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # إنشاء الرد
    reply = Reply(
        content=reply_request.content,
        user_id=user.get('id'),
        comment_id=comment_id,
        created_at=datetime.now(timezone.utc)
    )

    db.add(reply)
    db.commit()

    return {"message": "Reply added successfully", "reply_id": reply.id}

@router.get("/{task_id}/comments", status_code=status.HTTP_200_OK)
async def get_task_comments(
    user: user_dependency,
    db: db_dependency,
    task_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # التحقق من وجود المهمة
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # التحقق من أن المستخدم عضو في المشروع
    is_member = db.query(UserProject).filter(
        UserProject.user_id == user.get('id'),
        UserProject.project_id == task.project_id
    ).first()
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You are not a member of this project'
        )

    # جلب جميع التعليقات مع الردود الخاصة بها
    comments = db.query(Comment).filter(Comment.task_id == task_id).all()

    result = []
    for comment in comments:
        comment_data = {
            "id": comment.id,
            "content": comment.content,
            "created_at": comment.created_at,
            "user_id": comment.user_id,
            "user_username": comment.user.username,
            "replies": []
        }

        for reply in comment.replies:
            reply_data = {
                "id": reply.id,
                "content": reply.content,
                "created_at": reply.created_at,
                "user_id": reply.user_id,
                "user_username": reply.user.username
            }
            comment_data["replies"].append(reply_data)

        result.append(comment_data)

    return {"comments": result}


@router.delete("/replies/{reply_id}", status_code=status.HTTP_200_OK)
async def delete_reply(
        user: user_dependency,
        db: db_dependency,
        reply_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # جلب الرد المطلوب
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail='Reply not found')

    # جلب التعليق المرتبط بالرد
    comment = db.query(Comment).filter(Comment.id == reply.comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail='Comment not found')

    # جلب المهمة المرتبطة بالتعليق
    task = db.query(Task).filter(Task.id == comment.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # جلب المشروع المرتبط بالمهمة
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من الصلاحيات:
    # 1. إذا كان المستخدم الحالي هو صاحب الرد
    # 2. أو إذا كان المستخدم الحالي هو صاحب المهمة (العامل المسند إليه)
    # 3. أو إذا كان المستخدم الحالي هو مالك المشروع
    # 4. أو إذا كان المستخدم الحالي مدير المشروع
    has_permission = False

    # 1. صاحب الرد
    if user.get('id') == reply.user_id:
        has_permission = True

    # 2. صاحب المهمة (العامل المسند إليه)
    elif task.worker_id == user.get('id'):
        has_permission = True

    # 3. مالك المشروع
    elif project.owner_id == user.get('id'):
        has_permission = True

    # 4. مدير المشروع
    else:
        # التحقق إذا كان المستخدم مدير في المشروع
        user_project = db.query(UserProject).join(User).filter(
            UserProject.user_id == user.get('id'),
            UserProject.project_id == project.id,
            User.role == RoleEnum.Manager.value
        ).first()
        if user_project:
            has_permission = True

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You do not have permission to delete this reply'
        )

    # حذف الرد
    db.delete(reply)
    db.commit()

    return {"message": "Reply deleted successfully"}


@router.delete("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment(
        user: user_dependency,
        db: db_dependency,
        comment_id: int = Path(gt=0)
):
    if user is None:
        raise HTTPException(status_code=401, detail='Authentication Failed')

    # جلب التعليق
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail='Comment not found')

    # جلب المهمة المرتبطة بالتعليق
    task = db.query(Task).filter(Task.id == comment.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail='Task not found')

    # جلب المشروع المرتبط بالمهمة
    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail='Project not found')

    # التحقق من الصلاحيات:
    # 1. إذا كان المستخدم الحالي هو صاحب التعليق
    # 2. أو إذا كان المستخدم الحالي هو صاحب المهمة (العامل المسند إليه)
    # 3. أو إذا كان المستخدم الحالي هو مالك المشروع
    # 4. أو إذا كان المستخدم الحالي مدير المشروع
    has_permission = False

    # 1. صاحب التعليق
    if user.get('id') == comment.user_id:
        has_permission = True

    # 2. صاحب المهمة (العامل المسند إليه)
    elif task.worker_id == user.get('id'):
        has_permission = True

    # 3. مالك المشروع
    elif project.owner_id == user.get('id'):
        has_permission = True

    # 4. مدير المشروع
    else:
        # التحقق إذا كان المستخدم مدير في المشروع
        user_project = db.query(UserProject).join(User).filter(
            UserProject.user_id == user.get('id'),
            UserProject.project_id == project.id,
            User.role == RoleEnum.Manager.value
        ).first()
        if user_project:
            has_permission = True

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='You do not have permission to delete this comment'
        )

    # حذف جميع الردود المرتبطة بالتعليق أولاً
    db.query(Reply).filter(Reply.comment_id == comment_id).delete()

    # حذف التعليق نفسه
    db.delete(comment)
    db.commit()

    return {"message": "Comment and its replies deleted successfully"}

