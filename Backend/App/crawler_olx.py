import re
import time
import random
import json
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

from .database import get_connection
from .crawler_job_utils import (
    update_job,
    increment_job_field,
    is_cancel_requested,
    resolve_crawl_limits,
    should_stop_early,
)
from .location_resolver import resolve_location, normalize_text
from .duplicate_detector import (
    find_existing_duplicate_for_ad,
    save_rejected_duplicate_ad,
)

BASE_URL = "https://www.olx.ro"
START_URL = "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-vanzare/timisoara/"


def parse_price(text: str):
    if not text:
        return None

    normalized_text = (
        text.replace("\xa0", " ")
        .replace("€", " eur ")
        .replace("â‚¬", " eur ")
        .replace("EURO", " eur ")
        .replace("Euro", " eur ")
    )

    patterns = [
        r"(\d[\d\s\.,]*)\s*(?:eur|euro)",
        r"(?:eur|euro)\s*(\d[\d\s\.,]*)",
        r"pret(?:ul)?\s*[:\-]?\s*(\d[\d\s\.,]*)",
        r"price\s*[:\-]?\s*(\d[\d\s\.,]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized_text, re.IGNORECASE)
        if not match:
            continue

        raw_value = match.group(1)
        digits_only = re.sub(r"[^\d]", "", raw_value)

        if not digits_only:
            continue

        try:
            price = int(digits_only)
        except ValueError:
            continue

        if 10000 <= price <= 1000000:
            return price

    return None



def parse_surface(text: str, title: str = ""):
    if not text and not title:
        return None

    search_text = (text or "")
    title_text = (title or "")

    patterns = [
        r"Suprafata utila:\s*(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)",
        r"Suprafață utilă:\s*(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)",
        r"suprafata utila:\s*(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)",
        r"suprafață utilă:\s*(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)",
    ]

    for pattern in patterns:
        m = re.search(pattern, search_text, re.IGNORECASE)
        if m:
            value = float(m.group(1).replace(",", "."))
            if 10 <= value <= 500:
                return value

    title_patterns = [
        r"(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)",
    ]

    for pattern in title_patterns:
        m = re.search(pattern, title_text, re.IGNORECASE)
        if m:
            value = float(m.group(1).replace(",", "."))
            if 10 <= value <= 500:
                return value

    lines = [line.strip() for line in search_text.splitlines() if line.strip()]

    for line in lines:
        if any(keyword in line.lower() for keyword in ["suprafata", "suprafață", "mp", "m2", "m²"]):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m²|mp|m2)", line, re.IGNORECASE)
            if m:
                value = float(m.group(1).replace(",", "."))
                if 10 <= value <= 500:
                    return value

    return None


