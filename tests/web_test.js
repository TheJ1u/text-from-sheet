// Tests for web/index.html. Run: NODE_PATH=<dir with jsdom> node tests/web_test.js
// All contacts fictional. Nothing can send: the page only builds sms: links; it has no network code.
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(path.join(__dirname, "..", "web", "index.html"), "utf8");
let passed = 0;
const deq = (a, b, m) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), m);
const t = (name, fn) => { fn(); passed++; console.log("ok -", name); };

function page() {
  const dom = new JSDOM(html, { runScripts: "dangerously", url: "https://example.test/", pretendToBeVisual: true });
  return dom.window;
}

const w = page();
const SMS = w.SMS;

t("page has no network or external resource code", () => {
  assert.ok(!/fetch\(|XMLHttpRequest|WebSocket|sendBeacon|<script[^>]+src=|<link[^>]+href=["']http/i.test(html));
});

t("parseCSV: quotes, commas in fields, CRLF, BOM, semicolons", () => {
  deq(SMS.parseCSV('﻿A,B\r\n"x, y","he said ""hi"""\r\n'), [["A", "B"], ["x, y", 'he said "hi"']]);
  deq(SMS.parseCSV("A;B\n1;2"), [["A", "B"], ["1", "2"]]);
});

t("normalizePhone", () => {
  for (const r of ["+1 (801) 555-0101", "801-555-0101", "8015550101", "1-801-555-0101"])
    assert.strictEqual(SMS.normalizePhone(r).phone, "+18015550101", r);
  assert.strictEqual(SMS.normalizePhone("+44 20 7946 0958").phone, "+442079460958");
  assert.strictEqual(SMS.normalizePhone("20 7946 0958", "44").phone, "+442079460958");
  const bad = { "": "no phone", "555-0108": "area code", "1.80155501E+10": "Excel", "801-555-0101 x12": "extension", "801-CALL-NOW": "letters", "+1 (011) 555-0101": "valid US" };
  for (const [r, frag] of Object.entries(bad)) {
    const res = SMS.normalizePhone(r);
    assert.ok(res.error && res.error.includes(frag), r + " -> " + JSON.stringify(res));
  }
});

const SAMPLE = [
  "First Name,Last Name,Phone,Event,Opt Out",
  "Ava,Martinez,+1 801 555 0101,Friday dinner,",
  "Ben,Carter,801-555-0102,Friday dinner,",
  "Ava,Martinez,(801) 555-0101,Friday dinner,",
  "Eva,Lindqvist,801-555-0105,Friday dinner,Yes",
  "Henry,Brooks,555-0108,Friday dinner,",
  "Isla,Fernandez,1.80155501E+10,Friday dinner,",
  ",Wright,801-555-0115,,",
].join("\n");

t("buildContacts: dedupe, opt-out, bad numbers, row numbers", () => {
  const r = SMS.buildContacts(SMS.parseCSV(SAMPLE), "1");
  deq(r.contacts.map(c => c.phone), ["+18015550101", "+18015550102", "+18015550115"]);
  const reasons = Object.fromEntries(r.problems.map(p => [p.row, p.reason]));
  assert.ok(reasons[4].startsWith("duplicate of row 2"));
  assert.ok(reasons[5].includes("opted out"));
  assert.ok(reasons[6].includes("area code"));
  assert.ok(reasons[7].includes("Excel"));
});

t("buildContacts: no header row (just numbers), and no phone column", () => {
  const r = SMS.buildContacts(SMS.parseCSV("+1 801 555 0101\n801-555-0102"), "1");
  assert.strictEqual(r.contacts.length, 2);
  assert.ok(SMS.buildContacts(SMS.parseCSV("Name,City\nAva,Provo"), "1").error);
});

t("buildContacts: single 'Name' column splits first/last; consent column honored when present", () => {
  const r = SMS.buildContacts(SMS.parseCSV("Name,Mobile,Consent\nAva Martinez,801-555-0101,yes\nBen Carter,801-555-0102,"), "1");
  assert.strictEqual(r.contacts.length, 1);
  assert.strictEqual(r.contacts[0].vals.firstname, "Ava");
  assert.strictEqual(r.problems.length, 1);
});

t("render: placeholders case/space-insensitive, missing flagged, fallback, never invents", () => {
  const c = SMS.buildContacts(SMS.parseCSV(SAMPLE), "1").contacts;
  assert.strictEqual(SMS.render("Hi {first_name}, see you at {Event}!", c[0].vals, "").text, "Hi Ava, see you at Friday dinner!");
  assert.strictEqual(SMS.render("Hi {First Name} {FIRSTNAME}", c[0].vals, "").text, "Hi Ava Ava");
  const miss = SMS.render("Hi {first_name}", c[2].vals, "");
  deq(miss.missing, ["first_name"]);
  assert.strictEqual(miss.text, "Hi {first_name}");
  assert.strictEqual(SMS.render("Hi {first_name}", c[2].vals, "there").text, "Hi there");
  deq(SMS.render("{nope}", c[0].vals, "").missing, ["nope"]);
});

t("issues: empty, unfilled placeholder, SSN, card number", () => {
  deq(SMS.issues("Hi Ava, 7pm Friday."), []);
  assert.ok(SMS.issues("").length);
  assert.ok(SMS.issues("Hi {first_name}")[0].includes("Unfilled"));
  assert.ok(SMS.issues("ssn 123-45-6789").some(m => m.includes("Social Security")));
  assert.ok(SMS.issues("card 4111 1111 1111 1111").some(m => m.includes("card")));
  deq(SMS.issues("Call me at 801-555-0101 or 8015550101"), []);
});

t("smsHref: Android uses ?body=, iOS uses &body=, text is encoded", () => {
  const a = SMS.smsHref("+18015550101", "Hi Ava!\nSee you & me?", "Mozilla/5.0 (Linux; Android 14)");
  assert.strictEqual(a, "sms:+18015550101?body=Hi%20Ava!%0ASee%20you%20%26%20me%3F");
  assert.ok(SMS.smsHref("+18015550101", "x", "iPhone").startsWith("sms:+18015550101&body="));
});

t("logCSV escapes quotes and never claims delivery", () => {
  const csv = SMS.logCSV([{ name: 'A "B"', phone: "+1", status: "sent", finalText: 'say "hi", ok' }], "2026-01-01T00:00:00Z");
  assert.ok(csv.includes('"A ""B"""') && csv.includes('"say ""hi"", ok"'));
  assert.ok(!/deliver/i.test(csv));
});

t("UI flow: load -> message -> review -> open link -> sent -> skip -> done", () => {
  const w = page();
  const d = w.document, $ = id => d.getElementById(id);
  w.SMSUI.loadText(SAMPLE);
  assert.strictEqual($("s2").hidden, false);
  assert.ok($("summary").textContent.includes("3 ready") && $("summary").textContent.includes("4 skipped"));
  assert.strictEqual($("msg").value, "Hi {first_name}, ");
  assert.strictEqual($("start").disabled, true, "start needs permission checkbox + message");
  $("msg").value = "Hi {first_name}, are you free for {Event}?";
  $("ok").checked = true;
  $("msg").dispatchEvent(new w.Event("input"));
  assert.strictEqual($("start").disabled, false);
  assert.strictEqual($("preview").textContent, "Hi Ava, are you free for Friday dinner?");
  $("start").click();
  assert.strictEqual($("s3").hidden, false);
  assert.strictEqual($("who").textContent, "Ava Martinez");
  assert.strictEqual($("open").getAttribute("href"), "sms:+18015550101?body=Hi%20Ava%2C%20are%20you%20free%20for%20Friday%20dinner%3F");
  $("open").click();
  assert.strictEqual(w.SMSUI.state().contacts[0].status, "opened");
  $("sent").click();
  assert.strictEqual(w.SMSUI.state().contacts[0].status, "sent");
  assert.strictEqual($("who").textContent, "Ben Carter");
  $("skip").click();
  // third contact has no first name and no Event -> held back
  assert.strictEqual($("who").textContent, "Wright");
  assert.ok($("warn").textContent.includes("Unfilled placeholder"));
  assert.strictEqual($("open").getAttribute("aria-disabled"), "true");
  assert.strictEqual($("open").hasAttribute("href"), false, "no sms link while blocked");
  // user fixes by editing -> link enabled
  $("cardmsg").value = "Hi, are you free Friday?";
  $("cardmsg").dispatchEvent(new w.Event("input"));
  assert.ok($("open").getAttribute("href").startsWith("sms:+18015550115?body="));
  $("skip").click();
  assert.strictEqual($("done").hidden, false);
  assert.ok($("doneInfo").textContent.includes("1 marked sent, 2 skipped"));
});

t("UI: sensitive text blocks the Open link; no opt-out line is ever added", () => {
  const w = page();
  const d = w.document, $ = id => d.getElementById(id);
  w.SMSUI.loadText("Phone\n801-555-0101");
  $("msg").value = "Hi there";
  $("ok").checked = true;
  $("msg").dispatchEvent(new w.Event("input"));
  assert.strictEqual($("preview").textContent, "Hi there");
  assert.strictEqual($("optOn"), null);
  assert.ok(!/opt-out line/i.test(html));
  $("start").click();
  $("cardmsg").value = "Your SSN is 123-45-6789";
  $("cardmsg").dispatchEvent(new w.Event("input"));
  assert.strictEqual($("open").hasAttribute("href"), false);
});

t("UI: no recipient is ever reachable without an individual open+confirm (no send-all control)", () => {
  assert.ok(!/send all|send to all|blast/i.test(html.replace(/Text From Sheet/g, "")));
});

console.log(`\n${passed} tests passed`);
