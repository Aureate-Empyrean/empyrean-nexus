// Universal browser navigation across every public module, in the real aetest Nexus (never
// production). Synthetic records named "P1Nav ..." are created through each module's own API and
// removed at the end; existing records are only read.
//
//   PLAYWRIGHT_PATH=G:/AureateEmpyrean/mnemosyne/node_modules/playwright BROWSER=chromium \
//     node tests/e2e/universal_navigation_e2e.cjs [journey-name-filter]
//
// Results are written as JSON next to the aetest deployment record. Browser Back/Forward here use
// the automation's history controls and CDP-injected input: they are real browser traversals, but
// none of this is a physical mouse or a physical phone.
const fs = require("fs");
const path = require("path");
const playwright = require(process.env.PLAYWRIGHT_PATH || "playwright");

const NEXUS = "http://localhost:12334";
const ENGINE = process.env.BROWSER || "chromium";
const FILTER = process.argv[2] || "";
const RUN = Date.now().toString(36);
const ROOT = path.join(__dirname, "../../..");
const OUT = path.join(ROOT, "deployment/2026-11-09-aetest-p1-navigation");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
let current = "";
class Skip extends Error {}
function record(status, what, detail) {
  results.push({ journey: current, status, what, ...(detail ? { detail } : {}) });
  console.log(`${status.padEnd(4)} [${current}] ${what}${detail ? ` -- ${detail}` : ""}`);
}
const check = (ok, what, detail) => {
  if (!ok) {
    record("FAIL", what, detail);
    throw new Error(`failed: ${what}`);
  }
  record("ok", what);
};
const note = (what) => record("note", what);
async function until(fn, what, ms = 15000) {
  const end = Date.now() + ms;
  let last;
  while (Date.now() < end) {
    try {
      last = await fn();
      if (last) return last;
    } catch (error) {
      last = error.message.slice(0, 200);
    }
    await sleep(100);
  }
  check(false, `${what} (timed out)`, typeof last === "string" ? last : undefined);
}

