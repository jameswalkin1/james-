# HaloScalp store audit — 13 Sep 2026

Store: `zj9dzm-vc.myshopify.com` · Basic plan · EUR · Ireland
Catalogue: 1 product · Orders to date: **0** · Storefront: live, no password

---

## Done — live on the store now

### Product
- **Title** → `HaloScalp Red Light Therapy Cap — 100 LEDs, Dual-Band + Infrared`
  (was `LED Red Light Therapy Hair Growth Cap with Infrared Heat`)
- **Description** rewritten from raw supplier copy. Leads on cordless use, states
  delivery honestly, includes a "straight talk on results" section and safety notes.
- **Six supplier-hotlinked images removed** from the description body. They were
  served from `oss.teemdrop.com` — the supplier could delete them and break the
  page, and they identify the store as dropshipping.
- **Price** → €79.99 (was €69.99)
- **SEO title and description** written (both were `null`)
- **Tags** (7) and product type `Scalp Care Device` added
- **Variant option** → `Model: 100 LED Dual-Band` (was `color: 100Leds Cap DualBand PlugIn`)
- **Alt text** on all 8 images (all were empty)
- **Metafields** set: `descriptors.subtitle` (the theme reads this on product
  cards and it was rendering blank), `halo.card_spec`, `halo.lede`

### Pages
- **FAQ** — rewrote to match the product actually being sold, added "Is it
  cordless?" and "Do you ship to my country?"
- **Shipping information** — rewrote for all 28 destinations with real rates and
  per-region delivery estimates
- **Returns & refunds** — corrected the product name
- **Contact** — was completely empty; now has copy above the form
- **About HaloScalp** — new page, didn't exist

### Theme
- Duplicated the live theme as **"Savor — HaloScalp copy (review before
  publishing)"** and fixed the homepage on the copy. Preview it, then publish.
  The Admin API blocks writes to a live theme, which is why it's a duplicate.

---

## The things that were actually going to cost money

### 1. The site described a different product from the one being sold
The FAQ and returns pages described a flexible **insert** that sits inside a cap
you already own, with **four modes**. The listed product is a **full cap** with
**three** intensity levels. A customer reading the FAQ and then opening the box
gets something else — that's "item not as described", one of the few chargebacks
you lose automatically. Fixed.

### 2. The supplier copy contradicted itself on power
It advertised a built-in rechargeable battery while the variant was named
"PlugIn". Confirmed as **rechargeable**, and the copy now leads on cordless use —
which is the single strongest differentiator against helmet-style competitors.

**Residual risk:** the supplier's own SKU string still reads `PlugIn`. If a unit
arrives with no battery, the cordless claim is the first thing to pull.

### 3. Checkout accepted orders the shipping page said we refused
The pages promised "Ireland and the UK only" while checkout accepted 27 countries
including the US, Australia and Japan. Resolved by keeping all 27 countries and
rewriting the pages to match reality.

---

## Still needs you

### Publish the theme copy
Online Store → Themes → preview **"Savor — HaloScalp copy"** → Publish. Until you
do, the live homepage still reads *"A Family Tradition of Bold, Fresh Flavor"* —
Savor's demo copy, written for a food brand, on a hair-loss store.

### Install the store policies
You have a privacy policy and nothing else. Drafts are in `shopify/policies/`;
paste them into Settings → Policies. The API refused to write them
(`write_legal_policies` scope not granted).

This matters more than it sounds: your **pages** are not your **policies**.
Checkout, order emails, Shopify Payments review and Meta commerce review all read
the policies. A new store with no refund policy at checkout is a common reason
Shopify Payments holds payouts.

`contact-information.html` needs an address decision first — see
`shopify/policies/README.md`. The only address on the account looks like a home
address and I have not published it.

### Get real photographs
Shot list in `shopify/photo-shot-list.md`. This is the highest-value thing left
and nothing in the copy substitutes for it.

---

## Notes and corrections

**The two Ireland shipping rates are not a bug.** An earlier version of this file
called the €6.00 and €0.00 "Standard" rates an accidental duplicate. They are not:
the €0.00 entry is a free-shipping condition on the same rate, triggered at
**€65 or more**. At €79.99 every single-cap order ships free within Ireland. The
shipping page now states this precisely.

