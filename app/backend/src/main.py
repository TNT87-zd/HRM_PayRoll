import importlib.util
import logging
from contextlib import asynccontextmanager
import mimetypes
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from config import PROJECT_ROOT, Settings
from database import Base, open_database
from repository import seed_employees
from routers import analytics, auth, employees, kiosk, ws
from services.enrollment_service import EnrollmentService
from services.face_service import FaceService
from cv.head_pose import PoseEstimator
from hrm import store as workflow_store
from hrm.api import router as workflow_router
from hrm.auth import router as workflow_auth_router

logger = logging.getLogger("uvicorn.error")
mimetypes.init()
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")

def create_app(settings=None, face_engine=None, pose_estimator=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application):
        settings.storage_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        engine, factory = open_database(settings.database_url)
        Base.metadata.create_all(engine)
        application.state.engine, application.state.session_factory = engine, factory
        with factory() as db:
            seed_employees(db, settings)
        face = FaceService(settings, factory, engine=face_engine)
        application.state.face = face
        face.startup()
        face.import_legacy_gallery()
        estimator = pose_estimator or PoseEstimator(settings.landmark_model)
        enrollment = EnrollmentService(settings, factory, face, estimator)
        application.state.enrollment = enrollment
        with factory() as db:
            enrollment.cleanup(db)
        application.state.dummy_password_hash = auth.hash_password("invalid-login-password")
        yield
        if hasattr(estimator, "close"):
            estimator.close()
        engine.dispose()

    application = FastAPI(title="HRM Payroll API", lifespan=lifespan)
    application.state.settings = settings
    application.state.login_attempts = {}

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            try:
                auth.same_origin(request)
            except Exception as exc:
                if hasattr(exc, "status_code"):
                    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
                raise
            content_length = request.headers.get("content-length", "0")
            if content_length.isdigit() and int(content_length) > 55 * 1024 * 1024:
                return JSONResponse({"detail": "Yêu cầu vượt giới hạn dung lượng"}, status_code=413)
        token = analytics.repository_factory.set(getattr(application.state, "session_factory", None))
        workflow_token = workflow_store.context.set((getattr(application.state, "session_factory", None), settings))
        try:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            analytics.repository_factory.reset(token)
            workflow_store.context.reset(workflow_token)

    application.include_router(auth.router)
    application.include_router(workflow_router)
    application.include_router(workflow_auth_router)
    application.include_router(employees.router, prefix="/api/employees", tags=["employees"])
    application.include_router(kiosk.router, prefix="/api/kiosk", tags=["kiosk"])
    application.include_router(analytics.router, dependencies=[Depends(auth.require_hr)])
    application.include_router(ws.router)

    @application.get("/api/health")
    def health(request: Request):
        face = request.app.state.face
        return {"status": "ok", "engine_ready": face.engine is not None, "engine_error": face.error,
                "pose_model_available": settings.landmark_model.is_file() and importlib.util.find_spec("mediapipe") is not None,
                "web_assets_available": (PROJECT_ROOT / "app/frontend/vendor/mediapipe/vision_bundle.mjs").is_file(),
                "gallery_size": len(face.gallery), "gallery_version": face.gallery_version,
                "preprocessing_policy": "baseline", "liveness_enabled": False,
                "threshold": settings.threshold, "min_margin": settings.min_margin}

    @application.get("/api/face-assets/face_landmarker.task", include_in_schema=False)
    def landmark_asset():
        if not settings.landmark_model.is_file():
            return JSONResponse({"detail": "Thiếu model. Chạy app/backend/scripts/setup_face_assets.py"}, status_code=503)
        return FileResponse(settings.landmark_model, media_type="application/octet-stream")

    application.mount("/", StaticFiles(directory=str(PROJECT_ROOT / "app/frontend"), html=True), name="frontend")
    return application


app = create_app()
