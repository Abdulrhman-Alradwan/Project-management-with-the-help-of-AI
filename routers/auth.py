from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException , UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette import status
from models import User, RoleEnum, GenderEnum, Project, UserProject
from passlib.context import CryptContext
from database import  SessionLocal
from fastapi.security import OAuth2PasswordRequestForm , OAuth2PasswordBearer
from jose import jwt , JWTError
import os




router = APIRouter(
    prefix='/auth',
    tags=['auth']
)


SECRET_KEY = '7234e33543197289c85448fe3de37e86f0da99907a3ad989ba4b03ca17e11bd6'
ALGORITHM = 'HS256'

PROFILE_PICTURES_DIR = "static/profile_pictures"
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/jpg"]
Path(PROFILE_PICTURES_DIR).mkdir(parents=True, exist_ok=True)

bcrypt_context = CryptContext(schemes=['bcrypt'] , deprecated = 'auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')


class CreateUserRequest(BaseModel):

    first_name : str = Field(min_length=3 , max_length=20)
    last_name : str = Field(min_length=3 , max_length=20)
    email : str
    password : str
    role: RoleEnum
    job_title : Optional[str] = None
    username : str = Field(min_length=3 , max_length=20)
    gender: GenderEnum
    age : int = Field(gt=17, lt=75)

    class Config:
        use_enum_values = True


class Token(BaseModel):

    access_token : str
    token_type : str



def get_db():
    db = SessionLocal()
    try:
        yield  db
    finally:
        db.close()


db_dependency = Annotated[Session , Depends(get_db)]


def authenticate_user(username : str , password : str , db):
    user = db.query(User).filter(User.username == username).first()
    if not user :
        return False
    if not bcrypt_context.verify(password , user.hashed_password):
        return False
    return user

def create_access_token(username : str , user_id : int , expires_delta : timedelta):
    encode = { 'sub' : username , 'id' : user_id}
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp' : expires})
    return jwt.encode(encode , SECRET_KEY , algorithm=ALGORITHM)

async def get_current_user(token : Annotated[str , Depends(oauth2_bearer)]):
    try :
        payload = jwt.decode(token , SECRET_KEY ,algorithms=ALGORITHM)
        username : str = payload.get('sub')
        user_id : int = payload.get('id')
        if username is None or user_id is None :
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not Validate user.')
        db = SessionLocal()
        user = db.query(User).filter(User.id == user_id).first()
        db.close()

        if not user:
            raise HTTPException(status_code=404, detail='User not found')

        return {'username' : username , 'id' : user_id , "role": user.role.value}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not Validate user.')


def check_project_permission(db: Session, user_id: int, project_id: int):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return False

    if project.owner_id == user_id:
        return True

    user_project = db.query(UserProject).join(User).filter(
        UserProject.user_id == user_id,
        UserProject.project_id == project_id,
        User.role == RoleEnum.Manager.value
    ).first()

    return user_project is not None



@router.post("/", status_code= status.HTTP_201_CREATED )
async def create_user(db : db_dependency ,
                      create_user_request : CreateUserRequest):


    create_user_model = User(

        first_name = create_user_request.first_name ,
        last_name = create_user_request.last_name ,
        email = create_user_request.email ,
        hashed_password = bcrypt_context.hash(create_user_request.password) ,
        role=create_user_request.role,
        job_title = create_user_request.job_title ,
        username = create_user_request.username ,
        gender=create_user_request.gender,
        age = create_user_request.age

    )

    db.add(create_user_model)
    db.commit()


@router.post("/token",response_model=Token)
async def login_for_access_token(form_data : Annotated[OAuth2PasswordRequestForm , Depends()],
                                 db : db_dependency):
    user = authenticate_user(form_data.username , form_data.password , db)
    if not user :
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not Validate user.')
    token = create_access_token(user.username , user.id ,timedelta(minutes=15))
    return {'access_token' : token , 'token_type' : 'bearer'}


@router.put("/users/{user_id}/profile-picture")
async def upload_profile_picture(
    user_id: int,
    db : db_dependency,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # التحقق من نوع الملف
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, JPG, or PNG images are allowed."
        )

    # التحقق من وجود المستخدم
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # التحقق من الصلاحية
    if current_user['id'] != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")

    # حذف الصورة القديمة إن وجدت
    if user.profile_picture:
        old_file_path = os.path.join(PROFILE_PICTURES_DIR, user.profile_picture.split('/')[-1])
        if os.path.exists(old_file_path):
            os.remove(old_file_path)

    # حفظ الصورة الجديدة
    file_extension = file.filename.split('.')[-1]
    unique_filename = f"user_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_extension}"
    file_path = os.path.join(PROFILE_PICTURES_DIR, unique_filename)
    db_file_path = os.path.join("profile_pictures", unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # تحديث قاعدة البيانات
    user.profile_picture = db_file_path
    db.commit()

    return {"message": "Profile picture updated successfully", "file_path": db_file_path}