# Facility discovery design

ThePetStop helps Singapore pet owners find a facility and understand its registry evidence. This web redesign applies Apple's foundations, not native macOS navigation conventions. Review is grounded in the React/CSS source and browser interaction checks; assistive-technology behaviour still needs manual verification.

## Review

Overall: Needs work before this change. The screen's job is geographic discovery, but independently framed filters, result cards and location messages compete with the map.

- **High, layout:** Detached cards and a separate results-count box obscure the relationship between results and pins. `layout.md › Visual hierarchy`: “Group related items to clearly express related information or functions.” Use one frame and one divider between result rows and map.
- **Medium, density:** Repeating large icons, badges and metadata sections makes the directory unnecessarily tall. `lists-and-tables.md › Content`: “Keep item text succinct so row content is comfortable to read.” Keep names, type, address and compact verification evidence; disclose full contact/licence details on selection.
- **Medium, interaction:** List selection should visibly locate the corresponding pin. `split-views.md › Best practices`: “persistently highlight the current selection”. Keep an active row and marker, move the camera on selection, reveal the matching result on pin selection, and provide a dismissible inspector to the right of the map.
- **Keep:** In-context geolocation permission, honest registry/source labelling, source/check dates, external directions, map/list alternatives and reduced-motion behaviour.

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

Regular width: a results pane, map canvas, and optional right inspector share one frame. The inspector docks beside the canvas when the map region is at least 580px wide; the map resizes and keeps the selected facility centred.

```text
Search location · radius · All / Vets / Pet shops
+----------------+---------------------+----------------+
| Results        | Singapore map       | Type     Close |
| selected row   | selected pin        | Facility name  |
| scrolls here   |                     | Source / date  |
|                |                     | Directions     |
+----------------+---------------------+----------------+
```

Compact width: search → map → results. In a narrow map region, the inspector fills the map area with an opaque surface; Close or Escape returns to the map. The results remain independently scrollable below it. Choosing a result brings the inspector into view; dismissing it returns to the chosen row. Text wraps inside the inspector, and its type/close toolbar stays visible while details scroll.

Selection is shared between map, list, and inspector. Pin activation scrolls only the results container, never the document, and only when the selected row is outside the visible list area. The selected row uses both a highlight and “Selected · details open”. Selection focuses the details heading, and dismissal restores focus to the opener. On compact layouts, choosing a row also brings the inspector into view. This is a nonmodal web inspector, so keyboard users can move between panes without a focus trap.

References applied: `split-views.md › Best practices`: “persistently highlight the current selection”; `focus-and-selection.md › Best practices`: “Avoid changing focus without people’s interaction”; `motion.md › Best practices`: “Make motion optional.” These inform the web interaction rather than impose native macOS window conventions.

Motion: one camera movement on explicit selection or geolocation; disabled for reduced motion. Opaque surfaces need no reduced-transparency fallback. Existing system dark appearance is retained; map provider artwork remains unmodified. Retain textual labels and distinct icons alongside colour.

## Implementation and verification

The directory owns search, scope, layout and selected facility state. MapLibre renders the map, stable keyboard-accessible pin buttons and selection feedback. Details open in the right inspector, matching the updated user preference. Stable map-selection callbacks preserve pin elements and keyboard focus across selections. A single location-first input retrieves address/postal-code suggestions. Selection sets the centre; the sidebar shows facilities within the chosen radius, nearest first. Category filters refine these results. Search centres use a pin, device locations use a blue dot, and a dashed map boundary shows the selected radius. Location search uses the shared API client and centres a selected result without implying facility verification; production search networking remains PR 3 work.

Check formatting, ESLint, TypeScript and existing behaviour tests. Manually verify light/dark appearances, 320px widths, 200% text/zoom, keyboard pin selection, map/list switching, selected details dismissal and location failure. The Linux runtime cannot use the installed Windows native SWC/Lightning CSS packages; the production static export was verified successfully with Windows Node during PR 2.

Radius refinement: offer 1/2/5/10/20 km and All Singapore; disable the control until a centre is selected. Label distances as straight-line and keep the distance computation consistent with the displayed boundary. Clear search resets the centre; changing the radius preserves category choices.

Right-inspector verification (28 October 2026): checked against the local Django API with 465 active facilities. Browser checks confirmed that a pin for a distant list item scrolls that row into view without changing document scroll position, selected rows and pins agree, Close/Escape restore focus, and keyboard result selection opens details. At 320px, long details scroll while Close remains visible. At 768px, the inspector fills the map region; at 1024px and 1440px, it docks beside the canvas. No horizontal overflow occurred at these widths. ESLint on changed components, TypeScript, Prettier, all 25 frontend tests, and the static production build passed. Screen-reader output, real touch devices, and the system dark appearance were not exercised in this pass.
