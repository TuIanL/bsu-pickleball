# Footpoint Estimator

## Purpose

将脚点估计从单一的 `bbox_bottom_center` 升级为多策略 hybrid 方法，优先使用姿态关键点推算真实脚位，降低因检测框偏移导致的投影误差。

## Strategy Priority

```
1. pose_ankle_midpoint: 双踝可见且置信度 ≥ 0.35
2. pose_single_ankle: 单踝可见
3. knee_extrapolated: 双膝可见且置信度 ≥ 0.4，从膝向下外推 KNEE_TO_FOOT_RATIO 身高比例
4. bbox_bottom_center: fallback
```

## Keypoint Index（COCO）

| 关键点 | 索引 |
|--------|------|
| left_ankle | 15 |
| right_ankle | 16 |
| left_knee | 13 |
| right_knee | 14 |

## Decision Logic

```python
def _estimate_from_pose(self, keypoints: dict) -> FootpointEstimate | None:
    left_ankle = keypoints.get(15)
    right_ankle = keypoints.get(16)

    # 双踝可用
    if (left_ankle and left_ankle.confidence >= 0.35
            and right_ankle and right_ankle.confidence >= 0.35):
        return FootpointEstimate(
            image_footpoint=midpoint(left_ankle.xy, right_ankle.xy),
            method="pose_ankle_midpoint",
            confidence=min(left_ankle.confidence, right_ankle.confidence),
        )

    # 单踝可用
    single = None
    if left_ankle and left_ankle.confidence >= 0.35:
        single = left_ankle
    elif right_ankle and right_ankle.confidence >= 0.35:
        single = right_ankle
    if single:
        return FootpointEstimate(
            image_footpoint=single.xy,
            method="pose_ankle_single",
            confidence=single.confidence,
        )

    # 膝外推
    left_knee = keypoints.get(13)
    right_knee = keypoints.get(14)
    if (left_knee and left_knee.confidence >= 0.4
            and right_knee and right_knee.confidence >= 0.4):
        knee_mid = midpoint(left_knee.xy, right_knee.xy)
        # 估算脚在膝下方一定距离
        foot_y = knee_mid[1] + (knee_mid[1] - _get_neck_y(keypoints)) * KNEE_TO_FOOT_RATIO
        return FootpointEstimate(
            image_footpoint=[knee_mid[0], foot_y],
            method="knee_extrapolated",
            confidence=min(left_knee.confidence, right_knee.confidence) * 0.8,
        )

    return None  # pose 不可用
```

## Constants

```python
ANKLE_CONF_THRESHOLD = 0.35
KNEE_CONF_THRESHOLD = 0.4
KNEE_TO_FOOT_RATIO = 0.28  # 膝到脚占身高的估算比例
```

## FootpointEstimate

```python
@dataclass
class FootpointEstimate:
    image_footpoint: list[float]
    method: str            # "bbox_bottom_center" | "pose_ankle_midpoint" | "pose_ankle_single" | "knee_extrapolated"
    confidence: float | None = None
```

## Integration

`FootpointEstimator.estimate()` 增加 `pose_keypoints` 参数：

```python
class FootpointEstimator:
    def estimate(self, bbox_or_track, pose_keypoints=None) -> FootpointEstimate
```

调用方（PlayerProjector）传入姿态数据；若姿态不可用，行为与之前完全一致。
