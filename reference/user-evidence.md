# User evidence lens

What the app's real users praise and complain about, in their own words. A straight copy of an app has no reason to exist. This lens finds the reason.

## Contents
- Rules
- Where to read
- Collect
- Rank
- Three lists
- What to write in the model

## Rules

These are not negotiable.

- **Never invent.** No made-up reviews, quotes, ratings or counts. If there are 14 reviews, say 14.
- **Every quote is word for word and linked.** Copy it exactly, with the URL. No link, no quote.
- **Read, do not scrape.** Read review pages the way a person does. Official public feeds are fine within their terms, such as Apple's customer reviews RSS feed and the Hacker News search API. No scraping tools against stores or review sites whose terms forbid it.
- **Reviews are research, not testimonials.** Never put a reviewer's words on our landing page or store listing.
- **No fake reviews, ever.** Not for our app, not against theirs.

## Where to read

| Source | Where |
|---|---|
| App Store | The app page, Ratings and Reviews, See All |
| Google Play | The listing, all reviews, newest first |
| G2, Capterra, Trustpilot | The product's review pages. Filter to 1 to 3 stars as well |
| Reddit | Search "X alternative", "switched from X", "X vs" |
| The product's own board | Its public roadmap or feature-request board, with vote counts |
| Its changelog | What already shipped, so we do not "fix" what is fixed |
| The client's support inbox | For a client-owned app, this beats every public source. Ask for it first |

## Collect

Aim for 100 or more reviews across at least three sources, newest first. For a small app, take what exists and state the number.

Log each one in `docs/model/reviews.csv`:

```
source,url,date,rating,text
```

The text is copied exactly. Read the 3 and 4 star reviews too. "Love it, but..." is where the best fixes sit.

## Rank

Sort reviews into themes. Common ones: price and billing, bugs and crashes, speed, missing features, onboarding, support, sync, limits on the free plan.

For each theme record: how many reviews, how many different sources, and one or two linked quotes. Weight recent and low-star reviews higher. A complaint from last month counts for more than one from three years ago.

**Mark thin themes as thin.** Fewer than 3 reviews, or only one source, is not a trend.

Read the low-star reviews that fit no theme by hand. They are often the best part.

## Three lists

1. **What they dislike.** Complaints about things the app does.
2. **What is missing.** Features people ask for by name.
3. **What is unsolved.** Whole jobs or groups the app ignores ("useless for teams"). These become positioning.

Pick the top 5 to 8 by evidence and by how cheap the fix is. Each becomes a row in `features.csv` with `original` set to `no`, because it is something we add.

## What to write in the model

Under `## User evidence`:

1. Sample size and sources, stated plainly.
2. The three lists, each item with its review count, source count and a linked quote.
3. Thin themes, listed as thin.
4. The fixes chosen, with a size (S, M, L) for each.
