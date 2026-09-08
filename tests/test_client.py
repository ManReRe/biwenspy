import pytest

from client import BiwengerAuthError, BiwengerClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_call = None

    def get(self, url, headers=None, params=None, timeout=None):
        self.last_call = {"url": url, "headers": headers, "params": params}
        return self.response


def _client(response):
    session = FakeSession(response)
    client = BiwengerClient("token123", 1967092, 12683880, session=session)
    return client, session


def test_sends_expected_headers():
    client, session = _client(FakeResponse(200, {"status": 200, "data": {"users": []}}))
    client.get_league_users()
    headers = session.last_call["headers"]
    assert headers["Authorization"] == "Bearer token123"
    assert headers["X-League"] == "1967092"
    assert headers["X-User"] == "12683880"


def test_get_league_users_returns_users_list():
    client, _ = _client(FakeResponse(200, {"status": 200, "data": {"users": [{"id": 1, "name": "Ana"}]}}))
    assert client.get_league_users() == [{"id": 1, "name": "Ana"}]


def test_get_standings_returns_standings_list():
    client, _ = _client(FakeResponse(200, {"status": 200, "data": {"standings": [{"id": 1, "points": 50}]}}))
    assert client.get_standings() == [{"id": 1, "points": 50}]


def test_get_board_page_returns_raw_items():
    client, session = _client(FakeResponse(200, {"status": 200, "data": [{"type": "market"}]}))
    result = client.get_board_page(offset=500, limit=500)
    assert result == [{"type": "market"}]
    assert session.last_call["params"] == {"offset": 500, "limit": 500}


def test_get_players_resolves_team_names_by_id():
    payload = {
        "status": 200,
        "data": {
            "players": {"10": {"id": 10, "name": "Jugador A", "teamID": 1}},
            "teams": {"1": {"id": 1, "name": "Equipo X"}},
        },
    }
    client, _ = _client(FakeResponse(200, payload))
    assert client.get_players() == {10: {"name": "Jugador A", "team": "Equipo X"}}


def test_raises_auth_error_on_401():
    client, _ = _client(FakeResponse(401, {"status": 401, "message": "Invalid user"}))
    with pytest.raises(BiwengerAuthError):
        client.get_league_users()
