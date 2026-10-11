# Design system lens

The visual rules the site already follows, written as rules a build agent can match.

## Contents
- Static parse first
- When to open a browser
- The twelve things to record
- Roles beat values
- Verify the extraction
- What to write in the model

## Static parse first

Most sites declare their design layer in CSS. Read it before opening a browser.

```bash
python3 scripts/static_parse.py --url <site-url> --out /tmp/raw.json
python3 scripts/static_parse.py --dir ./the-repo --out /tmp/raw.json
```

Python 3 standard library only. It returns declared custom properties, and frequency-ranked colours, font families, sizes, weights, spacing, radius, shadows, breakpoints, durations and a dark-mode signal. In `--dir` mode it also names the UI library and icon set.

It never executes a scanned file. It fetches the page and the stylesheets that page links, which can sit on a CDN, skips font-service stylesheets, and sends the target to no other service.

**Read `coverage` in the output first.** It says which sections the parse filled.

| `coverage` says | Do this |
|---|---|
| Most sections filled | Write from the JSON. Use a browser only for screenshots and component styling. |
| Colours and spacing only | Keep those numbers. Fill the rest from the browser. |
| Almost nothing, or a JS-rendered note | Use the browser for everything. |

**The counts are the point.** A value used 35 times is the system. A value used once is a one-off. Rank before you record.

## When to open a browser

For what CSS cannot show: values computed at runtime, component styling, real rendered state and screenshots. Use a browser automation tool such as Playwright.

Capture more than the home page. A home page rarely shows forms, tables, empty states or errors. Get a listing page and a form page as well. Take each at 390px and 1440px wide.

## The twelve things to record

A gap is a finding. Write "not detected" before dropping a row.

| # | Section | Record |
|---|---|---|
| 1 | Theme | Light or dark, warm or cool, flat or layered, density |
| 2 | Colour | Hex plus role: background, surface, text, muted, accent, border, danger, success |
| 3 | Typography | Families, the size scale in use, weights, line height |
| 4 | Spacing | Base unit and scale. Most systems are 4px or 8px |
| 5 | Shape | Radius values, border widths |
| 6 | Depth | Shadows, or how layers are shown without them |
| 7 | Components | Buttons, inputs, cards, menus: variants and states |
| 8 | Layout | Container width, grid, gutters |
| 9 | Motion | Durations, easings, what moves |
| 10 | Responsive | Breakpoints and what reflows at each |
| 11 | Dark mode | The variable pairs, or "not supported" |
| 12 | Do and do not | The rules that keep new work consistent |

Record the font category when the font is paid or proprietary, then name an open font that does the same job.

## Roles beat values

Eleven hex codes are close to useless. "Accent `#0B6FA4`, on primary buttons and links only, never on body text" is a rule an agent can follow.

## Verify the extraction

1. Build one small component from the written rules alone.
2. Put it beside the real one at the same viewport.
3. Anything that looks foreign means a rule is missing or wrong. Fix the model, not the component.

## What to write in the model

Write the twelve rows, with roles, to `docs/model/design-system.md`. Under `## Design system` in the model, give a short summary and a link to that file. Put the extraction date and the source URL or commit in the header. A stale design section is worse than none, because it is trusted.
