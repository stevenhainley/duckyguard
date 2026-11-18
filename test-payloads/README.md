# Test payloads

Five harmless scripts for checking DuckyGuard against your own Flipper Zero (Bad USB / Bad KB app) or any board
that reads Ducky-style scripts. Each one only types a sentence. None of them opens an app, presses Return or runs anything.

1. Copy the `.txt` files to the device (Flipper: `SD Card/badusb/`).
2. Open a text editor and click into an empty document.
3. Run a script and count the characters that get through. The sentence is 60 characters long.

| script | what it checks | result on a Flipper Zero in our runs |
|---|---|---|
| `01-full-speed.txt` | fastest typing | blocked, 4 characters got through |
| `02-25ms.txt` | 25 ms per key | blocked, 5 got through (measured before the key press rules were added; not re-run since) |
| `03-100ms.txt` | slow and perfectly even | blocked, 5 or fewer got through |
| `04-after-15s.txt` | waits out the new-keyboard signal first | blocked, 5 got through |
| `05-new-identity.txt` | Hold new keyboards | 0 got through |

Our runs used the same sentence twice (124 characters) typed through the Flipper's JavaScript `badusb` module, not these
exact files through the Bad USB app; the timing rules and the hold do not depend on which app sends the keys. See
`docs/EVALUATION.md` for the method. Results on other devices are not measured.

For `05-new-identity.txt`, DuckyGuard holds the device as soon as it is plugged in. Choose Keep blocked, or leave the
prompt alone and run the script before the hold length (20 s by default) runs out. With Always allow or Allow once the
script is judged by the timing rules like the others.

The app's own safe test (Run safe test) follows the same rule as these files: one sentence, no command, no Return.

`random-delay.js` is the randomised-delay case for firmware with the JavaScript runner (Momentum): it types the same
sentence with 60 to 140 ms between keys. Script syntax follows the Flipper Bad USB file format. DuckyScript is a Hak5
name; DuckyGuard is not affiliated with Hak5.
