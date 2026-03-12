const scrapeBtn = document.getElementById("scrape-btn");
const createBtn = document.getElementById("create-btn");
const scrapeStatus = document.getElementById("scrape-status");
const createStatus = document.getElementById("create-status");
const jumpScrape = document.getElementById("jump-scrape");
const jumpManual = document.getElementById("jump-manual");

function setStatus(el, message, tone) {
  if (!el) return;
  el.textContent = message;
  el.style.color = tone === "error" ? "#b9473a" : tone === "success" ? "#2f6b3c" : "#6b5f57";
}

function getValue(id) {
  const node = document.getElementById(id);
  return node ? node.value.trim() : "";
}

function setValue(id, value) {
  const node = document.getElementById(id);
  if (node && value) {
    node.value = value;
  }
}

async function scrapeWebsite() {
  const url = getValue("website_url");
  if (!url) {
    setStatus(scrapeStatus, "Enter a website URL first.", "error");
    return;
  }

  setStatus(scrapeStatus, "Fetching website details...", "info");
  try {
    const resp = await fetch("/api/onboarding/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Scrape failed");
    }

    setValue("hotel_name", data.name);
    setValue("hotel_phone", data.phone);
    setValue("hotel_address", data.address);
    setStatus(scrapeStatus, "Imported. Review the fields below.", "success");
  } catch (err) {
    setStatus(scrapeStatus, err.message || "Scrape failed.", "error");
  }
}

async function createHotel() {
  const payload = {
    name: getValue("hotel_name"),
    receptionist_name: getValue("receptionist_name"),
    phone: getValue("hotel_phone"),
    address: getValue("hotel_address"),
    checkin_time: getValue("checkin_time"),
    checkout_time: getValue("checkout_time"),
    currency: getValue("currency"),
    timezone: getValue("timezone"),
    twilio_voice_number: getValue("twilio_voice_number"),
    twilio_whatsapp_number: getValue("twilio_whatsapp_number"),
    twilio_account_sid: getValue("twilio_account_sid"),
    twilio_auth_token: getValue("twilio_auth_token"),
    website_url: getValue("website_url"),
    owner_email: getValue("owner_email"),
    owner_password: getValue("owner_password"),
  };

  if (!payload.name) {
    setStatus(createStatus, "Hotel name is required.", "error");
    return;
  }

  setStatus(createStatus, "Creating hotel profile...", "info");
  try {
    const resp = await fetch("/api/onboarding/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Creation failed");
    }

    setStatus(
      createStatus,
      `Created. Hotel ID: ${data.hotel.hotel_id}. Database: ${data.hotel.db_name}.`,
      "success"
    );
  } catch (err) {
    setStatus(createStatus, err.message || "Creation failed.", "error");
  }
}

if (scrapeBtn) scrapeBtn.addEventListener("click", scrapeWebsite);
if (createBtn) createBtn.addEventListener("click", createHotel);
if (jumpScrape) jumpScrape.addEventListener("click", () => document.getElementById("scrape-panel").scrollIntoView({ behavior: "smooth" }));
if (jumpManual) jumpManual.addEventListener("click", () => document.getElementById("manual-panel").scrollIntoView({ behavior: "smooth" }));
