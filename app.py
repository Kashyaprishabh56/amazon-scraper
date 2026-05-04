import streamlit as st
import pandas as pd
import re
import json
import os
import time
import random
from playwright.sync_api import sync_playwright

# ✅ GOOGLE SHEETS IMPORTS
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Amazon Scraper", layout="wide")
st.title("🛒 Amazon Scraper (Fast Version ⚡)")

# ==========================
# 📥 INPUT
# ==========================
urls_input = st.text_area(
    "Paste Amazon URLs (one per line)",
    height=200
)

sheet_name_input = st.text_input(
    "Enter Google Sheet Tab Name (optional)",
    placeholder="e.g. Mobile_Data_April"
)

# ✅ COUNT URLS
urls_list = [u.strip() for u in urls_input.split("\n") if u.strip()]
st.info(f"🔗 Total URLs detected: {len(urls_list)}")

ASIN_PATTERN = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?]|$)", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"([₹$€£]\s?[\d,]+(?:\.\d{1,2})?)")
RATING_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*out of 5", re.IGNORECASE)
COUNT_PATTERN = re.compile(r"([\d,]+)")
BEST_SELLERS_RANK_PATTERN = re.compile(r"#[\d,]+\s+in\s+.*?(?=\s+#\d|$)")
LOW_STOCK_PATTERN = re.compile(r"only\s+\d+\s+left in stock", re.IGNORECASE)
OUTPUT_COLUMNS = [
    "ASIN",
    "URL",
    "Title",
    "Best Sellers Ranking",
    "ratings",
    "reviews",
    "sales_price",
    "MRP",
    "buybox_winner",
    "deal_tag",
    "stock_status"
]

# ==========================
# 🔁 GOOGLE SHEETS FUNCTION
# ==========================
def get_sheets_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_data = None

    try:
        creds_data = st.secrets.get("gcp_service_account")
    except Exception:
        pass

    if not creds_data and os.environ.get("GOOGLE_CREDENTIALS_JSON"):
        creds_data = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

    if creds_data:
        creds_data = dict(creds_data)
        if "private_key" in creds_data:
            creds_data["private_key"] = creds_data["private_key"].replace("\\n", "\n")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_data, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "credentials.json", scope
        )

    return gspread.authorize(creds)


def get_target_worksheet(custom_name=None):
    client = get_sheets_client()

    try:
        spreadsheet = client.open("Amazon Scraper Data")
    except Exception as e:
        raise RuntimeError("Please create 'Amazon Scraper Data' sheet manually and share access") from e

    if custom_name and custom_name.strip():
        sheet_name = custom_name.strip()
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name,
                rows="1000",
                cols="20"
            )
    else:
        existing_titles = {ws.title for ws in spreadsheet.worksheets()}
        run_number = 1
        while f"Run_{run_number}" in existing_titles:
            run_number += 1
        sheet_name = f"Run_{run_number}"
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows="1000",
            cols="20"
        )

    current_headers = worksheet.row_values(1)

    if not current_headers:
        worksheet.append_row(OUTPUT_COLUMNS, value_input_option="USER_ENTERED")
    elif current_headers != OUTPUT_COLUMNS:
        worksheet.update([OUTPUT_COLUMNS])

    return worksheet


def append_row_to_sheet(worksheet, row_data):
    worksheet.append_row(
        [row_data.get(column, "") for column in OUTPUT_COLUMNS],
        value_input_option="USER_ENTERED"
    )


def upload_to_sheets(df, custom_name=None):
    worksheet = get_target_worksheet(custom_name)

    for row in df.to_dict("records"):
        append_row_to_sheet(worksheet, row)

    return True


def extract_asin_from_url(url):
    match = ASIN_PATTERN.search(url or "")
    return match.group(1).upper() if match else None


def extract_text(page, selectors, timeout=3000):
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=timeout)
            if not text or not text.strip():
                text = locator.text_content(timeout=timeout)
            if text and text.strip():
                return text.strip()
        except:
            continue
    return None