**Do not fake a compare-at price.** Setting a €149 strikethrough to make €79.99
look like a deal is illegal in the EU under the Omnibus Directive unless you
genuinely charged €149 for 30 days first, and the CCPC enforces it in Ireland.

**Alt text is approximate.** The images could not be loaded from this environment,
so the alt text describes the product accurately but does not describe what each
specific shot shows. Refine it when you can see them side by side.

**`halo.wavelengths` is deliberately empty.** The metafield exists but the actual
nm figures aren't in any source I can see. Typical dual-band devices are around
650nm and 850nm, but do not publish those numbers until the supplier confirms —
a fabricated spec is exactly the kind of claim that gets a listing pulled.

**SKU left as the supplier's** (`SU00129491-100Leds Cap DualBand PlugIn`). Your
fulfilment app probably matches on it; changing it could break order routing.

**Inventory shows 1000 units** with an oversell policy. Mechanically fine, but if
your theme surfaces the number, "1000 in stock" from a one-product store reads as
dropshipping.

**Leftover Zendrop delivery profile** with worldwide free shipping priced in USD,
while the store runs in EUR. The product isn't linked to Zendrop, so it's inert —
but delete it before it collides with something.

**A `bartragreen43@gmail.com` contact address on a `myshopify.com` domain** is the
main remaining trust problem after the homepage. A custom domain and a matching
email address is the cheapest credibility you can buy at this price point.

---

## On "start making money"

The listing was blocking sales; fixing it does not cause them. There are zero
orders because there is zero traffic, and none of this changes that. What it does
is make sure traffic you eventually pay for doesn't land on a page that
contradicts itself.

Order of operations: publish the theme → install the policies → get real photos →
custom domain → then spend on traffic. Note that Meta routinely rejects hair-loss
advertising that uses before/after imagery or implies regrowth, and the store is
already published to the Facebook & Instagram channel. Keep ad creative as hedged
as the product copy or you lose the ad account rather than just the budget.

---

# Round 2 — homepage, header and one-product restructure

Triggered by a screenshot of the live preview. Two things were visible there that
the API had not shown.

## What the screenshot revealed

**1. The header was set to transparent on the homepage, with white text.**
`enable_transparent_header_home: true` plus `text_color_transparent_home` set to
the background colour meant the logo, hamburger, account and cart icons were
white-on-white over the hero image. That is why the menu was effectively
invisible. Set to `false` for home, product and collection, text switched to the
foreground colour, and a 1px bottom border added so the header reads as a header.

**2. The product images are supplier marketing banners, not product photos.**
The hero image is a poster that already contains its own headline
("HEALTHIER HAIR / A BRIGHTER YOU"), a benefit icon row, and the line
"INVEST IN A HEALTHIER YOU". The homepage headline was being overlaid directly on
top of that, producing two competing sets of text in the same space, in giant
uppercase, half of it unreadable.

This is worse than a layout bug:

- **The banners carry claims the copy deliberately avoids.** They say
  "SUPPORTS NATURAL GROWTH" and "Red Light Therapy **Hair Growth** Cap". The
  product copy was rewritten specifically to stop asserting growth. The images
  now contradict the text on the same page.
- **Meta rejects this category of creative** for hair-loss advertising. Since the
  store is published to the Facebook & Instagram channel, these images are what
  would be pulled into ads.
- Every other store selling this cap is using the same banners.

The shot list in `shopify/photo-shot-list.md` has now gone from "highest-value
improvement" to **the blocking item**. Until there are real photographs, the site
is arguing with itself.

## Homepage rebuilt as a one-product store

The `hero` section and the `product-list` grid are both gone. A collection grid
showing exactly one product is not a shop, and the hero could not be salvaged
while the only available image is a poster with baked-in text.

New structure:

1. **`featured-product`** — product image on the left, title, price and swatches
   on the right, clicking through to the product page. For a single-product store
   this is the hero: the product is the message, and nothing is overlaid on
   anything.
