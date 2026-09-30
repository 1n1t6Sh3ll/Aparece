# Aparece web design system

A working tool for people who run apparel stores: paper-and-ink neutrals, one forest-green accent, dense tables, square-ish components. No gradients, glass effects, sparkle/"AI" icons or emoji.

Source of truth: tokens in `src/index.css` (`:root` and `:root[data-theme="dark"]`). Theme = saved choice (`pl.theme`), else dark; toggle in the top bar or with `t`.

## Type

| Role | Family | Use |
|---|---|---|
| Display | Fraunces 500-700 (serif) | `h1`, `h2` (page and section titles) |
| UI | IBM Plex Sans 400-700 | everything else; small section labels (`h2.text-sm`) stay in Plex Sans |
| Numbers | IBM Plex Mono (via `.tabular-nums`) | scores, ranks, counts, prices in tables and stats |

Loaded from Google Fonts in `index.html`, with Georgia / system-ui / Consolas fallbacks.

## Colour tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f4efe6` | `#15130f` | page (warm paper / warm black) |
| `--surface` | `#fbf8f2` | `#1d1a16` | cards, header, inputs |
| `--surface-2` | `#ede6da` | `#27231d` | hover, tab track, table header, skeletons |
| `--border` | `#d9d0c1` | `#3a342b` | all lines |
| `--text` | `#1d1b17` | `#efe9de` | ink |
| `--muted` | `#625b50` | `#a89f90` | secondary text |
| `--accent` | `#1e5b43` | `#5fae86` | primary buttons, links, "you" in charts |
| `--accent-fg` | `#ffffff` | `#0f1f17` | text on accent |
| `--accent-soft` | `#e1ede5` | `#1f3329` | icon tiles, "you" column tint |
| `--chart-peer` | `#8c8374` | `#857c6e` | comparable products (context) in charts |
| `--chart-band` | `#cfe2d5` | `#2d4a3b` | middle-half price band |
| `--sidebar` / `--sidebar-ink` | `#1d1b17` / `#c9c0b0` | `#0f0d0a` / `#a89f90` | app sidebar |

Tailwind's `indigo`/`violet` are not used; a `brand-50..950` forest-green ramp is defined in `@theme` and neutrals use `stone`. Status colours keep their meaning only: emerald = done/found, amber = gap/warning or merchant-stated, rose = error/destructive, always with a text label or icon.

## Shape and density

- Radius capped in `@theme`: `sm` 2px, `md` 3px, `lg`/`xl` 4px, `2xl` 6px. Chips are 2px. Pills are only used for progress bars and chart dots.
- No shadows on cards (1px border only); a shadow is used only for floating layers (menus, toasts, dialogs).
- Tables: 8px vertical cell padding, sticky first column, row highlight for gaps, column highlight on hover.
- Motion: one 250 ms 4px rise on panels; disabled under `prefers-reduced-motion`.

## Charts

Highlight-vs-context: the product under audit in `--chart-you`, comparable products in `--chart-peer`, always direct-labelled ("You") plus a legend, with a table view for the rank chart. One axis per chart; bars have 4px rounded data ends; 2px gaps and a 2px surface ring on overlapping dots. `--chart-peer` intentionally reads as grey (context), so identity never relies on hue alone.

## Contrast (WCAG 2.1, computed)

Computed with the WCAG relative-luminance formula for every text/background pair the UI uses. Text needs 4.5:1; non-text marks 3:1.

| Pair | Light | Dark |
|---|---|---|
| text on bg | 15.01:1 AA | 15.35:1 AA |
| text on surface | 16.22:1 AA | 14.35:1 AA |
| text on surface-2 | 13.86:1 AA | 12.93:1 AA |
| muted on surface | 6.33:1 AA | 6.63:1 AA |
| muted on bg | 5.86:1 AA | 7.09:1 AA |
| muted on surface-2 | 5.41:1 AA | 5.97:1 AA |
| accent (links) on surface | 7.52:1 AA | 6.51:1 AA |
| accent-fg on accent (buttons) | 7.98:1 AA | 6.42:1 AA |
| sidebar-ink on sidebar | 9.54:1 AA | 7.42:1 AA |
| chart-peer mark on surface (3:1) | 3.53:1 AA | 4.21:1 AA |
| accent mark on surface-2 (3:1) | 6.43:1 AA | 5.87:1 AA |

Tailwind status tints (`amber-800` on `amber-50`, `rose-700` on `rose-50`, etc.) are Tailwind defaults and were not re-measured here.

## Layout

App shell: fixed 240px sidebar (Overview, Audit, My products, Reports, Models, Ask, Settings) that becomes a drawer below 1024px; 56px top bar with the company switcher, language and theme toggles. Logged-out visitors get the marketing landing at `#/`; the shared report (`#/share/...`) renders without the shell. Keyboard: `g` + `o/a/p/r/m/c/s` to navigate, `/` focus the main input, `t` theme, `l` language, `?` shortcut list.
