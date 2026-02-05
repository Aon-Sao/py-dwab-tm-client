import datetime
from abc import ABC
from decimal import Decimal
from enum import StrEnum, Enum
from typing import Literal, Callable, Optional, Any, Union

from pydantic import BaseModel, InstanceOf, ConfigDict, computed_field

numeric = int | float | Decimal

class TMError(StrEnum):
    CredentialsExpired = "DWAB Third-Party Authorization Credentials have expired"
    CredentialsInvalid = "DWAB Third-Party Authorization Credentials are invalid"
    CredentialsError = "Could not obtain a bearer token from DWAB server"
    WebServerError = "Tournament Manager Web Server returned non-200 status code"
    WebServerInvalidSignature = "Tournament Manager Client API Key is invalid"
    WebServerConnectionError = "Could not connect to Tournament Manager Web Server"
    WebServerNotEnabled = "The Tournament Manager API is not enabled"
    WebSocketInvalidURL = "Fieldset WebSocket URL is invalid"
    WebSocketError = "Fieldset WebSocket could not be established"
    WebSocketClosed = "Fieldset WebSocket is closed"


class RemoteAuthorizationArgs(BaseModel):
    client_id: str
    client_secret: str
    expiration_date: datetime.datetime
    @computed_field
    @property
    def grant_type(self) -> str: return "client_credentials"


class ManualAuthorizationConfig(BaseModel):
    getBearer: Callable[[], BearerResult]


class AuthorizationArgs(BaseModel):
    authorization: RemoteAuthorizationArgs | ManualAuthorizationConfig

    def __str__(self):
        return self.authorization.__str__()

class ClientArgs(BaseModel):
    address: str
    clientAPIKey: str
    bearer_margin: datetime.timedelta = datetime.timedelta(seconds=0)
    authorization_args: AuthorizationArgs

class BearerToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: datetime.timedelta

