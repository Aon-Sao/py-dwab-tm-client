# https://github.com/brenapp/vex-tm-client/blob/eb106aff4e4ea47467b51a08dd76dfa9bde1db6e/src/Fieldset.ts#L182
import asyncio
import json
from asyncio import Task
from contextlib import suppress
from urllib.parse import urljoin

import websockets.exceptions
from pubsub import pub
from websockets import InvalidURI, InvalidHandshake
from websockets.asyncio.client import connect, ClientConnection

from Types import ClientModel, FieldsetData, Field, APIResult, APISuccess, numeric, FieldsetEvent, FieldsetState, \
    ActiveMatchType, AudienceDisplay, FieldsetMatchActiveNone, QueueState, FieldsetMatchActiveTimeout, \
    FieldsetMatchActiveMatch, MatchTuple, APIFailure, TMError, FieldsetCommand, StartMatch, EndMatchEarly, AbortMatch, \
    ResetTimer, QueuePreviousMatch, QueueNextMatch, QueueSkillsType, QueueSkills, SetAudienceDisplay


class Fieldset:

    def __init__(self, client, data: FieldsetData):
        self.id: numeric = data.id
        self.name: str = data.name
        self.client = client
        self.websocket: ClientConnection | None = None
        self.events = None
        self.state: FieldsetState = FieldsetState(
            match=FieldsetMatchActiveNone(type=ActiveMatchType.NONE),
            audience_display=AudienceDisplay.Blank
        )

    def get_fields(self) -> APIResult:
        rs: APIResult = self.client.get(f"/api/fieldsets/{self.id}/fields")
        if rs.success:
            return APISuccess[Field](
                success=True,
                data=rs.data["fields"],
                cached=rs.cached
            )
        return rs

    def update_state(self, event: FieldsetEvent):
        match event.type:
            case "audienceDisplayChanged":
                self.state.audience_display = event.display
            case "fieldMatchAssigned":
                is_none = len(event.match.keys()) == 0 and event.field_id is None
                if is_none:
                    self.state.match = FieldsetMatchActiveNone(type=ActiveMatchType.NONE)
                else:
                    is_timeout = len(event.match.keys()) == 0
                    if is_timeout:
                        self.state.match = FieldsetMatchActiveTimeout(
                            type=ActiveMatchType.Timeout,
                            field_id=event.field_id,
                            state=QueueState.Unplayed,
                            active=False
                        )
                    else:
                        self.state.match = FieldsetMatchActiveMatch(
                            type=ActiveMatchType.Match,
                            match=event.match,
                            field_id=event.field_id,
                            state=QueueState.Unplayed,
                            active=False
                        )
            case "fieldActivated":
                match self.state.match.type:
                    case ActiveMatchType.NONE:
                        self.state.match = FieldsetMatchActiveTimeout(
                            type = ActiveMatchType.Timeout,
                            state=QueueState.Unplayed,
                            field_id=event.field_id,
                            active=True
                        )
                    case ActiveMatchType.Timeout \
                         | ActiveMatchType.Match:
                        self.state.match.active = True
                        self.state.match.field_id = event.field_id
            case "matchStarted":
                match self.state.match.type:
                    case ActiveMatchType.NONE:
                        self.state.match = FieldsetMatchActiveTimeout(
                            type=ActiveMatchType.Timeout,
                            state=QueueState.Running,
                            field_id=event.field_id,
                            active=False
                        )
                    case ActiveMatchType.Timeout \
                         | ActiveMatchType.Match:
                        self.state.match.state=QueueState.Running
                        self.state.match.field_id = event.field_id
            case "matchStopped":
                match self.state.match.type:
                    case ActiveMatchType.Timeout \
                         | ActiveMatchType.Match:
                        self.state.match.state = QueueState.Stopped

    async def connect(self) -> APIResult:
        if not (rs:=self.client.ensure_bearer()).success:
            return rs

        # url protocol should be "ws"
        uri = urljoin(self.client.connection_args.address, f"/api/fieldsets/{self.id}")
        auth_headers = self.client.get_authorization_headers(uri)

        try:
            socket = await connect(uri, additional_headers=auth_headers)
            self.websocket = socket
            # Should live in the event loop forever
            asyncio.create_task(self.listen_loop())
            # Subscribe basic send and receive handlers
            pub.subscribe(self.ws_receiver, "ws_receive")
            pub.subscribe(self.ws_transmitter, "ws_transmit")
            return APISuccess(
                success=True,
                data=socket,
                cached=False
            )
        except InvalidURI as e:
            return APIFailure(
                success=False,
                error=TMError.WebSocketInvalidURL,
                error_details=e
            )
        except OSError | InvalidHandshake | TimeoutError as e:
            return APIFailure(
                success=False,
                error=TMError.WebSocketError,
                error_details=e
            )

    async def listen_loop(self):
        if self.websocket is not None:
            # An infinite async iterator
            async for response in self.websocket:
                pub.sendMessage("ws_receive", message=response)

    def ws_receiver(self, data):
        print(f"ws_receiver handling {data}")
        # turn data into a FieldSetEvent
        event: FieldsetEvent = data
        # update self state
        self.update_state(event)
        # emit the event type and data
        pub(event.type, event)

    async def ws_transmitter(self, data) -> Task:
        print(f"ws_transmitter handling {data}")
        async def speak(msg):
            with suppress(websockets.exceptions.ConnectionClosedOK):
                await self.websocket.send(msg)
        # Create a send task and schedule it for execution
        # We expect to send whenever the event loop is willing to yield control
        # It is important to handle exceptions from the Task to prevent it from crashing everything
        return asyncio.create_task(speak(data))

    async def disconnect(self):
        if self.websocket is not None:
            await self.websocket.close()

    async def send(self, cmd: FieldsetCommand) -> APIResult:
        message = json.dumps(cmd)
        try:
            snd_task = self.ws_transmitter(message)
        except Exception as e:
            raise e  # Later, cast to TMError as appropriate
        return APISuccess(
            success=True,
            data=None,
            cached=False
        )

    async def start_match(self, field_id: numeric) -> APIResult:
        return await self.send(StartMatch(
            cmd="start",
            field_id=field_id
        ))

    async def end_match_early(self, field_id: numeric) -> APIResult:
        return await self.send(EndMatchEarly(
            cmd="endEarly",
            field_id=field_id
        ))

    async def abort_match(self, field_id: numeric) -> APIResult:
        return await self.send(AbortMatch(
            cmd="abort",
            field_id=field_id
        ))

    async def reset_timer(self, field_id: numeric) -> APIResult:
        return await self.send(ResetTimer(
            cmd="reset",
            field_id=field_id
        ))

    async def queue_previous_match(self) -> APIResult:
        return await self.send(QueuePreviousMatch(
            cmd="queuePrevMatch",
        ))

    async def queue_next_match(self) -> APIResult:
        return await self.send(QueueNextMatch(
            cmd="queueNextMatch"
        ))

    async def queue_skills(self, skills_id: QueueSkillsType) -> APIResult:
        return await self.send(QueueSkills(
            cmd="queueSkills",
            skills_id=skills_id
        ))

    async def set_audience_display(self, display: AudienceDisplay) -> APIResult:
        return await self.send(SetAudienceDisplay(
            cmd="setAudienceDisplay",
            display=display
        ))