2. **"Most light therapy devices end up in a drawer"** — text band on the second
   brand colour.
3. **"Straight talk before you buy"** — new text band covering the honest framing,
   delivery times and the returns window, so the three things most likely to cause
   a refund are stated before the click, not after.

## Navigation

The main menu contained two links to anchors that do not exist on the homepage
(`/#how-it-works` and `/#wavelengths`). They scrolled nowhere. Both menus are now:
The cap · FAQ · Shipping · Returns · About · Contact.

## Footer

Still carried Savor's food-theme demo copy — the email signup read
"We send tasty emails" — plus three menu columns where two pointed at menus that
did not exist, and five social links pointing at `facebook.com`, `instagram.com`,
`youtube.com`, `tiktok.com` and `x.com` — the platforms' own homepages, not any
HaloScalp profile. Dead social icons read as a scam site more than as no icons at
all, so they are removed. Add them back when there are real accounts to link.

## Still on the duplicate theme

Everything above is on **"Savor — HaloScalp copy (review before publishing)"**,
still unpublished. Preview it and publish when you are happy. The live theme is
untouched and still shows the food copy.

---

# Round 3 — image cropping and typography

From a second screenshot of the product page in preview.

## The cropping

The product gallery was set to **square (`aspect_ratio: "1"`) with `media_fit: "cover"`**.
The images are tall infographics. Forcing a tall image into a square with `cover`
crops the top and bottom off — which is why "CONCENTRATED LIGHT THERAPY" was cut
in half.

Changed to `aspect_ratio: "adapt"` so each image renders at its own proportions,
`media_fit: "contain"`, and `media_columns` from two to one, because these are
things to be *read*, not decorative shots to be tiled. Nothing is cropped now.

## Typography

The theme had every heading level forced to **uppercase**, with h2 at **48px**.
On a 60-character product title that produced a wall of capitals. Set h1–h4 to
sentence case, h2 to 36px, and kept h5/h6 uppercase for small labels where it
still works. Body text raised from 14px to 16px — 14px is small for an audience
that skews older.

## Product page order

The add-to-cart button sat *below* the full description, so on mobile you had to
scroll through roughly 500 words before you could buy. Reordered to
title → price → variant → buy → description.

Also removed the **reviews block** (it renders an empty star rating on a store
with no reviews, which reads worse than no stars at all) and the **related
products section** (it has nothing to recommend on a one-product store).

## A contradiction in the infographics — needs your supplier

The specification banner is now legible, and it says:

> 100 PIECES — Red light 660nm
> 200 PIECES — Near red light 850nm

That is **300 LEDs**. The product title, variant and all the copy say **100**.
One of the two is wrong, and both are currently on the same page.

Either the title is undercounting by a factor of three, or the banner belongs to
a different model in the supplier's range. Get this confirmed before running any
traffic — "300 LEDs" is a materially better selling point than 100 if it is true,
and a false advertising problem if it is not.

The same banner gives the wavelengths as **660nm and 850nm**, which are the
standard pairing. The `halo.wavelengths` metafield is still deliberately empty:
given the LED count on the same image is in dispute, the wavelengths from it are
not yet trustworthy enough to publish as a spec.

---

# Round 4 — uneven image sizes

The images are four different aspect ratios (5:6, 2:3, 9:16 and square). Reading
`snippets/product-media-gallery-content.liquid`, the theme allows uniform frames
*or* uncropped images, never both — a fixed ratio forces `object-fit: cover`.

Applied a fixed `1/1.25` frame plus a `custom-liquid` section holding a CSS
override that forces `contain` back on. Frames are now identical and nothing is
cropped; the shape mismatch shows as white space instead of lost content.

That is a workaround. The permanent fix is re-exporting all eight images at 4:5,
padded rather than cropped — spec and method in `shopify/image-spec.md`. I could
not do it here: `cdn.shopify.com` is blocked by the session's egress policy, so
image bytes are unreachable, though Admin API metadata still gave exact dimensions.

---

# Round 5 — homepage stripped back

## The teal t-shirt

