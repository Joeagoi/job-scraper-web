from flask import Flask, render_template, request
from .scraper import JobScraper
from dotenv import load_dotenv
import os
import mysql.connector
import math

# Load environment variables
load_dotenv()

app = Flask(__name__)

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/scrape')
def scrape():
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME')
    }

    scraper = JobScraper(db_config)
    new_jobs = scraper.scrape_jobs()
    return f"Scraping complete. Saved {new_jobs} new jobs."

@app.route('/jobs')
def list_jobs():
    # Get search query and page number from query string
    search_query = request.args.get('q', '').strip()
    page = request.args.get('page', default=1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME')
    }

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)

    # Base WHERE clause: posted_date = CURDATE()
    where_clauses = ["posted_date = CURDATE()"]
    params = []

    # If search query exists, add filtering on title or company
    if search_query:
        where_clauses.append("(title LIKE %s OR company LIKE %s)")
        like_pattern = f"%{search_query}%"
        params.extend([like_pattern, like_pattern])

    where_statement = " AND ".join(where_clauses)

    # Count total matching jobs for pagination
    count_query = f"SELECT COUNT(*) AS total FROM jobs WHERE {where_statement}"
    cursor.execute(count_query, params)
    total_jobs = cursor.fetchone()['total']
    total_pages = math.ceil(total_jobs / per_page) if total_jobs > 0 else 1

    # Fetch jobs for the current page with filtering
    select_query = f"""
        SELECT * FROM jobs 
        WHERE {where_statement}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    """
    params.extend([per_page, offset])
    cursor.execute(select_query, params)
    jobs = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("jobs.html", jobs=jobs, page=page, total_pages=total_pages, search_query=search_query)
