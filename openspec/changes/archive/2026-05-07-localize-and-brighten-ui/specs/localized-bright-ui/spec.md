## ADDED Requirements

### Requirement: Chinese-first visible interface
The system SHALL present the current web demo's visible user-facing prose, labels, navigation, buttons, table headers, filters, chart legends, tooltips, report titles, overlay labels, and status text in natural Chinese.

#### Scenario: User views top-level product pages
- **WHEN** the user opens the overview, visual analysis, training, or hardware page
- **THEN** the page chrome, headings, body copy, navigation labels, CTAs, cards, and footer actions are written in Chinese without mixed English marketing or workflow labels

#### Scenario: User views report and analysis modules
- **WHEN** the user opens any supported report detail page or visual analysis module
- **THEN** report titles, metric labels, insight text, shot filters, table headers, table values, timeline labels, chart legends, video overlay labels, and action affordances are written in Chinese

#### Scenario: Technical identifiers remain visible only when appropriate
- **WHEN** the UI displays technical acronyms, units, report IDs, dates, player markers, or hardware terminology such as TENG, IMU, `km/h`, or `m/s`
- **THEN** the system MAY keep those identifiers unchanged when they are technical labels rather than English prose

### Requirement: Bright primary visual theme
The system SHALL use a bright, lightweight sports-analysis theme as the app's dominant visual presentation instead of a black primary interface.

#### Scenario: User opens the app shell
- **WHEN** the application renders the header, body background, main cards, navigation, and footer
- **THEN** the dominant surfaces are light or white-tinted with dark readable text and restrained shadows rather than black backgrounds with white text

#### Scenario: User views analysis cards and controls
- **WHEN** cards, buttons, filters, tables, charts, and report panels are visible
- **THEN** their default state uses bright surfaces, readable dark text, and clear borders while retaining polished hover and active states

#### Scenario: Accent colors are preserved
- **WHEN** the UI communicates success, positive performance, action emphasis, training context, risk, or error
- **THEN** the system preserves the existing accent relationships of green/lime, blue, orange, and red while adapting their contrast for the bright theme

### Requirement: Presentation-ready responsive polish
The system SHALL keep localized Chinese text and the brighter theme stable across desktop and mobile presentation viewports.

#### Scenario: User views desktop layout
- **WHEN** the app is viewed on a desktop viewport
- **THEN** Chinese text fits within buttons, navigation, cards, charts, and table columns without incoherent overlap or clipped labels

#### Scenario: User views mobile layout
- **WHEN** the app is viewed on a narrow viewport
- **THEN** navigation chips, CTAs, localized headings, analysis cards, and data tables remain readable without horizontal page scrolling caused by translated text

#### Scenario: User reviews visual-analysis modules
- **WHEN** simulated video, court, timeline, or tooltip overlays require high contrast
- **THEN** the system MAY use localized darker overlay panels inside those modules while the app's overall primary theme remains bright
