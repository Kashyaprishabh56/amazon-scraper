import streamlit as st
import pandas as pd
import re
import os
from playwright.sync_api import sync_playwright

# 🔥 REQUIRED FOR STREAMLIT CLOUD
os.system("playwright install")

# ✅ GOOGLE SHEETS IMPORTS
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Amazon Scraper", layout="wide")
st.title("🛒 Amazon Scraper (Cloud Version ☁️)")

urls_input = st.text_area(
    "Paste Amazon URLs (one per line)",
    height=200
)

sheet_name_input = st.text_input(
    "Enter Google Sheet Tab Name (optional)",
    placeholder="e.g. Mobile_Data_April"
)

# ==========================
# 🔁 GOOGLE SHEETS FUNCTION (SECRETS VERSION)
# ==========================
def upload_to_sheets(df, custom_name=None):

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    # 🔐 USE STREAMLIT SECRETS
    creds_dict = st.secrets["gcp_service_account"]

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict, scope
    )

    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open("Amazon Scraper Data")
    except:
        spreadsheet = client.create("Amazon Scraper Data")

    # Sheet naming
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
    try:
        page.goto(url, timeout=40000)
        page.wait_for_load_state("domcontentloaded")
        page.mouse.wheel(0, 1500)

        # TITLE
        try:
            title = page.locator("#productTitle").text_content(timeout=5000).strip()
        except:
            title = page.title()

        # PRICE
        price = "NOT FOUND"

        price_selectors = [
            ".a-price .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-offscreen",
            "span.a-price-whole"
        ]

        found_price = None

        for sel in price_selectors:
            if page.locator(sel).count() > 0:
                try:
                    text = page.locator(sel).first.text_content().strip()
                    if text and "₹" in text:
                        found_price = text
                        break
                except:
                    pass

        # Availability
        availability = ""
        try:
            availability = page.locator("#availability").text_content().lower()
        except:
            pass

        if "unavailable" in availability:
            price = "NOT FOUND"
        elif found_price:
            price = found_price

        # SELLER
        seller = "N/A"
        seller_selectors = [
            "#sellerProfileTriggerId",
            "#bylineInfo",
            "#merchant-info"
        ]

        for sel in seller_selectors:
            if page.locator(sel).count() > 0:
                try:
                    seller = page.locator(sel).first.text_content().strip()
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
        return {
            "ASIN": "N/A",
            "URL": url,
            "Title": "ERROR",
            "sales_price": "ERROR",
            "buybox_winner": str(e)
        }

# ==========================
# 🔁 MAIN SCRAPER (CLOUD SAFE)
# ==========================
def scrape_amazon(urls):
    all_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )

        pages = [browser.new_page() for _ in range(min(5, len(urls)))]

        for i, url in enumerate(urls):
            page = pages[i % len(pages)]
            st.write(f"⚡ Fetching: {url}")

            data = scrape_single(page, url)
            all_data.append(data)

        browser.close()

    return pd.DataFrame(all_data)

# ==========================
# ▶️ RUN BUTTON
# ==========================
if st.button("🚀 Run Scraper"):

    urls = [u.strip() for u in urls_input.split("\n") if u.strip()]

    if not urls:
        st.warning("⚠️ Please enter at least one URL")
    else:
        df = scrape_amazon(urls)

        st.session_state["df_data"] = df

        st.success("✅ Scraping Completed")

        st.dataframe(df, width='stretch')

        st.download_button(
            "📥 Download CSV",
            df.to_csv(index=False),
            file_name="amazon_products.csv",
            mime="text/csv"
        )

# ==========================
# ☁️ GOOGLE SHEETS BUTTON
# ==========================
if "df_data" in st.session_state:

    if st.button("☁️ Upload to Google Sheets"):

        try:
            upload_to_sheets(st.session_state["df_data"], sheet_name_input)
            st.success("✅ Uploaded to Google Sheets")
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")
