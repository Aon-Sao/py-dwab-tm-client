import abc
import datetime
from abc import ABC
from decimal import Decimal
from enum import StrEnum, Enum
from typing import Literal, Callable, Optional, Any, Union, List

from pydantic import BaseModel, InstanceOf, ConfigDict

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
    grant_type: Literal["client_credentials"]
    expiration_date: datetime.datetime

class ManualAuthorizationConfig(BaseModel):
    getBearer: Callable[[], BearerResult]


class AuthorizationArgs(BaseModel):
    authorization: RemoteAuthorizationArgs | ManualAuthorizationConfig

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
    success: Literal[True]
    token: BearerToken
class BearerFailure(BaseModel):
    success: Literal[False]
    error: InstanceOf[TMError]
    error_details: Optional[Any] = None

BearerResult = Union[BearerSuccess, BearerFailure]

class ConnectionSuccess(BaseModel):
    success: Literal[True]
class ConnectionFailure(BaseModel):
    success: Literal[False]
    origin: Literal["bearer"] | Literal["connection"]
    error: InstanceOf[TMError]
    error_details: Optional[Any] = None

ConnectionResult =  Union[ConnectionSuccess, ConnectionFailure]

class APISuccess[T](BaseModel):
    success: Literal[True]
    data: T
    cached: bool
class APIFailure(BaseModel):
    success: Literal[False]
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

FieldID = numeric | None

class FieldsetEvent(BaseModel, ABC):
    type: str

class FieldMatchAssigned(FieldsetEvent):
    type: Literal["fieldMatchAssigned"]
    field_id: FieldID
    match: MatchTuple

class FieldActivated(FieldsetEvent):
    type: Literal["fieldActivated"]
    field_id: FieldID

class MatchStarted(FieldsetEvent):
    type: Literal["matchStarted"]
    field_id: FieldID

class MatchStopped(FieldsetEvent):
    type: Literal["matchStopped"]
    field_id: FieldID

class AudienceDisplayChanged(FieldsetEvent):
    type: Literal["audienceDisplayChanged"]
    display: AudienceDisplay

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

FieldsetEventTypes = [
    FieldMatchAssigned,
    FieldActivated,
    MatchStarted,
    MatchStopped,
    AudienceDisplayChanged
]

class FieldsetCommand(BaseModel, ABC):
    cmd: str

class StartMatch(FieldsetCommand):
    cmd: Literal["start"]
    field_id: numeric

class EndMatchEarly(FieldsetCommand):
    cmd: Literal["endEarly"]
    field_id: numeric

class AbortMatch(FieldsetCommand):
    cmd: Literal["abort"]
    field_id: numeric

class ResetTimer(FieldsetCommand):
    cmd: Literal["reset"]
    field_id: numeric

class QueuePreviousMatch(FieldsetCommand):
    cmd: Literal["queuePrevMatch"]

class QueueNextMatch(FieldsetCommand):
    cmd: Literal["queueNextMatch"]

class QueueSkills(FieldsetCommand):
    cmd: Literal["queueSkills"]
    skills_id: QueueSkillsType

class SetAudienceDisplay(FieldsetCommand):
    cmd: Literal["setAudienceDisplay"]
    display: AudienceDisplay

class QueueSkillsType(Enum):
    Programming = 1
    Driver = 2

FieldsetCommandTypes = [
    StartMatch,
    EndMatchEarly,
    AbortMatch,
    ResetTimer,
    QueuePreviousMatch,
    QueueNextMatch,
    QueueSkills,
    SetAudienceDisplay
]

class ActiveMatchType(Enum):
    NONE = 0
    Timeout = 1
    Match = 2

class QueueState(Enum):
    Unplayed = 0
    Running = 1
    Stopped = 2

class FieldsetMatch(BaseModel, ABC):
    type: ActiveMatchType

class FieldsetMatchActiveNone(FieldsetMatch):
    type: Literal[ActiveMatchType.NONE]
class FieldsetMatchActiveTimeout(FieldsetMatch):
    type: Literal[ActiveMatchType.Timeout]
    state: QueueState
    field_id: numeric
    active: bool
class FieldsetMatchActiveMatch(FieldsetMatch):
    type: Literal[ActiveMatchType.Match]
    state: QueueState
    match: MatchTuple
    field_id: numeric
    active: bool

class FieldsetState(BaseModel):
    match: FieldsetMatch
    audience_display: AudienceDisplay

class FieldsetEvents(BaseModel):
    # https://github.com/brenapp/vex-tm-client/blob/eb106aff4e4ea47467b51a08dd76dfa9bde1db6e/src/Fieldset.ts#L159
    pass

# https://github.com/brenapp/vex-tm-client/blob/eb106aff4e4ea47467b51a08dd76dfa9bde1db6e/src/Fieldset.ts#L167

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
