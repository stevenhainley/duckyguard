# Third-party data and code shipped with DuckyGuard

## usb_vendors.json
Vendor ids and names derived from the USB ID database (`usb.ids`), version 2026.06.26.
Maintained by Stephen J. Gowdy, http://www.linux-usb.org/usb-ids.html.
The database is offered under the GNU GPL (version 2 or later) or the 3-clause BSD licence; DuckyGuard uses it
under the 3-clause BSD option. Only vendor ids and names are included, plus three vendors missing upstream
(2e8a Raspberry Pi, 303a Espressif Systems, 1b4f SparkFun Electronics) taken from those vendors' own published allocations.

## injector_identities.json
Curated by DuckyGuard from firmware source code and vendor documentation. Each entry carries the URL it was read from.
No payload text from any third-party repository is included anywhere in DuckyGuard.

## three.js (in `ui/plate.js`)
The duck on the Overview is drawn with three.js, version 0.187.0, MIT licence, Copyright 2010-2026 Three.js Authors,
https://threejs.org. It is bundled into `src/duckyguard/ui/plate.js` by esbuild from `ui-src/plate.src.js`; the licence
header is kept inside the bundle.

## The duck's depth map (in `ui/duck-texture.js`)
The depth channel of the duck texture was estimated once from the duck engraving with Depth Anything V2 Small
(Apache-2.0), run locally. Only the resulting image is shipped; the model is not. The engraving itself was generated for
DuckyGuard with an AI image tool. `packaging/make_plate_texture.py` packs both into the texture.

## Fonts (in `ui/fonts/`)
Sofia Sans Extra Condensed, Hanken Grotesk and JetBrains Mono, each under the SIL Open Font License 1.1. The licence
texts are next to the font files (`OFL-SofiaSans.txt`, `OFL-HankenGrotesk.txt`, `OFL-JetBrainsMono.txt`).
