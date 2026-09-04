#!/usr/bin/env python3
"""
FargoRate League Schedule -> Table Assignment -> SMS Stub

This script:
1. GETs the FargoRate league page.
2. Finds TARGET_DIVISION_NAME in #division-list.
3. Extracts its divisionId.
4. POSTs GenerateDivisionScheduleReport with groupBy=date.
5. Finds the next scheduled match date on/after today.
6. Numbers the matches in the order FargoRate presents them.
7. Assigns tables using TABLE_ASSIGNMENTS.
8. Looks up each team's phone numbers.
9. Calls send_sms() for every phone number.

The SMS method is intentionally a stub. Replace send_sms() with Twilio,
Textbelt, or another provider later.

Dependencies:
    pip install requests beautifulsoup4
"""

from datetime import date, datetime
import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

LEAGUE_URL = (
    "https://lms.fargorate.com/PublicReport/LeagueReports"
    "?leagueId=044d186c-8b01-4001-a00a-b30e014f4ede"
)

TARGET_DIVISION_NAME = "2026 Fall Tuesdays in Paradise"

SCHEDULE_URL = (
    "https://lms.fargorate.com/PublicReport/"
    "GenerateDivisionScheduleReport"
)

# Match number -> tables used by BOTH teams in that match.
TABLE_ASSIGNMENTS = {
    1: [7, 8, 9],
    2: [10, 11, 12],
    3: [13, 14, 15],
    4: [16, 17, 18],
}

