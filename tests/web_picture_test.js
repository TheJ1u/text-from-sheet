// Picture/file sending tests for web/index.html (jsdom; the phone's share screen is faked).
// Run: NODE_PATH=<dir with jsdom> node tests/web_picture_test.js
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(path.join(__dirname, "..", "web", "index.html"), "utf8");
let passed = 0;

function page({ canShare = true } = {}) {
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://example.test/", pretendToBeVisual: true });
  const w = dom.window;
  const calls = { share: [], clip: [] };
  if (canShare) {
    Object.defineProperty(w.navigator, "canShare", { value: d => !!(d && d.files && d.files.length), configurable: true });
    Object.defineProperty(w.navigator, "share", { value: async d => { calls.share.push(d); }, configurable: true });
  }
  Object.defineProperty(w.navigator, "clipboard", { value: { writeText: async t => { calls.clip.push(t); } }, configurable: true });
  return { w, d: w.document, $: id => w.document.getElementById(id), calls };
}

function ready(p, msg = "Hi {first_name}, flyer attached!") {
  p.w.SMSUI.loadText("First Name,Phone\nAva,801-555-0101\nBen,801-555-0102");
  p.$("msg").value = msg;
  p.$("ok").checked = true;
  p.$("msg").dispatchEvent(new p.w.Event("input"));
}

const pic = (w, name = "flyer.jpg", type = "image/jpeg", bytes = 2048) => new w.File([new Uint8Array(bytes)], name, { type });

async function t(name, fn) { await fn(); passed++; console.log("ok -", name); }

(async () => {
  await t("attachmentNotes: pictures fine, PDFs/other files and big files get a warning", async () => {
    const { w } = page();
    const n = w.SMS.attachmentNotes;
    assert.deepStrictEqual(Array.from(n("a.jpg", "image/jpeg", 50000)), []);
    assert.deepStrictEqual(Array.from(n("card.vcf", "text/vcard", 900)), []);
    assert.ok(n("brochure.pdf", "application/pdf", 50000)[0].includes("PDF"));
    assert.ok(n("plan.docx", "application/vnd.openxmlformats", 50000)[0].includes("often can't be sent"));
    assert.ok(n("big.jpg", "image/jpeg", 4000000).join(" ").includes("Big file"));
  });

  await t("with a picture: Share replaces Open, copies the number, shares text + picture, logs the file", async () => {
    const p = page();
    ready(p);
    const f = pic(p.w);
    p.w.SMSUI.setPic(f);
    assert.ok(p.$("picInfo").textContent.includes("flyer.jpg"));
    p.$("start").click();
    assert.strictEqual(p.$("share").hidden, false);
    assert.strictEqual(p.$("open").hidden, true);
    assert.strictEqual(p.$("share").disabled, false);
    await p.w.SMSUI.sharePic();
    assert.deepStrictEqual(p.calls.clip, ["+18015550101"]);
    assert.strictEqual(p.calls.share.length, 1);
    assert.strictEqual(p.calls.share[0].text, "Hi Ava, flyer attached!");
    assert.strictEqual(p.calls.share[0].files[0], f);
    assert.strictEqual(p.w.SMSUI.state().contacts[0].status, "opened");   // not "sent" until you confirm
    p.$("sent").click();
    const c0 = p.w.SMSUI.state().contacts[0];
    assert.strictEqual(c0.status, "sent");
    assert.strictEqual(c0.attachment, "flyer.jpg");
    assert.ok(p.w.SMS.logCSV([c0], "now").includes('"flyer.jpg"'));
  });

  await t("no picture: normal text-only Open in Messages, no Share button", async () => {
    const p = page();
    ready(p, "Hi {first_name}");
    p.$("start").click();
    assert.strictEqual(p.$("share").hidden, true);
    assert.strictEqual(p.$("open").hidden, false);
  });

  await t("browser that can't share files: clear message, nothing shared", async () => {
    const p = page({ canShare: false });
    ready(p);
    p.w.SMSUI.setPic(pic(p.w));
    p.$("start").click();
    assert.ok(p.$("warn").textContent.includes("can't attach pictures"));
    await p.w.SMSUI.sharePic();
    assert.strictEqual(p.calls.share.length, 0);
  });

  await t("sensitive text still blocks sending, even with a picture", async () => {
    const p = page();
    ready(p);
    p.w.SMSUI.setPic(pic(p.w));
    p.$("start").click();
    p.$("cardmsg").value = "Your SSN is 123-45-6789";
    p.$("cardmsg").dispatchEvent(new p.w.Event("input"));
    assert.strictEqual(p.$("share").disabled, true);
    await p.w.SMSUI.sharePic();
    assert.strictEqual(p.calls.share.length, 0);
  });

  await t("the picture is never saved in progress; after resume it asks you to choose it again", async () => {
    const p = page();
    ready(p);
    p.w.SMSUI.setPic(pic(p.w));
    p.$("start").click();
    const saved = p.w.localStorage.getItem("tfs_state_v1");
    assert.ok(saved.includes("flyer.jpg") && saved.length < 5000);     // only the name, not the file
    const p2 = page();
    p2.w.localStorage.setItem("tfs_state_v1", saved);
    const p3 = (() => { const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://example.test/", pretendToBeVisual: true,
      beforeParse(win) { win.localStorage.setItem("tfs_state_v1", saved); } }); return { w: dom.window, $: id => dom.window.document.getElementById(id) }; })();
    p3.$("resumeBtn").click();
    assert.strictEqual(p3.$("picCardBtn").hidden, false);
    assert.strictEqual(p3.$("share").disabled, true);
    assert.ok(p3.$("picCardInfo").textContent.includes("Choose it again"));
  });

  await t("still no send-all control", async () => {
    assert.ok(!/send all|send to all|blast/i.test(html.replace(/Text From Sheet/g, "")));
  });

  console.log(`\n${passed} tests passed`);
})().catch(e => { console.error(e); process.exit(1); });
