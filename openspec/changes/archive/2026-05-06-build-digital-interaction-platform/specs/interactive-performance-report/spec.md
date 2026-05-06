## ADDED Requirements

### Requirement: Report-first entry experience

The system SHALL open into a product demo experience where the first viewport presents a pickleball post-session analysis report rather than a generic marketing landing page.

#### Scenario: User opens the site on desktop

- **WHEN** the user loads the website on a desktop viewport
- **THEN** the first viewport presents the platform name, current demo report context, key performance metrics, and a primary court visualization without requiring navigation to another page

#### Scenario: User opens the site on mobile

- **WHEN** the user loads the website on a mobile viewport
- **THEN** the report context and key metrics remain visible in a vertically stacked layout without text overlap or horizontal scrolling

### Requirement: Core metric summary

The system SHALL display a concise summary of pickleball performance metrics using local demo data.

#### Scenario: Metrics are rendered from demo data

- **WHEN** the report demo is displayed
- **THEN** the system shows metrics for overall score, ball speed, movement efficiency, rally stability, and landing accuracy using values from the structured demo data source

### Requirement: Court visualization

The system SHALL visualize pickleball court analysis including landing heat points, shot routes, and player movement paths.

#### Scenario: User views court analysis

- **WHEN** the court visualization section is visible
- **THEN** the system shows a pickleball court with landing distribution, return routes, and movement trajectory based on demo events

#### Scenario: User switches visualization mode

- **WHEN** the user selects a supported court visualization mode
- **THEN** the court panel updates to emphasize the selected view while preserving the same report context

### Requirement: Rally analysis

The system SHALL present rally-level analysis that connects visible court events with readable performance interpretation.

#### Scenario: User reviews rally details

- **WHEN** the user selects or views a rally summary
- **THEN** the system displays rally duration, shot count, route pattern, result, and at least one tactical observation

### Requirement: Responsive report layout

The system SHALL keep report panels, controls, text, and visualizations legible across desktop and mobile viewport sizes.

#### Scenario: Layout adapts to narrow screens

- **WHEN** the viewport width is narrow
- **THEN** report sections stack into stable blocks with constrained visualization aspect ratios and no incoherent overlap
