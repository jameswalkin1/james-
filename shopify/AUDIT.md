# HaloScalp store audit — 13 Sep 2026

Store: `zj9dzm-vc.myshopify.com` · Basic plan · EUR · Ireland
Catalogue: 1 product · Orders to date: **0**

---

## Fixed already (live on the store)

| # | Was | Now |
|---|-----|-----|
| 1 | Title `LED Red Light Therapy Hair Growth Cap with Infrared Heat` | `HaloScalp Red Light Therapy Cap — 100 LEDs, Dual-Band + Infrared` |
| 2 | Description = raw supplier copy, 6 images hotlinked from `oss.teemdrop.com` | Rewritten: benefit-led, brand voice, no supplier assets |
| 3 | SEO title + description both `null` | Both written, keyword-targeted |
| 4 | No tags, product type `Cap` | 7 tags, type `Scalp Care Device` |
| 5 | Option `color` = `100Leds Cap DualBand PlugIn` | Option `Model` = `100 LED Dual-Band` |
| 6 | FAQ described a **cap insert** with **4 modes** | Rewritten to match the actual product |
| 7 | Returns page said "Halo Scalp cap insert" | Corrected to "HaloScalp cap" |

Handle left unchanged deliberately, so no URL breaks or redirects.

---

## The three things that were actually going to cost you money

### 1. Your pages described a different product from the one you sell
The FAQ and returns pages (written 13 Aug) describe a **flexible insert that sits
inside a cap you already own**, with **four modes**. The product you listed today
is a **full cap** with **three gear settings**. A customer reading your FAQ and
then opening the box gets something else. That is a chargeback, not a return —
"item not as described" is one of the few disputes you lose automatically.

Fixed. But it shows the real risk: the pages were written for a product you no
longer sell, and nothing flagged it.

### 2. The supplier copy contradicted itself
The description claimed a **"built-in rechargeable battery for cordless use"**
while the variant you sell is literally named **"PlugIn"**. It also advertised
**"48, 56, 100 or 108 LED configurations"** when you stock exactly one.

I wrote the new copy to say "power cable" and avoid claiming cordless —
**confirm which it actually is before you run traffic.** If it's mains-powered,
"cordless" in any ad creative is a false advertising claim in the EU.

### 3. Six images were hotlinked from your supplier's CDN
The description pulled images straight from `oss.teemdrop.com`. Three problems:
the supplier can delete them and break your page overnight; they usually carry
other sellers' branding and text; and it identifies you as a dropshipper to
anyone who right-clicks. Removed. If any of those images had specs worth
keeping, re-upload them to Shopify's own CDN.

---

## Still open — needs you

**Homepage still has food-brand demo copy.** The live Savor theme contains
"A Family Tradition of Bold, Fresh Flavor" and an empty hero text block, plus a
video block with no URL that renders as a blank box. The Admin API refuses writes
to a live theme, so this one is yours — paste-ready copy is in
`shopify/copy/homepage-copy.md`.

**Do not fake a compare-at price.** The obvious "fix" for €69.99 looking cheap is
to set a €149 strikethrough. Under the EU Omnibus Directive that is illegal
unless you genuinely charged €149 for 30 days first. Irish CCPC enforces it.
If you want a higher perceived value, raise the real price — €69.99 is arguably
under-priced for this category anyway (competitors sit €150–€400), and cheap
reads as ineffective in a market where people equate price with efficacy.

**SKU is still the supplier's** (`SU00129491-100Leds Cap DualBand PlugIn`).
Left alone on purpose — your fulfilment app probably matches on it. Change it
only if you know it won't break the link.

**Inventory shows 1000 units** with policy `CONTINUE`. Fine mechanically, but
some themes surface the number, and "1000 in stock" from a one-product store
reads as dropship. Consider hiding the count.

**Claims and ad approval.** You're published to Facebook & Instagram. Meta
routinely rejects hair-loss advertising that uses before/after imagery or implies
regrowth. The new copy is deliberately hedged — keep ad creative equally hedged
or you'll burn the ad account rather than the budget.

---

## On "start making money"

Worth being straight, since the copy above is: the listing was blocking sales,
but fixing it doesn't cause them. You have zero orders because you have zero
traffic, and nothing in this audit changes that. What this work does is make sure
the traffic you eventually buy doesn't land on a page contradicting itself and
bounce.

The order of operations from here is: finish the homepage → decide the
plug-in/rechargeable question → get 3–5 real photos or a video of the actual
product (the single highest-converting asset you don't have) → then spend on
traffic. Buying traffic before the homepage is fixed is setting money on fire.
