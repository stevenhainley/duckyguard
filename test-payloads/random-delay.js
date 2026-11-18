// DuckyGuard test payload: random 60-140 ms between keys. Types one harmless sentence. Nothing is opened or run.
let badusb = require("badusb");
let math = require("math");
badusb.setup({ vid: 0x046D, pid: 0xC529, mfrName: "Flipper Devices Inc.", prodName: "Flipper Zero", layoutPath: "/ext/badusb/assets/layouts/en-US.kl" });
let n = 0;
while (!badusb.isConnected() && n < 150) { delay(100); n++; }
delay(3000);
let t = "DGTEST the quick brown fox jumps over the lazy dog 0123456789";
for (let i = 0; i < t.length; i++) { badusb.print(t.slice(i, i + 1)); delay(60 + math.floor(math.random() * 80)); }
delay(500);
badusb.quit();