def get_detected_page_asin(page):
    asin_selectors = [
        "#ASIN",
        "input[name='ASIN']",
        "input[name='ASIN.0']",
        "[data-asin]"
    ]

    for sel in asin_selectors:
        try:
            locator = page.locator(sel).first
            if locator.count() == 0:
                continue
            asin = locator.get_attribute("value") or locator.get_attribute("data-asin")
            if asin and re.fullmatch(r"[A-Z0-9]{10}", asin.strip(), re.IGNORECASE):
                return asin.strip().upper()
        except:
            continue

    return extract_asin_from_url(page.url)


def build_not_found_result(url, asin, reason="Not found"):
    return {
        "ASIN": asin or "N/A",
        "URL": url,
        "Title": reason,
        "Best Sellers Ranking": "Not found",
        "ratings": "Not found",
        "reviews": "Not found",
        "sales_price": "Not found",
        "MRP": "Not found",
        "buybox_winner": "Not found",
        "deal_tag": "Not found",
        "stock_status": "Not found"
    }


def detect_page_issue(page):
    current_url = (page.url or "").lower()
    title = ""
    visible_text = ""

    try:
        title = (page.title() or "").lower()
    except:
        pass

    try:
        visible_text = (page.locator("body").inner_text(timeout=2000) or "").lower()
    except:
        pass

    captcha_selectors = [
        "input#captchacharacters",
        "form[action*='validateCaptcha']",
        "img[alt*='captcha']"
    ]
    for sel in captcha_selectors:
        try:
            if page.locator(sel).count() > 0:
                return "captcha"
        except:
            pass

    if any(token in current_url for token in ["validatecaptcha", "/errors/captcha", "/ap/cvf"]):
        return "captcha"

    sign_in_selectors = [
        "form[name='signIn']",
        "#ap_email",
        "input[name='email']",
        "#ap_password"
    ]
    for sel in sign_in_selectors:
        try:
            if page.locator(sel).count() > 0:
                return "sign_in_required"
        except:
            pass

    if "/ap/signin" in current_url or "amazon sign in" in title:
        return "sign_in_required"

    not_found_markers = [
        "dogs of amazon",
        "sorry! we couldn't find that page",
        "looking for something?"
    ]
    if any(marker in visible_text for marker in not_found_markers):
        return "page_not_found"

    return None


def extract_price(page):
    price_selectors = [
        ".a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#corePrice_feature_div .a-offscreen",
        "#apex_desktop .a-offscreen",
        "span.a-price-whole",
        ".priceToPay .a-offscreen"
    ]

    for sel in price_selectors:
        try:
            locator = page.locator(sel).first
            if locator.count() == 0:
                continue
            text = (locator.text_content(timeout=3000) or "").strip()
            if not text:
                continue
            match = PRICE_PATTERN.search(text)
            if match:
                return match.group(1)
            if any(char.isdigit() for char in text):
                return text
        except:
            continue

    return "NOT FOUND"


def extract_mrp(page):
    mrp_pattern = re.compile(
        r"(?:M\.?\s*R\.?\s*P\.?|List Price)\s*:?\s*([₹$€£]\s?[\d,]+(?:\.\d{1,2})?)",
        re.IGNORECASE
    )

    labeled_mrp_selectors = [
        "#corePriceDisplay_desktop_feature_div",
        "#corePrice_feature_div",
        "#apex_desktop",
        "body"
    ]

    for sel in labeled_mrp_selectors:
        try:
            text = (page.locator(sel).first.inner_text(timeout=3000) or "").strip()
            if not text:
                continue
            match = mrp_pattern.search(" ".join(text.split()))
            if match:
                return match.group(1)
        except:
            continue

    mrp_selectors = [
        ".basisPrice .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .basisPrice .a-offscreen",
        "#corePrice_feature_div .basisPrice .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price.a-text-price .a-offscreen",
        "#corePrice_feature_div .a-price.a-text-price .a-offscreen",
        ".priceBlockStrikePriceString"
    ]

    for sel in mrp_selectors:
        try:
            locator = page.locator(sel)
            count = locator.count()
            for i in range(min(count, 5)):
                text = (locator.nth(i).text_content(timeout=3000) or "").strip()
                if not text:
                    continue
                lowered = text.lower()
                if "/" in lowered or "count" in lowered or "unit" in lowered:
                    continue
                match = PRICE_PATTERN.search(text)
                if match:
                    return match.group(1)
        except:
            continue

    return "Not found"


