import streamlit as st
import pandas as pd
import re
import time
import random
import os
from playwright.sync_api import sync_playwright

# ✅ GOOGLE SHEETS IMPORTS
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ✅ IMPORTANT FOR RAILWAY
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

st.set_page_config(page_title="Amazon Scraper", layout="wide")
st.title("🛒 Amazon Scraper (Fast Version ⚡)")

# ==========================
# 🧾 INPUTS
# ==========================
urls_input = st.text_area(
    "Paste Amazon URLs (one per line)",
    height=200
)

sheet_name_input = st.text_input(
    "Enter Google Sheet Tab Name (optional)",
    placeholder="e.g. Mobile_Data_April"
)

# ==========================
# ☁️ GOOGLE SHEETS FUNCTION
# ==========================
def upload_to_sheets(df, custom_name=None):

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "credentials.json", scope
    )

    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open("Amazon Scraper Data")
    except:
        spreadsheet = client.create("Amazon Scraper Data")

    if custom_name and custom_name.strip():
        sheet_name = custom_name.strip()
    else:
        sheet_name = f"Run_{len(spreadsheet.worksheets()) + 1}"

    worksheet = spreadsheet.add_worksheet(
        title=sheet_name,
        rows="1000",
        cols="20"
    )

    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

    return True

# ==========================
# 🔁 SINGLE SCRAPE FUNCTION
# ==========================
def scrape_single(page, url):
    for attempt in range(3):
        try:
            page.goto(url, timeout=40000, wait_until="domcontentloaded")

            # human-like delay
            time.sleep(random.uniform(1.5, 3))
            page.mouse.wheel(0, 1500)

            # TITLE
            try:
                title = page.locator("#productTitle").text_content(timeout=5000).strip()
            except:
                title = page.title()

            # PRICE
            price = "NOT FOUND"
            selectors = [
                ".a-price .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .a-offscreen",
                "span.a-price-whole"
            ]

            for sel in selectors:
                loc = page.locator(sel)
                if loc.count() > 0:
                    try:
                        text = loc.first.text_content().strip()
                        if text and "₹" in text:
                            price = text
                            break
                    except:
                        pass

            # AVAILABILITY
            availability = ""
            try:
                availability = page.locator("#availability").text_content().lower()
            except:
                pass

            if "unavailable" in availability:
                price = "NOT FOUND"

            # SELLER
            seller = "N/A"
            for sel in ["#sellerProfileTriggerId", "#bylineInfo", "#merchant-info"]:
                loc = page.locator(sel)
                if loc.count() > 0:
                    try:
                        seller = loc.first.text_content().strip()
                        break
                    except:
                        pass

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
            if attempt == 2:
                return {
                    "ASIN": "N/A",
                    "URL": url,
                    "Title": "ERROR",
                    "sales_price": "ERROR",
                    "buybox_winner": str(e)
                }
            time.sleep(2)

# ==========================
# 🔁 MAIN SCRAPER
# ==========================
def scrape_amazon(urls):
    all_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ✅ Anti-block browser context
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        pages = [context.new_page() for _ in range(min(5, len(urls)))]

        for i, url in enumerate(urls):
            page = pages[i % len(pages)]

            st.write(f"⚡ Fetching: {url}")

            data = scrape_single(page, url)
            all_data.append(data)

        browser.close()

    return pd.DataFrame(all_data)

# ==========================
# ▶️ RUN SCRAPER
# ==========================
if st.button("🚀 Run Scraper (Fast)"):

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    if not urls:
        st.warning("⚠️ Please enter at least one URL")

    else:
        df = scrape_amazon(urls)

        st.session_state["df_data"] = df

        st.success("✅ Scraping Completed")

        st.dataframe(df, use_container_width=True)

        st.download_button(
            "📥 Download CSV",
            df.to_csv(index=False),
            file_name="amazon_products.csv",
            mime="text/csv"
        )

# ==========================
# ☁️ UPLOAD BUTTON
# ==========================
if "df_data" in st.session_state:

    if st.button("☁️ Upload to Google Sheets"):

        try:
            upload_to_sheets(st.session_state["df_data"], sheet_name_input)
            st.success("✅ Uploaded to Google Sheets")
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")
