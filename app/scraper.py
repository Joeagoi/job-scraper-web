import requests
from bs4 import BeautifulSoup
import mysql.connector
from datetime import datetime, timedelta, date
import time
import random
import re
from dotenv import load_dotenv
import os

load_dotenv()

class JobScraper:
    def __init__(self, db_config):
        self.db_config = db_config
        self.base_url = "https://www.alljobspo.com/kenya-jobs/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://www.alljobspo.com/',
            'Connection': 'keep-alive',
        }
        self.conn = None
        self.cursor = None

    def connect_db(self):
        try:
            self.conn = mysql.connector.connect(**self.db_config)
            self.cursor = self.conn.cursor()
            print("Connected to MySQL.")
            return True
        except mysql.connector.Error as err:
            print(f"Failed to connect to MySQL: {err}")
            return False

    def create_tables(self):
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    company VARCHAR(255),
                    location VARCHAR(255),
                    posted_date DATE,
                    job_url VARCHAR(512),
                    description TEXT,
                    scraped_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_url)
                )
            ''')
            print("Table ready.")
            return True
        except mysql.connector.Error as err:
            print(f"Error creating tables: {err}")
            return False

    def fetch_page(self, page_num=1):
        url = f"{self.base_url}?search=&submit=search&start={page_num}"
        try:
            print(f"Fetching page: {url}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching page {page_num}: {e}")
            return None

    def parse_job_listings(self, html_content):
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, 'html.parser')
        job_entries = soup.find_all('article', class_='job')
        print(f"Found {len(job_entries)} job entries.")

        job_listings = []

        for job_entry in job_entries:
            try:
                title_element = job_entry.find('h2', class_='heading')
                if not title_element or not title_element.find('a'):
                    continue

                full_title = title_element.find('a').text.strip()
                job_url = title_element.find('a')['href']

                # Extract company from full title if present
                company_match = re.search(r'\s+at\s+(.+)', full_title, re.IGNORECASE)
                company = company_match.group(1).strip() if company_match else "Unknown"

                # Clean job title by removing 'at ...'
                title = re.sub(r'\s+at\s+.+', '', full_title, flags=re.IGNORECASE)

                location = ""
                location_divs = job_entry.find_all('div', class_='attribute location')
                if location_divs:
                    for div in location_divs:
                        spans = div.find_all('span', class_='value')
                        if spans:
                            location_candidate = spans[0].text.strip()
                            if location_candidate and "kenya" in location_candidate.lower():
                                location = location_candidate
                                break

                # 🔍 Extract posted_date from any value span with date-like text
                posted_date = None
                for loc_div in location_divs:
                    span_values = loc_div.find_all('span', class_='value')
                    for span in span_values:
                        text = span.get_text(strip=True)
                        if any(keyword in text.lower() for keyword in ["today", "yesterday", "ago", "may", "june", "july", "april", "march"]):
                            print(f"📅 Raw date text: '{text}'")
                            posted_date = self.parse_date(text)
                            if posted_date:
                                break
                    if posted_date:
                        break

                description_div = job_entry.find('div', class_='summary')
                description = ""
                if description_div and description_div.find('p'):
                    description = description_div.find('p').text.strip()

                print(f"Parsed job: {title} | {posted_date}")
                job_listings.append({
                    'title': title,
                    'company': company,
                    'location': location,
                    'posted_date': posted_date,
                    'job_url': job_url,
                    'description': description
                })

            except Exception as e:
                print(f"Error parsing job entry: {e}")
                continue

        return job_listings

    def parse_date(self, date_text):
        today = datetime.now().date()
        try:
            if "today" in date_text.lower():
                return today

            days_ago_match = re.search(r'(\d+)\s+days?\s+ago', date_text.lower())
            if days_ago_match:
                days = int(days_ago_match.group(1))
                return today - timedelta(days=days)

            # Normalize ordinal suffixes (1st, 2nd, etc.)
            date_text_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_text, flags=re.IGNORECASE)
            # Remove weekday names
            date_text_clean = re.sub(r'(today\s*)?\w+day,?\s*', '', date_text_clean, flags=re.IGNORECASE).strip()

            for fmt in ["%d %B %Y", "%d %b %Y"]:
                try:
                    return datetime.strptime(date_text_clean, fmt).date()
                except ValueError:
                    continue

            print(f"❓ Unrecognized date format: '{date_text}' cleaned to '{date_text_clean}'")
            return None

        except Exception as e:
            print(f"❌ Date parsing error: {e}")
            return None

    def save_job_to_db(self, job):
        try:
            self.cursor.execute("SELECT id FROM jobs WHERE job_url = %s", (job['job_url'],))
            if self.cursor.fetchone():
                print(f"⏩ Already exists: {job['title']}")
                return False

            self.cursor.execute("""
                INSERT INTO jobs (title, company, location, posted_date, job_url, description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                job['title'], job['company'], job['location'],
                job['posted_date'], job['job_url'], job['description']
            ))
            self.conn.commit()
            print(f"✅ Saved: {job['title']}")
            return True
        except mysql.connector.Error as err:
            print(f"❌ DB insert error: {err}")
            return False

    def scrape_jobs(self):
        if not self.connect_db():
            return False
        if not self.create_tables():
            return False

        total_jobs = 0
        page_num = 1
        today = datetime.now().date()
        stop = False

        while not stop:
            html = self.fetch_page(page_num)
            if not html:
                break

            jobs = self.parse_job_listings(html)
            if not jobs:
                break

            for job in jobs:
                if job['posted_date'] != today:
                    print(f"⏭ Skipping non-today job: {job['posted_date']}")
                    stop = True
                    break
                if self.save_job_to_db(job):
                    total_jobs += 1

            if not stop:
                page_num += 1
                delay = random.uniform(2, 5)
                print(f"⏳ Waiting {delay:.2f}s...")
                time.sleep(delay)

        print(f"✅ Scraping complete. Total jobs saved: {total_jobs}")

        if self.cursor: self.cursor.close()
        if self.conn: self.conn.close()
        return total_jobs


def main():
    db_config = {
        'host': os.getenv("DB_HOST"),
        'user': os.getenv("DB_USER"),
        'password': os.getenv("DB_PASSWORD"),
        'database': os.getenv("DB_NAME")
    }

    scraper = JobScraper(db_config)
    scraper.scrape_jobs()


if __name__ == "__main__":
    main()
