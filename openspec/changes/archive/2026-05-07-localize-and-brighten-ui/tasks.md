## 1. Copy Localization

- [x] 1.1 Translate structured demo data in `src/data/demoData.ts`, including navigation labels, match context, overlay labels, timeline markers, highlights, coach notes, metrics, filters, shot rows, skill ratings, drills, and report definitions.
- [x] 1.2 Translate page-level copy and CTAs in `src/App.tsx` for overview, visual analysis, report detail, training, hardware, drill cards, and fusion blocks.
- [x] 1.3 Translate platform component copy in `src/components/platform/*`, including app shell, video card labels, shot explorer headings/table text, chart legends/titles, rating headings, metric accessibility titles, and report visualization labels.
- [x] 1.4 Preserve internal route names, type identifiers, technical acronyms, units, report IDs, dates, and player markers where they are implementation or technical labels rather than visible English prose.

## 2. Bright Theme Implementation

- [x] 2.1 Update `src/index.css` root theme tokens, page background, selection color, `.sport-card`, `.glass-panel`, `.green-button`, and `.quiet-button` for a bright primary interface.
- [x] 2.2 Adjust header, footer, navigation, card, table, chip, and panel Tailwind classes that currently depend on black surfaces, white borders, or white text.
- [x] 2.3 Retune component-specific dark containers in video, court, chart, and tooltip modules so high-contrast overlays remain legible while the overall app reads bright.
- [x] 2.4 Preserve green/lime, blue, orange, and red accent semantics with contrast appropriate for light surfaces.

## 3. Responsive Polish

- [x] 3.1 Check desktop layouts for Chinese text fit in navigation, CTAs, cards, report hero panels, tables, chart legends, and overlays.
- [x] 3.2 Check mobile layouts for localized navigation chips, button wrapping, table/container overflow, and visualization dimensions.
- [x] 3.3 Tune spacing, font weights, widths, or wrapping only where Chinese copy causes overlap or clipping.

## 4. Verification

- [x] 4.1 Run a source search for remaining visible English string literals and classify any remaining technical/internal exceptions.
- [x] 4.2 Run the project build or type check to catch translation-related mapping/type regressions.
- [x] 4.3 Start the local dev server and inspect the updated pages in desktop and mobile viewports.
- [x] 4.4 Capture final implementation notes with any intentionally retained technical English terms.
