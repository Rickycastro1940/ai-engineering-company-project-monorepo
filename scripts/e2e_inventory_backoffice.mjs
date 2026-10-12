import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://127.0.0.1:5174";
const ART = "/opt/cursor/artifacts";
fs.mkdirSync(ART, { recursive: true });

const email = `pw.inventory.${Date.now()}@brasaland.test`;
const password = "secret-password";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const results = [];

function note(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

try {
  await page.goto(`${BASE}/register`);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const nameField = page.getByLabel(/name/i).first();
  if (await nameField.count()) {
    await nameField.fill("Playwright Ops");
  }
  await page.getByRole("button", { name: /create|register|sign up/i }).click();
  await page.waitForURL(/accessible|inventory/, { timeout: 15000 });
  note("register_login", true, page.url());

  await page.goto(`${BASE}/inventory/products`);
  await page.waitForSelector("text=Stockout");
  await page.waitForSelector("text=Current stock");
  await page.waitForSelector("text=Beef brisket");
  const body = await page.locator("body").innerText();
  note("stock_indicators", /Stockout/.test(body) && /Healthy/.test(body) && /Overstock/.test(body));
  note("brasaland_terms_products", /ingredient/i.test(body) && /supplier delivery/i.test(body) && /kitchen usage/i.test(body));
  await page.screenshot({ path: `${ART}/e2e-products.png`, fullPage: true });

  await page.goto(`${BASE}/inventory/orders/inbound`);
  await page.waitForSelector('select[name="ingredient_id"]');
  await page.waitForFunction(() => {
    const select = document.querySelector('select[name="ingredient_id"]');
    return select && select.options.length > 1;
  });
  const inboundValue = await page.locator('select[name="ingredient_id"] option').nth(1).getAttribute("value");
  const inboundLabel = await page.locator('select[name="ingredient_id"] option').nth(1).innerText();
  note("inbound_ingredient_options", Boolean(inboundValue), inboundLabel.trim());
  await page.selectOption('select[name="ingredient_id"]', inboundValue);
  await page.fill('input[name="supplier_name"]', "Carnes del Valle S.A.");
  await page.selectOption('select[name="location_id"]', "1");
  await page.fill('input[name="quantity"]', "5");
  await page.getByRole("button", { name: /record supplier delivery/i }).click();
  await page.waitForSelector(".auth-form__success", { timeout: 10000 });
  const inboundOk = await page.locator(".auth-form__success").innerText();
  note("inbound_confirmation", /supplier delivery recorded/i.test(inboundOk), inboundOk.slice(0, 120));
  await page.screenshot({ path: `${ART}/e2e-inbound-success.png`, fullPage: true });

  await page.goto(`${BASE}/inventory/orders/outbound`);
  await page.waitForSelector('select[name="ingredient_id"]');
  await page.waitForFunction(() => {
    const select = document.querySelector('select[name="ingredient_id"]');
    return select && select.options.length > 1;
  });
  const outboundValue = await page.locator('select[name="ingredient_id"] option').nth(1).getAttribute("value");
  await page.selectOption('select[name="ingredient_id"]', outboundValue);
  await page.waitForSelector(".outbound-stock__value strong", { timeout: 10000 });
  const onHandText = await page.locator(".outbound-stock__value").innerText();
  note("outbound_live_stock", /\d+/.test(onHandText), onHandText.trim());
  await page.fill('input[name="quantity"]', "9999");
  await page.waitForSelector(".auth-form__warning");
  const warn = await page.locator(".auth-form__warning").innerText();
  note("outbound_client_warning", /higher than current stock/i.test(warn), warn.slice(0, 100));
  await page.getByRole("button", { name: /record kitchen usage/i }).click();
  await page.waitForSelector(".auth-form__error", { timeout: 10000 });
  const reject = await page.locator(".auth-form__error").first().innerText();
  note("outbound_api_rejection", /insufficient stock/i.test(reject), reject.slice(0, 140));
  await page.screenshot({ path: `${ART}/e2e-outbound-reject.png`, fullPage: true });

  await page.fill('input[name="quantity"]', "1");
  await page.selectOption('select[name="reason"]', "consumption");
  await page.getByRole("button", { name: /record kitchen usage/i }).click();
  await page.waitForSelector(".auth-form__success", { timeout: 10000 });
  const outOk = await page.locator(".auth-form__success").innerText();
  note("outbound_success", /kitchen usage recorded/i.test(outOk), outOk.slice(0, 120));

  await page.goto(`${BASE}/inventory/orders`);
  await page.waitForSelector("text=Ingredient orders");
  await page.waitForSelector(".orders__table tbody tr", { timeout: 10000 });
  const ordersHtml = await page.locator(".orders").innerHTML();
  const ordersText = await page.locator(".orders").innerText();
  const hasInbound = /Supplier delivery/i.test(ordersText);
  const hasOutbound = /Kitchen usage/i.test(ordersText);
  const hasUuid = /user_uuid/i.test(ordersHtml) || /Kitchen staff/i.test(ordersText);
  const editDeleteCount = await page.locator(".orders button", { hasText: /Edit|Delete/i }).count();
  note(
    "order_history",
    hasInbound && hasOutbound && hasUuid && editDeleteCount === 0,
    `inbound=${hasInbound} outbound=${hasOutbound} uuid=${hasUuid} editDelete=${editDeleteCount}`,
  );
  await page.screenshot({ path: `${ART}/e2e-orders.png`, fullPage: true });

  for (const path of [
    "/inventory/products",
    "/inventory/orders/inbound",
    "/inventory/orders/outbound",
    "/inventory/orders",
  ]) {
    await page.goto(`${BASE}${path}`);
    note(`view_${path}`, page.url().includes(path), page.url());
  }
} catch (error) {
  note("script_error", false, String(error));
  await page.screenshot({ path: `${ART}/e2e-error.png`, fullPage: true }).catch(() => {});
} finally {
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
fs.writeFileSync(`${ART}/e2e-inventory-results.json`, JSON.stringify(results, null, 2));
console.log(JSON.stringify({ passed: results.filter((r) => r.ok).length, failed: failed.length }, null, 2));
process.exit(failed.length ? 1 : 0);
