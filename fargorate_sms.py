#!/usr/bin/env python3
"""
FargoRate League Schedule -> Table Assignment -> SMS Stub

This script:
1. GETs the FargoRate league page.
2. Finds the DIVISION's name (see DIVISIONS) in #division-list.
3. Extracts its divisionId.
4. POSTs GenerateDivisionScheduleReport with groupBy=date.
5. Finds the next scheduled match date on/after today.
6. Numbers the matches in the order FargoRate presents them.
7. Assigns tables using the division's table_assignments.
8. Looks up each team's phone numbers.
9. Calls send_sms() for every phone number.

The SMS method is intentionally a stub. Replace send_sms() with Twilio,
Textbelt, or another provider later.

Dependencies:
    pip install requests beautifulsoup4 tzdata
"""

from datetime import datetime
import os
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from twilio_sms import TwilioSMS

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

LEAGUE_URL = (
    "https://lms.fargorate.com/PublicReport/LeagueReports"
    "?leagueId=044d186c-8b01-4001-a00a-b30e014f4ede"
)

SCHEDULE_URL = (
    "https://lms.fargorate.com/PublicReport/"
    "GenerateDivisionScheduleReport"
)

LOCAL_TIMEZONE = ZoneInfo("America/Denver")

# Selected with the DIVISION environment variable (default: tuesday).
# - table_assignments: match number -> tables used by BOTH teams.
# - team_phones: team name -> list of phone numbers ("+13035550007").
# - time_note: optional sentence appended to each text.
# - max_days_ahead: only text if the next match is within this many days
#   (None = always text about the next match, however far away).
DIVISIONS = {
    "tuesday": {
        "name": "2026 Fall Tuesdays in Paradise",
        "table_assignments": {
            1: [7, 8],
            2: [9, 10],
            3: [11, 12],
            4: [13, 14],
        },
        "team_phones": {
            "What Now?": ["+13033964624"], # Dan Bergeron
            "Skyler's Team": [],
            "Beers on the Beach": ["+12622279777", "+17205204243", "+17202496704"], # Eli, Abhi, Alice
            "Andrew's Team": ["+13039097055"], # Andrew Martinez
            "Inglorious Racksters": ["+13037170395"], # Laura
            "The Replacements": ["+17206412044"], # Jalonski
            "Rack 'n' Roll": ["+16313123793"], # Rishi
            "Five Guys - 6 Holes": ["+13032416058"], # Brandon Georges
        },
        "time_note": "",
        "max_days_ahead": 2,
    },
    "sunday": {
        "name": "2026 Fall Sunday in Paradise",
        "table_assignments": {
            1: [7, 8],
            2: [9, 10],
            3: [11, 12],
        },
        "team_phones": {
            "Ball Polishers": ["+17202496704", "+13035905613", "+13036417862"], # Alice, Brandon, JT
            "Cue the Drama": ["+12622279777", "+19854455955"], # Elijah, Bree
            "Heavy W8's": ["+12629939737", "+15056601057"], # Isaiah, Rob
            "Hole Rippers": ["+13193306421", "+13176267553"], # Brett, Greg
            "Rack Wreckers": ["+14092218235", "+13035504366", "+17203981566"], # Tom, Scott, Brandon
            "Wrong Hole": ["+12253263682"], # Justin
        },
        "time_note": " Match starts at noon MST.",
        "max_days_ahead": 2,
    },
}

DEFAULT_DIVISION_KEY = "tuesday"


def get_division_config():
    """Return the config for the division named by the DIVISION env var."""
    key = os.environ.get("DIVISION", DEFAULT_DIVISION_KEY).strip().lower()

    if key not in DIVISIONS:
        raise RuntimeError(
            f"Unknown DIVISION {key!r}. Valid: {', '.join(DIVISIONS)}"
        )

    return DIVISIONS[key]


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
                # FargoRate may include a match start time after the date.
                date_only = date_text.split(" - ", 1)[0].strip()
            
                current_date = datetime.strptime(
                    date_only,
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
        today = datetime.now(LOCAL_TIMEZONE).date()

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


def assign_tables(matches, table_assignments):
    """
    Assign table groups to matches based on match number.

    Raises an error rather than silently assigning incomplete data.
    """

    assigned = []

    for match_number, match in enumerate(matches, start=1):
        if match_number not in table_assignments:
            raise RuntimeError(
                f"No table assignment exists for match "
                f"#{match_number}. Add it to table_assignments."
            )

        match["match_number"] = match_number
        match["tables"] = table_assignments[match_number]
        assigned.append(match)

    return assigned


def find_team_phone_numbers(team_name, team_phones):
    """
    Return all phone numbers configured for a team.

    Team names are matched exactly, because FargoRate's displayed team
    names are the identifiers used in team_phones.
    """

    return team_phones.get(team_name, [])


# ---------------------------------------------------------------------------
# SMS
# ---------------------------------------------------------------------------
_twilio = None


def is_dry_run():
    """True if the DRY_RUN env var is set to a truthy value."""
    return os.environ.get("DRY_RUN", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def get_twilio():
    """Create the Twilio client on first use (not needed for dry runs)."""
    global _twilio

    if _twilio is None:
        _twilio = TwilioSMS()

    return _twilio


def send_sms(phone_number, message):
    """Print the SMS, and send it through Twilio unless DRY_RUN is set."""

    print()
    print("----- SMS DRY RUN (not sent) -----" if is_dry_run() else "----- SMS -----")
    print(f"TO:      {phone_number}")
    print(f"MESSAGE: {message}")
    print("--------------------")

    if is_dry_run():
        return

    get_twilio().send_sms(phone_number, message)


def build_sms_message(match, team_name, time_note=""):
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
        f"{time_note}"
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def is_within_days_ahead(next_date, max_days_ahead, today=None):
    """True if the next match is soon enough to text about."""

    if max_days_ahead is None:
        return True

    if today is None:
        today = datetime.now(LOCAL_TIMEZONE).date()

    return (next_date - today).days <= max_days_ahead


def notify_match(match, division):
    """Print match details and text every configured player on both teams."""

    print()
    print(
        f"Match #{match['match_number']}: "
        f"{match['home']} vs {match['away']}"
    )
    print(f"Location: {match['location']}")
    print(f"Tables: {match['tables']}")

    for team_name in (match["home"], match["away"]):
        phone_numbers = find_team_phone_numbers(
            team_name,
            division["team_phones"],
        )

        if not phone_numbers:
            print(f"WARNING: No phone numbers configured for '{team_name}'.")
            continue

        message = build_sms_message(match, team_name, division["time_note"])

        for phone_number in phone_numbers:
            send_sms(phone_number, message)


def main():
    division = get_division_config()
    session = create_session()

    print(f"League URL: {LEAGUE_URL}")
    print(f"Target division: {division['name']}")
    print()

    division_id = get_division_id(session, LEAGUE_URL, division["name"])
    print(f"Division ID: {division_id}")

    schedule = get_schedule(session, division_id)
    print(f"Parsed {len(schedule)} scheduled matches.")

    next_date, matches = get_next_matches(schedule)

    if next_date is None:
        print("No future matches found.")
        return

    print()
    print(
        f"Next match date: "
        f"{next_date:%A, %B} {next_date.day}, {next_date:%Y}"
    )

    if not is_within_days_ahead(next_date, division["max_days_ahead"]):
        print("Next match is too far away; not sending texts.")
        return

    matches = assign_tables(matches, division["table_assignments"])

    for match in matches:
        notify_match(match, division)


if __name__ == "__main__":
    main()