const owner = JSON.parse(fs.readFileSync(path.join(ROOT, "empyrean-nexus/.data/aetest-owner.json"), "utf8"));
async function signIn(page) {
  await page.locator("#username").fill(owner.username);
  await page.locator("#password").fill(owner.password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}
const route = (page) => new URL(page.url()).searchParams.get("route");
const pathOf = (page) => new URL(page.url()).pathname;
async function appFrame(page) {
  const handle = await page.locator("#module-application").elementHandle({ timeout: 20000 });
  return handle.contentFrame();
}
/** Wait until the module in the iframe has finished starting and is on `reference`. */
async function atRoute(page, reference, module) {
  await until(() => route(page) === reference && (!module || pathOf(page) === `/app/modules/${module}`), `address is ${module || ""} ${reference}`);
}
async function ready(page, adapter) {
  return until(async () => {
    const frame = await appFrame(page);
    return frame && (await frame.evaluate((name) => globalThis.eval(`typeof ${name} !== "undefined" && ${name}.enabled`), adapter)) ? frame : null;
  }, `${adapter} negotiated`);
}
async function open(page, module, reference) {
  const url = `${NEXUS}/app/modules/${module}${reference ? `?nav=1&route=${encodeURIComponent(reference)}` : ""}`;
  await page.goto(url);
  await page.locator("#username, #module-application").first().waitFor({ timeout: 30000 });
  if (await page.locator("#username").isVisible()) await signIn(page);
}
const ADAPTER = { meridian: "meridianNavigation", lyra: "lyraNavigation", chronos: "chronosNavigation", atlas: "atlasNavigation", argus: "argusNavigation", mnemosyne: "moduleNavigation" };
async function openReady(page, module, reference) {
  await open(page, module, reference);
  return ready(page, ADAPTER[module]);
}
const call = (frame, p, method = "GET", body) => frame.evaluate(([x, m, b]) => (b === null ? api(x, m) : api(x, m, b)), [p, method, body === undefined ? null : body]);
const text = (frame, selector) => frame.locator(selector).first().innerText({ timeout: 15000 });
const heading = (page, selector) => until(async () => (await appFrame(page)).locator(selector).first().innerText({ timeout: 500 }).catch(() => ""), `${selector} rendered`);
async function headingIs(page, selector, expected, what) {
  await until(async () => (await (await appFrame(page)).locator(selector).first().innerText({ timeout: 500 }).catch(() => "")).includes(expected), what);
  record("ok", what);
}
const hostError = (page) => page.locator("#navigation-status").count();
/** Nexus changes the address first and replaces the frame only after the module's leave is acknowledged. */
async function leftForOverview(page, what) {
  await until(async () => pathOf(page) === "/app/overview" && (await page.locator("#module-application").count()) === 0, what);
}

const FX = {};
async function fixtures(page) {
  let frame = await openReady(page, "meridian");
  FX.a = (await call(frame, "/people", "POST", { names: [{ kind: "full", given: "P1Nav", family: `Alpha${RUN}` }] })).id;
  FX.b = (await call(frame, "/people", "POST", { names: [{ kind: "full", given: "P1Nav", family: `Beta${RUN}` }], notes: "original fixture note" })).id;
  FX.ix1 = (await call(frame, "/interactions", "POST", { summary: `P1Nav coffee ${RUN}`, type: "meeting", participants: [{ entity_id: FX.a }] })).id;
  FX.ix2 = (await call(frame, "/interactions", "POST", { summary: `P1Nav call ${RUN}`, type: "meeting", participants: [{ entity_id: FX.a }] })).id;
  frame = await openReady(page, "chronos");
  const data = await call(frame, "/state");
  const calendar = data.calendars.find((c) => c.kind === "native");
  const today = await frame.evaluate(() => today());
  const event = (title, extra) => call(frame, "/events", "POST", { calendar_id: calendar.id, title, start: `${today}T10:00`, end: `${today}T11:00`, time_zone: data.settings.time_zone, ...extra });
  FX.today = today;
  FX.e1 = (await event(`P1Nav event ${RUN}`)).id;
  FX.e2 = (await event(`P1Nav weekly ${RUN}`, { rrule: "FREQ=WEEKLY", start: `${today}T12:00`, end: `${today}T13:00` })).id;
  frame = await openReady(page, "atlas");
  FX.p1 = (await call(frame, "/places", "POST", { name: `P1Nav place one ${RUN}`, latitude: 48.1, longitude: 17.1 })).id;
  FX.p2 = (await call(frame, "/places", "POST", { name: `P1Nav place two ${RUN}`, latitude: 48.2, longitude: 17.2 })).id;
  frame = await openReady(page, "argus");
  const upload = (name, color) => frame.evaluate(async ([n, c]) => {
    const canvas = Object.assign(document.createElement("canvas"), { width: 64, height: 48 });
    const g = canvas.getContext("2d");
    g.fillStyle = c;
    g.fillRect(0, 0, 64, 48);
    g.fillStyle = "#fff";
    g.fillText(n, 4, 24);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
    return (await uploadOne({ file: new File([blob], n, { type: "image/png" }), name: n, status: "", progress: 0 }, { quiet: true })).id;
  }, [name, color]);
  FX.ph1 = await upload(`p1nav-one-${RUN}.png`, "#225577");
  FX.ph2 = await upload(`p1nav-two-${RUN}.png`, "#775522");
  frame = await openReady(page, "lyra");
  const series = (await call(frame, "/library?type=series")).items;
  const movies = (await call(frame, "/library?type=movie")).items;
  FX.series = series[0];
  FX.movie = movies[0];
  if (!FX.series || !FX.movie) note("Lyra has no series/movie fixture: its title journeys are limited");
}
async function cleanup(page) {
  const steps = [
    ["meridian", async (f) => {
      for (const id of [FX.ix1, FX.ix2]) if (id) await call(f, `/interactions/${id}`, "DELETE").catch(() => {});
      for (const id of [FX.a, FX.b, FX.c]) if (id) { await call(f, `/people/${id}`, "DELETE").catch(() => {}); await f.evaluate((x) => api(`/trash/${x}?confirm=true`, "DELETE"), id).catch(() => {}); }
    }],
    ["chronos", async (f) => {
      // A repeating event needs an explicit scope, and since Chronos 0.6.0 deleting moves to Trash.
      for (const [id, target] of [[FX.e1, ""], [FX.e2, "?scope=series"]]) {
        if (!id) continue;
        try {
          const deleted = await call(f, `/events/${id}${target}`, "DELETE");
          if (deleted.trash) await call(f, `/trash/${deleted.trash}?confirmed=true`, "DELETE");
        } catch (error) {
          console.log(`cleanup chronos ${id}: ${error.message.slice(0, 160)}`);
        }
      }
    }],
    ["atlas", async (f) => { for (const id of [FX.p1, FX.p2]) if (id) { await call(f, `/places/${id}`, "DELETE").catch(() => {}); await call(f, `/trash/${id}`, "DELETE").catch(() => {}); } }],
    ["argus", async (f) => { for (const id of [FX.ph1, FX.ph2]) if (id) { await call(f, `/photos/${id}`, "DELETE").catch(() => {}); await call(f, `/photos/${id}/purge?confirm=true`, "DELETE").catch(() => {}); } }],
  ];
  for (const [module, run] of steps) {
    try { await run(await openReady(page, module)); } catch (error) { console.log(`cleanup ${module}: ${error.message.slice(0, 160)}`); }
  }
}

/* â”€â”€ Meridian draft safety â”€â”€ */
async function editField(page, value) {
  const frame = await appFrame(page);
  await frame.locator('.profile-head [data-act="edit"]').click();
  await frame.locator("#panel-body").waitFor();
  const field = frame.locator("#panel-body input.ae-input, #panel-body textarea").first();
  await field.fill(value);
  return field;
}
const fieldValue = async (page) => (await appFrame(page)).locator("#panel-body input.ae-input, #panel-body textarea").first().inputValue({ timeout: 5000 });
async function closeEditor(page) {
  await (await appFrame(page)).evaluate(() => closePanel());
  await sleep(350);
}
/** Run an app function from a real click in the frame. History entries made by script without
 *  a user gesture may be skipped by a browser's Back (WebKit does this), which real use never hits. */
async function act(frame, fn, arg) {
  await frame.evaluate(([source, value]) => {
    const run = (0, eval)(`(${source})`); // here, not in the handler: the module's CSP forbids eval there
    const button = document.createElement("button");
    button.id = "__act";
    button.style = "position:fixed;left:0;top:0;width:24px;height:24px;z-index:2147483647";
    button.onclick = () => {
      button.remove();
      run(value);
    };
    document.body.append(button);
  }, [fn.toString(), arg === undefined ? null : arg]);
  await frame.locator("#__act").click();
}
const J = {};
J["meridian-keep-changes-preserves-forward"] = async (page) => {
  let frame = await openReady(page, "meridian");
  for (const [view, id, ref] of [["people", null, "/people"], ["person", FX.a, `/people/${FX.a}`], ["person", FX.b, `/people/${FX.b}`]]) {
    await act(frame, ([v, i]) => go(v, i), [view, id]);
    await atRoute(page, ref, "meridian");
  }
  await headingIs(page, ".profile-head", `Beta${RUN}`, "A â†’ B â†’ C built: C is on screen");
  const before = await page.evaluate(() => history.length);
  await editField(page, `P1Nav edited ${RUN}`);
  await page.goBack();
  await atRoute(page, `/people/${FX.a}`, "meridian");
  frame = await appFrame(page);
  await frame.locator("#panel-hold").waitFor({ timeout: 5000 });
  check((await fieldValue(page)) === `P1Nav edited ${RUN}`, "Back with unsaved edits keeps the editor and its text");
  check((await frame.locator("#dialog[open]").count()) === 0, "no modal interrupts the traversal");
  check((await text(frame, ".profile-head")).includes(`Beta${RUN}`), "the screen stays with the editor while the address moves");
  check((await page.evaluate(() => history.length)) === before, "no history entry was added");
  await page.goForward();
  await atRoute(page, `/people/${FX.b}`, "meridian");
  await until(async () => (await frame.locator("#panel-hold").count()) === 0, "returning to the editor's page clears the notice");
  check((await fieldValue(page)) === `P1Nav edited ${RUN}`, "Forward still exists and returns to the editor with its text");
  await page.goBack();
  await atRoute(page, `/people/${FX.a}`, "meridian");
  await frame.locator("#panel-hold-discard").click();
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "discarding shows the page the address names");
  await page.goForward();
  await atRoute(page, `/people/${FX.b}`, "meridian");
  await headingIs(page, ".profile-head", `Beta${RUN}`, "Forward branch intact after keeping and then discarding");
  await page.goBack(); await atRoute(page, `/people/${FX.a}`, "meridian");
  await page.goBack(); await atRoute(page, "/people", "meridian");
  check(true, "the full A â†’ B â†’ C traversal still works");
  const saved = await call(await appFrame(page), `/people/${FX.b}`);
  check(saved.display_name.includes(`Beta${RUN}`), "the unsaved edit never reached the record");
};
J["meridian-draft-survives-launcher"] = async (page) => {
  await openReady(page, "meridian", `/people/${FX.b}`);
  await headingIs(page, ".profile-head", `Beta${RUN}`, "person open from a direct link");
  await editField(page, `P1Nav launcher ${RUN}`);
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "Nexus launcher left Meridian");
  await page.goBack();
  await atRoute(page, `/people/${FX.b}`, "meridian");
  const frame = await ready(page, "meridianNavigation");
  await frame.locator("#draft-tray").waitFor({ timeout: 10000 });
  check((await text(frame, "#draft-tray")).includes(`Beta${RUN}`), "after remounting, the draft is offered by name");
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await frame.locator("#panel-body").waitFor();
  await until(async () => (await fieldValue(page)) === `P1Nav launcher ${RUN}`, "Resume restores the exact text");
  check(true, "draft recovered through the Nexus launcher");
  await closeEditor(page);
  await until(async () => (await frame.locator("#draft-tray").count()) === 0, "tray clears after resuming");
};
J["meridian-draft-survives-reload"] = async (page) => {
  await openReady(page, "meridian", `/people/${FX.b}`);
  await headingIs(page, ".profile-head", `Beta${RUN}`, "person open");
  await editField(page, `P1Nav reload ${RUN}`);
  await sleep(900); // the debounced checkpoint
  await page.reload();
  await atRoute(page, `/people/${FX.b}`, "meridian");
  const frame = await ready(page, "meridianNavigation");
  await frame.locator("#draft-tray").waitFor({ timeout: 10000 });
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await until(async () => (await fieldValue(page)) === `P1Nav reload ${RUN}`, "the draft survives a full page reload");
  check(true, "reload kept an acknowledged checkpoint");
  await closeEditor(page);
};
J["meridian-draft-survives-backlink"] = async (page) => {
  const frame = await openReady(page, "meridian", `/people/${FX.b}`);
  await headingIs(page, ".profile-head", `Beta${RUN}`, "person open");
  await editField(page, `P1Nav backlink ${RUN}`);
  await frame.evaluate(() => { bridge("navigate", { module: "chronos" }).catch(() => {}); });
  await until(() => pathOf(page) === "/app/modules/chronos", "a backlink left Meridian");
  await ready(page, "chronosNavigation");
  await page.goBack();
  await atRoute(page, `/people/${FX.b}`, "meridian");
  const back = await ready(page, "meridianNavigation");
  await back.locator("#draft-tray").waitFor({ timeout: 10000 });
  await back.locator('#draft-tray [data-draft="resume"]').click();
  await until(async () => (await fieldValue(page)) === `P1Nav backlink ${RUN}`, "text is restored");
  check(true, "draft recovered after a cross-module backlink");
  await closeEditor(page);
};
J["meridian-save-conflict-after-recovery"] = async (page) => {
  const setup = await openReady(page, "meridian");
  FX.c = (await call(setup, "/people", "POST", { names: [{ kind: "full", given: "P1Nav", family: `Conflict${RUN}` }], notes: "original fixture note" })).id;
  await openReady(page, "meridian", `/people/${FX.c}`);
  await headingIs(page, ".profile-head", `Conflict${RUN}`, "person open");
  await (await appFrame(page)).evaluate(() => openPanel("notes"));
  await (await appFrame(page)).locator("#notes").fill(`P1Nav conflict ${RUN}`);
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "left Meridian");
  await page.goBack();
  await atRoute(page, `/people/${FX.c}`, "meridian");
  const frame = await ready(page, "meridianNavigation");
  // Someone else saves a newer version of the record while the draft waits.
  const latest = await call(frame, `/people/${FX.c}`);
  const doc = await frame.evaluate((p) => ({ ...editable(p), expected_revision: p.edit_revision }), latest);
  doc.names[0] = { ...doc.names[0], family: `Gamma${RUN}` };
  await call(frame, `/people/${FX.c}`, "PUT", doc);
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await frame.locator("#panel-body").waitFor();
  await frame.locator('[data-act="panel-save"]').click();
  await until(async () => /changed in another session/.test(await text(frame, "#form-error")), "the save is refused as a conflict");
  check((await frame.locator("#notes").inputValue()) === `P1Nav conflict ${RUN}`, "the conflict leaves the draft in the editor");
  check(true, "conflict surfaced instead of overwriting");
  await frame.locator("#form-error button").click();
  await frame.locator('[data-act="panel-save"]').click();
  await until(async () => (await call(frame, `/people/${FX.c}`)).notes === `P1Nav conflict ${RUN}`, "keeping my version saves it");
  const after = await call(frame, `/people/${FX.c}`);
  check(after.display_name.includes(`Gamma${RUN}`), "the other session's change in another section survives");
  await closeEditor(page);
};
J["meridian-failed-checkpoint-keeps-editor"] = async (page) => {
  const frame = await openReady(page, "meridian", `/people/${FX.b}`);
  await headingIs(page, ".profile-head", `Beta${RUN}`, "person open");
  await page.evaluate(() => {
    window.__setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function (k, v) { if (String(k).includes("navigation.drafts")) throw new DOMException("full", "QuotaExceededError"); return window.__setItem.call(this, k, v); };
  });
  await editField(page, `P1Nav quota ${RUN}`);
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await until(async () => (await page.locator("#navigation-status").count()) === 1, "Nexus reports that the leave was not safe");
  check((await fieldValue(page)) === `P1Nav quota ${RUN}`, "the editor and its text stay on screen");
  check((await page.locator("#module-application").count()) === 1, "the module frame was not replaced");
  await page.evaluate(() => { Storage.prototype.setItem = window.__setItem; });
  await closeEditor(page);
  void frame;
};

