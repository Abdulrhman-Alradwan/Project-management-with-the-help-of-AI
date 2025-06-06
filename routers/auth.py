from datetime import timedelta, datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette import status
from models import User
from passlib.context import CryptContext
from database import  SessionLocal
from fastapi.security import OAuth2PasswordRequestForm , OAuth2PasswordBearer
from jose import jwt , JWTError




router = APIRouter(
    prefix='/auth',
    tags=['auth']
)


SECRET_KEY = '7234e33543197289c85448fe3de37e86f0da99907a3ad989ba4b03ca17e11bd6'
ALGORITHM = 'HS256'


bcrypt_context = CryptContext(schemes=['bcrypt'] , deprecated = 'auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')


class CreateUserRequest(BaseModel):

    first_name : str = Field(min_length=3 , max_length=20)
    last_name : str = Field(min_length=3 , max_length=20)
    email : str
    password : str
    role : str
    job_title : Optional[str] = None
    username : str = Field(min_length=3 , max_length=20)
    gender : str
    age : int = Field(gt=17, lt=75)


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
        return {'username' : username , 'id' : user_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail='Could not Validate user.')



@router.post("/", status_code= status.HTTP_201_CREATED )
async def create_user(db : db_dependency ,
                      create_user_request : CreateUserRequest):
    create_user_model = User(

        first_name = create_user_request.first_name ,
        last_name = create_user_request.last_name ,
        email = create_user_request.email ,
        hashed_password = bcrypt_context.hash(create_user_request.password) ,
        role = create_user_request.role ,
        job_title = create_user_request.job_title ,
        username = create_user_request.username ,
        gender = create_user_request.gender ,
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