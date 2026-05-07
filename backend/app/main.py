from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analysis import router as analysis_router

app = FastAPI(
    title="Pre Pickleball Analysis API",
    version="0.1.0",
    description="Lightweight API foundation for future YOLO11 and RTMPose26 video analysis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

app.include_router(analysis_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
