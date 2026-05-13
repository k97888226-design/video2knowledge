import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .config import settings
from .api.routes import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"启动 {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}")

    for dir_path in [
        settings.DOWNLOAD_DIR,
        settings.OUTPUT_DIR,
        settings.TEMP_DIR,
        settings.MODELS_DIR,
    ]:
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"工作目录就绪: {dir_path}")

    logger.info(f"API地址: http://{settings.HOST}:{settings.PORT}{settings.API_PREFIX}")
    logger.info(f"API文档: http://{settings.HOST}:{settings.PORT}/docs")

    yield

    logger.info(f"关闭 {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "src"
if frontend_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(frontend_dir), html=True), name="ui")


@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "description": settings.PROJECT_DESCRIPTION,
        "docs": "/docs",
        "api_prefix": settings.API_PREFIX,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info",
    )
