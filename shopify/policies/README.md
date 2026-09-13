# Store policies — paste into Settings → Policies

The Admin API refused `shopPolicyUpdate` (no `write_legal_policies` scope), so
these could not be installed automatically. Paste each file's contents into the
matching box at **Shopify admin → Settings → Policies**.

Why this matters: your **pages** (`/pages/returns`, `/pages/shipping`) are not the
same thing as your **policies**. Checkout, order confirmation emails, Shopify
Payments review and Meta's commerce review all read the *policies*. Right now you
have a privacy policy and nothing else, which is a gap at checkout and a common
reason Shopify Payments holds payouts on a new store.

| File | Paste into |
|---|---|
| `refund-policy.html` | Refund policy |
| `shipping-policy.html` | Shipping policy |
| `terms-of-service.html` | Terms of service |
| `contact-information.html` | Contact information — **needs your address first, see below** |

## Contact information — read before pasting

EU and Irish distance-selling rules require a **geographic address** on the site,
not just an email. The only address on your Shopify account is
**8 Bartra Green, Co. Mayo, F26 Y039** — which looks like your home address.

I have deliberately **not** published it. Your options:

1. Publish it. Legally cleanest, but it is then public on the open internet.
2. Register a business address or use a virtual office / mail-forwarding service
   in Ireland, and publish that.
3. If you trade as a registered company, use the registered office address.

Fill the `[ADDRESS]` placeholder in `contact-information.html` with whichever you
pick, then paste.

## Not legal advice

These are solid, honest starting drafts written to match how you actually
operate. They are not a substitute for a solicitor, and the terms of service in
particular is a template. If this store starts taking real money, get them
reviewed.
