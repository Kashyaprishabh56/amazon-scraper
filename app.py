import streamlit as st
import pandas as pd
import re
import json
import os
import asyncio
import random
from playwright.async_api import async_playwright

# ✅ FIX FOR RENDER
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

# ✅ GOOGLE SHEETS
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Amazon Scraper", layout="wide")
st.title("🚀 Amazon Scraper (Production Level 🔥)")

urls_input = st.text_area("Paste Amazon URLs", height=200)

sheet_name_input = st.text_input(
    "Google Sheet Tab Name",
    placeholder="e.g. Mobile_Data"
)

# ==========================
# GOOGLE SHEETS
# ==========================
def upload_to_sheets(df, custom_name=None):

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])

    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open("Amazon Scraper Data")
    except:
        spreadsheet = client.create("Amazon Scraper Data")

    sheet_name = custom_name if custom_name else f"Run_{len(spreadsheet.worksheets())+1}"

    worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    return True

# ==========================
# USER AGENTS
# ==========================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/118 Safari/537.36"
]

# ==========================
# VALIDATION
# ==========================
def is_blocked(title):
    return (
        not title or
        "amazon.in" in title.lower() or
        "sorry" in title.lower()
    )

# ==========================
# SCRAPE ONE
# ==========================
async def scrape_one(page, url):
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_selector("#productTitle", timeout=8000)

        # delay (anti-bot)
        await asyncio.sleep(random.uniform(1.2, 2.0))

        # TITLE
        title = "N/A"
        selectors = ["#productTitle", "h1 span", "#title span"]

        for sel in selectors:
            if await page.locator(sel).count() > 0:
                text = await page.locator(sel).first.text_content()
                if text and len(text.strip()) > 5:
                    title = text.strip()
                    break

        # PRICE
        price = "NOT FOUND"
        price_selectors = [
            ".a-price .a-offscreen",
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#corePriceDisplay_desktop_feature_div .a-offscreen"
        ]

        for sel in price_selectors:
            if await page.locator(sel).count() > 0:
                text = await page.locator(sel).first.text_content()
                if text and "₹" in text:
                    price = text.strip()
                    break

        # SELLER
        seller = "N/A"
        seller_selectors = [
            "#sellerProfileTriggerId",
            "#bylineInfo",
            "#merchant-info"
        ]

        for sel in seller_selectors:
            if await page.locator(sel).count() > 0:
                seller = (await page.locator(sel).first.text_content()).strip()
                break

        # ASIN
        match = re.search(r"/dp/([A-Z0-9]{10})", url)
        asin = match.group(1) if match else "N/A"

        return {
            "ASIN": asin,
            "URL": url,
            "Title": title,
            "sales_price": price,
            "buybox_winner": seller
        }

    except Exception as e:
        return {
            "ASIN": "N/A",
            "URL": url,
            "Title": "ERROR",
            "sales_price": "ERROR",
            "buybox_winner": str(e)
        }

# ==========================
# RETRY WRAPPER 🔥
# ==========================
async def safe_scrape(page, url, retries=3):

    for attempt in range(retries):
        data = await scrape_one(page, url)

        if is_blocked(data["Title"]) or data["sales_price"] == "NOT FOUND":
            await page.wait_for_timeout(1500)
            await page.reload()
        else:
            return data

    return data

# ==========================
# BATCH SCRAPER
# ==========================
async def scrape_batch(urls):

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="en-IN",
            viewport={"width": 1280, "height": 800}
        )

        # block heavy resources
        await context.route("**/*", lambda route, request:
            asyncio.create_task(
                route.abort() if request.resource_type in ["image", "stylesheet", "font"]
                else route.continue_()
            )
        )

        tasks = []

        for url in urls:
            page = await context.new_page()
            tasks.append(safe_scrape(page, url))

        results = await asyncio.gather(*tasks)

        await browser.close()
        return results

# ==========================
# MAIN
# ==========================
def run_scraper(urls):

    BATCH_SIZE = 4
    all_results = []

    for i in range(0, len(urls), BATCH_SIZE):

        batch = urls[i:i+BATCH_SIZE]
        st.write(f"⚡ Batch {i//BATCH_SIZE + 1}")

        results = asyncio.run(scrape_batch(batch))
        all_results.extend(results)

    return pd.DataFrame(all_results)

# ==========================
# UI
# ==========================
if st.button("🚀 Run Scraper"):

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    if not urls:
        st.warning("Enter URLs")
    else:
        df = run_scraper(urls)

        st.session_state["df_data"] = df

        st.success("✅ Completed")
        st.dataframe(df, width="stretch")

        st.download_button(
            "Download CSV",
            df.to_csv(index=False),
            "amazon_data.csv"
        )

# ==========================
# GOOGLE SHEETS
# ==========================
if "df_data" in st.session_state:

    if st.button("Upload to Google Sheets"):
        upload_to_sheets(st.session_state["df_data"], sheet_name_input)
        st.success("Uploaded 🚀")