That was Shopify's **placeholder graphic**, not a broken image. The
`featured-product` section renders its media through a `_media-without-appearance`
block which reads its *own* `image` setting — it does not inherit the product's
featured image. I left that setting empty when I built the section, so it fell
back to the placeholder. The title and price rendered fine, which is why only the
image was wrong.

## New homepage

Replaced `featured-product` with `media-with-content`, holding exactly what was
asked for:

1. The product image
2. The price, directly underneath
3. **Buy now** (primary) → the product page
4. **How it works** (secondary) → the new page

On mobile the section stacks, so the price and both buttons sit immediately under
the image. Both buttons are full-width on mobile for tapping.

The price is a `custom-liquid` block reading `all_products[...].price | money`,
so it tracks the real product price and cannot go stale. A plain text block was
rejected — `themeFilesUpsert` validates dynamic sources in text settings against
an allowlist, and `all_products` is not on it.

## New page: How it works

Created `/pages/how-it-works` and added it to both menus. Covers what red light
therapy is, the five-step routine, why consistency beats intensity, honest
expectations, and safety.

It deliberately does **not** quote wavelengths, LED counts or Hz figures, because
the supplier's own images contradict each other:

- One banner: "100 PIECES Red light **660nm**" + "200 PIECES Near red light 850nm"
- Another banner: "100 High-Performance LEDs" + "**650**nm Red Light + 850nm Near Infrared"

So the source material disagrees with itself on both the LED count (100 vs 300)
and the red wavelength (650 vs 660nm). None of it is safe to publish as a spec
until the supplier confirms.

## One thing given up deliberately

The homepage now has **no `<h1>`**, because the request was for image, price and
two buttons only. That costs some SEO — Google has no headline to read on the
store's most important page. A single line above the price would fix it without
adding clutter.

---

# Round 6 — visual redesign

Brief: livelier, more inviting, less text, some motion. Four decisions taken with
the user beforehand: **warm premium** palette, **confident but tasteful** motion,
honesty copy **cut from the homepage**, and design **around** the supplier images
rather than leaning on them.

## Palette (store-wide)

| Token | Was | Now |
|---|---|---|
| background | `#ffffff` | `#FBF8F3` warm paper |
| foreground | `#000000` | `#22201C` soft charcoal |
| color1 | `#a42325` red | `#22201C` charcoal — primary buttons |
| color2 | `#e8d5c7` | `#EFE4D6` warm sand |
| color3 | `#E6E6E6` grey | `#E2D6C6` warm line |

Pure black on pure white is most of what made it feel cold and cheap. Buttons are
now pill-shaped, sentence case rather than uppercase, with a visible border on
secondaries. Gold `#B08D57` is used only as a micro-accent on eyebrows and step
numbers — never as a fill, which is what makes gold look cheap.

## Homepage rebuilt as one designed section

The theme's block system kept producing serviceable-but-flat layouts, so the
homepage is now a single `custom-liquid` section with hand-written HTML and CSS.
Full design control; the trade-off is that it is edited as code rather than by
dragging blocks in the theme editor.

Four sections, roughly 60 words of body copy total:

1. **Hero** — eyebrow, two-line headline, price, two buttons, one micro line of
   reassurance. A slow red radial glow pulses behind it (7s), which is the product
   rendered as atmosphere rather than as another banner.
2. **Number strip** — 100 / 3 / 0 / 30 with one-word labels, staggered in.
3. **Three steps** — Charge, Wear, Carry on. One line each, cards lift on hover.
4. **Closing band** — charcoal, one line, repeated CTA with the price.

The price and product URL are read live from Liquid, so nothing goes stale.

## Motion

Scroll reveal via `IntersectionObserver` (fade plus 18px rise, staggered), the
hero glow pulse, button lift on hover and focus, card lift on the steps.
Everything is wrapped in `prefers-reduced-motion: reduce`, and elements are
revealed unconditionally if the observer is unavailable — so nothing can end up
permanently invisible.

## Product page

Same treatment, lighter touch: gallery frames get a warm border and rounded
corners, images after the first fade in on scroll, buy buttons lift on hover.
The first image is never hidden, so the page is never blank on load.

