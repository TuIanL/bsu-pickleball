"""Bounded, per-view playback shards derived from immutable full overlay evidence."""
from __future__ import annotations

import json
import math
import os
import uuid
from pathlib import Path

CHUNK_SECONDS = 20


def _signature(path):
    stat = path.stat()
    return f"{stat.st_size}-{stat.st_mtime_ns}"


def _atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_overlay_playback(path: Path, payload: dict, *, artifact_name: str):
    """Publish the index last; a reader never observes partially written shards."""
    if not payload.get('views'):
        return
    signature = _signature(path)
    directory = path.with_suffix('.playback') / signature
    metadata = {key: value for key, value in payload.items() if key not in {'frames', 'views', 'diagnostics'}}
    metadata['frames'] = []
    metadata['views'] = {view: {**{k: v for k, v in item.items() if k != 'frames'}, 'frames': []}
                         for view, item in payload['views'].items()}
    chunks = {}
    for ordinal, (view, item) in enumerate(payload['views'].items()):
        grouped = {}
        for frame in item.get('frames', []):
            bucket = math.floor(float(frame['timestamp_seconds']) / CHUNK_SECONDS)
            grouped.setdefault(bucket, []).append(frame)
        chunks[view] = {}
        for bucket, frames in grouped.items():
            relative = f'view-{ordinal}-{bucket}.json'
            _atomic(directory / relative, {'frames': frames})
            chunks[view][str(bucket)] = relative
    metadata['playback'] = {
        'schema_version': 'overlay-playback.v1', 'chunk_seconds': CHUNK_SECONDS,
        'generation': signature,
        'url': f"/api/analysis/jobs/{payload['job_id']}/artifacts/{artifact_name}",
        'chunks': {view: sorted(map(int, values)) for view, values in chunks.items()},
    }
    _atomic(path.with_suffix('.playback') / 'manifest.json',
            {'source_signature': signature, 'metadata': metadata, 'chunks': chunks})


def read_playback_manifest(path: Path):
    try:
        with (path.with_suffix('.playback') / 'manifest.json').open(encoding='utf-8') as handle:
            manifest = json.load(handle)
        return manifest if manifest['source_signature'] == _signature(path) else None
    except (OSError, ValueError, KeyError):
        return None


def playback_chunk_path(path: Path, manifest, *, view_id: str, chunk: int):
    filename = manifest['chunks'].get(view_id, {}).get(str(chunk))
    if filename is None:
        return None
    return path.with_suffix('.playback') / manifest['source_signature'] / filename
