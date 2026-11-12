"""
Energy Performance Certificate (EPC) Data API Client
Documentation:
  - https://get-energy-performance-data.communities.gov.uk/api-technical-documentation
  - https://get-energy-performance-data.communities.gov.uk/api-technical-documentation/making-a-request
  - https://get-energy-performance-data.communities.gov.uk/api-technical-documentation/fetch-certificate-data
  - https://get-energy-performance-data.communities.gov.uk/api-technical-documentation/search-certificates/domestic
  - https://get-energy-performance-data.communities.gov.uk/api-technical-documentation/search-certificates/non-domestic
"""

from __future__ import annotations

import calendar
import csv
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
import requests


BASE_URL = "https://api.get-energy-performance-data.communities.gov.uk"

ENDPOINT_MAP = {
    "dom": "/api/domestic/search",
    "domestic": "/api/domestic/search",
    "non-dom": "/api/non-domestic/search",
    "non_dom": "/api/non-domestic/search",
    "nondom": "/api/non-domestic/search",
    "non-domestic": "/api/non-domestic/search",
    "non_domestic": "/api/non-domestic/search",
}


def _parse_month_date_range(month_date: str | date | datetime) -> tuple[str, str]:
    """
    Convert a month identifier (e.g., '2023-05', '2023-05-15', '05/2023', or date/datetime)
    into (date_start, date_end) in 'YYYY-MM-DD' format for that specific month.

    Per API documentation, neither date_start nor date_end can include today's date.
    """
    if isinstance(month_date, (datetime, date)):
        year, month = month_date.year, month_date.month
    elif isinstance(month_date, str):
        cleaned = month_date.strip()
        parsed_dt = None
        for fmt in ("%Y-%m", "%Y-%m-%d", "%Y/%m", "%m/%Y", "%B %Y", "%b %Y"):
            try:
                parsed_dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
        if parsed_dt is None:
            raise ValueError(
                f"Invalid date format '{month_date}'. Expected 'YYYY-MM' (e.g. '2023-05') "
                "or 'YYYY-MM-DD' (e.g. '2023-05-01')."
            )
        year, month = parsed_dt.year, parsed_dt.month
    else:
        raise TypeError("date parameter must be a string, datetime.date, or datetime.datetime.")

    first_day = date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_num)

    today = date.today()
    if first_day >= today:
        raise ValueError(
            f"Requested month ({first_day.strftime('%Y-%m')}) cannot start on or after "
            f"today's date ({today.isoformat()}). The API does not allow today's or future dates."
        )

    # Cap date_end at yesterday if the requested month is the current month
    if last_day >= today:
        last_day = today - timedelta(days=1)

    return first_day.isoformat(), last_day.isoformat()


