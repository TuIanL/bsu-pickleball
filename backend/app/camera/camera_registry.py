"""
摄像头配置注册表 —— 持久化到 data/cameras/{camera_id}.json，并在内存做缓存。

"注册表"的作用：管理所有已登记的摄像头。
- 内存里用字典 CAMERAS 做缓存，加速读取；
- 磁盘上把每个摄像头存成 data/cameras/{camera_id}.json，重启后也不丢。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.camera.models import CameraInfo
from app.services.storage_service import StorageService


# 全局内存缓存：camera_id -> CameraInfo
CAMERAS: dict[str, CameraInfo] = {}


class CameraRegistry:
    def __init__(self, storage: StorageService | None = None) -> None:
        # 没传 storage 就用默认的 StorageService（负责读写磁盘 JSON）
        self._storage = storage or StorageService()

    @property
    def cameras_dir(self) -> Path:
        # 摄像头配置存放目录
        return Path("data/cameras")

    def _camera_path(self, camera_id: str) -> Path:
        # 拼出某个摄像头的 JSON 文件路径
        return self.cameras_dir / f"{camera_id}.json"

    def create(self, camera_id: str, name: str, stream_url: str, protocol: str, username: str | None = None, password: str | None = None) -> CameraInfo:
        # 构造一条摄像头记录，写入磁盘并放入内存缓存
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
        # 先查内存缓存，命中直接返回
        cached = CAMERAS.get(camera_id)
        if cached is not None:
            return cached

        # 缓存未命中再读磁盘
        path = self._camera_path(camera_id)
        if not path.exists():
            return None

        camera = CameraInfo.model_validate(self._storage.read_json(path))
        CAMERAS[camera_id] = camera
        return camera

    def list_all(self) -> list[CameraInfo]:
        # 目录不存在就返回空列表
        if not self.cameras_dir.exists():
            return []

        result: list[CameraInfo] = []
        # 遍历目录下所有 .json，逐个解析成摄像头对象
        for path in sorted(self.cameras_dir.glob("*.json")):
            try:
                data = self._storage.read_json(path)
                camera = CameraInfo.model_validate(data)
                CAMERAS[camera.camera_id] = camera
                result.append(camera)
            except Exception:
                # 单个文件损坏不影响其他，跳过
                pass
        return result

    def delete(self, camera_id: str) -> bool:
        # 从内存和磁盘都删除
        path = self._camera_path(camera_id)
        CAMERAS.pop(camera_id, None)
        return self._storage.delete_path(path)

    def update(self, camera_id: str, new_camera_id: str, name: str) -> CameraInfo | None:
        camera = self.get(camera_id)
        if camera is None:
            return None

        updated = camera.model_copy(update={"camera_id": new_camera_id, "name": name})
        if new_camera_id != camera_id:
            self._storage.delete_path(self._camera_path(camera_id))
        self._storage.write_json(self._camera_path(new_camera_id), updated.model_dump(mode="json"))
        CAMERAS.pop(camera_id, None)
        CAMERAS[new_camera_id] = updated
        return updated

    def exists(self, camera_id: str) -> bool:
        # 用 get 判断是否存在
        return self.get(camera_id) is not None


# 全局单例：整个程序共用一个注册表对象
camera_registry = CameraRegistry()
