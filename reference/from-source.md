# Source path: we have the code

The strongest model. Read the code as text and record what it does.

## Contents
- Safety first
- Inventory
- Find the framework's map
- Screens and flows
- Data model
- API and integrations
- Auth and roles
- Dead code
- Completeness check

## Safety first

If we did not write the repo, treat it as untrusted. Read files. Do not run `npm install`, a build, a test or any script in it until the model is done and someone has decided to. Config files are read as text, never imported.

## Inventory

```bash
git log -1 --format='%H %ad'
git ls-files | cut -d/ -f1-3 | sort -u | head -120
```

Record the commit hash in the model header. Read `package.json`, `requirements.txt`, `go.mod` or the equivalent for the stack. The README is a claim, not evidence. Check it against the code.

## Find the framework's map

Every framework keeps its list of screens and endpoints somewhere. Start there.

| Stack | Where the map is |
|---|---|
| Next.js App Router | `app/`: `page.tsx` is a screen, `route.ts` is an endpoint, `layout.tsx` is shared chrome |
| Next.js Pages Router | `pages/`, with `pages/api/` for endpoints |
| React with a router | The router config file |
| Vue or Nuxt | `pages/` for Nuxt, `router/index.*` for Vue |
| Expo or React Native | `app/` for Expo Router, or the stack and tab definitions |
| Express, Fastify, NestJS | Route registrations and controllers |
| Django, FastAPI | URL config and routers |
| Supabase | `supabase/migrations/`, `supabase/functions/`, RLS policies |

## Screens and flows

One row per screen: `S01 | name | route | purpose | key components | states`.

States are the part most often missed: empty, loading, filled, error, no permission, phone width. An empty state that is not recorded is an empty state that is not rebuilt.

Then the flows. Each is a goal and the screens it passes through:

```
F01 Guest books a slot
    S07 booking page -> S08 pick a time -> S09 details form -> S10 confirmed
    edge cases: no slots this week, time zone differs, slot taken mid-form
```

For each screen, record every interactive element and what it does. Buttons, forms and their validation, modals, keyboard shortcuts. The code can work while the behaviour stays hidden in a handler three files away.

## Data model

Find the schema: `schema.prisma`, Drizzle schema, `models.py`, migrations, `schema.sql`.

For each table: purpose, columns and types, constraints, foreign keys with their `on delete` rule, indexes, and the access rule (RLS policy, or the check in the data layer).

Look for what is missing as hard as for what is there. No unique index where two users could collide. No access rule on a table that holds user data. These are the findings a client pays for.

## API and integrations

One row per endpoint or server action: `method path | does what | who can call it | input | output | side effects | flow`.

Side effects are writes, outside API calls, queued jobs and emails sent.

Then find where the app talks to the outside:

```bash
grep -rnE "fetch\(|axios\.|createClient\(|new Stripe\(|Resend\(|openai" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.py" . | grep -v node_modules | head -80
```

For each service: what it is used for, which env var holds its key, and whether a webhook comes back in. Record the env var **name** only. Never copy a secret value into the model.

Background work goes here too: cron routes, queues, workers and their schedules.

## Auth and roles

Record the auth method, how a session is held, the roles that exist, and where each permission is checked. Name the one function or policy that answers "can this user do this to this record". If there is no single place, say so. That is a finding.

## Dead code

Before documenting a feature, check it is reachable:

```bash
grep -rn "ComponentOrFunctionName" --include="*.ts" --include="*.tsx" . | grep -v node_modules
```

Zero uses outside its own file means dead. List dead code under Uncertain with "appears unused, confirm before removing". Do not model it as a live feature.

## Completeness check

Before writing the model, confirm:

- Every route file appears as a screen or an endpoint.
- Every table appears in the data model.
- Every outside service appears under integrations.
- Every scheduled job is listed.
- Counts in the summary match the counts in the tables.

If the client needs a full product requirements document, the model is the input for it.