def _save_certificates(certificates: list[dict[str, Any]], output_path: Path) -> None:
    """Save certificate records to a CSV or JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    if suffix == ".json":
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(certificates, f, indent=2, ensure_ascii=False)
    else:
        # Default to CSV format
        with output_path.open("w", newline="", encoding="utf-8") as f:
            if not certificates:
                f.write("")
                return
            fieldnames = list(certificates[0].keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(certificates)


def get_epc_certificates(
    cert_type: str,
    month_date: str | date | datetime,
    bearer_token: str,
    *,
    postcode: str | None = None,
    uprn: str | int | None = None,
    address: str | None = None,
    councils: Sequence[str] | None = None,
    constituencies: Sequence[str] | None = None,
    efficiency_ratings: Sequence[str] | None = None,
    page_size: int = 5000,
    output_file: str | Path | None = None,
    max_retries: int = 3,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """
    Fetch domestic or non-domestic Energy Performance Certificates (EPCs) for a specific month
    from the UK Government Energy Performance of Buildings Data API.
    """
    endpoint_map = {
        "dom": "/api/domestic/search",
        "domestic": "/api/domestic/search",
        "non-dom": "/api/non-domestic/search",
        "non_dom": "/api/non-domestic/search",
        "nondom": "/api/non-domestic/search",
        "non-domestic": "/api/non-domestic/search",
        "non_domestic": "/api/non-domestic/search",
    }

    normalized_type = cert_type.strip().lower()
    if normalized_type not in endpoint_map:
        raise ValueError(
            f"Invalid cert_type '{cert_type}'. Expected 'dom' ('domestic') or 'non-dom' ('non-domestic')."
        )

    if not bearer_token or not bearer_token.strip():
        raise ValueError("A valid bearer_token must be provided.")

    if not (1 <= page_size <= 5000):
        raise ValueError("page_size must be between 1 and 5000.")

    # Parse month_date into (date_start, date_end) for that specific month
    if isinstance(month_date, (datetime, date)):
        year, month = month_date.year, month_date.month
    elif isinstance(month_date, str):
        cleaned = month_date.strip()
        parsed_dt = None
        for fmt in ("%Y-%m", "%Y-%m-%d", "%Y/%m", "%m/%Y", "%B %Y", "%b %Y"):
            try:
                parsed_dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
        if parsed_dt is None:
            raise ValueError(
                f"Invalid date format '{month_date}'. Expected 'YYYY-MM' (e.g. '2023-05') "
                "or 'YYYY-MM-DD' (e.g. '2023-05-01')."
            )
        year, month = parsed_dt.year, parsed_dt.month
    else:
        raise TypeError("date parameter must be a string, datetime.date, or datetime.datetime.")

    first_day = date(year, month, 1)
    _, last_day_num = calendar.monthrange(year, month)
    last_day = date(year, month, last_day_num)

    today = date.today()
    if first_day >= today:
        raise ValueError(
            f"Requested month ({first_day.strftime('%Y-%m')}) cannot start on or after "
            f"today's date ({today.isoformat()}). The API does not allow today's or future dates."
        )
    if last_day >= today:
        last_day = today - timedelta(days=1)

    date_start, date_end = first_day.isoformat(), last_day.isoformat()
    url = f"https://api.get-energy-performance-data.communities.gov.uk{endpoint_map[normalized_type]}"

    clean_token = bearer_token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Accept": "application/json",
    }

    base_params: dict[str, Any] = {
        "date_start": date_start,
        "date_end": date_end,
        "page_size": page_size,
    }

    if postcode:
        base_params["postcode"] = postcode.strip()
    if uprn is not None:
        base_params["uprn"] = str(uprn).strip().zfill(12)
    if address:
        base_params["address"] = address.strip()
    if councils:
        base_params["council[]"] = list(councils)
    if constituencies:
        base_params["constituency[]"] = list(constituencies)
    if efficiency_ratings:
        base_params["efficiency_rating[]"] = [r.strip().upper() for r in efficiency_ratings]

    all_certificates: list[dict[str, Any]] = []
    current_page = 1

    with requests.Session() as session:
        session.headers.update(headers)

        while True:
            params = {**base_params, "current_page": current_page}

            for attempt in range(max_retries + 1):
                response = session.get(url, params=params, timeout=timeout)

                if response.status_code == 429:
                    if attempt < max_retries:
                        retry_after = int(response.headers.get("Retry-After", 10 * (attempt + 1)))
                        time.sleep(retry_after)
                        continue
                    response.raise_for_status()

                break

            if response.status_code == 404:
                break

            if response.status_code == 400:
                try:
                    err_detail = response.json()
                except ValueError:
                    err_detail = response.text
                raise ValueError(f"Bad Request (400) from EPC API: {err_detail}")

            response.raise_for_status()

            payload = response.json()
            page_data = payload.get("data", [])
            if isinstance(page_data, list):
                all_certificates.extend(page_data)

            pagination = payload.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            next_page = pagination.get("nextPage")

            if next_page is not None:
                current_page = int(next_page)
            elif current_page < total_pages:
                current_page += 1
            else:
                break

    if output_file is not None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() == ".json":
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(all_certificates, f, indent=2, ensure_ascii=False)
        else:
            with output_path.open("w", newline="", encoding="utf-8") as f:
                if all_certificates:
                    fieldnames = list(all_certificates[0].keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(all_certificates)
                else:
                    f.write("")

    return all_certificates


def fetch_certificate_data(
    certificate_number: str | Sequence[str],
    bearer_token: str,
    *,
    output_file: str | Path | None = None,
    max_retries: int = 3,
    timeout: int = 60,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """
    Fetch the full data for one or more EPCs or DECs using their 20-digit certificate number.
    Endpoint: GET https://api.get-energy-performance-data.communities.gov.uk/api/certificate

    Parameters
    ----------
    certificate_number : str | Sequence[str]
        A 20-digit certificate number (e.g. '1111-2222-3333-4444-5555' or '11112222333344445555'),
        or a sequence of certificate numbers to fetch in batch.
    bearer_token : str
        Your API Bearer token from https://get-energy-performance-data.communities.gov.uk/api/my-account
    output_file : str | Path, optional
        If provided, saves the certificate data to this file (.json or .csv).
    max_retries : int, default 3
        Retries when HTTP 429 (Too Many Requests) rate limit is encountered.
    timeout : int, default 60
        HTTP request timeout in seconds.

    Returns
    -------
    dict[str, Any] | list[dict[str, Any]] | None
        - When `certificate_number` is a single string: returns the certificate `data` dict,
          or `None` if no certificate was found (HTTP 404).
        - When `certificate_number` is a sequence of strings: returns a list of certificate
          `data` dicts for all found certificates.
    """
    if not bearer_token or not bearer_token.strip():
        raise ValueError("A valid bearer_token must be provided.")

    is_single = isinstance(certificate_number, str)
    raw_numbers = [certificate_number] if is_single else list(certificate_number)

    if not raw_numbers:
        raise ValueError("At least one certificate_number must be provided.")

    formatted_numbers: list[str] = []
    for raw in raw_numbers:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"Invalid certificate_number: {raw!r}")
        cleaned = raw.strip()
        # If 20 digits without hyphens are passed, format as XXXX-XXXX-XXXX-XXXX-XXXX
        digits_only = re.sub(r"[\s-]", "", cleaned)
        if re.fullmatch(r"\d{20}", digits_only):
            formatted = "-".join(digits_only[i : i + 4] for i in range(0, 20, 4))
        elif re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{4}-\d{4}", cleaned):
            formatted = cleaned
        else:
            raise ValueError(
                f"Invalid certificate_number format '{raw}'. Expected 20-digit format "
                "'1111-2222-3333-4444-5555'."
            )
        formatted_numbers.append(formatted)

    clean_token = bearer_token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    url = "https://api.get-energy-performance-data.communities.gov.uk/api/certificate"
    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Accept": "application/json",
    }

    results: list[dict[str, Any]] = []

    with requests.Session() as session:
        session.headers.update(headers)

        for cert_num in formatted_numbers:
            params = {"certificate_number": cert_num}

            for attempt in range(max_retries + 1):
                response = session.get(url, params=params, timeout=timeout)

                if response.status_code == 429:
                    if attempt < max_retries:
                        retry_after = int(response.headers.get("Retry-After", 10 * (attempt + 1)))
                        time.sleep(retry_after)
                        continue
                    response.raise_for_status()

                break

            if response.status_code == 404:
                # 404 – no certificate could be found with the certificate number
                continue

            if response.status_code == 400:
                # 400 – the certificate_number was not in the right format
                try:
                    err_detail = response.json()
                except ValueError:
                    err_detail = response.text
                raise ValueError(f"Bad Request (400) for certificate '{cert_num}': {err_detail}")

            response.raise_for_status()

            payload = response.json()
            cert_data = payload.get("data", payload)
            if isinstance(cert_data, dict):
                results.append(cert_data)

    if output_file is not None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() == ".json":
            data_to_write = (results[0] if results else None) if is_single else results
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(data_to_write, f, indent=2, ensure_ascii=False)
        else:
            with output_path.open("w", newline="", encoding="utf-8") as f:
                if results:
                    fieldnames = list(results[0].keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(results)
                else:
                    f.write("")

    if is_single:
        return results[0] if results else None
    return results