## Note on the honesty copy

Removed from the homepage as requested. It still appears in full on the product
page and on How it works, so the compliance position is unchanged — but the
homepage no longer leads with the caveat. Worth knowing that was the most
distinctive thing on the page, and it can go back as one line if the new version
feels too much like everyone else's.

---

# Round 7 — white/red palette, accordion product page

Three asks: different colours, stop over-using the cordless angle, and put the
product page content behind click-to-open sections. Colours and section
behaviour were chosen by the user beforehand.

## Palette — white with one red

| Token | Was (warm premium) | Now |
|---|---|---|
| background | `#FBF8F3` | `#FFFFFF` |
| foreground | `#22201C` | `#111111` |
| color1 | `#22201C` charcoal | `#D92D20` red |
| color2 | `#EFE4D6` | `#F7F7F6` |
| color3 | `#E2D6C6` | `#E5E5E3` |

Red is now the only colour on the site and it does all the work: primary buttons,
the number strip, step numbers, the eyebrow, the hero glow. Everything else is
black, white and grey. Corners went from pills to an 8px radius, which reads less
consumer-app and more device brand.

## Product page — accordion sections

Built with the theme's native `accordion` block and three `_accordion-row`
children, so they stay editable in the theme editor rather than being hand-rolled
HTML:

1. **What's in the box** (box icon, open by default)
2. **How to use it** (stopwatch icon)
3. **Delivery & returns** (truck icon)

They sit directly below the buy button, expand in place with a + toggle, and
multiple can be open at once. Rows get a larger tap target, a red hover state, and
their content slides in over 320ms.

The product description was cut to match — "How to use", "In the box" and
"Delivery & returns" are gone from it, since they are now the accordion rows. What
remains is the lead, why-a-cap, the spec list, straight talk on results, and
safety.

**Note on the safety section:** it was not one of the chosen accordion rows, so
rather than delete it, it stays in the product description body. Dropping the
"not a medical device" language entirely would have been a compliance regression.

## Cordless, dialled back

It had crept into the eyebrow, a strip stat, a step, a whole FAQ question and
three lines of description. Now one mention per surface:

- Homepage eyebrow → "Red + near-infrared light therapy"; the "0 cables" stat
  became "2 wavelengths"; step 01 keeps a single passing reference
- FAQ → the standalone "Is it cordless?" question is gone
- Product description → one clause in the opening paragraph

## The images changed under us

Mid-round, six new images appeared on the product, replacing most of the old
supplier banners. They are all **1122 × 1402**, a ratio of exactly 0.80 — which
is precisely the `1/1.25` gallery frame already configured. They fit with no
letterboxing at all.

The original featured image is still 1145 × 1374 (0.833), so it is the one odd
one out and will show a hairline of white at top and bottom. Re-exporting that one
at 1122 × 1402 would make the gallery perfectly uniform, and the `contain`
override in `gallery_fit_css` could then be removed entirely.

All six new images had empty alt text; generic but accurate alt text is set. It
still cannot describe what each shot actually shows, because `cdn.shopify.com`
remains blocked from this session.

---

# Round 8 — everything into sections

The remaining description content ("Why a cap, not a helmet", "What you get",
"Straight talk on results", "Safety") was still a wall of text below the buy
button. It is now all in accordion rows.

Six sections, in the order people actually want them:

| Section | Icon | Default |
|---|---|---|
| What you get | check box | **open** |
| Why a cap, not a helmet | question mark | closed |
| How to use it | stopwatch | closed |
| What's in the box | box | closed |
| Delivery & returns | truck | closed |
| Results & safety | heart | closed |

The product description is now a **single paragraph** — the lead line only —
because everything else would otherwise appear twice on the page.

## Two consequences worth knowing

**The detail text now lives in the theme, not in the product.** Accordion content
is stored in `templates/product.json`, not in Shopify's product record. Changing
theme, or duplicating the product, will not carry it across. The copy is version
controlled in this repo (`shopify/theme/product.json`), so it is recoverable, but
it is no longer edited from the product admin page.

