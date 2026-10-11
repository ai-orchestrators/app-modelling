# Running-app path: no source code

Model the app by using it. Screens and flows are observed. The data model is inferred, and marked as inferred.

## Contents
- What is allowed
- List the sources
- Screen inventory
- Flows
- Components
- Inferred data model
- What cannot be rebuilt
- Size it

## What is allowed

This path is often used on a product we do not own. The limits are firm.

| Do | Do not |
|---|---|
| Use public pages and our own account, as a normal user | Use an account that is not ours, or get past a paywall |
| Read help docs, pricing, changelogs, public API docs | Read its JS bundles, decompile it, or log its network calls |
| Take screenshots as reference, kept in `docs/model/screens/` | Put its screenshots, words, logo or icons into our build |
| Click through at human pace | Run crawlers, loops, load tests or fuzzers against it |

Check the product's terms. Some forbid using an account to build a competing product. If ours does, say so in the model header and work from public sources only.

If the client owns the app and has only lost the source, the limits on bundles and network calls lift. Run the shipped-artifact path from SKILL.md as well.

## List the sources

Build a sources table first, with a URL on every row.

| Source | What it gives |
|---|---|
| Help centre or docs | The fullest feature list there is, plus every setting |
| Pricing page | Which features matter. They are the ones gated |
| Changelog | What shipped lately, and what the team thinks is important |
| App store listing | Screenshots of every key screen, the pitch, the rating |
| Public walkthrough videos | Real flows, click by click |
| Our own account | The real thing, in every state |
| Public API docs | The data model, almost for free |

## Screen inventory

One row per screen. IDs are stable: `S01`, `S02`.

`ID | screen | how you get there | purpose | key components | states seen`

Record every state you can reach: empty, loading, filled, error, no permission, phone width. Screenshot each to `docs/model/screens/S07-empty.png`.

Use a browser automation tool such as Playwright for web apps, and a simulator or device for mobile.

## Flows

`F01`, `F02`. Each is a goal and the screens it passes through, with edge cases.

```
F01 Guest books a slot
    S07 booking page -> S08 pick a time -> S09 details form -> S10 confirmed
    edge cases: no slots this week, time zone differs, slot taken mid-form
    clicks on the happy path: 4
```

Count the clicks on the happy path. That is the number to beat.

Also record what the screens do not show: which emails arrive, what is remembered between visits, what happens on a second device.

## Components

Every repeated UI part: buttons, inputs, date pickers, modals, tables, toasts, menus. Name, variants, states, and which screens use it. This feeds the design lens and the component build.

## Inferred data model

Entities, fields and relationships, each with the evidence it was inferred from.

```
Booking  id, event_type_id, start_at, end_at, guest_name, guest_email,
         status (confirmed | cancelled | rescheduled), answers (json)
         evidence: S09 form fields, S10 confirmation, help article "Cancel a booking"
         confidence: medium
```

Nothing inferred is ever `high`. A field seen on a form is `medium`. A relationship guessed from behaviour is `low`. Whoever designs the database turns this into a real schema and owns the final call.

## What cannot be rebuilt

List it plainly, as `skip` rows in `features.csv` with the reason: licensed content, the user network, data the product owns, partner deals, hardware, regulated licences. Rebuilding an app means its features and flows. It does not mean what the product owns.

## Size it

Count screens, flows and entities. Name the hard parts: realtime, sync, payments, calendar or email integrations, offline. Give a size: S (a weekend), M (a few weeks), L (a quarter), XL (rescope it). Promise nothing about a perfect match.
