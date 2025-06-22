from fastapi import FastAPI
import models
from database import engine, SessionLocal
from routers import auth, projects, epics, tasks, sprints, comments
from routers.sprints import check_sprint_expiration
from contextlib import asynccontextmanager
import asyncio



@asynccontextmanager
async def lifespan(app: FastAPI):
    # بدء المهمة الخلفية عند التشغيل
    db = SessionLocal()
    asyncio.create_task(check_sprint_expiration(db))
    yield
    # تنظيف عند الإيقاف (اختياري)
    db.close()

app = FastAPI(lifespan=lifespan)

models.Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(epics.router)
app.include_router(tasks.router)
app.include_router(sprints.router)
app.include_router(comments.router)