class BearerSuccess(BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return True
    token: BearerToken
class BearerFailure(BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return False
    error: InstanceOf[TMError]
    error_details: Optional[Any] = None

BearerResult = Union[BearerSuccess, BearerFailure]

class ConnectionSuccess(BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return True
class ConnectionFailure(BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return False
    origin: Literal["bearer"] | Literal["connection"]
    error: InstanceOf[TMError]
    error_details: Optional[Any] = None

ConnectionResult =  Union[ConnectionSuccess, ConnectionFailure]

class APISuccess[T](BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return True
    data: T
    cached: bool
class APIFailure(BaseModel):
    @computed_field
    @property
    def success(self) -> bool: return False
    error: InstanceOf[TMError]
    error_details: Optional[Any] = None

APIResult = Union[APISuccess, APIFailure]

class SkillsRanking(BaseModel):
    rank: int
    tie: bool
    number: str
    totalScore: int
    progHighScore: int
    progAttempts: int
    driverHighScore: int
    driverAttempts: int

class EventInfo(BaseModel):
    code: str
    name: str

class DivisionData(BaseModel):
    id: numeric
    name: str

class ClientModel(BaseModel, ABC):
    model_config = ConfigDict(from_attributes=True)

    connection_args: ClientArgs
    bearer_token: BearerToken | None = None
    bearer_expiration: datetime.datetime
    connection_string: Literal[r"https://auth.vextm.dwabtech.com/oauth2/token"]
    endpoint_cache: dict[str, EndpointCacheMember] = dict()

class Field(BaseModel):
    id: numeric
    name: str

class FieldsetData(BaseModel):
    id: numeric
    name: str

FieldID = numeric

class FieldsetEvent(BaseModel, ABC):
    pass

class FieldMatchAssigned(FieldsetEvent):
    @computed_field
    @property
    def type(self) -> str: return "fieldMatchAssigned"
    field_id: FieldID | None
    match: MatchTuple | None

    def __str__(self):
        return f"{self.__class__.__name__}\n\tfield_id: {self.field_id}\n\tmatch: {self.match}"

class FieldActivated(FieldsetEvent):
    @computed_field
    @property
    def type(self) -> str: return "fieldActivated"
    field_id: FieldID | None

    def __str__(self):
        return f"{self.__class__.__name__}\n\tfield_id: {self.field_id}"

class MatchStarted(FieldsetEvent):
    @computed_field
    @property
    def type(self) -> str: return "matchStarted"
    field_id: FieldID | None

    def __str__(self):
        return f"{self.__class__.__name__}\n\tfield_id: {self.field_id}"

class MatchStopped(FieldsetEvent):
    @computed_field
    @property
    def type(self) -> str: return "matchStopped"
    field_id: FieldID | None

    def __str__(self):
        return f"{self.__class__.__name__}\n\tfield_id: {self.field_id}"

class AudienceDisplayChanged(FieldsetEvent):
    @computed_field
    @property
    def type(self) -> str: return "audienceDisplayChanged"
    display: AudienceDisplay | None

    def __str__(self):
        return f"{self.__class__.__name__}\n\tfield_id: {self.display.name}"

class AudienceDisplay(StrEnum):
    Blank = "BLANK"
    Logo = "LOGO"
    Intro = "INTRO"
    InMatch = "IN_MATCH"
    SavedMatchResults = "RESULTS"
    Schedule = "SCHEDULE"
    Rankings = "RANKINGS"
    SkillsRankings = "SC_RANKINGS"
    AllianceSelection = "ALLIANCE_SELECTION"
    ElimBracket = "BRACKET"
    Slides = "AWARD"
    Inspection = "INSPECTION"

FieldsetEventTypes = (
    "fieldMatchAssigned",
    "fieldActivated",
    "matchStarted",
    "matchStopped",
    "audienceDisplayChanged"
)

class FieldsetCommand(BaseModel, ABC):
    pass

class StartMatch(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "start"
    field_id: numeric

    def __str__(self):
        return f"{self.__class__.__name__} on field_id: {self.field_id}"

class EndMatchEarly(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "endEarly"
    field_id: numeric

    def __str__(self):
        return f"{self.__class__.__name__} on field_id: {self.field_id}"

class AbortMatch(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "abort"
    field_id: numeric

    def __str__(self):
        return f"{self.__class__.__name__} on field_id: {self.field_id}"

class ResetTimer(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "reset"
    field_id: numeric

    def __str__(self):
        return f"{self.__class__.__name__} on field_id: {self.field_id}"

class QueuePreviousMatch(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "queuePrevMatch"

    def __str__(self):
        return f"{self.__class__.__name__}"

class QueueNextMatch(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "queueNextMatch"

    def __str__(self):
        return f"{self.__class__.__name__}"

class QueueSkills(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "queueSkills"
    skills_id: QueueSkillsType

    def __str__(self):
        return f"{self.__class__.__name__} with skills_id: {self.skills_id}"

class SetAudienceDisplay(FieldsetCommand):
    @computed_field
    @property
    def cmd(self) -> str: return "setAudienceDisplay"
    display: AudienceDisplay

    def __str__(self):
        return f"{self.__class__.__name__} to {self.display.name}"

class QueueSkillsType(Enum):
    Programming = 1
    Driver = 2

FieldsetCommandTypes = (
    "start",
    "endEarly",
    "abort",
    "reset",
    "queuePrevMatch",
    "queueNextMatch",
    "queueSkills",
    "setAudienceDisplay"
)

class ActiveMatchType(Enum):
    NONE = 0
    Timeout = 1
    Match = 2

class QueueState(Enum):
    Unplayed = 0
    Running = 1
    Stopped = 2

class FieldsetMatchActiveNone(BaseModel):
    @computed_field
    @property
    def type(self) -> ActiveMatchType: return ActiveMatchType.NONE
class FieldsetMatchActiveTimeout(BaseModel):
    @computed_field
    @property
    def type(self) -> ActiveMatchType: return ActiveMatchType.Timeout
    state: QueueState
    field_id: numeric
    active: bool
class FieldsetMatchActiveMatch(BaseModel):
    @computed_field
    @property
    def type(self) -> ActiveMatchType: return ActiveMatchType.Match
    state: QueueState
    match: MatchTuple
    field_id: numeric
    active: bool

FieldsetMatch = Union[
    FieldsetMatchActiveNone,
    FieldsetMatchActiveTimeout,
    FieldsetMatchActiveMatch
]

class FieldsetState(BaseModel):
    match: FieldsetMatch
    audience_display: AudienceDisplay

class MatchState(StrEnum):
    Unplayed = "UNPLAYED"
    Scored = "SCORED"

class MatchRound(StrEnum):
    NONE = "NONE"
    Practice = "PRACTICE"
    Qualification = "QUAL"
    Semifinal = "SF"
    Final = "F"
    RoundOf16 = "R16"
    RoundOf32 = "R32"
    RoundOf64 = "R64"
    RoundOf128 = "R128"
    TopN = "TOP_N"
    RoundRobin = "ROUND_ROBIN"
    Skills = "SKILLS"
    Timeout = "TIMEOUT"

class _team(BaseModel):
    number: str

class MatchAlliance(BaseModel):
    teams: list[_team]

class MatchTuple(BaseModel):
    session: int
    division: int
    round: int
    instance: int
    match: int

    def __str__(self):
        return f"{self.__class__.__name__}\n\t" + \
            f"session: {self.session}\n\t" + \
            f"division: {self.division}\n\t" + \
            f"round: {self.round}\n\t" + \
            f"instance: {self.instance}\n\t" + \
            f"match: {self.match}"

class Match(BaseModel):
    class MatchInfo(BaseModel):
        time_scheduled: datetime.datetime
        state: MatchState
        alliances: list[MatchAlliance]
        match_tuple: MatchTuple
    winning_alliance: int
    finalScore: list[int]
    state: MatchState
    match_info: MatchInfo

class RankAlliance(BaseModel):
    name: str
    teams: list[_team]

class Ranking(BaseModel):
    rank: int
    tied: Literal[False]
    alliance: list[RankAlliance]
    wins: int
    losses: int
    ties: int
    wp: int
    ap: int
    sp: int
    avg_points: numeric
    total_points: int
    high_score: int
    num_matches: int
    min_num_matches: bool

class AgeGroup(StrEnum):
    HighSchool = "HIGH_SCHOOL"
    MiddleSchool = "MIDDLE_SCHOOL"
    ElementarySchool = "ELEMENTARY_SCHOOL"
    College = "COLLEGE"

class Team(BaseModel):
    number: str
    name: str
    city: str
    state: str
    country: str
    age_group: AgeGroup
    div_id: int
    checked_in: bool
    # Deprecated
    short_name: str
    sponsors: str

class EndpointCacheMember(BaseModel):
    data: Any
    last_modified: datetime.datetime
