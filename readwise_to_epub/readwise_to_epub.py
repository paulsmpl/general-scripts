import os
from urllib.parse import urlparse
import requests
import subprocess
from ebooklib import epub
from bs4 import BeautifulSoup
from ftplib import FTP
from datetime import datetime, timedelta, timezone
from dateutil import parser


# === CONFIGURATION ===
READWISE_TOKEN = os.environ["EPUB_READWISE_TOKEN"]
FTP_HOST = "reseau.pbconseil.ovh"
FTP_USER = "readwise@reseau.pbconseil.ovh"
FTP_PASS = os.environ["EPUB_FTP_PASS"]
FTP_DIR = ""
APP_KEY = "3cg7aby9"
KV_LAST_UPDATED_AT_KEY = "lastUpdatedAt"
CATEGORIES = ["pdf", "article", "email", "rss", "twitter"]

# === NEW: GOOGLE APPS SCRIPT CONFIG ===
GAS_ENDPOINT = os.environ["GAS_ENDPOINT_EPUBS_PROCESSED_TRACKER"]
PROCESSED_SHEET_NAME = "_Processed_Articles"
# === NEW: GOOGLE APPS SCRIPT ENDPOINTS ===
def is_processed(article_id):
    """Checks if an article ID is in the processed sheet via the GAS endpoint."""
    try:
        url = f"{GAS_ENDPOINT}?sheet={PROCESSED_SHEET_NAME}&value={article_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('isPresent', False)
    except requests.exceptions.RequestException as e:
        print(f"\u26A0\uFE0F Error checking processed status for {article_id}: {e}")
        return False

def mark_as_processed(article_id):
    """Stores an article ID in the processed sheet via the GAS endpoint."""
    try:
        url = f"{GAS_ENDPOINT}?sheet={PROCESSED_SHEET_NAME}"
        headers = {"Content-Type": "application/json"}
        data = {"value": article_id}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"\U0001F511 Marked article ID {article_id} as processed.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"\u274C Failed to mark article ID {article_id} as processed: {e}")
        return False

# === KEYVALUE API ===
# The functions below (`get_last_processed_timestamp` and `update_last_processed_timestamp`)
# are kept for tracking the timestamp of the last fetch, but the processed articles
# are now managed by the new GAS functions.
def get_last_processed_timestamp():
    url = f"https://keyvalue.immanuel.co/api/KeyVal/GetValue/{APP_KEY}/{KV_LAST_UPDATED_AT_KEY}"
    response = requests.get(url)
    if response.status_code == 200 and response.text != 'null':
        value = response.text.strip().strip('"')
        return int(value)
    return None

def update_last_processed_timestamp(epoch_seconds):
    url = f"https://keyvalue.immanuel.co/api/KeyVal/UpdateValue/{APP_KEY}/{KV_LAST_UPDATED_AT_KEY}/{epoch_seconds}"
    response = requests.post(url)
    if response.status_code == 200:
        print(f"\U0001F511 Updated last processed timestamp to {epoch_seconds}")
    else:
        print(f"\u26A0\uFE0F Failed to update timestamp to {epoch_seconds}")

# === FETCH ITEMS ===
def fetch_items_by_category(category):
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    iso_timestamp = seven_days_ago.isoformat(timespec='seconds')
    url = "https://readwise.io/api/v3/list/"
    headers = {"Authorization": f"Token {READWISE_TOKEN}"}
    params = {
        "category": category,
        "withHtmlContent": "true",
        "updatedAfter": iso_timestamp,
        "page_size": 100
    }
    print(f"\U0001F50D Fetching {category} updated since {iso_timestamp}...")
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    results = response.json().get("results", [])
    print(f"\U0001F4C4 {len(results)} new {category} item(s) found.")
    return results