# Team name -> list of phone numbers.
# Replace these examples with the real numbers.
TEAM_PHONES = {
    "What Now?": ["+13035551234", "+13035555678"],
    "Skyler's Team": ["+13035550001"],
    "Beers on the Beach": ["+13035550002"],
    "Andrew's Team": ["+13035550003"],
    "Inglorious Racksters": ["+13035550004"],
    "The Replacements": ["+13035550005"],
    "Rack 'n' Roll": ["+13035550006"],
    "Five Guys - 6 Holes": ["+13035550007"],
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def create_session():
    """Create an HTTP session with a normal browser-like User-Agent."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        )
    })
    return session


# ---------------------------------------------------------------------------
# FARGORATE
# ---------------------------------------------------------------------------

def get_division_id(session, league_url, target_division_name):
    """
    GET the league page and find the division ID associated with the
    requested division name.

    FargoRate's HTML contains:
        <select id="division-list">
            <option value="...">Division Name</option>
            ...
        </select>
    """

    response = session.get(league_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    division_select = soup.select_one("#division-list")

    if division_select is None:
        raise RuntimeError(
            "Could not find #division-list in the FargoRate league page."
        )

    for option in division_select.find_all("option"):
        division_name = option.get_text(" ", strip=True)

        if division_name == target_division_name:
            division_id = option.get("value")

            if not division_id:
                raise RuntimeError(
                    f"Division '{target_division_name}' was found, "
                    "but its option has no value."
                )

            return division_id

    available_divisions = [
        option.get_text(" ", strip=True)
        for option in division_select.find_all("option")
    ]

    raise RuntimeError(
        f"Division '{target_division_name}' was not found.\n"
        "Available divisions:\n"
        + "\n".join(f"  - {name}" for name in available_divisions)
    )


def get_schedule(session, division_id):
    """
    POST to FargoRate's schedule endpoint and parse the returned HTML.

    The schedule is grouped by date. Match order is preserved exactly
    as returned by FargoRate.
    """

    response = session.post(
        SCHEDULE_URL,
        data={
            "divisionId": division_id,
            "groupBy": "date",
        },
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    schedule = []
    current_date = None

    table = soup.select_one("table.report-table-modern")

    if table is None:
        raise RuntimeError(
            "Could not find the schedule table in FargoRate's response."
        )

    for row in table.select("tr"):
        # Date separator row, e.g.
        # Tuesday, September 8, 2026
        if "subtitle-row" in row.get("class", []):
            subtitle = row.select_one(".subtitle")

            if subtitle is None:
                continue

            date_text = subtitle.get_text(" ", strip=True)

            try:
                current_date = datetime.strptime(
                    date_text,
                    "%A, %B %d, %Y",
                ).date()
            except ValueError as exc:
                raise RuntimeError(
                    f"Could not parse FargoRate date: {date_text!r}"
                ) from exc

            continue

        if current_date is None:
            continue

        cells = row.find_all("td", recursive=False)

        # Match rows have Home, Away, Location, and an action cell.
        if len(cells) < 2:
            continue

        home = cells[0].get_text(" ", strip=True)
        away = cells[1].get_text(" ", strip=True)

        if not home or not away:
            continue

        location = (
            cells[2].get_text(" ", strip=True)
            if len(cells) >= 3
            else ""
        )

        schedule.append({
            "date": current_date,
            "home": home,
            "away": away,
            "location": location,
        })

    if not schedule:
        raise RuntimeError(
            "FargoRate returned a schedule response, but no matches "
            "could be parsed."
        )

    return schedule


# ---------------------------------------------------------------------------
# MATCH PROCESSING
# ---------------------------------------------------------------------------

def get_next_matches(schedule, today=None):
    """
    Find the earliest scheduled date on or after today and return all
    matches on that date, preserving FargoRate's match order.
    """

    if today is None:
        today = date.today()

    future_dates = sorted({
        match["date"]
        for match in schedule
        if match["date"] >= today
    })

    if not future_dates:
        return None, []

    next_date = future_dates[0]

    matches = [
        match.copy()
        for match in schedule
        if match["date"] == next_date
    ]

    return next_date, matches


def assign_tables(matches):
    """
    Assign table groups to matches based on match number.

    Raises an error rather than silently assigning incomplete data.
    """

    assigned = []

    for match_number, match in enumerate(matches, start=1):
        if match_number not in TABLE_ASSIGNMENTS:
            raise RuntimeError(
                f"No table assignment exists for match "
                f"#{match_number}. Add it to TABLE_ASSIGNMENTS."
            )

        match["match_number"] = match_number
        match["tables"] = TABLE_ASSIGNMENTS[match_number]
        assigned.append(match)

    return assigned


def find_team_phone_numbers(team_name):
    """
    Return all phone numbers configured for a team.

    Team names are matched exactly, because FargoRate's displayed team
    names are the identifiers used in TEAM_PHONES.
    """

    return TEAM_PHONES.get(team_name, [])


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------

def send_sms(phone_number, message):
    """
    SMS stub.

    Replace this function with the actual SMS provider later.

    Example future implementation:
        Twilio client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=phone_number,
        )
    """

    print()
    print("----- SMS STUB -----")
    print(f"TO:      {phone_number}")
    print(f"MESSAGE: {message}")
    print("--------------------")


def build_sms_message(match, team_name):
    """Create the text message for one team."""

    tables = ", ".join(str(table) for table in match["tables"])

    opponent = (
        match["away"]
        if team_name == match["home"]
        else match["home"]
    )

    return (
        f"Your next match is "
        f"{match['date']:%A, %B} {match['date'].day} "
        f"vs {opponent}. "
        f"Your tables are {tables}."
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    session = create_session()

    print(f"League URL: {LEAGUE_URL}")
    print(f"Target division: {TARGET_DIVISION_NAME}")
    print()

    # 1. Discover division ID from the league page.
    division_id = get_division_id(
        session,
        LEAGUE_URL,
        TARGET_DIVISION_NAME,
    )

    print(f"Division ID: {division_id}")

    # 2. Get the schedule for that division.
    schedule = get_schedule(session, division_id)

    print(f"Parsed {len(schedule)} scheduled matches.")

    # 3. Find the next match date.
    next_date, matches = get_next_matches(schedule)

    if next_date is None:
        print("No future matches found.")
        return

    print()
    print(
        f"Next match date: "
        f"{next_date:%A, %B} {next_date.day}, {next_date:%Y}"
    )

    # 4. Assign tables according to match order.
    matches = assign_tables(matches)

    # 5. Process each match and notify both teams.
    for match in matches:
        print()
        print(
            f"Match #{match['match_number']}: "
            f"{match['home']} vs {match['away']}"
        )
        print(f"Location: {match['location']}")
        print(f"Tables: {match['tables']}")

        for team_name in (match["home"], match["away"]):
            phone_numbers = find_team_phone_numbers(team_name)

            if not phone_numbers:
                print(
                    f"WARNING: No phone numbers configured for "
                    f"'{team_name}'."
                )
                continue

            message = build_sms_message(match, team_name)

            for phone_number in phone_numbers:
                send_sms(phone_number, message)


if __name__ == "__main__":
    main()
