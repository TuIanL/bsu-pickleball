## ADDED Requirements

### Requirement: Real-scene Court region adaptation dataset
The system SHALL document and support using manually annotated `Court` region masks from real captured footage as a short-term domain adaptation path for automatic court calibration training.

#### Scenario: Developer chooses Court region target
- **WHEN** a developer prepares real captured frames for near-term court calibration adaptation
- **THEN** the workflow identifies `Court` as the intended manual segmentation category and distinguishes it from strict `Court-Line` annotation

#### Scenario: Developer validates real Court annotations
- **WHEN** a developer exports the annotated real footage frames as a COCO segmentation dataset
- **THEN** the existing dataset validation workflow can be run with `Court` as the target category or with an explicit merge strategy when combining compatible court-region categories

#### Scenario: Developer mixes online and real footage datasets
- **WHEN** online match imagery and real captured footage are combined for training or fine-tuning
- **THEN** the workflow documents that validation and test splits should be source-aware and should reserve real captured videos for evaluating deployment-domain performance
