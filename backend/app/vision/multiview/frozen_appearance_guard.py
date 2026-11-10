"""Conservative same-camera clothing evidence tied to confirmed roster anchors."""
from collections import defaultdict

from app.vision.player_tracking_engine.player_appearance import AppearanceTemplateGallery


class FrozenAppearanceGuard:
    version = "frozen-central-clothing.v2"
    enrollment_ms = 10000
    sample_period_ms = 1000
    margin = .05
    max_distance = .16

    def __init__(self):
        self.galleries = defaultdict(dict)
        self.last_sample = {}
        self.pending = {}

    def enroll(self, *, global_id, view_id, descriptor, timestamp_ms, anchor_ms):
        if not 0 <= timestamp_ms - anchor_ms <= self.enrollment_ms:
            return False
        if descriptor is None or descriptor.extractor_version != "clothing-central-hsv-lab.v2" or descriptor.status != "available" or descriptor.quality.score < .4:
            return False
        key = (global_id, view_id)
        if timestamp_ms - self.last_sample.get(key, float('-inf')) < self.sample_period_ms:
            return False
        gallery = self.galleries[global_id].setdefault(view_id, AppearanceTemplateGallery())
        if not gallery.update(descriptor, confirmed_observed=True):
            return False
        self.last_sample[key] = timestamp_ms
        return True

    def distances(self, observation, global_ids):
        descriptor = observation.appearance_descriptor
        if descriptor is None or descriptor.extractor_version != "clothing-central-hsv-lab.v2" or descriptor.status != "available" or descriptor.quality.score < .4:
            return {}
        distances = {}
        for gid in global_ids:
            gallery = self.galleries.get(gid, {}).get(observation.view_id)
            if gallery is not None and gallery.accepted_updates >= 3:
                distance = gallery.distance_to(descriptor)
                if distance is not None:
                    distances[gid] = distance
        return distances

    def owner(self, observation, global_ids, tick):
        distances = self.distances(observation, global_ids)
        ranked = sorted(distances, key=distances.get)
        key = (observation.view_id, observation.track_id, observation.local_identity_epoch)
        if len(ranked) < 2 or distances[ranked[0]] > self.max_distance or distances[ranked[1]] - distances[ranked[0]] < self.margin:
            self.pending.pop(key, None)
            return None
        winner = ranked[0]
        prior = self.pending.get(key)
        count = prior[2] + 1 if prior and prior[0] == winner and prior[1] == tick - 1 else 1
        self.pending[key] = (winner, tick, count)
        return winner if count >= 3 else None

    def expire(self, tick):
        self.pending = {k: v for k, v in self.pending.items() if tick - v[1] <= 60}
