"""
摄像头配置注册表 —— 持久化到 data/cameras/{camera_id}.json，并在内存做缓存。

"注册表"的作用：管理所有已登记的摄像头。
- 内存里用字典 CAMERAS 做缓存，加速读取；
- 磁盘上把每个摄像头存成 data/cameras/{camera_id}.json，重启后也不丢。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.camera.identifiers import validate_camera_id
from app.camera.models import CameraInfo
from app.core.config import get_settings
from app.services.storage_service import StorageService

# 全局内存缓存：camera_id -> CameraInfo
CAMERAS: dict[str, CameraInfo] = {}
VIRTUAL_CAMERA_ID = "virtual-test-camera"


def _virtual_camera() -> CameraInfo:
    return CameraInfo(
        camera_id=VIRTUAL_CAMERA_ID,
        name="测试摄像头（虚拟）",
        stream_url="virtual://black",
        protocol="http",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class CameraRegistry:
    def __init__(self, storage: StorageService | None = None) -> None:
        # 没传 storage 就用默认的 StorageService（负责读写磁盘 JSON）
        self._storage = storage or StorageService()

    @property
    def cameras_dir(self) -> Path:
        # 摄像头配置存放目录
        root = get_settings().resolved_cameras_dir.resolve(strict=False)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _camera_path(self, camera_id: str) -> Path:
        # 拼出某个摄像头的 JSON 文件路径
        safe_id = validate_camera_id(camera_id)
        root = self.cameras_dir
        candidate = (root / f"{safe_id}.json").resolve(strict=False)
        if candidate.parent != root:
            raise ValueError("camera path escapes configured cameras directory")
        return candidate

    def create(
        self,
        camera_id: str,
        name: str,
        stream_url: str,
        protocol: str,
        username: str | None = None,
        password: str | None = None,
    ) -> CameraInfo:
        # 构造一条摄像头记录，写入磁盘并放入内存缓存
        camera_id = validate_camera_id(camera_id)
        camera = CameraInfo(
            camera_id=camera_id,
            name=name,
            stream_url=stream_url,
            protocol=protocol,
            username=username,
            password=password,
            created_at=datetime.now(UTC),
        )
        path = self._camera_path(camera_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with path.open("x", encoding="utf-8") as handle:
            json.dump(camera.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
        CAMERAS[camera_id] = camera
        return camera

    def get(self, camera_id: str) -> CameraInfo | None:
        if camera_id == VIRTUAL_CAMERA_ID:
            return _virtual_camera()
        try:
            camera_id = validate_camera_id(camera_id)
        except ValueError:
            return None
        # Resolve on every read so configuration-root changes and symlinks cannot
        # reuse an earlier cached credential-bearing registration.
        try:
            path = self._camera_path(camera_id)
        except ValueError:
            return None
        if not path.exists():
            return None

        camera = CameraInfo.model_validate(self._storage.read_json(path))
        if camera.camera_id != camera_id:
            return None
        CAMERAS[camera_id] = camera
        return camera

    def list_all(self) -> list[CameraInfo]:
        result: list[CameraInfo] = []
        # 遍历目录下所有 .json，逐个解析成摄像头对象
        for path in sorted(self.cameras_dir.glob("*.json")) if self.cameras_dir.exists() else []:
            try:
                # Resolve the discovered entry before opening it.  A symlink
                # placed inside the configured directory must not make the
                # registry read arbitrary files elsewhere.
                safe_path = self._camera_path(path.stem)
                if safe_path != path.resolve(strict=False):
                    continue
                data = self._storage.read_json(safe_path)
                camera = CameraInfo.model_validate(data)
                if camera.camera_id != path.stem:
                    continue
                CAMERAS[camera.camera_id] = camera
                result.append(camera)
            except Exception:
                # 单个文件损坏不影响其他，跳过
                pass
        if not any(camera.camera_id == VIRTUAL_CAMERA_ID for camera in result):
            result.insert(0, _virtual_camera())
        return result

    def delete(self, camera_id: str) -> bool:
        # 从内存和磁盘都删除
        if camera_id == VIRTUAL_CAMERA_ID:
            return False
        try:
            path = self._camera_path(camera_id)
        except ValueError:
            return False
        CAMERAS.pop(camera_id, None)
        return self._storage.delete_path(path)

    def update(self, camera_id: str, new_camera_id: str, name: str) -> CameraInfo | None:
        try:
            camera_id = validate_camera_id(camera_id)
            new_camera_id = validate_camera_id(new_camera_id)
        except ValueError:
            return None
        camera = self.get(camera_id)
        if camera is None:
            return None

        updated = camera.model_copy(update={"camera_id": new_camera_id, "name": name})
        if new_camera_id != camera_id:
            new_path = self._camera_path(new_camera_id)
            if new_path.exists():
                raise FileExistsError(f"camera {new_camera_id} already exists")
            import json

            # Publish the new record before removing the old one.  A failed
            # write therefore leaves the original registration usable.
            with new_path.open("x", encoding="utf-8") as handle:
                json.dump(updated.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
            try:
                self._storage.delete_path(self._camera_path(camera_id))
            except Exception:
                self._storage.delete_path(new_path)
                raise
        else:
            self._storage.write_json(self._camera_path(new_camera_id), updated.model_dump(mode="json"))
        CAMERAS.pop(camera_id, None)
        CAMERAS[new_camera_id] = updated
        return updated

    def exists(self, camera_id: str) -> bool:
        # 用 get 判断是否存在
        return self.get(camera_id) is not None


# 全局单例：整个程序共用一个注册表对象
camera_registry = CameraRegistry()
