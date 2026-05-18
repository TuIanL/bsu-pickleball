## MODIFIED Requirements

### Requirement: COCO segmentation dataset validation
The system SHALL provide a developer workflow that validates the court-line COCO segmentation dataset before training and reports both structural dataset readiness and target-category readiness for the intended calibration model.

#### Scenario: Developer validates a supported dataset
- **WHEN** the dataset contains readable images, COCO annotation JSON, segmentation annotations, image references, categories, and split metadata or split folders
- **THEN** the validation workflow reports image counts, annotation counts, category names, category usage counts, unused categories, segmentation representation types, missing-file checks, required split readiness, and overall structural readiness

#### Scenario: Dataset has invalid or incomplete annotations
- **WHEN** the dataset references missing images, empty segmentations, malformed polygons, unsupported RLE records, or unknown categories
- **THEN** the validation workflow exits with a clear diagnostic and does not produce a successful training configuration

#### Scenario: Dataset category usage does not match intended target
- **WHEN** the developer validates the dataset with an intended target category or target strategy and the observed annotation categories do not match that intent
- **THEN** the validation workflow reports target readiness as failed or pending and identifies the observed categories, unused categories, and mismatch reason without hiding structural readiness

#### Scenario: Dataset contains unused training categories
- **WHEN** the COCO category list includes a category that has zero annotations in all validated splits
- **THEN** the validation workflow reports that category as unused so the developer can distinguish exported label metadata from actual training labels

#### Scenario: Dataset may leak related frames across splits
- **WHEN** image names or source metadata indicate that likely related source frames, source videos, or duplicated augmented samples appear in more than one split
- **THEN** the validation workflow reports a split-leakage risk diagnostic with enough examples for review without treating the dataset as structurally unreadable

#### Scenario: Dataset acceptance evidence is generated
- **WHEN** the developer runs the dataset acceptance workflow for a local COCO dataset
- **THEN** the workflow produces reviewable evidence including a machine-readable summary, split/category statistics, the target-category decision state, and representative annotation preview artifacts stored in ignored local paths
