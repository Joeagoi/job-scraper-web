from flask import Flask, render_template, request
from .scraper import JobScraper
from dotenv import load_dotenv
import os
import mysql.connector

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
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME')
    }

    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor(dictionary=True)  # Fetch rows as dictionaries

    cursor.execute("SELECT * FROM jobs ORDER BY posted_date DESC LIMIT 100")
    jobs = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("jobs.html", jobs=jobs)