# === EPUB CREATION ===
def create_epub(article, category):
    title = article.get("title") or "Untitled"
    url = article.get("url", "")
    content = article.get("html_content") or article.get("content") or ""

    if not content.strip():
        print(f"\u26A0\uFE0F Skipping EPUB: no content for '{title}'")
        return None

    print(f"\n\U0001F4DA Creating EPUB for [{category}] '{title}'")

    cleaned = BeautifulSoup(content, "html.parser").prettify()
    header = f"<h1>{title}</h1>\n"
    header += f"<p><strong>Category:</strong> {category}</p>\n"
    header += f"<p><strong>URL:</strong> <a href='{url}'>{url}</a></p>\n"
    header += f"<p><strong>Imported:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>\n"
    full_content = header + "<hr/>\n" + cleaned

    author = article.get("author") or "Readwise Reader"

    book = epub.EpubBook()
    book.set_identifier(f"id-{article['id']}")
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    chapter = epub.EpubHtml(title=title, file_name="chap.xhtml", lang="en")
    chapter.content = full_content
    book.add_item(chapter)
    book.spine = ['nav', chapter]
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    safe_author = "".join(c if c.isalnum() or c in " _-" else "_" for c in author).strip()
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title).strip()
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base_filename = f"{safe_title} - {safe_author} - {timestamp}"
    epub_filename = os.path.join(base_filename + ".epub")

    epub.write_epub(epub_filename, book)
    print(f"\u2705 EPUB created: {epub_filename}")

    try:
        subprocess.run(["kepubify", epub_filename], check=True)
        print(f"\U0001F4D8 Converted to Kepub with kepubify.")

        converted_name = os.path.join(base_filename + "_converted.kepub.epub")
        if os.path.exists(converted_name):
            print(f"\u2705 Kepub file ready: {converted_name}")
            return converted_name
        else:
            print(f"\u26A0\uFE0F Converted file not found: {converted_name}")
            return epub_filename
    except subprocess.CalledProcessError as e:
        print(f"\u274C Kepubify failed: {e}")
        return epub_filename

# === FTP UPLOAD ===
def upload_ftp(local_file):
    print(f"\U0001F680 Uploading {local_file} to FTP...")
    with FTP(FTP_HOST) as ftp:
        ftp.login(FTP_USER, FTP_PASS)
        with open(local_file, "rb") as f:
            ftp.storbinary(f"STOR " + os.path.basename(local_file), f)
    print(f"\u2705 Uploaded: {local_file}")

# === MAIN PIPELINE ===
def main():
    try:
        last_processed_ts = get_last_processed_timestamp()
        print(f"\U0001F511 Last processed timestamp: {last_processed_ts}")

        all_new_items = []
        
        for category in CATEGORIES:
            items = fetch_items_by_category(category)
            items_sorted = sorted(items, key=lambda x: x['updated_at'])
            
            for item in items_sorted:
                item_updated_at = parser.isoparse(item['updated_at'])
                item_epoch = int(item_updated_at.timestamp())
                
                # Check if the article is more recent and not already processed
                if (not last_processed_ts or item_epoch > last_processed_ts) and not is_processed(item['id']):
                    all_new_items.append((item, category))
        
        if all_new_items:
            print(f"\U0001F4C4 Processing {len(all_new_items)} new item(s) found across all categories.")
            
            latest_processed_ts = last_processed_ts
            for item, category in all_new_items:
                item_updated_at = parser.isoparse(item['updated_at'])
                item_epoch = int(item_updated_at.timestamp())
                
                epub_file = create_epub(item, category)
                if epub_file:
                    upload_ftp(epub_file)
                    mark_as_processed(item['id']) # Mark as processed after successful upload
                    #os.remove(epub_file)
                    #print(f"\U0001F9F9 Deleted local file: {epub_file}")
                
                latest_processed_ts = max(latest_processed_ts, item_epoch)
            
            update_last_processed_timestamp(latest_processed_ts)
            print("\n\U0001F389 All categories processed.")
        else:
            print("\n\u2705 No new items to process.")
            
    except Exception as e:
        print(f"\u274C Error: {e}")
        
# === RESET TIMESTAMP ===
def reset_last_processed_timestamp(minutes_back=10):
    new_timestamp = int((datetime.utcnow() - timedelta(minutes=minutes_back)).timestamp())
    url = f"https://keyvalue.immanuel.co/api/KeyVal/UpdateValue/{APP_KEY}/{KV_LAST_UPDATED_AT_KEY}/{new_timestamp}"
    response = requests.post(url)
    if response.status_code == 200:
        print(f"\U0001F501 Reset last processed timestamp to {new_timestamp} ({minutes_back} minutes back)")
    else:
        print(f"\u26A0\uFE0F Failed to reset timestamp to {new_timestamp}")

if __name__ == "__main__":
    main()