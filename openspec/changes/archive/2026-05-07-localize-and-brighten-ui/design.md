## Context

The app is a Vite/React/Tailwind demo for pickleball video analysis, reports, training recommendations, and a phase-two smart paddle preview. It currently renders several pages from local mock data in `src/data/demoData.ts` plus page-level and component-level copy in `src/App.tsx` and `src/components/platform/*`.

The active theme is defined mostly in `src/index.css` and Tailwind class names. The UI uses black surfaces, translucent white borders, white text, and neon green highlights. A legacy-looking `src/styles/app.css` already contains a lighter color vocabulary, but the running entry imports `src/index.css`, so implementation should update the active theme rather than assuming the legacy file controls the app.

## Goals / Non-Goals

**Goals:**
- Present all visible user-facing copy in natural Chinese across the current demo pages.
- Replace the dominant black theme with a bright sports-analysis palette while preserving the existing accent color meanings.
- Keep the current page structure, client-side routing, local demo data, and interactions stable.
- Preserve data-driven rendering so future demo copy/data replacements remain straightforward.
- Verify the result through source search plus desktop/mobile visual checks.

**Non-Goals:**
- Introduce a full i18n library, runtime language switcher, backend localization service, or route renaming.
- Replace the mock visualizations, add real video upload, or connect live TENG-IMU hardware feeds.
- Change the report data schema, navigation routes, or enum/type identifiers just because their internal names are English.
- Translate technical acronyms and units such as TENG, IMU, `km/h`, `m/s`, and report IDs when they function as technical labels rather than prose.

## Decisions

1. **Use direct Chinese copy updates instead of adding an i18n framework.**
   - Rationale: The product currently targets a single Chinese presentation context, and adding translation infrastructure would add complexity without user value.
   - Alternative considered: introduce a translation dictionary and provider. This is better for multi-language products, but this change only asks for a Chinese-facing prototype.

2. **Update structured mock data first, then component literals.**
   - Rationale: Most repeated report names, metrics, filters, highlights, coach notes, and drill metadata live in `demoData.ts`. Translating there keeps rendered pages consistent and avoids duplicating text patches.
   - Alternative considered: translate only visible component strings. That would leave tables, labels, overlays, and report definitions mixed-language.

3. **Keep internal route/type identifiers in English while translating what users see.**
   - Rationale: Routes such as `/vision`, report type keys, and union literal values are implementation contracts. Changing them would increase regression risk and is not necessary for the visible page.
   - Alternative considered: localize URL paths. That would be a behavior change outside the request and would require broader route and spec updates.

4. **Move the dominant visual system to bright tokens in `src/index.css` while preserving accent hues.**
   - Rationale: Component base classes `.sport-card`, `.green-button`, and `.quiet-button` give broad leverage for cards/buttons. Component-specific dark Tailwind classes can then be adjusted where they create heavy black islands.
   - Alternative considered: perform a global class replacement for every `text-white`, `bg-black`, and `border-white` token. That can overcorrect video mockups and accent overlays where a darker local panel still improves contrast.

5. **Allow selective darker overlays inside simulated video/court modules.**
   - Rationale: The user wants the web's main color tone brighter, not every single pixel pale. Video mockups, tooltips, and high-contrast timeline controls can retain localized darker layers when they make the analysis visuals legible.
   - Alternative considered: force all visual modules to white. That risks losing the premium sports-tech feeling and reducing overlay contrast.

## Risks / Trade-offs

- English text can remain in non-obvious places such as `aria-label`, SVG labels, chart `title` attributes, mobile short labels, and table mapping constants → Mitigation: run targeted source searches for visible English string literals after implementation and review component render paths.
- Brightening base cards may reduce contrast for existing neon accents → Mitigation: tune text colors and background tint opacity around the preserved green/lime/blue/orange/red accents.
- Some English words are also internal identifiers used by filters and result mappings → Mitigation: translate display values in data/mapping objects while preserving type contracts or updating mappings together.
- Visual modules may feel inconsistent if only the page background changes → Mitigation: update card, header, footer, table, chart, and visualization container surfaces as a coordinated palette rather than a single background swap.