/* â”€â”€ Handshake failure and legacy paths â”€â”€ */
for (const [module, adapter, probe] of [["meridian", "meridianNavigation", '[data-act="go"][data-view="people"]'], ["lyra", "lyraNavigation", '[data-nav="series"]'], ["chronos", "chronosNavigation", '.views [data-view="week"]'], ["atlas", "atlasNavigation", '[data-go="library"]'], ["argus", "argusNavigation", '[data-go="settings"]']]) {
  J[`${module}-handshake-timeout-falls-back`] = async (page, ctx) => {
    const failing = await ctx.newPage();
    await failing.addInitScript(() => {
      if (window.top !== window) return;
      const original = window.addEventListener;
      window.addEventListener = function (type, listener, options) {
        if (type !== "message") return original.call(this, type, listener, options);
        return original.call(this, type, (event) => (event.data?.channel === "empyrean-navigation-v1" ? undefined : listener(event)), options);
      };
    });
    await open(failing, module);
    const frame = await until(async () => {
      const f = await appFrame(failing);
      return (await f.evaluate((a) => globalThis.eval(`typeof ${a} !== "undefined" && ${a}.status`), adapter)) === "failed" ? f : null;
    }, "the handshake timed out", 12000);
    check((await frame.evaluate((a) => globalThis.eval(`${a}.enabled`), adapter)) === false, "a failed client is not enabled");
    const start = failing.url();
    await frame.locator(probe).first().click();
    await sleep(700);
    check((await frame.evaluate(() => document.body.innerText.length)) > 0 && failing.url() === start, "the legacy in-memory path still works and does not touch the URL");
    await failing.close();
  };
}
J["unsupported-host-stays-legacy"] = async (page, ctx) => {
  const legacy = await ctx.newPage();
  await legacy.route("**/api/v1/system", async (r) => {
    const response = await r.fetch();
    const body = await response.json();
    body.navigation = { versions: [] };
    await r.fulfill({ response, json: body });
  });
  await open(legacy, "lyra");
  const frame = await until(async () => {
    const f = await appFrame(legacy);
    return (await f.evaluate(() => !lyraNavigation.enabled && document.querySelector("#view .page") !== null)) ? f : null;
  }, "a host without the contract is detected");
  await frame.locator('[data-nav="series"]').first().click();
  await frame.locator(".page-title").first().waitFor();
  check((await frame.locator(".page-title").first().innerText()).length > 0 && !legacy.url().includes("route="), "Lyra works on a host without the contract");
  await legacy.close();
};