def extract_deal_tag(page):
    deal_selectors = [
        ".dealBadgeTextColor",
        "#dealBadge_feature_div",
        ".promoPriceBlockMessage",
        "[data-cy='dealBadge']",
        ".a-badge-label-inner"
    ]

    allowed_keywords = [
        "limited time deal",
        "mega deal",
        "deal of the day",
        "prime day deal",
        "ends in",
        "ends "
    ]

    blocked_patterns = [
        r"^-\d+%$",
        r"^save\s*[₹$€£]?\s*\d",
        r"^\d+%\s*off$"
    ]

    for sel in deal_selectors:
        try:
            locator = page.locator(sel)
            count = locator.count()
            for i in range(min(count, 5)):
                raw_text = (locator.nth(i).inner_text(timeout=2000) or "").strip()
                if not raw_text:
                    raw_text = (locator.nth(i).text_content(timeout=2000) or "").strip()
                if not raw_text:
                    continue

                normalized = " ".join(raw_text.split())
                lowered = normalized.lower()

                if any(re.fullmatch(pattern, lowered) for pattern in blocked_patterns):
                    continue

                if any(keyword in lowered for keyword in allowed_keywords):
                    return normalized
        except:
            continue

    return "Not found"


def extract_rating(page):
    rating_selectors = [
        "span[data-hook='rating-out-of-text']",
        "#averageCustomerReviews .a-icon-alt",
        "#acrPopover"
    ]

    for sel in rating_selectors:
        text = extract_text(page, [sel], timeout=2000)
        if not text:
            continue
        match = RATING_PATTERN.search(text)
        if match:
            return f"{match.group(1)} out of 5"

    visible_text = ""
    try:
        visible_text = page.locator("body").inner_text(timeout=2000) or ""
    except:
        pass

    if "no customer reviews" in visible_text.lower():
        return "0 out of 5"

    return "Not found"


def extract_review_count(page):
    review_selectors = [
        "#acrCustomerReviewText",
        "span[data-hook='total-review-count']",
        "#averageCustomerReviews"
    ]

    for sel in review_selectors:
        text = extract_text(page, [sel], timeout=2000)
        if not text:
            continue
        match = COUNT_PATTERN.search(text.replace("(", "").replace(")", ""))
        if match:
            return match.group(1)

    visible_text = ""
    try:
        visible_text = page.locator("body").inner_text(timeout=2000) or ""
    except:
        pass

    if "no customer reviews" in visible_text.lower():
        return "0"

    return "Not found"


def extract_stock_status(availability_text):
    normalized = " ".join((availability_text or "").split())
    lowered = normalized.lower()

    low_stock_match = LOW_STOCK_PATTERN.search(normalized)
    if low_stock_match:
        return low_stock_match.group(0)

    if any(keyword in lowered for keyword in ["currently unavailable", "temporarily out of stock", "out of stock"]):
        return "Currently unavailable"

    if "in stock" in lowered:
        return "In stock"

    return "Not found"


def extract_best_sellers_ranking(page):
    rank_selectors = [
        "tr:has(th:has-text('Best Sellers Rank')) td",
        "li:has-text('Best Sellers Rank')",
        "#prodDetails tr:has(th:has-text('Best Sellers Rank')) td"
    ]

    for sel in rank_selectors:
        rank_text = extract_text(page, [sel], timeout=2500)
        if not rank_text:
            continue

        normalized = " ".join(rank_text.split())
        matches = BEST_SELLERS_RANK_PATTERN.findall(normalized)
        cleaned_matches = []

        for match in matches:
            cleaned = re.sub(r"\s*\(See Top 100.*?\)", "", " ".join(match.split())).strip()
            if cleaned:
                cleaned_matches.append((match, cleaned))

        for original, cleaned in cleaned_matches[1:]:
            if "see top 100" not in original.lower():
                return cleaned

        if cleaned_matches:
            original, cleaned = cleaned_matches[0]
            if "see top 100" not in original.lower():
                return cleaned

    return "Not found"


