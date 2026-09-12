# Original NCDAI identity in version 2.0

The user requested the original NCDAI application's colour scheme and logos, referencing `www.ncdai.co.ke`. Version 2.0 now uses the original coral identity and artwork within the improved clinical workspace.

## Primary evidence

The supplied `gidyon/ncd-app` source snapshot is identified in the original review as commit `b061cf5062f963a452f05fc7ff6c04e89977bd50`.

- [`lib/colors.dart`](https://github.com/gidyon/ncd-app/blob/b061cf5062f963a452f05fc7ff6c04e89977bd50/lib/colors.dart) defines `seedColor = Color(0xFFFF5757)` and uses it for the light/dark theme primary colour, app bar and elevated buttons.
- `lib/pages/login.dart`, `lib/pages/about.dart` and `lib/pages/dashboard.dart` use `assets/logo-nobg.png`. Flutter tints the transparent artwork with the theme's primary colour in those views.
- The supplied `assets/logo.png` contains the same white stethoscope/cross emblem on a coral background. Its corner pixel, decoded to RGB, is exactly `(255, 87, 87)`.

The public website was attempted on 12 September 2026, but did not load through the available browser/network route. The source snapshot and original image files therefore provide the implementation evidence; no current website appearance is claimed to have been verified.

## Preserved artwork

Both image files were copied byte-for-byte. They were not redrawn, generated or recoloured.

| Original file | Version 2.0 file | Dimensions | SHA-256 |
|---|---|---|---|
| `assets/logo.png` | `frontend/public/brand/ncdai-logo.png` | 231×232 | `eb0187ebb417d9c689998dd87211d935316418ffc06e60046287a6ff0c67d0be` |
| `assets/logo-nobg.png` | `frontend/public/brand/ncdai-logo-transparent.png` | 231×232 | `65839a2933064870d6dcc184009dcb732f6b9a210425feaa1b2d1f850df62780` |

The original repository's licence accompanies the assets at `frontend/public/brand/LICENSE-original.txt`. Reuse was explicitly requested by the user. This change copies artwork and the associated licence; it does not import the original application implementation.

The unchanged coral logo is visible in the application navigation, sign-in branding, overview illustration and loading screen. It also supplies the favicon and touch icon. The existing NCDAI wordmark and the 2.0 version label remain visible.

## Colour treatment and accessibility

The primary colour is the exact original **`#FF5757`**, also used in the browser theme metadata. White remains the principal panel colour and the original emblem colour. Warm neutral text and pale coral surfaces adapt the improved layout to the original identity.

Accessibility adaptations are explicit: primary coral buttons use dark text (`#311717`), and links/focus indicators use darker coral (`#A12D2D`). These companion colours are version 2.0 design choices, not colours attributed to the original source. The original white-on-bright-coral treatment was not copied for small button text because its contrast is insufficient. Clinical urgency and completion retain semantic colours plus visible labels and icons.

`frontend/src/brand.css` owns the brand treatment; `frontend/src/Brand.tsx` renders the original image. Browser checks assert the original image path and exact primary button colour, alongside the existing workflow and accessibility checks. See [browser verification](browser-verification.md) for measured results and current screenshots.
