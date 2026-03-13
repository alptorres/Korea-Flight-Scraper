import json
import requests
import os
from datetime import datetime, timezone
import matplotlib.pyplot as plt
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

#########################
# CONFIG
#########################

ORIGINS = ["MNL", "CRK"]
DEST = "ICN"

DEP_DATE = "2027-01-10"
RET_DATE = "2027-01-16"

ROUNDTRIP_ALERT = 8000

NTFY_TOPIC = "hrcc-korea-flight-alerts"

ROUNDTRIP_LOG = "roundtrip_prices.json"
GRAPH_FILE = "prices.png"

#########################
# ALERT SYSTEM
#########################

def send_alert(title, body):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=f"{title}\n\n{body}".encode("utf-8")
    )

#########################
# GOOGLE FLIGHTS
#########################

def build_google_url(origin, dest, dep_date, ret_date):
    return (
        f"https://www.google.com/travel/flights?"
        f"q=Flights%20from%20{origin}%20to%20{dest}%20on%20{dep_date}%20returning%20on%20{ret_date}&curr=PHP"
    )

def start_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.binary_location = "/usr/bin/chromium-browser"
    return webdriver.Chrome(options=options)

def scrape_google_roundtrip(driver, url):
    driver.get(url)
    driver.implicitly_wait(8)
    prices = driver.find_elements(By.XPATH, "//*[contains(text(),'₱')]")
    values = []
    for p in prices:
        txt = p.text.replace("₱","").replace(",","")
        if txt.isdigit():
            values.append(int(txt))
    if values:
        return min(values)
    return None

#########################
# LOGGING
#########################

def load_log(file):
    try:
        with open(file) as f:
            return json.load(f)
    except:
        return []

def save_log(file,data):
    with open(file,"w") as f:
        json.dump(data,f,indent=2)

#########################
# GRAPH GENERATION
#########################

def generate_graph():
    log = load_log(ROUNDTRIP_LOG)
    df = pd.DataFrame(log)

    plt.figure(figsize=(12,6))

    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
        for origin in df["origin"].unique():
            subset = df[df["origin"] == origin]
            plt.plot(subset["time"], subset["price"], marker="o", label=f"{origin} → {DEST} Roundtrip")

    plt.title("Roundtrip Flight Price Trends (Jan 10–16)")
    plt.xlabel("Time Checked")
    plt.ylabel("Total Price (PHP)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(GRAPH_FILE)
    plt.close()
    return GRAPH_FILE

#########################
# ROUNDTRIP CHECK
#########################

def check_roundtrip(driver):
    log = load_log(ROUNDTRIP_LOG)
    results = []

    for origin in ORIGINS:
        g_url = build_google_url(origin, DEST, DEP_DATE, RET_DATE)
        g_price = scrape_google_roundtrip(driver, g_url)
        if g_price:
            entry = {
                "time": str(datetime.now()),
                "origin": origin,
                "dep_date": DEP_DATE,
                "ret_date": RET_DATE,
                "price": g_price,
                "source": "Google Flights",
                "url": g_url
            }
            log.append(entry)
            results.append(entry)

    save_log(ROUNDTRIP_LOG, log)

    if results:
        body_lines = []
        for r in results:
            body_lines.append(
                f"{r['origin']} → {DEST}: ₱{r['price']} "
                f"(Dep {r['dep_date']} / Ret {r['ret_date']})\n"
                f"Click here: {r['url']}"
            )
        body = "\n\n".join(body_lines)

        if any(r["price"] < ROUNDTRIP_ALERT for r in results):
            send_alert("⚡ Roundtrip Prices Found", body)

    return results

#########################
# MAIN
#########################

def main():
    driver = start_browser()
    results = check_roundtrip(driver)
    driver.quit()

    # Daily 12pm Philippine time notification (UTC+8 → 04:00 UTC)
    now = datetime.now(timezone.utc)
    is_noon_run = (now.hour == 4 and now.minute < 30)

    # Detect manual run
    is_manual_run = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    if is_noon_run or is_manual_run:
        graph_file = generate_graph()
        repo_url = "https://raw.githubusercontent.com/alptorres/Korea-Flight-Scraper/refs/heads/main/prices.png"
        send_alert("📊 Korea Ticket Price Log",
           f"Korea ticket price log: {repo_url}")

if __name__ == "__main__":
    main()