def create_scrape_page(browser):
    page = browser.new_page(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="en-IN"
    )

    page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-IN', 'en']
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5]
    });
    """)

    return page

# ==========================
# 🆕 VARIANT EXTRACTION
# ==========================
def get_all_variants(page):
    try:
        elements = page.locator("[data-asin]")
        variant_asins = set()

        for i in range(elements.count()):
            asin = elements.nth(i).get_attribute("data-asin")
            if asin and len(asin) == 10:
                variant_asins.add(asin)

        return list(variant_asins)
    except:
        return []

# ==========================
# 🔁 SINGLE SCRAPE FUNCTION
# ==========================
def scrape_single(page, url):
    original_asin = extract_asin_from_url(url)
    if not original_asin:
        return build_not_found_result(url, None, "Invalid ASIN URL")

    try:
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")

        # ✅ Human-like wait
        page.wait_for_timeout(random.randint(800, 2000))

        issue = detect_page_issue(page)
        if issue == "captcha":
            return build_not_found_result(url, original_asin, "Captcha blocked")
        if issue == "sign_in_required":
            return build_not_found_result(url, original_asin, "Sign-in blocked")
        if issue == "page_not_found":
            return build_not_found_result(url, original_asin)

        detected_asin = get_detected_page_asin(page)
        if detected_asin and detected_asin != original_asin:
            return build_not_found_result(url, original_asin)

        current_url = page.url
        current_asin = extract_asin_from_url(current_url)
        if detected_asin is None and current_asin and current_asin != original_asin:
            return build_not_found_result(url, original_asin)

        # 👇 HUMAN SCROLL
        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, random.randint(500, 1200))
            time.sleep(random.uniform(0.3, 0.8))

        # TITLE
        title = extract_text(page, ["#productTitle", "#title", "h1.a-size-large"])
        if not title:
            try:
                title = page.title()
            except:
                title = "N/A"

        # ✅ FINAL ASIN VALIDATION
        final_page_asin = get_detected_page_asin(page)
        if final_page_asin and final_page_asin != original_asin:
            return build_not_found_result(url, original_asin)

        # PRICE
        price = extract_price(page)
        mrp = extract_mrp(page)
        best_sellers_ranking = extract_best_sellers_ranking(page)
        rating = extract_rating(page)
        reviews = extract_review_count(page)

        availability = ""
        try:
            availability = (page.locator("#availability").inner_text(timeout=3000) or "").strip()
        except:
            try:
                availability = (page.locator("#availability").text_content(timeout=3000) or "").strip()
            except:
                pass

        stock_status = extract_stock_status(availability)

        if stock_status == "Currently unavailable":
            price = "Not found"

        deal_tag = extract_deal_tag(page)

        # SELLER
        seller = extract_text(
            page,
            [
                "#sellerProfileTriggerId",
                "#merchant-info",
                "#buyboxTabularTruncate-1 .tabular-buybox-text",
                "#bylineInfo"
            ]
        ) or "N/A"

        return {
            "ASIN": original_asin,
            "URL": url,
            "Title": title,
            "Best Sellers Ranking": best_sellers_ranking,
            "ratings": rating,
            "reviews": reviews,
            "sales_price": price,
            "MRP": mrp,
            "buybox_winner": seller,
            "deal_tag": deal_tag,
            "stock_status": stock_status
        }

    except Exception as e:
        return {
            "ASIN": "N/A",
            "URL": url,
            "Title": "ERROR",
            "Best Sellers Ranking": "ERROR",
            "ratings": "ERROR",
            "reviews": "ERROR",
            "sales_price": "ERROR",
            "MRP": "ERROR",
            "buybox_winner": str(e),
            "deal_tag": "ERROR",
            "stock_status": "ERROR"
        }

# ==========================
# 🔁 MAIN SCRAPER
# ==========================
def scrape_amazon(urls, custom_sheet_name=None):
    all_data = []

    progress_bar = st.progress(0)
    status_text = st.empty()
    sheets_status = st.empty()

    total = len(urls)
    worksheet = None
    worksheet_title = None
    uploaded_rows = 0
    sheet_sync_error = None

    try:
        worksheet = get_target_worksheet(custom_sheet_name)
        worksheet_title = worksheet.title
        sheets_status.text(f"☁️ Auto-syncing to Google Sheets: {worksheet_title}")
    except Exception as e:
        sheet_sync_error = str(e)
        sheets_status.text(f"⚠️ Google Sheets sync unavailable: {e}")

    with sync_playwright() as p:
        # ✅ HEADLESS + STEALTH
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        pool_size = max(1, min(3, total))
        pages = [create_scrape_page(browser) for _ in range(pool_size)]

        for i, url in enumerate(urls):
            page = pages[i % len(pages)]

            status_text.text(f"⚡ Scraping {i+1}/{total}")

            data = scrape_single(page, url)
            all_data.append(data)

            if worksheet:
                try:
                    append_row_to_sheet(worksheet, data)
                    uploaded_rows += 1
                    sheets_status.text(f"☁️ Synced {uploaded_rows}/{total} rows to Google Sheets: {worksheet_title}")
                except Exception as e:
                    sheet_sync_error = str(e)
                    worksheet = None
                    sheets_status.text(f"⚠️ Google Sheets sync stopped after {uploaded_rows} rows: {e}")

            progress_bar.progress((i + 1) / total)

            if (i + 1) % 15 == 0 and i + 1 < total:
                old_pages = pages
                pages = [create_scrape_page(browser) for _ in range(pool_size)]
                for old_page in old_pages:
                    try:
                        old_page.close()
                    except:
                        pass

            time.sleep(random.uniform(0.6, 1.5))

        for page in pages:
            try:
                page.close()
            except:
                pass

        browser.close()

    st.session_state["sheet_sync_title"] = worksheet_title
    st.session_state["sheet_rows_uploaded"] = uploaded_rows
    st.session_state["sheet_sync_error"] = sheet_sync_error

    status_text.text("✅ Scraping Completed")

    if worksheet_title and uploaded_rows == total and not sheet_sync_error:
        sheets_status.text(f"☁️ Google Sheets updated: {uploaded_rows} rows synced to {worksheet_title}")
    elif worksheet_title and uploaded_rows > 0:
        sheets_status.text(f"⚠️ Google Sheets synced {uploaded_rows} rows to {worksheet_title} before stopping")
    elif sheet_sync_error:
        sheets_status.text(f"⚠️ Google Sheets sync unavailable: {sheet_sync_error}")

    return pd.DataFrame(all_data, columns=OUTPUT_COLUMNS)

# ==========================
# ▶️ RUN SCRAPER
# ==========================
if st.button("🚀 Run Scraper (Fast)"):

    urls = urls_list

    if not urls:
        st.warning("⚠️ Please enter at least one URL")

    else:
        df = scrape_amazon(urls, sheet_name_input)

        st.session_state["df_data"] = df

        st.success("✅ Scraping Completed")

        sheet_rows_uploaded = st.session_state.get("sheet_rows_uploaded", 0)
        sheet_sync_error = st.session_state.get("sheet_sync_error")
        sheet_sync_title = st.session_state.get("sheet_sync_title")

        if sheet_rows_uploaded and not sheet_sync_error:
            st.success(f"☁️ Auto-uploaded {sheet_rows_uploaded} rows to Google Sheets ({sheet_sync_title})")
        elif sheet_rows_uploaded and sheet_sync_error:
            st.warning(f"⚠️ Google Sheets synced {sheet_rows_uploaded} rows before stopping: {sheet_sync_error}")
        elif sheet_sync_error:
            st.warning(f"⚠️ Google Sheets auto-sync unavailable: {sheet_sync_error}")

        st.dataframe(df, use_container_width=True)

        st.download_button(
            "📥 Download CSV",
            df.to_csv(index=False),
            file_name="amazon_products.csv",
            mime="text/csv"
        )
