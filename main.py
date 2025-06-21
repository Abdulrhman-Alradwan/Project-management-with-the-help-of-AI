from fastapi import FastAPI
import models
from database import engine
from routers import auth, projects, epics, tasks, sprints

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(epics.router)
app.include_router(tasks.router)
app.include_router(sprints.router)