**The Facebook & Instagram catalogue description is now one line.** That channel
reads the product description field, not the theme. A one-line description is
thinner than ideal for catalogue ads. If that becomes a problem, the fix is to put
the fuller copy back in the description field and drop the duplicate accordion
rows — worth revisiting before any catalogue ad spend.

**SEO is unaffected.** Accordion content sits in `<details>` elements in the page
HTML, so it is still crawlable; it is collapsed visually, not absent.

---

# Round 9 — homepage hero image

Swapped the homepage image from the "Concentrated light therapy" infographic to
the clean packshot (the two caps, one lit). It is the better homepage image by a
distance: a product shot rather than a dense spec diagram, and it does not fight
the headline sitting beside it.

**Selected by alt text, not position.** The image carries the alt
`HaloScalp LED red light hair care cap`, and the homepage Liquid picks it with
`where: 'alt', ...` falling back to the featured image. Reordering the gallery
cannot break it, and swapping the hero later is a matter of moving that alt string
to a different image. A comment in the Liquid says so.

Confirmed it is the sixth of seven in the gallery, matching the carousel dot in
the screenshot.

## Correction: the "100 vs 300 LEDs" contradiction is probably not one

Earlier rounds flagged the LED count as a possible false-advertising problem. With
both new banners readable, the numbers reconcile:

- Packshot: "300 three-core lamp beads"
- Spec banner: "100 PIECES Red light 660nm" + "200 PIECES Near red light 850nm"

100 + 200 = 300. The two banners agree with each other; they are counting the same
device. So this is not a contradiction between images — it is a mismatch between
the images and **our** title, which says 100 LEDs.

The likely explanation is that 100 refers to the red emitters only, or to physical
modules rather than beads. Either way the title may be **underselling** a 300-bead
device rather than overstating a 100-LED one, which is the opposite of the risk
originally flagged. Still worth one message to the supplier before changing the
title or the homepage "100 LEDs" stat — but the compliance alarm can be stood down.

---

# Round 10 — buy buttons

**The theme is live.** The draft was published between rounds, so
`Savor — HaloScalp copy` is now MAIN and the API refuses writes to it. Changes
now go on a fresh duplicate — currently
**"HaloScalp — buy button update (review before publishing)"** — which a person
publishes manually. That is the loop from here on.

Four decisions taken with the user first.

## Shop Pay, demoted not deleted

Shopify locks the Shop Pay purple; it cannot be recoloured by anyone, so the only
real choices were keep or hide. Kept for the one-tap conversion, but made
secondary: pushed below a hairline divider labelled "or check out with", height
reduced to 46px, corners matched to 10px. Add to cart is unambiguously the
primary action now.

## Quantity picker hidden

`.quantity-selector-wrapper:has(quantity-selector-component)` — scoped with
`:has()` so it only hides on the **product form**. The cart renders
`cart-quantity-selector-component` instead, so shoppers can still change quantity
there and no sale is lost. Add to cart takes the full row.

Note this is CSS, not a template removal: the block is a *static* block, so the
theme renders it whether or not it appears in `product.json`. Hiding was the only
route. Browsers without `:has()` support will still show it, which is a harmless
fallback.

## Add to cart restyled

Full width, 10px corners, heavier weight, larger tap target, a 2px resting shadow
that lifts to a red-tinted glow on hover and presses back down on click. Matches
the homepage buttons so the two pages read as one site.

## Price in the button

"Add to cart — €79.99". Injected by JS from `{{ product.price | money }}`, so it
tracks the real price rather than being typed in. A MutationObserver re-applies
it if the theme re-renders the form after a cart or variant change, and it skips
disabled (sold out) buttons.

Also tidied "More payment options" from a bare underlined link into something
deliberately quiet.

---

# Round 11 — status review

Live check, not memory.

| | Status |
|---|---|
| Live theme | `Savor — HaloScalp copy` (published) |
| Buy-button draft | **not published yet** |
| Storefront | public, no password |
| Product | ACTIVE, on Online Store / Shop / POS / Facebook & Instagram |
| Orders | **0** |
| Domain | `zj9dzm-vc.myshopify.com` — **no custom domain** |
| Policies | **privacy only** — refund, shipping, terms, contact all still missing |
| Contact email | `bartragreen43@gmail.com` |
| Inventory | 1000, oversell on |

