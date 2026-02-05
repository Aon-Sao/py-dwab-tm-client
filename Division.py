from Types import DivisionData, APIResult

class Division:
    def __init__(self, client, data: DivisionData):
        self.id = data.id
        self.name = data.name
        self.client = client

    def get_teams(self) -> APIResult:
        rs = self.client.get(f"/api/teams/{self.id}")
        if rs.success:
            rs.data = rs.data["teams"]
        return rs

    def get_matches(self) -> APIResult:
        rs = self.client.get(f"/api/matches/{self.id}")
        if rs.success:
            rs.data = rs.data["matches"]
        return rs

    def get_rankings(self, _round) -> APIResult:
        rs = self.client.get(f"/api/rankings/{self.id}/{_round}")
        if rs.success:
            rs.data = rs.data["rankings"]
        return rs
