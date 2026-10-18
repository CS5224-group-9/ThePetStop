# PetStop SG frontend design review

## Standalone frontend UI

The frontend now defaults to `NEXT_PUBLIC_DATA_SOURCE=local`: sample pets, six fictional merchant catalogues, facility search with an offline schematic map, care records/reminders, browser-persisted cart and simulated orders, plus merchant editing. No API or Cognito setup is needed to explore these flows. Local data is a single browser workspace for sample information; document files remain in tab memory until reload. Listings are fictional and unverified. Set `NEXT_PUBLIC_DATA_SOURCE=api` to opt into the previously implemented API/Cognito boundary described below; backend endpoints remain a separate task. Local mode does not replace API authorization or implement AWS services.


## Summary

Initial rating: **Critical issues** (readability). The illustration-led landing layout, sidebar, small labels and soft sage palette depart from the supplied Clinic Clean Municipal Pet Care screens. The redesign treats PetStop as a Singapore pet care workspace: top-level domain navigation, structured pet dossiers, scannable care records and a map/catalogue that prioritize discovery. This is a responsive Next.js web application; Apple HIG foundations inform the work, while native macOS menu bars, iOS materials and platform-specific point sizes are not web requirements.

## Findings and changes

- **Critical — readability:** the previous `#8b958d` on white is 3.10:1, below the 4.5:1 target for normal text. Supporting text moves to `#4f5d64` on white (6.81:1). Body text is 14–16 px and supporting text is generally 12–13 px, with rem-based sizing. Utility labels use a floor of 10 px on desktop and 11 px at compact widths. `typography.md › Ensuring legibility`: “Use font sizes that most people can read easily.” `accessibility.md › Vision` provides the contrast table.
- **High — reference fidelity (design judgment):** replace sidebar and promotional heroes with horizontal domain navigation, an emerald context ribbon, white dossier panels and lavender data groups. Preserve the reference’s 65/35 passport composition and map/results split, without its unsupported official registry claims.
- **High — interaction density:** primary buttons and input fields receive 44 px minimum target regions, visible press/hover/focus states and room between actions. `buttons.md › Best practices`: “Always include a press state for a custom button.”
- **Medium — writing:** replace repeated decorative “little” slogans with task names: Pet passports, Vaccination & care records, Care reminders, Product catalogue, Order summary. `writing.md › Best practices`: “Prioritize clarity and avoid the temptation to be too cute or clever with your labels.”
- **Medium — navigation and search:** keep the current domain visible, support keyboard arrow navigation in passport tabs, prominently place scoped searches, expose filter reset and list/map views. `searching.md › Best practices`: “Clearly display the current scope of a search.”

## Compact design system

| Role | Light | Dark | Measured contrast |
| --- | --- | --- | --- |
| Canvas / content | `#faf8ff` / `#131b2e` | `#101822` / `#e8ecf5` | 16.29:1 / 15.09:1 |
| Panel / supporting text | `#ffffff` / `#4f5d64` | `#18232e` / `#b5bfcc` | 6.81:1 / 8.56:1 |
| Accent / on-accent | `#003820` / `#ffffff` | `#9ce8c5` / `#183d30` | 13.24:1 / 8.44:1 |
| Teal status | `#006b5f` on `#e1f7f1` | mint text on deep teal | Light 5.74:1 |
| Urgent status | `#8d1536` on `#ffedf0` | rose text on deep burgundy | Light 8.12:1 |
| Grouped data | `#f2f3ff` | `#202d3c` | Uses the content/supporting text roles |

System sans serif for headings and body; monospace only for microchips, IDs and tabular data. Type scale: 10 / 11 / 12 / 13 / 14 / 16 / 20 / 24 / 32 px, expressed in rem. Spacing: 4 / 8 / 12 / 16 / 24 / 32 px. Borders are quiet, shadows shallow, and structural corners use 8–12 px radii.

Regular passport layout:

```text
[Brand       Map | Passports | Marketplace       Cart Account]
[Emerald domain ribbon                          Demo status]
[Page title / pet switcher                       Add pet]
[Identity and registration dossier      ][Care overview    ]
[Profile | Health records | Documents    ][Upcoming reminders]
[Grouped data / care record table        ][Facility shortcut]
```

Compact layout:

```text
[Brand                       Cart Account]
[Domain ribbon / demo status             ]
[Title and actions                       ]
[Pet switcher                            ]
[Identity > tabs > dossier panels        ]
[Reminders and facility shortcut         ]
[Overview | Map | Pets | Shop | Orders    ]
```

The signature is the clinical pet dossier: photographic reference portraits, a readable microchip identity block, lavender clinical groups and explicit care status. This is specific to the product rather than a generic promotional hero. No orchestrated animation is needed; transitions only acknowledge interaction and respect reduced motion. Opaque surfaces avoid a dependency on transparency preferences.

## What stays

The existing demo state adapter, static export, fictional facility disclosure, six-shop comparison, simulated checkout, private-document boundary and complete pet-to-order walkthrough remain. No AVS affiliation, licensing, payment or document-security capability is inferred from visual styling.

## Reference use and limits

Guidance read from `.agents/skills/apple-design/references/`: cross-platform translation, code audit, and HIG accessibility, layout, typography, color, designing-for-macos, buttons, entering-data, searching and writing. The source screenshots and HTML remain visual references; their claims about live AVS sync, compliance, prescriptions and emergency wait times are not implemented facts. Contrast ratios above use sRGB relative luminance; browser checks validate actual responsive layouts, focus behavior and core demo flows, rather than claiming a full screen-reader or native-platform accessibility audit.

## Implementation and verification

Post-redesign assessment: **Good**. The reference’s clinical identity is now consistent across navigation, dossiers, directory and catalogue; decorative landing elements have been removed. The prototype boundary stays visible.

The redesign lives in `frontend/app/globals.css` (semantic tokens and adaptive layouts), `components/shell.tsx` (domain navigation), `components/pets.tsx` (dossiers, care table and keyboard tabs), `components/directory.tsx` (map/list controls), `components/marketplace.tsx` (filter sidebar and catalogue) and `components/dashboard.tsx` (care overview). Portraits are copied from the supplied reference HTML and stored in `public/images/`; product illustrations remain fictional.

The three deterministic checkout tests passed. A local headless Chrome walkthrough verified pet creation, care record creation, generated reminder completion, emergency filtering, map/list switching, multi-merchant basket and simulated checkout, order confirmation and merchant status advancement. It also exercised keyboard arrow navigation in passport tabs, 320/390/768/1024px layouts, dark appearance and page exception checks. These checks are targeted verification, not a complete WCAG or assistive-technology audit.

Commands run through the installed Windows Node.js runtime from WSL:

```text
node.exe node_modules/typescript/bin/tsc --noEmit
node.exe node_modules/eslint/bin/eslint.js app components lib tests
node.exe node_modules/prettier/bin/prettier.cjs --check .
node.exe --experimental-strip-types --test tests/checkout.test.mts
node.exe node_modules/next/dist/bin/next build
```

The one-off browser walkthrough uses an ignored local QA script and an isolated Chrome profile; it adds no production dependency.

## Connected frontend update (2026-10-19)

The visual review above describes the redesign stage. The subsequent frontend-only production-integration work removes the demo selector, fixture roster, CSS product packaging and session-stored records. Neutral placeholders now replace reference pet/product imagery unless public product imagery comes from the API. Data/permissions/success states use the real request boundary; authentication is configurable Cognito OIDC, and facility locations use MapLibre/OneMap. The deployment and wire-contract limits are now documented in `frontend-integration.md`; the prior demo walkthrough is historical validation, not evidence of a live backend.
