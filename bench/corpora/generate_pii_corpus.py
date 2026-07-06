#!/usr/bin/env python3
"""Generates bench/corpora/en_pii.jsonl -- a small English PII benchmark
corpus (text + expected label set), for bench/run_pii_bench.py's P/R/F1
measurement. Not a substitute for a production-curated benchmark corpus
(e.g. ai4Privacy-scale) -- see DECISIONS.md."""
from __future__ import annotations

import json
from pathlib import Path

EXAMPLES = [
    ("Email me at jane.doe@example.com about the invoice.", ["EMAIL"]),
    ("Call me at 415-555-0199 tomorrow.", ["PHONE"]),
    ("My card number is 4111 1111 1111 1111, please charge it.", ["CREDIT_CARD"]),
    ("SSN is 123-45-6789 for the tax form.", ["GOV_ID"]),
    ("Here's the key: AKIAABCDEFGHIJKLMNOP for the S3 bucket.", ["SECRET"]),
    ("The server responded from 10.0.0.1 with an error.", ["IP_ADDRESS"]),
    ("The meeting is on November 20th, 1934.", ["DATE_TIME"]),
    ("Reach out to @jane_doe for details.", ["USERNAME"]),
    ("My name is Jane Doe and I need help.", ["PERSON"]),
    ("I live at 742 Evergreen Terrace, Springfield, IL 62704.", ["ADDRESS"]),
    ("Contact john.smith@company.org or call 212-555-0134.", ["EMAIL", "PHONE"]),
    ("Password: Xg9#mK2p is for the admin panel.", ["SECRET"]),
    ("Card 5500 0000 0000 0004 was declined.", ["CREDIT_CARD"]),
    ("My passport number, ID card is VT31867ES, expires soon.", ["GOV_ID"]),
    ("The IP was 192.168.1.1 during the incident.", ["IP_ADDRESS"]),
    ("Username: jdoe_99 is locked out.", ["USERNAME"]),
    ("This is Priya, calling about the order.", ["PERSON"]),
    ("Ship to 100 Main Street, Boston, MA 02108.", ["ADDRESS"]),
    ("Email support@help.io if you have questions.", ["EMAIL"]),
    ("His number is +44 7911 123456.", ["PHONE"]),
    ("Meeting scheduled for 07/02/2053.", ["DATE_TIME"]),
    ("The AWS secret looks like AKIAECOSFOGYR3XKXWNR here.", ["SECRET"]),
    ("SSN 321-54-9876 was on file.", ["GOV_ID"]),
    ("Reach jane.doe+work@example.co.uk for billing.", ["EMAIL"]),
    ("The handle @john99 posted again.", ["USERNAME"]),
    ("No personal information appears in this sentence at all.", []),
    ("The weather today is sunny with a light breeze.", []),
    ("Please review the quarterly report before Friday.", []),
    ("Our office is closed on public holidays.", []),
    ("The product launch is scheduled for next quarter.", []),
]


def main() -> None:
    out_path = Path(__file__).parent / "en_pii.jsonl"
    with open(out_path, "w") as f:
        for text, labels in EXAMPLES:
            f.write(json.dumps({"text": text, "expected_labels": labels}) + "\n")
    print(f"wrote {len(EXAMPLES)} PII benchmark examples to {out_path}")


if __name__ == "__main__":
    main()
