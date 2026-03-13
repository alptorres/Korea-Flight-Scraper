import json
import requests
import os
from datetime import datetime
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

DEPART_DATES = [
    "2027-01-09",
    "2027-01-10",
    "2027-01-11"
]

RETURN_DATES = [
    "2027-01-15",
    "2027-01-16",
    "2027-01-17"
]

PRICE_ALERT = 8000
ROUNDTRIP_ALERT = 10000

NTFY_TOPIC = "hrcc-korea-flight-alerts"

DEP_LOG = "depart_prices.json"
RET_LOG = "return_prices.json"
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

def build_google_url(origin, dest, date):
    return f"https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{dest}%20on%20{date}&curr=PHP"

def start_browser():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)

def scrape_google_price(driver, url):
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
# CEBU PACIFIC API
#########################

def cebpac_search(origin, dest, date):
    url = "https://api.cebupacificair.com/availability/search"
    payload = {
        "origin": origin,
        "destination": dest,
        "departureDate": date,
        "currency": "PHP"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        data = r.json()
        if "lowestFare" in data:
            return data["lowestFare"]
    except:
        pass
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
    dep = load_log(DEP_LOG)
    ret = load_log(RET_LOG)

    df_dep = pd.DataFrame(dep)
    df_ret = pd.DataFrame(ret)

    plt.figure(figsize=(12,6))

    if not df_dep.empty:
        df_dep["time"] = pd.to_datetime(df_dep["time"])
        for route in df_dep["route"].unique():
            subset = df_dep[df_dep["route"] == route]
            plt.plot(subset["time"], subset["price"], marker="o", label=f"Departure {route}")

    if not df_ret.empty:
        df_ret["time"] = pd.to_datetime(df_ret["time"])
        for route in df_ret["route"].unique():
            subset = df_ret[df_ret["route"] == route]
            plt.plot(subset["time"], subset["price"], marker="x", label=f"Return {route}")

    plt.title("Flight Price Trends")
    plt.xlabel("Time Checked")
    plt.ylabel("Price (PHP)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(GRAPH_FILE)
    plt.close()
    return GRAPH_FILE

#########################
# DEPARTURE CHECK
#########################

def check_departures(driver):
    log = load_log(DEP_LOG)
    cheapest = None
    for origin in ORIGINS:
        for d in DEPART_DATES:
            url = build_google_url(origin, DEST, d)
            g_price = scrape_google_price(driver, url)
            c_price = cebpac_search(origin, DEST, d)
            price = None
            source = None
            if g_price and c_price:
                price = min(g_price, c_price)
                source = "Google Flights / Cebu Pacific API"
            elif g_price:
                price = g_price
                source = "Google Flights"
            elif c_price:
                price = c_price
                source = "Cebu Pacific API"
            if not price:
                continue
            entry = {
                "time": str(datetime.now()),
                "route": f"{origin}-ICN",
                "date": d,
                "price": price,
                "source": source,
                "url": url
            }
            log.append(entry)
            if cheapest is None or price < cheapest["price"]:
                cheapest = entry
    save_log(DEP_LOG, log)
    if cheapest and cheapest["price"] < PRICE_ALERT:
        send_alert(
            "✈️ Cheap Departure Found",
            f"""Route: {cheapest["route"]}
Date: {cheapest["date"]}
Price: ₱{cheapest["price"]}

Click here to view flight:
{cheapest["url"]}
"""
        )
    return cheapest

#########################
# RETURN CHECK
#########################

def check_returns(driver):
    log = load_log(RET_LOG)
    cheapest = None
    for origin in ORIGINS:
        for d in RETURN_DATES:
            url = build_google_url(DEST, origin, d)
            g_price = scrape_google_price(driver, url)
            c_price = cebpac_search(DEST, origin, d)
            price = None
            source = None
            if g_price and c_price:
                price = min(g_price, c_price)
                source = "Google Flights / Cebu Pacific API"
            elif g_price:
                price = g_price
                source = "Google Flights"
            elif c_price:
                price = c_price
                source = "Cebu Pacific API"
            if not price:
                continue
            entry = {
                "time": str(datetime.now()),
                "route": f"ICN-{origin}",
                "date": d,
                "price": price,
                "source": source,
                "url": url
            }
            log.append(entry)
            if cheapest is None or price < cheapest["price"]:
                cheapest = entry
    save_log(RET_LOG, log)
    if cheapest and cheapest["price"] < PRICE_ALERT:
        send_alert(
            "✈️ Cheap Return Found",
            f"""Route: {cheapest["route"]}
Date: {cheapest["date"]}
Price: ₱{cheapest["price"]}

Click here to view flight:
{cheapest["url"]}
"""
        )
    return cheapest

#########################
# ROUND TRIP DETECTION
#########################

def check_roundtrip(dep, ret):
    if not dep or not ret:
        return
    total = dep["price"] + ret["price"]
    if total < ROUNDTRIP_ALERT:
        send_alert(
            "⚡ CHEAP ROUND TRIP FOUND",
            f"""Departure
{dep["route"]}
{dep["date"]}
₱{dep["price"]}

Return
{ret["route"]}
{ret["date"]}
₱{ret["price"]}

Total Price: ₱{total}

Click here for departure:
{dep["url"]}

Click here for return:
{ret["url"]}
"""
        )

#########################
# MAIN
#########################

def main():
    driver = start_browser()
    dep = check_departures(driver)
    ret = check_returns(driver)
    check_roundtrip(dep, ret)
    driver.quit()

    # Always generate graph
    graph_file = generate_graph()

    # Daily 12pm Philippine time notification (UTC+8 → 04:00 UTC)
    now = datetime.utcnow()
    if now.hour == 4 and now.minute == 0:
        repo_url = "https://alptorres.github.io/Korea-Flight-Scraper/prices.png"
        send_alert("📊 Korea Ticket Price Log",
           f"Korea ticket price log: {repo_url}")


if __name__ == "__main__":
    main()