/* â”€â”€ One module at a time â”€â”€ */
J["lyra-back-forward-exact"] = async (page) => {
  if (!FX.series || !FX.movie) throw new Skip("no Lyra titles on aetest");
  const frame = await openReady(page, "lyra");
  await atRoute(page, "/", "lyra");
  await frame.evaluate(() => { window.__sameDocument = true; });
  await frame.locator('.nav-item[data-nav="series"]').click();
  await atRoute(page, "/series", "lyra");
  await frame.locator(`[data-open="series:${FX.series.id}"]`).first().click();
  await atRoute(page, `/series/${FX.series.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.series.title, "series title open");
  await act(frame, (m) => navigate({ view: "title", type: "movie", id: m, from: "movies" }), FX.movie.id);
  await atRoute(page, `/movie/${FX.movie.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.movie.title, "second title open");
  check((await frame.evaluate(() => state.history.length)) === 0, "Lyra's private stack is no longer used");
  await page.goBack(); await atRoute(page, `/series/${FX.series.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.series.title, "Back returns to the exact title");
  await page.goBack(); await atRoute(page, "/series", "lyra");
  await page.goForward(); await atRoute(page, `/series/${FX.series.id}`, "lyra");
  await page.goForward(); await atRoute(page, `/movie/${FX.movie.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.movie.title, "Forward restores the exact title");
  check(await frame.evaluate(() => window.__sameDocument === true), "traversal inside a module keeps the same iframe document");
  await page.reload(); await atRoute(page, `/movie/${FX.movie.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.movie.title, "refresh shows the latest title, not a stale bootstrap");
  await (await appFrame(page)).locator("#back").click();
  await atRoute(page, "/movies", "lyra");
  check(true, "the in-module arrow goes up to the list");
};
J["lyra-deep-link-and-copied-url"] = async (page, ctx) => {
  if (!FX.series || !FX.movie) throw new Skip("no Lyra titles on aetest");
  await page.goto(`${NEXUS}/app/modules/lyra?path=${encodeURIComponent(`/series/${FX.series.id}`)}`);
  await headingIs(page, ".hero h1", FX.series.title, "bootstrap deep link opens the title");
  const frame = await ready(page, "lyraNavigation");
  await act(frame, (m) => navigate({ view: "title", type: "movie", id: m, from: "movies" }), FX.movie.id);
  await atRoute(page, `/movie/${FX.movie.id}`, "lyra");
  const copy = await ctx.newPage();
  await copy.goto(page.url());
  await headingIs(copy, ".hero h1", FX.movie.title, "a copied URL opens the latest title in a fresh tab");
  await copy.close();
};
J["chronos-views-events-occurrences"] = async (page) => {
  let frame = await openReady(page, "chronos");
  await atRoute(page, `/month/${FX.today}`, "chronos");
  check(true, "the first screen gets its exact view and date");
  await frame.locator('.views [data-view="week"]').click();
  await atRoute(page, `/week/${FX.today}`, "chronos");
  const key = await until(() => frame.evaluate((id) => state.occurrences.find((o) => o.event_id === id)?.key, FX.e1), "the event is loaded");
  await frame.locator(`[data-open="${key}"]`).first().click();
  await until(() => route(page)?.startsWith(`/events/${FX.e1}`), "the event has its own address");
  await headingIs(page, ".ae-drawer", `P1Nav event ${RUN}`, "the exact event opens");
  await page.goBack(); await atRoute(page, `/week/${FX.today}`, "chronos");
  await until(async () => (await frame.locator(".ae-drawer:not(.is-leaving)").count()) === 0, "Back closes the drawer");
  check(true, "Back returns to the week");
  await page.goBack(); await atRoute(page, `/month/${FX.today}`, "chronos");
  await page.goForward(); await atRoute(page, `/week/${FX.today}`, "chronos");
  await page.goForward(); await until(() => route(page)?.startsWith(`/events/${FX.e1}`), "Forward returns to the event");
  await headingIs(page, ".ae-drawer", `P1Nav event ${RUN}`, "Forward restores the exact event");
  await page.reload();
  await headingIs(page, ".ae-drawer", `P1Nav event ${RUN}`, "refresh restores the event over its view");
  frame = await ready(page, "chronosNavigation");
  await frame.keyboard?.press?.("Escape");
  await frame.evaluate(() => closeLayer());
  await atRoute(page, `/week/${FX.today}`, "chronos");
  // One exact occurrence of a repeating event, next week.
  const next = await frame.evaluate((d) => addDays(d, 7), FX.today);
  await act(frame, (d) => go("week", d), next);
  await atRoute(page, `/week/${next}`, "chronos");
  // The previous week's list stays in memory while the next one loads: wait for this exact week.
  const occurrence = await until(() => frame.evaluate(([id, day]) => state.occurrences.find((x) => x.event_id === id && x.occurrence.startsWith(day))?.key, [FX.e2, next]), "the repeat is loaded");
  await frame.locator(`[data-open="${occurrence}"]`).first().click();
  await until(() => new URLSearchParams(route(page)?.split("?")[1]).get("o"), "the address names the occurrence");
  const opened = route(page);
  const when = await heading(page, ".ae-drawer .fact .primary");
  await page.reload();
  await until(() => route(page) === opened, "address retained");
  await until(async () => (await heading(page, ".ae-drawer .fact .primary")) === when, "refresh reopens the same occurrence");
  check(true, "a recurring occurrence is restored exactly");
};
J["atlas-places-sections-contacts"] = async (page) => {
  let frame = await openReady(page, "atlas");
  await atRoute(page, "/", "atlas");
  await frame.locator('[data-go="library"]').click();
  await atRoute(page, "/library", "atlas");
  await frame.locator(`.place-card[data-place="${FX.p1}"]`).first().click();
  await atRoute(page, `/places/${FX.p1}?section=library`, "atlas");
  await headingIs(page, ".detail-title", `P1Nav place one ${RUN}`, "the Place opens over the Library");
  await frame.locator('[data-go="trash"]').click();
  await atRoute(page, "/trash", "atlas");
  await page.goBack(); await atRoute(page, `/places/${FX.p1}?section=library`, "atlas");
  await headingIs(page, ".detail-title", `P1Nav place one ${RUN}`, "Back restores the exact Place");
  await page.goBack(); await atRoute(page, "/library", "atlas");
  await until(async () => await frame.locator("#detail").isHidden(), "Back closes the Place");
  await page.goForward(); await atRoute(page, `/places/${FX.p1}?section=library`, "atlas");
  await page.reload();
  await headingIs(page, ".detail-title", `P1Nav place one ${RUN}`, "refresh restores the Place");
  frame = await ready(page, "atlasNavigation");
  await act(frame, (id) => openPlace(id, { center: true, section: "map" }), FX.p2);
  await atRoute(page, `/places/${FX.p2}`, "atlas");
  await headingIs(page, ".detail-title", `P1Nav place two ${RUN}`, "Show on map has its own address");
  const contacts = await frame.evaluate(() => state.contacts.items.length);
  if (!contacts) return note("no Meridian contact pins on aetest: contact selection not exercised");
  const key = await frame.evaluate(() => state.contacts.items[0].group);
  await act(frame, (k) => openContact(k, false), key);
  await atRoute(page, "/map/contact", "atlas");
  check(!page.url().includes(key) && !/\b\d{1,2}\.\d{3}/.test(page.url()), "a contact selection puts no identity or location in the URL");
  await until(() => frame.evaluate((k) => state.selectedGroup === k, key), "contact selected");
  await page.goBack(); await atRoute(page, `/places/${FX.p2}`, "atlas");
  await until(() => frame.evaluate(() => state.selectedGroup === null), "Back leaves the contact");
  await page.goForward(); await atRoute(page, "/map/contact", "atlas");
  await until(() => frame.evaluate((k) => state.selectedGroup === k, key), "Forward restores the same contact from private state");
  check(true, "contact selection restored per entry");
};
J["argus-photos-settings-refresh"] = async (page) => {
  let frame = await openReady(page, "argus");
  await atRoute(page, "/", "argus");
  await frame.locator(`[data-photo="${FX.ph1}"]`).first().click();
  await atRoute(page, `/photos/${FX.ph1}`, "argus");
  await headingIs(page, "[data-heading]", `p1nav-one-${RUN}`, "photo open");
  await frame.locator('[data-go="settings"]').click();
  await atRoute(page, "/settings", "argus");
  await page.goBack(); await atRoute(page, `/photos/${FX.ph1}`, "argus");
  await headingIs(page, "[data-heading]", `p1nav-one-${RUN}`, "Back restores the exact photo");
  await page.goBack(); await atRoute(page, "/", "argus");
  await page.goForward(); await atRoute(page, `/photos/${FX.ph1}`, "argus");
  await page.goForward(); await atRoute(page, "/settings", "argus");
  await page.goto(`${NEXUS}/app/modules/argus?path=${encodeURIComponent(`/photos/${FX.ph2}`)}`);
  await headingIs(page, "[data-heading]", `p1nav-two-${RUN}`, "bootstrap deep link opens the photo");
  frame = await ready(page, "argusNavigation");
  await frame.locator('[data-go="settings"]').click();
  await atRoute(page, "/settings", "argus");
  await page.reload();
  await headingIs(page, "[data-heading]", "Settings", "refresh after a local move shows Settings, not the stale photo");
  for (const [view, reference] of [["people", "/people"], ["import", "/import"], ["trash", "/trash"]]) {
    frame = await ready(page, "argusNavigation");
    await frame.locator(`[data-go="${view}"]`).click();
    await atRoute(page, reference, "argus");
  }
  check(true, "People, Import and Trash each have an address");
};
J["argus-picker-keeps-workflow"] = async (page) => {
  await page.goto(`${NEXUS}/app/modules/argus?path=${encodeURIComponent(`/pick/meridian/people/${FX.a}/picture`)}`);
  let frame = await ready(page, "argusNavigation");
  await frame.locator(".picker-band").waitFor({ timeout: 10000 });
  await frame.locator(`[data-photo="${FX.ph1}"]`).first().click();
  await atRoute(page, `/photos/${FX.ph1}`, "argus");
  await frame.locator(".picker-band").waitFor({ timeout: 10000 });
  await page.goBack(); await atRoute(page, "/", "argus");
  await frame.locator(".picker-band").waitFor();
  check(true, "picker mode survives moves");
  await page.reload();
  frame = await ready(page, "argusNavigation");
  await frame.locator(".picker-band").waitFor({ timeout: 10000 });
  check(true, "picker mode survives a reload");
  await frame.locator(`[data-photo="${FX.ph1}"]`).first().click();
  await atRoute(page, `/photos/${FX.ph1}`, "argus");
  await frame.locator('[data-act="use"]').click();
  await until(() => pathOf(page) === "/app/modules/meridian", "Use this photo returns to Meridian");
  check(new URL(page.url()).searchParams.get("path") === `/people/${FX.a}/picture/${FX.ph1}`, "the selection is passed back through the picker path");
};
J["mnemosyne-still-negotiates"] = async (page) => {
  const frame = await openReady(page, "mnemosyne");
  check(await frame.evaluate(() => moduleNavigation.enabled), "Mnemosyne's client negotiates with the new SDK");
};

/* â”€â”€ Editors in the newly adopted modules â”€â”€ */
J["chronos-event-editor-draft"] = async (page) => {
  let frame = await openReady(page, "chronos");
  await atRoute(page, `/month/${FX.today}`, "chronos");
  await frame.locator('.views [data-view="week"]').click();
  await atRoute(page, `/week/${FX.today}`, "chronos");
  const before = await page.evaluate(() => history.length);
  await frame.locator('[data-act="new"]').click();
  await frame.locator("#ev-title").fill(`P1Nav unsaved event ${RUN}`);
  await page.goBack();
  await atRoute(page, `/month/${FX.today}`, "chronos");
  await frame.locator("#dialog-hold").waitFor({ timeout: 5000 });
  check((await frame.locator("#ev-title").inputValue()) === `P1Nav unsaved event ${RUN}`, "Back keeps the event editor and its text");
  check((await page.evaluate(() => history.length)) === before, "no history entry was added");
  await page.goForward();
  await atRoute(page, `/week/${FX.today}`, "chronos");
  await until(async () => (await frame.locator("#dialog-hold").count()) === 0, "Forward returns to the editor's page");
  await page.goBack();
  await atRoute(page, `/month/${FX.today}`, "chronos");
  await frame.locator("#dialog-hold-discard").click();
  await until(() => frame.evaluate(() => state.view === "month"), "discarding shows the address's page");
  check(true, "event editor held and released without touching history");
  await page.goForward();
  await atRoute(page, `/week/${FX.today}`, "chronos");
  frame = await ready(page, "chronosNavigation");
  await frame.locator('[data-act="new"]').click();
  await frame.locator("#ev-title").fill(`P1Nav launcher event ${RUN}`);
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "left Chronos");
  await page.goBack();
  frame = await ready(page, "chronosNavigation");
  await frame.locator("#draft-tray").waitFor({ timeout: 10000 });
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await until(async () => (await frame.locator("#ev-title").inputValue({ timeout: 500 })) === `P1Nav launcher event ${RUN}`, "the event draft is restored after leaving");
  check(true, "event draft recovered");
  await frame.evaluate(() => closeDialog());
};
J["atlas-place-editor-draft"] = async (page) => {
  let frame = await openReady(page, "atlas");
  await frame.locator('[data-go="library"]').click();
  await atRoute(page, "/library", "atlas");
  await until(() => frame.evaluate(() => renderedSection === "library"), "the Library is on screen");
  await frame.evaluate(() => openEditor());
  await frame.locator("#pl-name").fill(`P1Nav unsaved place ${RUN}`);
  await page.goBack();
  await atRoute(page, "/", "atlas");
  await frame.locator("#dialog-hold").waitFor({ timeout: 5000 });
  check((await frame.locator("#pl-name").inputValue()) === `P1Nav unsaved place ${RUN}`, "Back keeps the Place editor and its text");
  await page.goForward();
  await atRoute(page, "/library", "atlas");
  await until(async () => (await frame.locator("#dialog-hold").count()) === 0, "Forward returns to the editor's page");
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "left Atlas");
  await page.goBack();
  frame = await ready(page, "atlasNavigation");
  await frame.locator("#draft-tray").waitFor({ timeout: 10000 });
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await until(async () => (await frame.locator("#pl-name").inputValue({ timeout: 500 })) === `P1Nav unsaved place ${RUN}`, "the Place draft is restored after leaving");
  check(true, "Place draft recovered");
  await frame.evaluate(() => document.querySelector("#dialog").close());
};
J["lyra-notes-saved-or-kept"] = async (page) => {
  if (!FX.series?.library) throw new Skip("no Lyra title in the library on aetest");
  const path = `/series/${FX.series.id}`;
  let frame = await openReady(page, "lyra", "/series");
  await act(frame, (s) => navigate({ view: "title", type: "series", id: s, from: "series" }), FX.series.id);
  await atRoute(page, path, "lyra");
  const original = (await call(frame, path)).library.notes;
  const box = frame.locator("[data-notes]");
  await box.waitFor();
  await box.fill(`P1Nav notes ${RUN}`);
  await page.goBack(); // no blur: a traversal does not move focus
  await atRoute(page, "/series", "lyra");
  await until(async () => (await call(frame, path)).library.notes === `P1Nav notes ${RUN}`, "the note was saved on the way out");
  check(true, "notes are saved by a browser traversal");
  await page.goForward();
  await atRoute(page, path, "lyra");
  await box.waitFor();
  let refused = 0;
  await page.route("**/api/library/series/**", (r) => {
    if (r.request().method() !== "PUT") return r.continue();
    refused++;
    return r.abort();
  });
  await box.fill(`P1Nav kept ${RUN}`);
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "left Lyra with a failing save");
  check(refused === 1, "the save really failed before the frame was replaced");
  await page.unroute("**/api/library/series/**");
  await page.goBack();
  frame = await ready(page, "lyraNavigation");
  await frame.locator("#draft-tray").waitFor({ timeout: 10000 });
  await frame.locator('#draft-tray [data-draft="resume"]').click();
  await until(async () => (await frame.locator("[data-notes]").inputValue({ timeout: 500 })) === `P1Nav kept ${RUN}`, "a note that could not be saved is kept as a draft");
  check((await call(frame, path)).library.notes === `P1Nav notes ${RUN}`, "the unsaved text never reached the record");
  await frame.locator("[data-notes]").blur();
  await until(async () => (await call(frame, path)).library.notes === `P1Nav kept ${RUN}`, "retrying saves the recovered note");
  await until(async () => (await frame.locator("#draft-tray").count()) === 0, "the draft is gone once saved");
  check(true, "failed note save recovered and retried");
  await call(frame, `/library/series/${FX.series.id}`, "PUT", { notes: original });
};
J["argus-title-saved-on-traversal"] = async (page) => {
  const frame = await openReady(page, "argus");
  await frame.locator(`[data-photo="${FX.ph2}"]`).first().click();
  await atRoute(page, `/photos/${FX.ph2}`, "argus");
  await frame.locator("#title").fill(`P1Nav title ${RUN}`);
  await page.goBack();
  await atRoute(page, "/", "argus");
  await until(async () => (await call(frame, `/photos/${FX.ph2}`)).title === `P1Nav title ${RUN}`, "the title was saved on the way out");
  check(true, "photo title saved by a browser traversal");
  await call(frame, `/photos/${FX.ph2}`, "PATCH", { title: "" });
};
J["rapid-traversal-ends-on-the-right-record"] = async (page) => {
  const frame = await openReady(page, "meridian", "/people");
  for (const [view, id, ref] of [["person", FX.a, `/people/${FX.a}`], ["person", FX.b, `/people/${FX.b}`], ["timeline", null, "/timeline"], ["person", FX.a, `/people/${FX.a}`]]) {
    await act(frame, ([v, i]) => go(v, i), [view, id]);
    await atRoute(page, ref, "meridian");
  }
  const names = { [`/people/${FX.a}`]: `Alpha${RUN}`, [`/people/${FX.b}`]: `Beta${RUN}` };
  await page.evaluate(async () => {
    for (let i = 0; i < 3; i++) {
      history.back();
      await new Promise((r) => setTimeout(r, 40));
    }
  });
  // Browsers may merge queued traversals: wait for the address to settle, then require that the screen matches it.
  let settled = route(page);
  await until(async () => {
    const now = route(page);
    const same = now === settled;
    settled = now;
    await sleep(350);
    return same && route(page) === now;
  }, "the address settles");
  note(`settled on ${settled === "/timeline" ? "/timeline" : settled.replace(/[0-9a-f-]{36}/, "<id>")}`);
  if (names[settled]) await headingIs(page, ".profile-head", names[settled], "the screen shows the record the address names");
  await sleep(800);
  if (names[settled]) check((await text(await appFrame(page), ".profile-head")).includes(names[settled]), "no late response paints another record");
  check((await hostError(page)) === 0, "no restore error was reported");
};
const DELAYED = {
  meridian: { adapter: "meridianNavigation", a: () => `/people/${FX.a}`, b: () => `/people/${FX.b}`, api: () => `**/api/people/${FX.a}`, selector: ".profile-head", name: () => `Beta${RUN}` },
  chronos: { adapter: "chronosNavigation", a: () => `/events/${FX.e1}`, b: () => `/events/${FX.e2}`, api: () => `**/api/events/${FX.e1}`, selector: ".ae-drawer:not(.is-leaving)", name: () => `P1Nav weekly ${RUN}` },
  atlas: { adapter: "atlasNavigation", a: () => `/places/${FX.p1}`, b: () => `/places/${FX.p2}`, api: () => `**/api/places/${FX.p1}`, selector: ".detail-title", name: () => `P1Nav place two ${RUN}` },
  argus: { adapter: "argusNavigation", a: () => `/photos/${FX.ph1}`, b: () => `/photos/${FX.ph2}`, api: () => `**/api/photos/${FX.ph1}`, selector: "[data-heading]", name: () => `p1nav-two-${RUN}` },
};
for (const [module, d] of Object.entries(DELAYED)) {
  J[`${module}-late-response-cannot-repaint`] = async (page) => {
    const live = await openReady(page, module, d.a());
    await act(live, (reference) => queueNavigation(reference, "push"), d.b());
    await atRoute(page, d.b(), module);
    await headingIs(page, d.selector, d.name(), "the second record is open");
    // A is reached by Back with its response held back; Forward to B happens meanwhile.
    let held = 0;
    await page.route(d.api(), async (r) => {
      held++;
      await sleep(1500);
      await r.continue().catch(() => {});
    });
    await page.goBack();
    await until(() => held > 0, "the slow request started");
    await page.goForward();
    await until(() => route(page) === d.b(), "address returned to the second record");
    await headingIs(page, d.selector, d.name(), "the newer record is on screen");
    await sleep(2000); // longer than the held response
    check((await text(live, d.selector)).includes(d.name()), "the late response did not repaint the older record");
    await page.unroute(d.api());
  };
}
J["immediate-back-keeps-the-editor"] = async (page) => {
  await openReady(page, "meridian", `/people/${FX.b}`);
  await headingIs(page, ".profile-head", `Beta${RUN}`, "person open");
  await editField(page, `P1Nav immediate ${RUN}`);
  // Back before the leave has finished: nothing replaces the frame, and the editor must survive.
  await page.evaluate(() => { document.querySelector('a[data-nav="overview"]').click(); history.back(); });
  await atRoute(page, `/people/${FX.b}`, "meridian");
  // Which wins is the browser's scheduling: Back before the leave keeps this frame, Back after it
  // remounts the module. Either way the text must survive.
  const frame = await ready(page, "meridianNavigation");
  await until(async () => (await frame.locator("#panel-body").count()) > 0 || (await frame.locator("#draft-tray").count()) > 0, "the editor or its draft is on screen");
  if (await frame.locator("#panel-body").count()) {
    note("Back beat the leave: the same frame and editor stayed");
  } else {
    note("the leave finished first: the module remounted and offered the draft");
    await frame.locator('#draft-tray [data-draft="resume"]').click();
    await frame.locator("#panel-body").waitFor();
  }
  await until(async () => (await fieldValue(page)) === `P1Nav immediate ${RUN}`, "the unsaved text survived");
  check(true, "immediate Back loses nothing");
  await closeEditor(page);
};
J["atlas-superseded-section-leaves-no-trace"] = async (page) => {
  const frame = await openReady(page, "atlas");
  await until(() => frame.evaluate(() => renderedSection === "map"), "the map is on screen");
  await page.route("**/api/map-filters", async (r) => { await sleep(900); await r.continue().catch(() => {}); });
  await frame.locator('[data-go="library"]').click();
  await atRoute(page, "/library", "atlas");
  await page.goBack(); // while the Library is still loading
  await atRoute(page, "/", "atlas");
  await sleep(1500);
  await page.unroute("**/api/map-filters");
  check(await frame.evaluate(() => state.view === "map" && renderedSection === "map" && !!document.querySelector("#map-stage")), "the map is still what is shown, and what Atlas believes is shown");
  await frame.locator('[data-go="library"]').click();
  await atRoute(page, "/library", "atlas");
  await until(() => frame.evaluate(() => renderedSection === "library" && !!document.querySelector(".place-card, .empty")), "the next visit renders normally");
  check(true, "a superseded section change leaves no trace");
};
J["leave-site-and-return"] = async (page) => {
  await openReady(page, "meridian", `/people/${FX.a}`);
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "person open");
  await page.goto("about:blank");
  await page.goBack();
  await until(() => route(page) === `/people/${FX.a}`, "the address is back");
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "returning from another site restores the record");
};

/* â”€â”€ Across modules â”€â”€ */
J["cross-module-lyra-meridian-chronos"] = async (page) => {
  if (!FX.series) throw new Skip("no Lyra titles on aetest");
  let frame = await openReady(page, "lyra");
  await act(frame, (s) => navigate({ view: "title", type: "series", id: s, from: "series" }), FX.series.id);
  await atRoute(page, `/series/${FX.series.id}`, "lyra");
  await headingIs(page, ".hero h1", FX.series.title, "L: Lyra title committed before leaving");
  const start = await page.evaluate(() => history.length);
  await frame.evaluate((p) => { bridge("navigate", { module: "meridian", path: p }).catch(() => {}); }, `/people/${FX.a}`);
  await until(() => pathOf(page) === "/app/modules/meridian", "M: arrived in Meridian");
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "M: exact person");
  frame = await ready(page, "meridianNavigation");
  await frame.evaluate((p) => { bridge("navigate", { module: "chronos", path: p }).catch(() => {}); }, `/events/${FX.e1}`);
  await until(() => pathOf(page) === "/app/modules/chronos", "E: arrived in Chronos");
  await headingIs(page, ".ae-drawer", `P1Nav event ${RUN}`, "E: exact event");
  check((await page.evaluate(() => history.length)) === start + 2, "exactly one entry per module visited");
  await page.goBack();
  await until(() => pathOf(page) === "/app/modules/meridian", "Back to Meridian");
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "Back â†’ M exact");
  await page.goBack();
  await until(() => pathOf(page) === "/app/modules/lyra", "Back to Lyra");
  await headingIs(page, ".hero h1", FX.series.title, "Back â†’ L exact (not Lyra's home)");
  await page.goForward();
  await until(() => pathOf(page) === "/app/modules/meridian", "Forward to Meridian");
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "Forward â†’ M exact");
  await page.goForward();
  await until(() => pathOf(page) === "/app/modules/chronos", "Forward to Chronos");
  await headingIs(page, ".ae-drawer", `P1Nav event ${RUN}`, "Forward â†’ E exact");
};

/* â”€â”€ Exact destinations and outcomes â”€â”€ */
J["meridian-interaction-is-exact"] = async (page) => {
  const frame = await openReady(page, "meridian", `/interactions/${FX.ix2}`);
  await until(async () => (await frame.locator(".ix-row.is-target").count()) === 1, "the linked Interaction is marked");
  check((await text(frame, ".ix-row.is-target")).includes(`P1Nav call ${RUN}`), "the exact Interaction is selected, not just its participant");
  check(route(page) === `/interactions/${FX.ix2}`, "the address stays on the Interaction");
  await page.goto(`${NEXUS}/app/modules/meridian?path=${encodeURIComponent(`/interactions/${FX.ix1}`)}`);
  const other = await ready(page, "meridianNavigation");
  await until(async () => (await other.locator(".ix-row.is-target").count()) === 1 && (await text(other, ".ix-row.is-target")).includes(`P1Nav coffee ${RUN}`), "a second Interaction of the same person is told apart");
  check(true, "two Interactions with one participant resolve to different destinations");
};
J["projected-provider-open"] = async (page) => {
  const frame = await openReady(page, "chronos");
  await frame.evaluate(() => { state.agendaDays = 120; go("agenda"); });
  await sleep(1500);
  const found = await frame.evaluate(() => { const o = state.occurrences.find((x) => x.origin === "projection" && state.context.applications.some((a) => a.id === x.provider)); return o ? { key: o.key, provider: o.provider, item: o.item_id } : null; });
  if (!found) throw new Skip("no projected occurrence in the next 120 days on aetest");
  const target = await call(frame, `/projected/open?provider=${encodeURIComponent(found.provider)}&item_id=${encodeURIComponent(found.item)}`);
  note(`resolved availability=${target.availability} path=${target.open_path ? "present" : "none"}`);
  await frame.locator(`[data-open="${found.key}"]`).first().click();
  await frame.locator('.ae-drawer [data-act="open-projected"]').click();
  await until(() => pathOf(page) === `/app/modules/${found.provider}`, "Open goes to the owner module");
  check(!target.open_path || new URL(page.url()).searchParams.get("path") === target.open_path, "Open uses the owner's path");
};
J["argus-usage-open"] = async (page) => {
  let frame = await openReady(page, "meridian");
  await call(frame, `/entities/${FX.a}/image`, "PUT", { photo_id: FX.ph1, crop: { x: 0, y: 0, size: 1 } }).catch(async () => call(frame, `/entities/${FX.a}/image`, "PUT", { photo_id: FX.ph1, crop: { x: 0.1, y: 0.1, w: 0.5, h: 0.5 } }));
  frame = await openReady(page, "argus", `/photos/${FX.ph1}`);
  const button = frame.locator('#usage [data-act="open-usage"]');
  await button.first().waitFor({ timeout: 15000 });
  await button.first().click();
  await until(() => pathOf(page) === "/app/modules/meridian", "Open follows the owner's path");
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "the exact person opens");
  await page.goBack();
  await atRoute(page, `/photos/${FX.ph1}`, "argus");
  check(true, "Back returns to the photo");
  const f = await openReady(page, "meridian");
  await call(f, `/entities/${FX.a}/image`, "DELETE").catch(() => {});
};
const MISSING = "00000000-0000-7000-8000-000000000000";
for (const [module, reference, phrase] of [
  ["meridian", "/no-such-screen", "could not be found"],
  ["meridian", `/people/${MISSING}`, "could not be found"],
  ["meridian", `/interactions/${MISSING}`, "could not be found"],
  ["lyra", "/no-such-screen", "could not be found"],
  ["lyra", `/movie/${MISSING}`, "could not be found"],
  ["chronos", "/no-such-screen", "could not be found"],
  ["chronos", `/events/${MISSING}`, "could not be found"],
  ["atlas", "/no-such-screen", "could not be found"],
  ["atlas", `/places/${MISSING}`, "could not be found"],
  ["argus", "/no-such-screen", "could not be found"],
  ["argus", `/photos/${MISSING}`, "could not be found"],
]) {
  J[`not-found ${module} ${reference.slice(0, 18)}`] = async (page) => {
    await open(page, module, reference);
    await until(async () => (await (await appFrame(page)).locator("body").innerText({ timeout: 500 })).includes(phrase), "an explicit not-found outcome");
    check(route(page) === reference, "the address is kept, not rewritten to another view");
    check((await hostError(page)) === 0, "the module's own outcome is shown without a host error");
  };
}
J["session-expiry-returns-to-record"] = async (page, ctx) => {
  const expired = await ctx.newPage();
  await openReady(expired, "meridian", `/people/${FX.a}`);
  await headingIs(expired, ".profile-head", `Alpha${RUN}`, "person open");
  const cookies = await ctx.cookies();
  await ctx.clearCookies();
  await expired.reload();
  await expired.locator("#username").waitFor({ timeout: 15000 });
  check(route(expired) === `/people/${FX.a}`, "an expired session keeps the address");
  await signIn(expired);
  await headingIs(expired, ".profile-head", `Alpha${RUN}`, "signing in returns to the exact record");
  await expired.close();
  void cookies;
};
J["unauthorized-navigation-is-refused"] = async (page, ctx, browser) => {
  const frame = await openReady(page, "meridian", `/people/${FX.a}`);
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "person open");
  const refused = (data) => frame.evaluate((d) => bridge("navigate", d).then(() => "sent", (e) => e.message), data);
  check(/Unknown application/.test(await refused({ module: "no-such-module" })), "an unknown module is refused");
  check(/Invalid path/.test(await refused({ module: "chronos", path: "//example.invalid/x" })), "an authority URL is refused as a path");
  check(/Invalid path/.test(await refused({ module: "chronos", path: "/events/a?b=c" })), "a path outside the bootstrap grammar is refused");
  check(pathOf(page) === "/app/modules/meridian", "nothing navigated");
  const stranger = await browser.newContext();
  const anon = await stranger.newPage();
  await anon.goto(`${NEXUS}/app/modules/meridian?nav=1&route=${encodeURIComponent(`/people/${FX.a}`)}`);
  await anon.locator("#username").waitFor({ timeout: 15000 });
  check((await anon.locator("#module-application").count()) === 0, "signed out, a record's address shows the sign-in form and no module frame");
  const direct = await anon.request.get(`${NEXUS}/modules/meridian/api/people/${FX.a}`);
  check([401, 403].includes(direct.status()), "signed out, the record's API refuses");
  await stranger.close();
};
J["module-unavailable-is-contained"] = async (page) => {
  const frame = await openReady(page, "chronos");
  void frame;
  await page.route("**/modules/lyra/**", (r) => r.fulfill({ status: 502, body: "unavailable" }));
  await open(page, "lyra");
  await until(() => pathOf(page) === "/app/modules/lyra", "the unavailable module's address is reached");
  await sleep(600);
  await page.goBack();
  await until(() => pathOf(page) === "/app/modules/chronos", "Back still works out of an unavailable module");
  await page.unroute("**/modules/lyra/**");
  await ready(page, "chronosNavigation");
  check(true, "the previous module restores");
};

/* â”€â”€ Private view state â”€â”€ */
J["meridian-directory-state"] = async (page) => {
  const frame = await openReady(page, "meridian", "/people");
  await frame.locator("#people-q").fill(`Alpha${RUN}`);
  await until(async () => (await frame.locator('#people-list [data-act="open-person"]').count()) === 1, "search narrows the list");
  await frame.locator('#people-list [data-act="open-person"]').first().click();
  await atRoute(page, `/people/${FX.a}`, "meridian");
  check(!page.url().includes(`Alpha${RUN}`), "the search text is not in the URL");
  await page.evaluate(() => document.querySelector('a[data-nav="overview"]').click());
  await leftForOverview(page, "left Meridian");
  await page.goBack(); await atRoute(page, `/people/${FX.a}`, "meridian");
  await ready(page, "meridianNavigation");
  await page.goBack(); await atRoute(page, "/people", "meridian");
  const after = await appFrame(page);
  await until(async () => (await after.locator("#people-q").inputValue({ timeout: 500 })) === `Alpha${RUN}`, "after a remount, Back restores the search");
  await until(async () => (await after.locator('#people-list [data-act="open-person"]').count()) === 1, "and its filtered list");
  check(true, "directory state restored per entry");
};
J["meridian-tab-state"] = async (page) => {
  const frame = await openReady(page, "meridian", `/people/${FX.a}`);
  await headingIs(page, ".profile-head", `Alpha${RUN}`, "person open");
  const tabs = await frame.locator(".tab[data-tab]").evaluateAll((els) => els.map((e) => e.dataset.tab));
  const tab = tabs.find((x) => x !== "overview");
  await frame.locator(`.tab[data-tab="${tab}"]`).click();
  await until(() => frame.evaluate((t) => state.tab === t, tab), "tab chosen");
  await act(frame, () => go("people"));
  await atRoute(page, "/people", "meridian");
  await page.goBack(); await atRoute(page, `/people/${FX.a}`, "meridian");
  await until(() => frame.evaluate((t) => state.tab === t, tab), "Back restores the tab");
  check(true, "contact tab restored");
};
J["lyra-filter-state"] = async (page) => {
  if (!FX.series) throw new Skip("no Lyra titles on aetest");
  const frame = await openReady(page, "lyra", "/series");
  await frame.locator('[data-filter="watching"]').first().click().catch(() => {});
  await until(() => frame.evaluate(() => state.filter.series === "watching"), "filter chosen");
  await act(frame, (s) => navigate({ view: "title", type: "series", id: s, from: "series" }), FX.series.id);
  await atRoute(page, `/series/${FX.series.id}`, "lyra");
  await frame.evaluate(() => { state.filter.series = "all"; });
  await page.goBack(); await atRoute(page, "/series", "lyra");
  await until(() => frame.evaluate(() => state.filter.series === "watching"), "Back restores this entry's filter");
  check(true, "list filter restored per entry");
  await frame.evaluate(() => { state.filter.series = "all"; });
};
J["chronos-filter-state"] = async (page) => {
  const frame = await openReady(page, "chronos");
  await frame.locator("#search").fill("P1Nav");
  await until(() => frame.evaluate(() => !!state.results), "search shows results");
  await frame.evaluate(() => chronosNavigation.viewChanged());
  await sleep(450);
  await frame.locator('.views [data-view="week"]').click();
  await atRoute(page, `/week/${FX.today}`, "chronos");
  check(!page.url().includes("P1Nav"), "the search text is not in the URL");
  await page.goBack(); await atRoute(page, `/month/${FX.today}`, "chronos");
  await until(() => frame.evaluate(() => state.query === "P1Nav" && !!state.results), "Back restores the search");
  check(true, "search restored per entry");
};
J["nexus-activity-pagination"] = async (page) => {
  await open(page, "chronos");
  await page.goto(`${NEXUS}/app/activity`);
  const more = page.getByRole("button", { name: "Load earlier activity" });
  await until(async () => (await page.locator(".activity-row").count()) > 0, "Activity loaded");
  if (!(await more.count())) throw new Skip("Activity has a single page on aetest");
  await more.click();
  await until(async () => (await page.locator(".activity-row").count()) > 0 && !(await more.isDisabled()), "a further page loaded");
  await sleep(500);
  const loaded = await page.locator(".activity-row").count();
  await page.evaluate(() => window.scrollTo(0, 500));
  await sleep(450);
  const scroll = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => document.querySelector('a[data-nav="settings"]').click());
  await until(() => pathOf(page) === "/app/settings", "left Activity");
  await page.goBack();
  await until(async () => (await page.locator(".activity-row").count()) >= loaded, "Back loads as far as had been read");
  check((await page.locator(".activity-row").count()) === loaded, "the same range is shown", `${loaded} rows`);
  await until(async () => Math.abs((await page.evaluate(() => window.scrollY)) - scroll) < 80, "scroll is restored");
  check(true, "Activity pagination and scroll restored");
};

/* â”€â”€ Input methods â”€â”€ */
J["synthetic-input-methods"] = async (page) => {
  if (ENGINE !== "chromium") throw new Skip("CDP input is Chromium only");
  const frame = await openReady(page, "meridian", "/people");
  await act(frame, (a) => go("person", a), FX.a);
  await atRoute(page, `/people/${FX.a}`, "meridian");
  const cdp = await page.context().newCDPSession(page);
  const button = async (name) => {
    for (const type of ["mousePressed", "mouseReleased"]) await cdp.send("Input.dispatchMouseEvent", { type, x: 700, y: 400, button: name, clickCount: 1 });
  };
  await button("back");
  const backed = await Promise.race([atRoute(page, "/people", "meridian").then(() => true), sleep(3500).then(() => false)]).catch(() => false);
  if (backed) {
    record("ok", "CDP-injected Mouse 4 over the iframe traverses Back (synthetic, not hardware)");
    await button("forward");
    await atRoute(page, `/people/${FX.a}`, "meridian");
    record("ok", "CDP-injected Mouse 5 over the iframe traverses Forward (synthetic, not hardware)");
  } else note("CDP-injected Mouse 4 was not handled by this browser build; physical input remains unverified");
  await page.keyboard.press("Alt+ArrowLeft");
  const alt = await Promise.race([atRoute(page, "/people", "meridian").then(() => true), sleep(3000).then(() => false)]).catch(() => false);
  note(alt ? "Alt+Left via automation traversed Back" : "Alt+Left via automation is not delivered to the browser's own shortcut handling; use a physical keyboard to verify");
};

/* â”€â”€ Phone-size viewport â”€â”€ */
J["viewport-390-journey"] = async (_page, ctx, browser) => {
  if (ENGINE === "firefox") throw new Skip("Firefox has no mobile device emulation");
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, storageState: await ctx.storageState() });
  const page = await phone.newPage();
  const frame = await openReady(page, "meridian", "/people");
  await frame.locator("#people-q").fill(`Alpha${RUN}`);
  await until(async () => (await frame.locator('#people-list [data-act="open-person"]').count()) === 1, "list narrowed");
  await frame.locator('#people-list [data-act="open-person"]').first().tap();
  await atRoute(page, `/people/${FX.a}`, "meridian");
  await page.goBack(); await atRoute(page, "/people", "meridian");
  await page.goForward(); await atRoute(page, `/people/${FX.a}`, "meridian");
  check(true, "Meridian at 390Ă—844 with touch taps (emulated viewport, not a phone)");
  if (FX.series) {
    const lyra = await openReady(page, "lyra");
    await lyra.locator('[data-act="nav"]').tap();
    await lyra.locator('.nav-item[data-nav="series"]').tap();
    await atRoute(page, "/series", "lyra");
    await lyra.locator(`[data-open="series:${FX.series.id}"]`).first().tap();
    await atRoute(page, `/series/${FX.series.id}`, "lyra");
    await page.goBack(); await atRoute(page, "/series", "lyra");
    check(true, "Lyra at 390Ă—844");
  }
  const chronos = await openReady(page, "chronos");
  await act(chronos, () => go("agenda"));
  await atRoute(page, `/agenda/${FX.today}`, "chronos");
  await page.goBack(); await atRoute(page, `/month/${FX.today}`, "chronos");
  check(true, "Chronos at 390Ă—844");
  await phone.close();
};

(async () => {
  const browser = await playwright[ENGINE].launch({ headless: true });
  // Nexus allows ten sign-ins per client per five minutes, so repeated runs reuse one session.
  const AUTH = process.env.AUTH_STATE;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ...(AUTH && fs.existsSync(AUTH) ? { storageState: AUTH } : {}) });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`${current}: ${e.message} ${String(e.stack).split("\n").slice(1, 7).join(" ").slice(0, 600)}`));
  current = "setup";
  await fixtures(page);
  record("ok", "synthetic fixtures created");
  if (AUTH) await ctx.storageState({ path: AUTH });
  for (const [name, run] of Object.entries(J)) {
    if (FILTER && !name.includes(FILTER)) continue;
    current = name;
    // A fresh tab each time: its own history (browsers cap history.length) and draft storage.
    const tab = await ctx.newPage();
    if (process.env.TRACE_NAV) {
      await tab.addInitScript(() => {
        const who = window.top === window ? "host " : "frame";
        addEventListener("message", (e) => {
          if (e.data?.channel === "empyrean-navigation-v1") console.log(`[nav ${performance.now().toFixed(0)} ${who}<-] ${e.data.type} rev=${e.data.revision ?? e.data.baseRevision ?? ""} ${e.data.cause || e.data.status || e.data.code || ""} ${e.data.route || ""}`);
        });
        addEventListener("load", () => console.log(`[nav ${performance.now().toFixed(0)} ${who} load]`));
      });
      tab.on("console", (m) => m.text().startsWith("[nav") && console.log(m.text().slice(0, 160)));
    }
    tab.on("pageerror", (e) => errors.push(`${current}: ${e.message} ${String(e.stack).split("\n").slice(1, 7).join(" ").slice(0, 600)}`));
    try {
      await run(tab, ctx, browser);
    } catch (error) {
      if (error instanceof Skip) record("skip", error.message);
      else if (!error.message.startsWith("failed:")) {
        record("FAIL", "journey raised", error.message.slice(0, 400));
        if (process.env.DEBUG_JOURNEY) console.log(await (await appFrame(tab)).evaluate(process.env.DEBUG_JOURNEY).catch((e) => e.message));
      } else {
        if (process.env.DEBUG_JOURNEY) console.log(await (await appFrame(tab)).evaluate(process.env.DEBUG_JOURNEY).catch((e) => e.message));
        const frame = await appFrame(tab).catch(() => null);
        const seen = frame ? await frame.locator("body").innerText({ timeout: 1000 }).catch(() => "") : "";
        console.log(`     url=${tab.url().slice(21, 200)} banner=${await tab.locator("#navigation-status").innerText({ timeout: 300 }).catch(() => "none")} frame=${seen.replace(/\s+/g, " ").slice(0, 300)}`);
      }
    }
    await tab.close().catch(() => {});
  }
  current = "cleanup";
  await cleanup(page);
  await browser.close();
  const summary = { engine: ENGINE, version: browser.version?.() || "", passed: results.filter((r) => r.status === "ok").length, failed: results.filter((r) => r.status === "FAIL").length, skipped: results.filter((r) => r.status === "skip").length, notes: results.filter((r) => r.status === "note").length, pageErrors: errors };
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, `results-${ENGINE}.json`), JSON.stringify({ summary, results }, null, 1));
  console.log(JSON.stringify(summary));
  process.exit(summary.failed ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(2);
});
