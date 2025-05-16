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
            print("Successfully connected to MySQL database")
            return True
        except mysql.connector.Error as err:
            print(f"Failed to connect to MySQL database: {err}")
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
            print("Tables created or already exist")
            return True
        except mysql.connector.Error as err:
            print(f"Error creating tables: {err}")
            return False

    def fetch_page(self, page_num=1):
        url = f"{self.base_url}?search=&submit=search&start={page_num}"
        try:
            print(f"Fetching URL: {url}")
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
        print(f"Found {len(job_entries)} job entries in HTML")

        job_listings = []

        for job_entry in job_entries:
            try:
                title_element = job_entry.find('h2', class_='heading')
                if not title_element or not title_element.find('a'):
                    continue

                title = title_element.find('a').text.strip()
                # Strip " at Company" from title, if present
                title = re.sub(r'\s+at\s+.+', '', title, flags=re.IGNORECASE)
                job_url = title_element.find('a')['href']

                company_div = job_entry.find('div', class_='attribute company')
                company = company_div.find('span', class_='value').text.strip() if company_div and company_div.find('span', class_='value') else "Unknown"

                if not company or company == "Unknown":
                    company_match = re.search(r'at\s+(.+)', title, re.IGNORECASE)
                    if company_match:
                        company = company_match.group(1).strip()

                location_div = job_entry.find('div', class_='attribute location')
                location = ""
                if location_div:
                    location_spans = location_div.find_all('span', class_='value')
                    if location_spans:
                        location = location_spans[0].text.strip()

                posted_date = None
                if location_div:
                    date_spans = location_div.find_all('span', class_='value')
                    for span in date_spans:
                        if 'data-value' in span.attrs:
                            posted_date_text = span.text.strip()
                            posted_date = self.parse_date(posted_date_text)
                            break

                description_div = job_entry.find('div', class_='summary')
                description = ""
                if description_div and description_div.find('p'):
                    description = description_div.find('p').text.strip()

                print(f"Extracted job: {title}")
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
        try:
            today = datetime.now().date()

            if "today" in date_text.lower():
                return today

            days_ago_match = re.search(r'(\d+) days? ago', date_text.lower())
            if days_ago_match:
                days = int(days_ago_match.group(1))
                return today - timedelta(days=days)

            date_pattern = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})', date_text)
            if date_pattern:
                day = int(date_pattern.group(1))
                month = date_pattern.group(2)
                year = int(date_pattern.group(3))

                month_dict = {
                    'January': 1, 'February': 2, 'March': 3, 'April': 4,
                    'May': 5, 'June': 6, 'July': 7, 'August': 8,
                    'September': 9, 'October': 10, 'November': 11, 'December': 12
                }

                month_num = month_dict.get(month)
                if month_num:
                    return date(year, month_num, day)

            try:
                return datetime.strptime(date_text, "%b %d, %Y").date()
            except ValueError:
                pass

            try:
                return datetime.strptime(date_text, "%d-%b-%Y").date()
            except ValueError:
                pass

            print(f"Could not parse date: '{date_text}'")
            return None

        except Exception as e:
            print(f"Error parsing date '{date_text}': {e}")
            return None

    def save_job_to_db(self, job):
        try:
            self.cursor.execute("SELECT id FROM jobs WHERE job_url = %s", (job['job_url'],))
            existing_job = self.cursor.fetchone()

            if existing_job:
                print(f"Job already exists: {job['title']}")
                return False

            query = """
                INSERT INTO jobs (title, company, location, posted_date, job_url, description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.cursor.execute(query, (
                job['title'], job['company'], job['location'],
                job['posted_date'], job['job_url'], job['description']
            ))
            self.conn.commit()
            print(f"Saved job: {job['title']}")
            return True

        except mysql.connector.Error as err:
            print(f"Error saving job to database: {err}")
            return False

    def scrape_jobs(self):
        """Scrape jobs posted only today, across all available pages."""
        if not self.connect_db():
            return False

        if not self.create_tables():
            return False

        total_jobs = 0
        page_num = 1
        today = datetime.now().date()
        stop_scraping = False

        while not stop_scraping:
            print(f"Scraping page {page_num}...")
            html_content = self.fetch_page(page_num)

            if not html_content:
                print(f"Failed to fetch page {page_num}, stopping.")
                break

            jobs = self.parse_job_listings(html_content)

            if not jobs:
                print(f"No jobs found on page {page_num}.")
                break

            for job in jobs:
                # Stop if we hit a job not from today
                if job['posted_date'] != today:
                    print(f"Encountered job not from today: {job['title']} - {job['posted_date']}")
                    stop_scraping = True
                    break

                if self.save_job_to_db(job):
                    total_jobs += 1

            if not stop_scraping:
                page_num += 1
                delay = random.uniform(2, 5)
                print(f"Waiting {delay:.2f} seconds before next request...")
                time.sleep(delay)

        print(f"Scraping complete. Saved {total_jobs} jobs from today.")

        # Close DB connection
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

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
