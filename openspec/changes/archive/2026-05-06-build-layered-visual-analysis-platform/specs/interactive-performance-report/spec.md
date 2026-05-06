## MODIFIED Requirements

### Requirement: Report-first entry experience

The system SHALL provide a product demo experience where users can enter a pickleball post-session analysis report through the layered overview, visual analysis workspace, and focused report detail pages rather than relying on one long report-first scrolling page.

#### Scenario: User opens the site on desktop

- **WHEN** the user loads the website on a desktop viewport
- **THEN** the first viewport presents the platform name, product value, current demo match context, and clear entry points into visual analysis and report detail workflows

#### Scenario: User opens the site on mobile

- **WHEN** the user loads the website on a mobile viewport
- **THEN** the overview, visual analysis entry, and report entry controls remain visible in a vertically stacked layout without text overlap or horizontal scrolling

### Requirement: Core metric summary

The system SHALL display a concise summary of pickleball performance metrics using local demo data across the visual analysis workspace and relevant report detail pages.

#### Scenario: Metrics are rendered from demo data

- **WHEN** the report demo or a report detail page is displayed
- **THEN** the system shows performance metrics such as overall score, serve or return quality, third-shot success, movement efficiency, rally stability, landing accuracy, unforced errors, or court control using values from the structured demo data source

### Requirement: Court visualization

The system SHALL visualize pickleball court analysis including landing heat points, shot routes, and player movement paths in the visual analysis workspace and report detail pages.

#### Scenario: User views court analysis

- **WHEN** a court visualization module is visible
- **THEN** the system shows a pickleball court with landing distribution, return routes, movement trajectory, or video-overlay events based on demo data

#### Scenario: User switches visualization mode

- **WHEN** the user selects a supported court visualization mode or opens a report type focused on landing, routes, or movement
- **THEN** the court panel updates to emphasize the selected view while preserving the same report context

### Requirement: Rally analysis

The system SHALL present rally-level analysis that connects visible video or court events with readable performance interpretation.

#### Scenario: User reviews rally details

- **WHEN** the user selects or views a rally summary, highlight, timeline marker, or rally report
- **THEN** the system displays rally duration, shot count, route pattern, result, and at least one tactical observation

### Requirement: Responsive report layout

The system SHALL keep report panels, controls, text, navigation, and visualizations legible across desktop and mobile viewport sizes.

#### Scenario: Layout adapts to narrow screens

- **WHEN** the viewport width is narrow
- **THEN** report pages and visual analysis modules stack into stable blocks with constrained visualization aspect ratios and no incoherent overlap
