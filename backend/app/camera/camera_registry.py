"""摄像头配置注册表 —— 持久化到 data/cameras/{camera_id}.json，内存缓存。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.camera.models import CameraInfo
from app.services.storage_service import StorageService


CAMERAS: dict[str, CameraInfo] = {}


class CameraRegistry:
    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or StorageService()

    @property
    def cameras_dir(self) -> Path:
        return Path("data/cameras")

    def _camera_path(self, camera_id: str) -> Path:
        return self.cameras_dir / f"{camera_id}.json"

    def create(self, camera_id: str, name: str, stream_url: str, protocol: str, username: str | None = None, password: str | None = None) -> CameraInfo:
        camera = CameraInfo(
            camera_id=camera_id,
            name=name,
            stream_url=stream_url,
            protocol=protocol,
            username=username,
            password=password,
            created_at=datetime.now(timezone.utc),
        )
        self._storage.write_json(self._camera_path(camera_id), camera.model_dump(mode="json"))
        CAMERAS[camera_id] = camera
        return camera

    def get(self, camera_id: str) -> CameraInfo | None:
        cached = CAMERAS.get(camera_id)
        if cached is not None:
            return cached

        path = self._camera_path(camera_id)
        if not path.exists():
            return None

        camera = CameraInfo.model_validate(self._storage.read_json(path))
        CAMERAS[camera_id] = camera
        return camera

    def list_all(self) -> list[CameraInfo]:
        if not self.cameras_dir.exists():
            return []

        result: list[CameraInfo] = []
        for path in sorted(self.cameras_dir.glob("*.json")):
            try:
                data = self._storage.read_json(path)
                camera = CameraInfo.model_validate(data)
                CAMERAS[camera.camera_id] = camera
                result.append(camera)
            except Exception:
                pass
        return result

    def delete(self, camera_id: str) -> bool:
        path = self._camera_path(camera_id)
        CAMERAS.pop(camera_id, None)
        return self._storage.delete_path(path)

    def exists(self, camera_id: str) -> bool:
        return self.get(camera_id) is not None


camera_registry = CameraRegistry()
