# Image spec — the permanent fix for uneven photos

## The actual problem

The eight product images are **four different shapes**:

| Image | Pixels | Ratio |
|---|---|---|
| 1, 3 | 1145 × 1374 | 0.83 (5:6) |
| 4, 5, 6, 8 | 1024 × 1536 | 0.67 (2:3) |
| 2 | 941 × 1672 | 0.56 (9:16) — much taller than the rest |
| 7 | 1254 × 1254 | 1.00 (square) |

No theme setting fixes mismatched source images. The Savor gallery offers exactly
two behaviours, and the logic is hard-coded in
`snippets/product-media-gallery-content.liquid`:

```
if aspect_ratio != 'adapt'   -> media-fit-cover   (uniform frames, but CROPS)
elsif constrain_to_viewport  -> media-fit-<media_fit>
else                         -> media-fit-contain (never crops, frames VARY)
```

So out of the box you pick one: uniform or uncropped, never both.

## What is currently applied

A fixed `1/1.25` frame plus a small CSS override (a `custom-liquid` section named
`gallery_fit_css` at the top of the product template) that forces
`object-fit: contain` back on. Result: every frame is the same size, and nothing
is cropped — the difference in shape shows up as white space at the edges of the
odd-sized images instead.

This is a workaround, not a fix. It is stable and safe, but images 2 and 7 will
carry visibly more white space than the rest because they are furthest from 4:5.

## The permanent fix

Re-export all eight at **one ratio, padded not cropped**:

- **Ratio:** 4:5 portrait
- **Size:** 1600 × 2000 px
- **Background:** white `#ffffff` (matches the theme background exactly)
- **Method:** fit the whole image inside the canvas and pad the gaps. Do **not**
  crop, and do not stretch — these images contain text.

Anything that can pad an image does this: Canva (custom 1600×2000, drop image in,
fit to frame), Photopea (free, browser, Image → Canvas Size), or Preview on a Mac.

Once all eight are 4:5, delete the `gallery_fit_css` section from the product
template and set the gallery back to a plain `1/1.25` frame. Everything will be
uniform with no white space and no workaround.

## Why I could not do this for you

`cdn.shopify.com` is blocked by your organisation's egress policy for this
session — the proxy returns 403 on connect. I can read image *metadata* through
the Admin API, which is how the table above was produced, but I cannot download
the image bytes to re-pad them or upload replacements.

## Worth doing at the same time

These are supplier marketing banners, not photographs of your product. They carry
claims your copy deliberately avoids ("SUPPORTS NATURAL GROWTH"), and image 2
states 100 red + 200 near-infrared LEDs, which contradicts the 100 in your title.
If you are re-exporting them anyway, that is the moment to replace them with real
photographs — see `shopify/photo-shot-list.md`.
