# Design

Add a versioned `FrameTimingProvider` at the video boundary. Every downstream
consumer receives a `FrameTiming` containing source PTS, optional DTS, frame
index, and canonical take timestamp. Mapping and window logic consume that
timestamp; frame index remains only for seeking and traceability.

Migration is staged: first emit and validate PTS sidecars, then migrate each
consumer behind compatibility readers, and finally reject artifacts that lack
the required timing provenance for new runs. Historical artifacts remain
read-only compatible.

