# Facility discovery design

ThePetStop helps Singapore pet owners find a facility and understand its registry evidence. This web redesign applies Apple's foundations, not native macOS navigation conventions. Review is grounded in the React/CSS source; browser rendering and assistive-technology behaviour still need visual/manual verification.

## Review

Overall: Needs work before this change. The screen's job is geographic discovery, but independently framed filters, result cards and location messages compete with the map.

- **High, layout:** Detached cards and a separate results-count box obscure the relationship between results and pins. `layout.md › Visual hierarchy`: “Group related items to clearly express related information or functions.” Use one frame and one divider between result rows and map.
- **Medium, density:** Repeating large icons, badges and metadata sections makes the directory unnecessarily tall. `lists-and-tables.md › Content`: “Keep item text succinct so row content is comfortable to read.” Keep names, type, address and compact verification evidence; disclose full contact/licence details on selection.
- **Medium, interaction:** List selection should visibly locate the corresponding pin. `split-views.md › Best practices`: “persistently highlight the current selection”. Keep an active row and marker, move the camera on selection, and provide a dismissible detail section below the workspace.
- **Keep:** In-context geolocation permission, honest sample-data labelling, source/check dates, external directions, map/list alternatives and reduced-motion behaviour.

## Plan and tokens

Signature (design judgment): a quiet green facility directory attached to the Singapore map, with matching medical-cross and shop-bag symbols connecting rows to pins. This belongs to pet-care discovery; no decorative hero or glass cards are needed. Remove the separate results-count card and large repeated status badges.

Reuse semantic tokens, with computed WCAG contrast on the indicated surface:

| Role               | Light              | Dark               | Contrast light / dark |
| ------------------ | ------------------ | ------------------ | --------------------- |
| Surface            | #ffffff            | #18232e            | Base                  |
| Primary content    | #131b2e            | #e8ecf5            | 17.16 / 13.46         |
| Secondary content  | #4f5d64            | #b5bfcc            | 6.81 / 8.56           |
| Interactive accent | #006b5f            | #89e4d2            | 6.43 / 10.69          |
| Caution            | #785316 on #fff4de | #f3d29c on #382e1e | 6.32 / 9.20           |

Type: existing system sans for display and body; 28–36px heading, 16px row title, 14px controls/body, 12–13px metadata, all in rem. No added font. Controls have a minimum 44px target and visible keyboard focus. Avoid fixed row heights, line clamping and decorative animations.

Regular width:

```text
Find pet care in Singapore                 Sample listings
+-------------------------------------------------------+
| Search facilities                  Use my location     |
| All / Vets / Pet shops     Emergency    Split/Map/List |
+------------------+------------------------------------+
| Results          |                                    |
| compact rows     | Singapore map                      |
| selected row     | matching pins                      |
+------------------+------------------------------------+
| Map legend / location status                          |
+-------------------------------------------------------+
Selected facility details (only after selection; dismissible)
```

Compact width: heading → search → wrapping scope/actions → map → results → details. Map/list controls can hide either pane. No fixed-height scrolling list at compact widths, so browser zoom and larger text can expand the page.

Motion: one camera movement on explicit selection or geolocation; disabled for reduced motion. Opaque surfaces need no reduced-transparency fallback. Existing system dark appearance is retained; map provider artwork remains unmodified. Retain textual labels and distinct icons alongside colour.

## Implementation and verification

The directory owns search, scope, layout and selected facility state. MapLibre renders the map, stable keyboard-accessible pin buttons and selection feedback. Details stay below the map, matching the user's preference. Search remains facility filtering; address geocoding is separate future work.

Check formatting, ESLint, TypeScript and existing behaviour tests. Manually verify light/dark appearances, 320px widths, 200% text/zoom, keyboard pin selection, map/list switching, selected details dismissal and location failure. A production build in the current Linux shell is limited by Windows-installed native SWC/Lightning CSS packages.
