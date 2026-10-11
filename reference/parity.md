# Parity pass

Run after the build, before release sign-off. It answers one question: does the rebuild do everything the model says the original did?

## Contents
- What parity means
- Feature parity
- Flow check
- Data check
- What ships
- Verdict

## What parity means

**Parity means it does the same job. It does not mean it looks the same.** Do not chase a pixel match with someone else's product. Its exact look is theirs.

## Feature parity

Update `docs/model/features.csv` first. Check each row against what is actually built, by reading the build output and the source, and set its `build` column yourself. A matrix left at `no` scores 0 and tells nobody anything.

**A parity pass reports. It does not build.** Do not write or change product code to make a row pass. List what is missing and hand it back.

Every row's `build` column is one of:

| Value | Means |
|---|---|
| `yes` | Works end to end, and you checked. A stub endpoint, or a screen with no handler, is not `yes` |
| `partial` | Some of it works. Say what is missing in `notes` |
| `no` | Not built |
| `skip` | Left out on purpose. The reason goes in `notes` |

Then run:

```bash
python3 scripts/parity.py docs/model/features.csv
```

It weights must 3, should 2, could 1 and counts partial as half. It leaves out `skip` rows and rows where `original` is `no`, because those are things we added. It prints the score, must-haves built, each area weakest first and what is left to build, in order.

**It exits 1 while any must-have is not `yes`, or the score is under 80.** A must-have cannot be `skip`. If it is truly out of scope, lower its priority and say why in `notes`. Fix the build or the row, then run it again. Do not edit a row to `yes` to make it pass.

## Flow check

Walk every flow in the model (`F01`, `F02`) in the rebuild. For each:

- Does it finish?
- Clicks on the happy path, against the count in the model. Fewer is a win.
- Each edge case listed in the model. What happens?
- Each state for each screen: empty, loading, error, no permission, phone width.

Use a browser automation tool such as Playwright for web, and a simulator or device for mobile.

**If the app cannot be run,** do not skip this check. Trace each flow through the rebuilt code, one step at a time: the screen, the handler it calls, the endpoint, the write. Do the same for each edge case. Say in the report that the flow was traced, not run.

Write each difference as: flow, original does, rebuild does, fix or keep.

## Data check

For a migration, the data has to arrive too.

- Row counts per table, old against new.
- A spot check of ten real records, field by field.
- Every access rule in the model has a test: a second user gets nothing back.

## What ships

```bash
python3 scripts/bundle_scan.py dist
```

Open every hit. A hit is a lead, not a verdict. A real secret in the bundle means rotate it, then rebuild.

For a mobile build, check each permission and usage description against a feature in the model.

## Verdict

| Verdict | Test |
|---|---|
| Not shippable | Any must-have missing, a flow that does not finish, or a real secret in the bundle |
| Shippable | All must-haves built, score 80 or more, every flow finishes, scan clean or every hit explained |

Give honest numbers. A rebuild at 62 is at 62.

End the answer with the verdict, the score, the must-have count and the next step: hand the verdict and both outputs to whoever signs off the release.
