import logging
import os
import threading
import time
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone

import psycopg2
import requests
from fastapi import FastAPI, HTTPException, Query
from psycopg2.extras import RealDictCursor

SITES = [
    site.strip()
    for site in os.getenv("MONITOR_SITES", "https://google.com,https://github.com").split(",")
    if site.strip()
]
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "uptime")
DB_USER = os.getenv("DB_USER", "uptime_agent")
DB_PASS = os.getenv("DB_PASS")
CHECK_INTERVAL = 60
HEALTH_TIMEOUT = 300
STOP_EVENT = threading.Event()
last_loop_at = time.monotonic()


def connect_db():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=5,
    )


def init_db():
    for attempt in range(1, 13):
        try:
            with closing(connect_db()) as conn:
                with conn, conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS http_logs (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMPTZ NOT NULL,
                            site VARCHAR(255) NOT NULL,
                            status VARCHAR(50) NOT NULL,
                            status_code INT NOT NULL,
                            latency_ms INT NOT NULL
                        )
                    """)
            logging.info("Database initialized successfully.")
            return True
        except psycopg2.Error as error:
            logging.warning("Database initialization failed (%s/12): %s", attempt, error)
            if attempt == 12:
                raise SystemExit("Database initialization failed after 12 attempts.") from error
            if STOP_EVENT.wait(5):
                return False
    return False


def check_site(url):
    start_time = time.perf_counter()
    try:
        response = requests.get(url, timeout=5)
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        status = "UP" if response.status_code < 400 else "DOWN"
        return status, response.status_code, latency_ms
    except requests.exceptions.RequestException:
        return "DOWN", 0, 0


def write_to_db(timestamp, site, status, status_code, latency_ms):
    try:
        with closing(connect_db()) as conn:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO http_logs "
                    "(timestamp, site, status, status_code, latency_ms) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (timestamp, site, status, status_code, latency_ms),
                )
        return True
    except psycopg2.Error as error:
        logging.error("Failed to write to database: %s", error)
        return False


def check_loop():
    global last_loop_at
    while not STOP_EVENT.is_set():
        for site in SITES:
            if STOP_EVENT.is_set():
                break
            status, status_code, latency = check_site(site)
            logging.info("%s | %s | Code: %s | Latency: %sms", site, status, status_code, latency)
            write_to_db(datetime.now(timezone.utc), site, status, status_code, latency)
        last_loop_at = time.monotonic()
        STOP_EVENT.wait(CHECK_INTERVAL)


def read_from_db(query, params=()):
    try:
        with closing(connect_db()) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchall()
    except psycopg2.Error as error:
        logging.error("Failed to read from database: %s", error)
        raise HTTPException(status_code=503, detail="Database is unavailable") from error


@asynccontextmanager
async def lifespan(app):
    global last_loop_at
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not DB_PASS:
        raise SystemExit("DB_PASS must be set.")
    if not SITES:
        raise SystemExit("MONITOR_SITES must contain at least one URL.")

    logging.info("Starting uptime agent for: %s", SITES)
    init_db()
    STOP_EVENT.clear()
    last_loop_at = time.monotonic()
    worker = threading.Thread(target=check_loop, daemon=True)
    worker.start()
    yield
    STOP_EVENT.set()
    worker.join(timeout=10)
    logging.info("Uptime agent stopped.")


app = FastAPI(title="Uptime Monitor", lifespan=lifespan)


@app.get("/health")
def health():
    if time.monotonic() - last_loop_at > HEALTH_TIMEOUT:
        raise HTTPException(status_code=503, detail="Check loop is stalled")
    return {"status": "ok"}


@app.get("/sites")
def sites_status():
    return read_from_db("""
        SELECT DISTINCT ON (site) site, status, status_code, latency_ms, timestamp
        FROM http_logs
        ORDER BY site, timestamp DESC
    """)


@app.get("/sites/history")
def site_history(site: str, limit: int = Query(100, ge=1, le=1000)):
    if site not in SITES:
        raise HTTPException(status_code=404, detail="Site is not monitored")
    return read_from_db(
        "SELECT site, status, status_code, latency_ms, timestamp "
        "FROM http_logs WHERE site = %s ORDER BY timestamp DESC LIMIT %s",
        (site, limit),
    )
