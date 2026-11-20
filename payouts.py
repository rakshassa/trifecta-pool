#!/usr/bin/env python3
"""
Calculate league payouts for "2026 Fall Tuesdays in Paradise".

Run manually:
    python payouts.py

Each team receives a payout based on its placement in the FargoRate team
standings (PAYOUT_BY_PLACE). Within a team, the payout is split between the
players in proportion to each player's "Player Points" on that team's report.
A player who played for several teams is paid by each of those teams.

Output:
  1. A per-team breakdown (for team captains).
  2. A per-person total with a per-team breakdown.

Dependencies:
    pip install requests beautifulsoup4
"""

from collections import defaultdict
from decimal import ROUND_DOWN, Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from fargorate_sms import (
    DIVISIONS,
    LEAGUE_URL,
    create_session,
    get_division_id,
)

CENT = Decimal("0.01")

# Placement -> total team payout (dollars).
PAYOUT_BY_PLACE = {
    1: Decimal("1482.22"),
    2: Decimal("1296.94"),
    3: Decimal("1111.67"),
    4: Decimal("926.39"),
    5: Decimal("741.11"),
    6: Decimal("555.83"),
    7: Decimal("370.56"),
    8: Decimal("185.28"),
}

BASE_URL = "https://lms.fargorate.com/"
TEAM_STANDINGS_URL = BASE_URL + "PublicReport/GenerateTeamStandingsReport/{}"
POINTS_HEADER = "Player Points"


class TeamStanding:
    """One row of the team standings."""

    def __init__(self, place, name, report_url):
        self.place = place
        self.name = name
        self.report_url = report_url


class PlayerShare:
    """One player's points and payout on one team."""

    def __init__(self, name, points, amount):
        self.name = name
        self.points = points
        self.amount = amount


class FargoRateClient:
    """Fetches and parses the FargoRate pages needed for payouts."""

    def __init__(self, session):
        self.session = session

    def get_soup(self, url):
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    def get_team_standings(self, division_id):
        """Return TeamStanding objects ordered by placement."""
        soup = self.get_soup(TEAM_STANDINGS_URL.format(division_id))
        table = soup.select_one("table.report-table-modern")

        if table is None:
            raise RuntimeError("Could not find the team standings table.")

        standings = [self._parse_standing_row(row) for row in table.select("tbody tr")]
        return sorted(standings, key=lambda standing: standing.place)

    def _parse_standing_row(self, row):
        link = row.select_one("td.highlight a")
        place = int(row.select_one("td.rank").get_text(strip=True))
        return TeamStanding(
            place,
            link.get_text(" ", strip=True),
            urljoin(BASE_URL, link["href"]),
        )

    def get_team_player_points(self, report_url):
        """Return {player name: Player Points} from a team report page."""
        soup = self.get_soup(report_url)
        rows = soup.select("table.table-header-rotated tbody tr")
        header = [cell.get_text(" ", strip=True) for cell in rows[0].find_all("td")]

        if POINTS_HEADER not in header:
            raise RuntimeError(f"No '{POINTS_HEADER}' column at {report_url}")

        column = header.index(POINTS_HEADER)
        return self._parse_player_rows(rows[1:], column, len(header))

    def _parse_player_rows(self, rows, column, width):
        """Player rows have as many cells as the header; summary rows don't."""
        points = {}

        for row in rows:
            cells = row.find_all("td")
            name = cells[0].get_text(" ", strip=True)

            if len(cells) == width and name:
                points[name] = int(cells[column].get_text(strip=True) or 0)

        return points


class PayoutCalculator:
    """Splits a team payout between players in proportion to their points."""

    @staticmethod
    def split(team_payout, player_points):
        """
        Return {player: dollars} summing exactly to team_payout.

        Shares are rounded down to the cent; leftover cents go to the players
        with the largest fractional remainders.
        """
        total_points = sum(player_points.values())

        if total_points <= 0:
            raise RuntimeError("Team has no player points to split a payout by.")

        exact = {
            name: team_payout * points / total_points
            for name, points in player_points.items()
        }
        amounts = {name: value.quantize(CENT, ROUND_DOWN) for name, value in exact.items()}
        leftover_cents = int((team_payout - sum(amounts.values())) / CENT)
        by_remainder = sorted(exact, key=lambda n: exact[n] - amounts[n], reverse=True)

        for name in by_remainder[:leftover_cents]:
            amounts[name] += CENT

        return amounts


class PayoutReport:
    """Builds and prints the per-team and per-person payout reports."""

    def __init__(self, client):
        self.client = client
        self.team_results = []  # [(TeamStanding, payout, [PlayerShare])]

    def build(self, division_id):
        standings = self.client.get_team_standings(division_id)
        self._check_placements(standings)

        for standing in standings:
            self.team_results.append(self._build_team(standing))

    def _check_placements(self, standings):
        places = [standing.place for standing in standings]

        if len(set(places)) != len(places):
            raise RuntimeError(f"Tied placements need a payout rule: {places}")

        missing = [place for place in places if place not in PAYOUT_BY_PLACE]

        if missing:
            raise RuntimeError(f"No payout configured for places {missing}")

    def _build_team(self, standing):
        payout = PAYOUT_BY_PLACE[standing.place]
        points = self.client.get_team_player_points(standing.report_url)
        amounts = PayoutCalculator.split(payout, points)
        shares = [PlayerShare(name, points[name], amounts[name]) for name in points]
        shares.sort(key=lambda share: share.amount, reverse=True)
        return standing, payout, shares

    def print_team_report(self):
        print("=" * 70)
        print("TEAM PAYOUTS")
        print("=" * 70)

        for standing, payout, shares in self.team_results:
            self._print_team(standing, payout, shares)

    def _print_team(self, standing, payout, shares):
        total_points = sum(share.points for share in shares)
        print()
        print(f"#{standing.place} {standing.name} - team payout ${payout:,.2f} ({total_points} pts)")

        for share in shares:
            print(f"    {share.name:<28} {share.points:>5} pts   ${share.amount:>9,.2f}")

    def person_totals(self):
        """Return {person: [(team name, dollars), ...]}."""
        people = defaultdict(list)

        for standing, _payout, shares in self.team_results:
            for share in shares:
                people[share.name].append((standing.name, share.amount))

        return people

    def print_person_report(self):
        print()
        print("=" * 70)
        print("PAYOUTS BY PERSON")
        print("=" * 70)
        people = self.person_totals()
        ranked = sorted(people.items(), key=lambda item: item[0].casefold())

        for name, teams in ranked:
            breakdown = ", ".join(f"[{team}]: ${amount:,.2f}" for team, amount in teams)
            print(f"{name}, total: ${self._total(teams):,.2f}. Team breakdown: {breakdown}")

        print()
        print(f"Grand total: ${sum(self._total(t) for t in people.values()):,.2f}")

    @staticmethod
    def _total(teams):
        return sum(amount for _team, amount in teams)


def main():
    name = DIVISIONS["tuesday"]["name"]
    session = create_session()
    division_id = get_division_id(session, LEAGUE_URL, name)

    report = PayoutReport(FargoRateClient(session))
    report.build(division_id)

    print(f"Division: {name}")
    report.print_team_report()
    report.print_person_report()


if __name__ == "__main__":
    main()
