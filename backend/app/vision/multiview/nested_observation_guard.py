"""Reject ambiguous partial-person evidence inside a stronger same-frame body.

This is an abstention, not an identity transfer: a covered box can represent
either a duplicate detection or an occluded player. Neither supports a second
independent identity measurement until it separates from the containing body.
"""
from math import isfinite

VERSION = 'same-view-containment.v1'
NET_CROWD_VERSION = 'near-net-overlap-abstention.v2'


def ambiguous_net_crowd_observations(observations, identity_by_observation=None):
    """Do not choose a body identity from strongly overlapping net-side boxes.

    Either box may span two people. Reject both ambiguous measurements, retaining
    independent evidence from the opposite camera and the frozen roster itself.
    Court end thresholds and reported quality gates are unchanged.
    """
    from app.vision.multiview.image_track_handoff import bbox_iou
    rejected = set()
    identities = identity_by_observation or {}
    eligible = [obs for obs in observations
        if obs.detection_origin == 'base' and obs.confidence >= .25
        and abs((obs.canonical_y_ft if obs.canonical_y_ft is not None else obs.local_y_ft)-22.) <= 6.]
    for index, one in enumerate(eligible):
        for two in eligible[index+1:]:
            if (one.view_id != two.view_id or one.source_frame_index != two.source_frame_index
                    or one.track_id == two.track_id or bbox_iou(one.bbox, two.bbox) < .3):
                continue
            x1,y1,x2,y2 = one.bbox
            a,b,c,d = two.bbox
            area_one, area_two = (x2-x1)*(y2-y1), (c-a)*(d-b)
            owners = {identities[id(obs)] for obs in (one,two) if id(obs) in identities}
            if (len(owners)==1 and bbox_iou(one.bbox,two.bbox)>=.65
                    and max(area_one,area_two)/min(area_one,area_two)<=1.75):
                # A nearly identical replacement track of the same known body
                # is a duplicate/fragment, not evidence of two crowd identities.
                # The nested-box guard can retain the stronger measured body.
                continue
            covered = max(0., min(x2,c)-max(x1,a))*max(0., min(y2,d)-max(y1,b))/min(area_one,area_two)
            if covered >= .65:
                rejected.update((id(one),id(two)))
    return rejected


def ambiguous_nested_observations(observations):
    rejected = set()
    for obs in observations:
        box = obs.bbox
        if not box or len(box) != 4 or not all(map(isfinite, box)):
            continue
        x1, y1, x2, y2 = box
        area = (x2-x1)*(y2-y1)
        if x2 <= x1 or y2 <= y1:
            continue
        for peer in observations:
            if (peer is obs or peer.view_id != obs.view_id
                    or peer.source_frame_index != obs.source_frame_index
                    or peer.detection_origin != 'base' or peer.confidence < .5):
                continue
            other = peer.bbox
            if not other or len(other) != 4 or not all(map(isfinite, other)):
                continue
            a, b, c, d = other
            if c <= a or d <= b or (c-a)*(d-b) < area*1.25:
                continue
            covered = max(0., min(x2,c)-max(x1,a))*max(0., min(y2,d)-max(y1,b))/area
            # Similar footpoints distinguish a partial/duplicate body from a
            # separate player standing behind it in this camera's perspective.
            if (covered >= .9 and abs(y2-d) <= .2*(d-b)
                    and abs((x1+x2-a-c)/2) <= .25*(c-a)):
                rejected.add(id(obs))
                break
    return rejected