def parse_rooms(text: str):
    if not text:
        return None

    patterns = [
        r"(\d+)\s*cam(?:era|ere)?",
        r"apartament\s+(\d+)\s*camera",
        r"apartament\s+(\d+)\s*camere",
    ]
    lowered = text.lower()
    for pattern in patterns:
        m = re.search(pattern, lowered, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None

def parse_total_floors(text: str):
    if not text:
        return None

    patterns = [
        r"Etaj:\s*\d+\s*din\s*(\d+)",
        r"Etaj:\s*parter\s*din\s*(\d+)",
        r"situat(?:ă)?\s+la\s+etaj(?:ul)?\s+\d+\s+din\s+(\d+)",
        r"etaj(?:ul)?\s+\d+\s+din\s+(\d+)",
        r"etaj(?:ul)?\s+\d+\s*/\s*(\d+)",
        r"parter\s+din\s+(\d+)",
        r"p\+(\d+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return int(m.group(1))

    return None

def parse_floor(text: str):
    if not text:
        return None
    m = re.search(r"Etaj:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not m:
        return None
    value = m.group(1).strip()

    if "Parter" in value:
        return 0
    
    if "Demisol" in value:
        return -1
    
    num = re.search(r"\d+", value)
    return int(num.group()) if num else None

def parse_year_built(text: str):
    if not text:
        return None

    m = re.search(r"An constructie:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not m:
        return None

    value = m.group(1).strip()

    year = re.search(r"(19\d{2}|20\d{2})", value)
    if year:
        return int(year.group(1))

    if "Dupa 2000" in value or "După 2000" in value:
        return 2000

    return None

def parse_partitioning(text: str):
    if not text:
        return None

    m = re.search(r"Compartimentare:\s*([^\n\r]+)", text, re.IGNORECASE)
    if not m:
        return None

    return m.group(1).strip()


def extract_listing_links(page):
    hrefs = page.locator("a").evaluate_all("""
        els => els
            .map(e => e.href)
            .filter(Boolean)
    """)

    links = []
    for href in hrefs:
        if not href:
            continue
        if "olx.ro" not in href:
            continue
        if "/d/oferta/" in href or "/oferta/" in href:
            links.append(href.split("?")[0])

    # deduplicare păstrând ordinea
    unique = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return unique

def safe_locator_text(page, selector: str):
    try:
        locator = page.locator(selector)
        if locator.count() > 0:
            text = locator.first.inner_text().strip()
            return text or None
    except Exception:
        return None
    return None


def safe_locator_attr(page, selector: str, attr: str):
    try:
        locator = page.locator(selector)
        if locator.count() > 0:
            value = locator.first.get_attribute(attr)
            if value:
                value = value.strip()
                return value or None
    except Exception:
        return None
    return None


def clean_title_candidate(value: str):
    if not value:
        return None

    value = value.strip()
    value = re.sub(r"\s*\|\s*OLX(?:\.ro)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*-\s*OLX(?:\.ro)?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s{2,}", " ", value).strip()

    if not value:
        return None

    bad_values = {
        "olx",
        "olx.ro",
        "anunt",
        "anunț",
    }

    if value.lower() in bad_values:
        return None

    return value


def extract_json_ld_objects(page):
    objects = []

    try:
        scripts = page.locator("script[type='application/ld+json']")
        count = scripts.count()

        for i in range(count):
            raw = scripts.nth(i).inner_text().strip()
            if not raw:
                continue

            try:
                parsed = json.loads(raw)
            except Exception:
                continue

            candidates = []

            if isinstance(parsed, dict):
                candidates.append(parsed)

                graph = parsed.get("@graph")
                if isinstance(graph, list):
                    candidates.extend(item for item in graph if isinstance(item, dict))

            elif isinstance(parsed, list):
                candidates.extend(item for item in parsed if isinstance(item, dict))

            for item in candidates:
                objects.append(item)

    except Exception:
        return []

    return objects


def extract_title_from_json_ld(objects):
    for obj in objects:
        for key in ("name", "headline"):
            value = obj.get(key)
            if isinstance(value, str):
                cleaned = clean_title_candidate(value)
                if cleaned and len(cleaned) >= 8:
                    return cleaned
    return None


def parse_price_value(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        value = int(value)
        if 10000 <= value <= 1000000:
            return value
        return None

    if isinstance(value, str):
        return parse_price(value)

    return None


def extract_price_from_json_ld(objects):
    for obj in objects:
        direct_price = parse_price_value(obj.get("price"))
        if direct_price:
            return direct_price

        offers = obj.get("offers")
        if isinstance(offers, dict):
            for key in ("price", "lowPrice", "highPrice"):
                candidate = parse_price_value(offers.get(key))
                if candidate:
                    return candidate

            price_spec = offers.get("priceSpecification")
            if isinstance(price_spec, dict):
                for key in ("price", "minPrice", "maxPrice"):
                    candidate = parse_price_value(price_spec.get(key))
                    if candidate:
                        return candidate

        if isinstance(offers, list):
            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                for key in ("price", "lowPrice", "highPrice"):
                    candidate = parse_price_value(offer.get(key))
                    if candidate:
                        return candidate

    return None


def extract_title_from_text_fallback(text: str):
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    bad_starts = [
        "Pagina principal",
        "Navigheaza",
        "Navighează",
        "Chat",
        "Notificari",
        "Notificări",
        "Contul tau",
        "Contul tău",
        "Adauga anunt nou",
        "Adaugă anunț nou",
        "Cautare",
        "Căutare",
        "Inapoi",
        "Înapoi",
        "Reactualizat la",
    ]

    for i, line in enumerate(lines):
        if parse_price(line):
            if i > 0:
                previous_line = clean_title_candidate(lines[i - 1])
                if previous_line and not any(previous_line.startswith(x) for x in bad_starts):
                    return previous_line

    return None


def extract_title(detail_page, text: str, json_ld_objects):
    candidates = [
        safe_locator_text(detail_page, "h1"),
        safe_locator_attr(detail_page, "meta[property='og:title']", "content"),
        safe_locator_attr(detail_page, "meta[name='twitter:title']", "content"),
        safe_locator_attr(detail_page, "meta[name='title']", "content"),
        extract_title_from_json_ld(json_ld_objects),
    ]

    try:
        page_title = detail_page.title()
        candidates.append(page_title)
    except Exception:
        pass

    candidates.append(extract_title_from_text_fallback(text))

    for candidate in candidates:
        cleaned = clean_title_candidate(candidate)
        if cleaned and len(cleaned) >= 8:
            return cleaned

    return None

def is_blocked_page(text: str):
    if not text:
        return False

    preview = normalize_text(text[:1200])

    blocked_markers = [
        "403",
        "403 error",
        "access denied",
        "forbidden",
        "pagina blocata",
        "pagina blocată",
        "blocked",
        "temporarily unavailable",
    ]

    return any(marker in preview for marker in blocked_markers)


def load_detail_page_with_retry(detail_page, ad_url, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            detail_page.goto(ad_url, timeout=18000, wait_until="domcontentloaded")
            detail_page.wait_for_timeout(random.randint(900, 1400))

            text = detail_page.locator("body").inner_text()

            if is_blocked_page(text):
                raise RuntimeError("blocked_page")

            return text, False

        except Exception as exc:
            is_blocked = "blocked_page" in str(exc).lower() or "403" in str(exc)

            if attempt == retries:
                return None, is_blocked

            backoff_ms = random.randint(1800, 3200) * (attempt + 1)
            print(f"[OLX] Retry {attempt + 1}/{retries} pentru {ad_url} dupa {backoff_ms}ms")
            detail_page.wait_for_timeout(backoff_ms)

    return None, False


def extract_ad_details(detail_page, ad_url):
    text = detail_page.locator("body").inner_text()

    #print("\n[DEBUG PREVIEW]")
    #print(text[:500])
    #print("[END DEBUG PREVIEW]\n")
    #etaj_lines = [line.strip() for line in text.splitlines() if "etaj" in line.lower() or "p+" in line.lower()]
    #print("ETAJ LINES:", etaj_lines[:20])

    #preview = text[:500].lower()

    #if "403 error" in preview or preview.startswith("403"):
    #    print(f"[OLX] Pagina blocata / 403 pentru: {ad_url}")
    #    return None

    json_ld_objects = extract_json_ld_objects(detail_page)

    title = extract_title(detail_page, text, json_ld_objects)

    price = (
        extract_price_from_json_ld(json_ld_objects)
        or parse_price(text)
        or parse_price(title or "")
    )

    surface = parse_surface(text, title or "")
    rooms = parse_rooms((title or "") + "\n" + text)
    location_info = resolve_location(title or "", text or "")
    neighborhood = location_info["neighborhood"]
    city = location_info["city"]
    nearby_neighborhood = location_info["nearby_neighborhood"]
    location_confidence = location_info["location_confidence"]
    floor = parse_floor(text)
    year_built = parse_year_built(text)
    partitioning = parse_partitioning(text)
    total_floors=parse_total_floors(text)

   # print("\n======================== Detaliu anunt ======================")
   # print(f"URL: {ad_url}")
   # print(f"TITLE: {title}")
   # print(f"PRICE: {price}")
   # print(f"SURFACE: {surface}")
   # print(f"FLOOR: {floor}")
   # print(f"TOTAL_FLOORS {total_floors}")
   # print(f"YEAR_BUILD: {year_built}")
   # print(f"PARTITIONING: {partitioning}")
   # print(f"ROOMS: {rooms}")
   # print(f"NEIGHBORHOOD: {neighborhood}")
   # print(f"TEXT PREVIEW:")
   # print(text[:1000])
   # print("================================================================")

    if price is not None and (price < 10000 or price > 1000000):
        price = None

    if floor is not None and (floor < -2 or floor > 50):
        floor = None

    if surface is not None and (surface < 10 or surface > 500):
        surface = None

    if rooms is not None and (rooms < 1 or rooms > 10):
        rooms = None

    if not title:
        print("[OLX] Lipseste title")
    if not price:
        print("[OLX] Lipseste price")

    if neighborhood is None:
        print("[OLX] Neighborhood negasit")
        print(f"TITLE: {title}")

    if surface is None:
        print("[OLX] Surface negasita")
        print(f"TITLE: {title}")

    if not title or not price or neighborhood is None:
        save_ignored_url(
            ad_url,
            "missing_neighborhood" if neighborhood is None else "invalid_listing",
            source="olx",
        )
        return None

    return {
        "title": title,
        "price_eur": price,
        "surface_mp": surface,
        "rooms": rooms,
        "neighborhood": neighborhood,
        "city": city,
        "nearby_neighborhood": nearby_neighborhood,
        "location_confidence": location_confidence,
        "floor": floor,
        "total_floors": total_floors,
        "year_built": year_built,
        "partitioning": partitioning,
        "url": ad_url,
        "source": "olx"
    }

def save_ads(ads):
    if not ads:
        return 0, 0

    urls = [ad["url"] for ad in ads]
    existing_urls = get_existing_urls(urls)
    ads_to_save = []

    for ad in ads:
        was_existing = ad["url"] in existing_urls

        if not was_existing:
            duplicate_match = find_existing_duplicate_for_ad(ad)
            if duplicate_match:
                save_rejected_duplicate_ad(ad, duplicate_match, source_label=ad.get("source"))
                matched_ad = duplicate_match["matched_ad"]
                print(
                    f"[{ad.get('source', 'CRAWLER').upper()}] Duplicat cross-source blocat: "
                    f"matched_ad_id={matched_ad['id']} score={duplicate_match['score']} url={ad.get('url')}"
                )
                continue

        ads_to_save.append((ad, was_existing))

    if not ads_to_save:
        return 0, 0

    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    updated = 0

    for ad, was_existing in ads_to_save:
        cursor.execute("""
            INSERT INTO ads (
                title, price_eur, surface_mp, rooms, neighborhood,
                city, nearby_neighborhood, location_confidence,
                floor, total_floors, year_built, partitioning, url, source,
                first_seen_at, last_seen_at, last_crawled_at, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                price_eur = excluded.price_eur,
                surface_mp = excluded.surface_mp,
                rooms = excluded.rooms,
                neighborhood = excluded.neighborhood,
                city = excluded.city,
                nearby_neighborhood = excluded.nearby_neighborhood,
                location_confidence = excluded.location_confidence,
                floor = excluded.floor,
                total_floors = excluded.total_floors,
                year_built = excluded.year_built,
                partitioning = excluded.partitioning,
                source = excluded.source,
                last_seen_at = CURRENT_TIMESTAMP,
                last_crawled_at = CURRENT_TIMESTAMP,
                is_active = 1
        """, (
            ad["title"],
            ad["price_eur"],
            ad["surface_mp"],
            ad["rooms"],
            ad["neighborhood"],
            ad["city"],
            ad["nearby_neighborhood"],
            ad["location_confidence"],
            ad["floor"],
            ad["total_floors"],
            ad["year_built"],
            ad["partitioning"],
            ad["url"],
            ad["source"],
        ))

        if was_existing:
            updated += 1
        else:
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


def get_existing_urls(urls):
    if not urls:
        return set()

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"SELECT url FROM ads WHERE url IN ({placeholders})",
        urls,
    )

    existing = {row["url"] for row in cursor.fetchall()}
    conn.close()
    return existing


def get_ignored_urls(urls, source: str = "olx"):
    if not urls:
        return set()

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"""
        SELECT url
        FROM ignored_listing_urls
        WHERE source = ?
          AND url IN ({placeholders})
        """,
        [source, *urls],
    )

    ignored = {row["url"] for row in cursor.fetchall()}
    conn.close()
    return ignored


def save_ignored_url(url: str, reason: str, source: str = "olx"):
    if not url:
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ignored_listing_urls (url, source, reason)
        VALUES (?, ?, ?)
        ON CONFLICT(url, source) DO UPDATE SET
            reason = excluded.reason
    """, (url, source, reason))

    conn.commit()
    conn.close()
    return None

def mark_existing_urls_seen(urls):
    if not urls:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    placeholders = ",".join("?" for _ in urls)
    cursor.execute(
        f"""
        UPDATE ads
        SET
            last_seen_at = CURRENT_TIMESTAMP,
            last_crawled_at = CURRENT_TIMESTAMP,
            is_active = 1
        WHERE url IN ({placeholders})
        """,
        urls,
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected




def run_olx_crawler(
    job_id: int,
    max_pages: int | None = None,
    max_ads: int | None = None,
    mode: str = "quick_refresh",
):
    try:
        resolved_max_pages, resolved_max_ads = resolve_crawl_limits(
            mode, max_pages, max_ads
        )

        update_job(
            job_id,
            status="running",
            message="Crawler OLX ruleaza",
            source="olx",
            mode=mode,
            max_pages=resolved_max_pages,
            max_ads=resolved_max_ads,
            pages_discovered=0,
            ads_discovered=0,
            ads_processed=0,
            ads_inserted=0,
            ads_updated=0,
            error_count=0,
            blocked_count=0,
        )

        all_ads = []
        all_links = []
        new_links_to_process = []
        cancelled = False
        consecutive_duplicate_pages = 0
        consecutive_blocked_details = 0
        max_consecutive_blocked_details = 5
        stop_reason = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="ro-RO",
                timezone_id="Europe/Bucharest",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={
                    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"
                }
            )

            def handle_route(route):
                request = route.request
                resource_type = request.resource_type
                url = request.url.lower()

                blocked_resource_type = {"image", "media", "font"}
                blocked_domains = [
                    "googletagmanager.com",
                    "google-analytics.com",
                    "doubleclick.net",
                    "facebook.net",
                    "facebook.com/tr",
                ]

                if resource_type in blocked_resource_type:
                    route.abort()
                    return

                if any(domain in url for domain in blocked_domains):
                    route.abort()
                    return

                route.continue_()

            context.route("**/*", handle_route)

            page = context.new_page()

            for page_no in range(1, resolved_max_pages + 1):
                if is_cancel_requested(job_id):
                    cancelled = True
                    break

                if resolved_max_ads is not None and len(new_links_to_process) >= resolved_max_ads:
                    stop_reason = "A fost atinsa limita maxima de anunturi noi pentru acest job"
                    break

                if page_no == 1:
                    url = START_URL
                else:
                    url = f"{START_URL}?page={page_no}"

                print(f"[OLX] Deschid pagina de listare: {url}")

                page.goto(url, timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(700)

                links = extract_listing_links(page)

                page_unique_links = []
                seen_page = set()
                for link in links:
                    if link not in seen_page:
                        seen_page.add(link)
                        page_unique_links.append(link)

                existing_urls = get_existing_urls(page_unique_links)
                ignored_urls = get_ignored_urls(page_unique_links, source="olx")
                mark_existing_urls_seen(list(existing_urls))
                page_new_links = [
                    link
                    for link in page_unique_links
                    if link not in existing_urls and link not in ignored_urls
                ]
                

                all_links.extend(page_unique_links)

                for link in page_new_links:
                    if link not in new_links_to_process:
                        new_links_to_process.append(link)

                if resolved_max_ads is not None:
                    new_links_to_process = new_links_to_process[:resolved_max_ads]

                if len(page_new_links) == 0:
                    consecutive_duplicate_pages += 1
                else:
                    consecutive_duplicate_pages = 0

                update_job(
                    job_id,
                    pages_discovered=page_no,
                    ads_discovered=len(new_links_to_process),
                    message=(
                        f"OLX [{mode}]: pagina {page_no}/{resolved_max_pages}, "
                        f"linkuri pe pagina: {len(page_unique_links)}, "
                        f"noi: {len(page_new_links)}, "
                        f"ignorate: {len(ignored_urls)}, "
                        f"duplicate consecutive: {consecutive_duplicate_pages}"
                    ),
                )

                print(
                    f"[OLX] Pagina {page_no}: total={len(page_unique_links)}, "
                    f"noi={len(page_new_links)}, duplicate consecutive={consecutive_duplicate_pages}"
                )

                if should_stop_early(mode, consecutive_duplicate_pages):
                    stop_reason = (
                        f"Oprire automata: {consecutive_duplicate_pages} pagini consecutive "
                        f"fara anunturi noi"
                    )
                    break

                page.wait_for_timeout(400)

            if resolved_max_ads is not None:
                new_links_to_process = new_links_to_process[:resolved_max_ads]

            update_job(
                job_id,
                ads_discovered=len(new_links_to_process),
                message=(
                    f"OLX [{mode}]: urmeaza procesarea a {len(new_links_to_process)} anunturi noi"
                ),
            )

            print(f"[OLX] Total linkuri noi pentru procesare: {len(new_links_to_process)}")
            print(f"[OLX] Primele linkuri noi: {new_links_to_process[:5]}")

            detail = context.new_page()

            for idx, link in enumerate(new_links_to_process, start=1):
                if is_cancel_requested(job_id):
                    cancelled = True
                    break

                text, was_blocked = load_detail_page_with_retry(detail, link, retries=2)

                if text is None:
                    if was_blocked:
                        increment_job_field(job_id, "blocked_count", 1)
                        consecutive_blocked_details += 1
                        update_job(
                            job_id,
                            ads_processed=idx,
                            message=(
                                f"OLX [{mode}]: pagina blocata pentru anuntul {idx}/{len(new_links_to_process)}"
                            ),
                        )
                        print(f"[OLX] Pagina blocata / 403 pentru: {link}")

                        if consecutive_blocked_details >= max_consecutive_blocked_details:
                            stop_reason = (
                                f"Oprire automata: {consecutive_blocked_details} pagini de detaliu blocate consecutiv"
                            )
                            break
                    else:
                        increment_job_field(job_id, "error_count", 1)
                        update_job(
                            job_id,
                            ads_processed=idx,
                            message=(
                                f"OLX [{mode}]: eroare la anuntul {idx}/{len(new_links_to_process)}"
                            ),
                        )
                        print(f"[OLX] ({idx}) Eroare la {link}: pagina nu a putut fi incarcata")

                    detail.wait_for_timeout(random.randint(1200, 2200))
                    continue

                consecutive_blocked_details = 0

                try:
                    ad = extract_ad_details(detail, link)

                    if ad:
                        all_ads.append(ad)

                    update_job(
                        job_id,
                        ads_processed=idx,
                        message=(
                            f"OLX [{mode}]: procesat {idx}/{len(new_links_to_process)} anunturi noi"
                        ),
                    )

                    detail.wait_for_timeout(random.randint(900, 1600))

                except Exception as e:
                    increment_job_field(job_id, "error_count", 1)
                    update_job(
                        job_id,
                        ads_processed=idx,
                        message=(
                            f"OLX [{mode}]: eroare la parsarea anuntului {idx}/{len(new_links_to_process)}"
                        ),
                    )
                    print(f"[OLX] ({idx}) Eroare la parsare pentru {link}: {e}")
                    detail.wait_for_timeout(random.randint(1200, 2200))


            detail.close()
            page.close()
            context.close()
            browser.close()

        inserted, updated = save_ads(all_ads)

        update_job(
            job_id,
            ads_inserted=inserted,
            ads_updated=updated,
        )

        if cancelled:
            update_job(
                job_id,
                status="cancelled",
                message=(
                    f"Crawler OLX oprit manual. "
                    f"Anunturi noi descoperite: {len(new_links_to_process)}, "
                    f"procesate: {len(all_ads)}, inserate: {inserted}, actualizate: {updated}"
                ),
                finished=True,
            )
            return

        final_message = (
            f"Crawler OLX terminat [{mode}]. "
            f"Pagini parcurse: {min(resolved_max_pages, page_no if 'page_no' in locals() else 0)}, "
            f"anunturi noi descoperite: {len(new_links_to_process)}, "
            f"procesate: {len(all_ads)}, inserate noi: {inserted}, actualizate: {updated}"
        )

        if stop_reason:
            final_message += f". {stop_reason}"

        update_job(
            job_id,
            status="done",
            message=final_message,
            finished=True,
        )

    except Exception as e:
        update_job(
            job_id,
            status="failed",
            message=f"Eroare OLX: {str(e)}",
            finished=True,
        )