Fixed this round: the SEO meta description still read "Ships to Ireland & the UK",
left over from before the shipping scope changed. It now matches the 28
destinations checkout actually accepts. Search engines were being told something
the shipping page contradicts.

## The four things blocking a sale

1. **Store policies.** Still privacy-only. Drafts have been sitting in
   `shopify/policies/` since round 1. Checkout, order emails and Shopify Payments
   review all read these, not the pages.
2. **Nobody has ever completed a checkout.** Zero orders means the payment →
   confirmation → fulfilment path has never been exercised end to end. A test
   purchase is the only way to know it works.
3. **No custom domain.** `zj9dzm-vc.myshopify.com` reads as unfinished to a
   first-time visitor being asked for €79.99.
4. **No social proof of any kind.** No reviews, no photos that aren't the
   supplier's, no named business.

## The number that decides whether ads are viable

The landed cost per unit is not recorded anywhere in this store, and it decides
everything about paid traffic. At €79.99 with free Irish delivery, gross margin
is €79.99 minus landed cost minus transaction fees. Meta customer acquisition
cost in hair-loss categories commonly runs €30–60. If landed cost is €35, there
is roughly €40 of room and ads are marginal-but-possible; if it is €55, paid
acquisition cannot work at this price and the route has to be organic or the
price has to rise.

---

# Round 12 — Ireland references removed

Brief: take the Irish-brand framing out of the store.

## Removed

| Where | Was | Now |
|---|---|---|
| About page | "a small independent operation **based in County Mayo, Ireland**" | "a small independent operation" |
| Shipping page | "We ship to **Ireland** and to 27 further countries" | "We ship to 28 countries" (Ireland listed alphabetically among them) |
| Shipping page | Delivery table led with an Ireland row | Rows are UK / Europe / rest of world |
| Shipping page | "standard delivery **within Ireland** is free on a single cap" | Cost table only, no commentary |
| FAQ | "We ship to **Ireland**, the UK, most of western Europe…" | "28 countries across Europe, North America, Asia, Australasia and the Middle East" |
| FAQ | "7–14 business days to **Ireland** and the UK" | "7–18 business days across Europe and the UK" |
| Homepage hero | "**Free delivery in Ireland** · 30-day returns" | "Ships to 28 countries · 30-day returns" |
| Product accordion | "roughly 7–14 to **Ireland** and the UK… Free standard delivery **within Ireland**" | Neutral ranges; cost calculated at checkout |
| SEO meta description | "Free delivery in **Ireland**, ships to 27 more countries" | "Ships to 28 countries" |
| Header | country/region selector was on, showing a flag | `show_country` and `show_language` set to false |

Store pages, the product and its SEO are live. The theme changes are on the
**"HaloScalp — buy button update"** draft, which now also carries this round.

## Deliberately left, with reasons

**Ireland still appears once in the shipping rate table.** It has to: the €6.00 /
free-over-€65 / €9.00 express rates are configured in Shopify against the
domestic (Ireland) zone, and everywhere else pays a flat €16.00. Removing the
word would leave the page unable to explain why some customers pay nothing and
others pay €16 — recreating exactly the copy-versus-checkout mismatch fixed in
round 1.

To remove it properly, the **shipping zones themselves** have to change: collapse
to a single worldwide rate. That is a money decision (either give free delivery
worldwide, or start charging domestic customers €16), so it is not something to
do quietly.

**`terms-of-service.html` still says governed by the laws of Ireland.** A
governing-law clause has to name a real jurisdiction, and it has to be the one
you actually trade from. Changing it to a country you have no connection to would
make the document worse than useless. Same for **`contact-information.html`**,
where EU distance-selling rules require a genuine geographic address.

If the intent is to trade from somewhere else, that is a real-world change —
company registration, address, tax — not a copy edit, and worth an accountant
rather than me.

**The returns page still cites EU and UK consumer law.** Those are the statutory
rights your customers actually have; they are not brand positioning.
