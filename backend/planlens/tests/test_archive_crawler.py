from __future__ import annotations

from datetime import date

import duckdb
from backend.planlens.crawl.cpc_archive import parse_archive_html, upsert_archive_hearings

ARCHIVE_HTML = """
<html>
  <body>
    <table>
      <thead>
        <tr>
          <th>Hearing Date</th>
          <th>Agenda</th>
          <th>Minutes</th>
          <th>Supporting</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>December 18, 2025</td>
          <td><a href="/agendas/2025-12/agenda.pdf">Agenda</a></td>
          <td><a href="https://citypln-m-extnl.sfgov.org/minutes/121825.pdf">Minutes</a></td>
          <td><a href="/supporting/2025-12-18">Supporting</a></td>
        </tr>
        <tr>
          <td>December 25, 2025 (Cancelled)</td>
          <td><a href="/notices/cancelled.pdf">Notice</a></td>
          <td>N/A</td>
          <td>N/A</td>
        </tr>
        <tr>
          <td>July 17, 2025 (Joint w/ Rec and Park)</td>
          <td><a href="/agendas/joint.pdf">Agenda</a></td>
          <td>N/A</td>
          <td><a href="/supporting/joint">Supporting</a></td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_archive_html_extracts_hearings_and_links() -> None:
    hearings = parse_archive_html(
        ARCHIVE_HTML,
        source_url="https://sfplanning.org/cpc-hearing-archives",
    )

    assert len(hearings) == 3

    regular = hearings[0]
    assert regular.hearing_id == "cpc-2025-12-18"
    assert regular.hearing_date == date(2025, 12, 18)
    assert regular.status == "scheduled"
    assert regular.agenda_url == "https://sfplanning.org/agendas/2025-12/agenda.pdf"
    assert regular.minutes_url == "https://citypln-m-extnl.sfgov.org/minutes/121825.pdf"
    assert regular.supporting_url == "https://sfplanning.org/supporting/2025-12-18"


def test_parse_archive_html_handles_cancelled_and_missing_links() -> None:
    hearings = parse_archive_html(
        ARCHIVE_HTML,
        source_url="https://sfplanning.org/cpc-hearing-archives",
    )

    cancelled = hearings[1]
    assert cancelled.hearing_id == "cpc-2025-12-25"
    assert cancelled.status == "cancelled"
    assert cancelled.agenda_url is None
    assert cancelled.minutes_url is None
    assert cancelled.supporting_url is None


def test_parse_archive_html_keeps_same_day_hearings_distinct() -> None:
    hearings = parse_archive_html(
        ARCHIVE_HTML,
        source_url="https://sfplanning.org/cpc-hearing-archives",
    )

    joint = hearings[2]
    assert joint.hearing_id == "cpc-2025-07-17-joint-w-rec-and-park"
    assert joint.title == "Planning Commission - Joint w/ Rec and Park"


def test_parse_archive_html_filters_since_until_and_limit() -> None:
    hearings = parse_archive_html(
        ARCHIVE_HTML,
        source_url="https://sfplanning.org/cpc-hearing-archives",
        since=date(2025, 7, 1),
        until=date(2025, 12, 20),
        limit=1,
    )

    assert [hearing.hearing_id for hearing in hearings] == ["cpc-2025-12-18"]


def test_upsert_archive_hearings_is_idempotent() -> None:
    hearings = parse_archive_html(
        ARCHIVE_HTML,
        source_url="https://sfplanning.org/cpc-hearing-archives",
    )
    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE hearings (
            hearing_id VARCHAR PRIMARY KEY,
            hearing_date DATE NOT NULL,
            title VARCHAR,
            status VARCHAR,
            agenda_url VARCHAR,
            minutes_url VARCHAR,
            supporting_url VARCHAR,
            source_url VARCHAR NOT NULL,
            crawled_at TIMESTAMP DEFAULT current_timestamp
        )
        """
    )

    upsert_archive_hearings(conn, hearings)
    upsert_archive_hearings(conn, hearings)

    assert conn.execute("SELECT count(*) FROM hearings").fetchone()[0] == 3
