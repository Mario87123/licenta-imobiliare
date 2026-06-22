import time
from .database import get_connection


def update_job(job_id: int, status: str, message: str = None, finished: bool = False):
    conn = get_connection()
    cursor = conn.cursor()

    if finished:
        cursor.execute("""
            UPDATE crawl_jobs
            SET status = ?, message = ?, finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, message, job_id))
    else:
        cursor.execute("""
            UPDATE crawl_jobs
            SET status = ?, message = ?
            WHERE id = ?
        """, (status, message, job_id))

    conn.commit()
    conn.close()


def insert_demo_ads():
    ads = [
        {
            "title": "Apartament 2 camere Lipovei",
            "price_eur": 92000,
            "surface_mp": 52,
            "rooms": 2,
            "neighborhood": "Lipovei",
            "floor": 3,
            "total_floors": 10,
            "year_built": 2014,
            "url": "https://exemplu.ro/anunt1",
            "source": "demo"
        },
        {
            "title": "Apartament 3 camere Soarelui",
            "price_eur": 118000,
            "surface_mp": 67,
            "rooms": 3,
            "neighborhood": "Soarelui",
            "floor": 2,
            "total_floors": 4,
            "year_built": 2018,
            "url": "https://exemplu.ro/anunt2",
            "source": "demo"
        },
        {
            "title": "Apartament 2 camere Girocului",
            "price_eur": 79000,
            "surface_mp": 46,
            "rooms": 2,
            "neighborhood": "Girocului",
            "floor": 1,
            "total_floors": 4,
            "year_built": 2010,
            "url": "https://exemplu.ro/anunt3",
            "source": "demo"
        }
    ]

    conn = get_connection()
    cursor = conn.cursor()

    for ad in ads:
        cursor.execute("""
            INSERT OR IGNORE INTO ads (
                title, price_eur, surface_mp, rooms, neighborhood,
                floor, total_floors, year_built, url, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ad["title"],
            ad["price_eur"],
            ad["surface_mp"],
            ad["rooms"],
            ad["neighborhood"],
            ad["floor"],
            ad["total_floors"],
            ad["year_built"],
            ad["url"],
            ad["source"]
        ))

    conn.commit()
    conn.close()


def run_demo_crawler(job_id: int):
    try:
        update_job(job_id, "running", "Crawlerul rulează")
        time.sleep(3)

        insert_demo_ads()

        update_job(job_id, "done", "Crawlerul a terminat", finished=True)
    except Exception as e:
        update_job(job_id, "failed", f"Eroare: {str(e)}", finished=True)