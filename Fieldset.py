import asyncio
import json
from asyncio import Task
from contextlib import suppress
from typing import Callable, Any
from urllib.parse import urlparse, ParseResult

import websockets
from pubsub import pub
from pubsub.core import Listener
from websockets import ClientConnection

from Types import FieldsetData, Field, APIResult, APISuccess, numeric, FieldsetEvent, FieldsetState, \
    ActiveMatchType, AudienceDisplay, FieldsetMatchActiveNone, QueueState, FieldsetMatchActiveTimeout, \
    FieldsetMatchActiveMatch, APIFailure, TMError, FieldsetCommand, StartMatch, EndMatchEarly, AbortMatch, \
    ResetTimer, QueuePreviousMatch, QueueNextMatch, QueueSkillsType, QueueSkills, SetAudienceDisplay, \
    FieldsetEventTypes, FieldMatchAssigned, FieldActivated, MatchStarted, MatchStopped, \
    AudienceDisplayChanged


class Fieldset:

    def __init__(self: Fieldset, client, data: FieldsetData):
        self.id: numeric = data.id
        self.name: str = data.name
        self.client = client  # Of type Client, not imported to prevent circular imports
        self.websocket: websockets.ClientConnection | None = None
        self.listeners: list[dict] = []
        self.state: FieldsetState = FieldsetState(
            match=FieldsetMatchActiveNone(),
            audience_display=AudienceDisplay.Blank
        )

    def get_fields(self: Fieldset) -> APIResult:
        rs: APIResult = self.client.get(f"/api/fieldsets/{self.id}/fields")
        if rs.success:
            data: list[Field] = [Field(id=f["id"], name=f["name"]) for f in rs.data["fields"]]
            return APISuccess[list[Field]](
                data=data,
                cached=rs.cached
            )
        return rs

    def update_state(self: Fieldset, event: FieldsetEvent) -> None:
        match event.type:
            case "audienceDisplayChanged":
                self.state.audience_display = event.display
            case "fieldMatchAssigned":
                is_none: bool = (event.match is None or len(event.match.keys()) == 0) and event.field_id is None
                if is_none:
                    self.state.match = FieldsetMatchActiveNone()
                else:
                    is_timeout: bool = len(event.match.keys()) == 0
                    if is_timeout:
                        self.state.match = FieldsetMatchActiveTimeout(
                            field_id=event.field_id,
                            state=QueueState.Unplayed,
                            active=False
                        )
                    else:
                        self.state.match = FieldsetMatchActiveMatch(
                            match=event.match,
                            field_id=event.field_id,
                            state=QueueState.Unplayed,
                            active=False
                        )
            case "fieldActivated":
                match self.state.match.type:
                    case ActiveMatchType.NONE:
                        self.state.match = FieldsetMatchActiveTimeout(
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
        return None

    async def connect(self: Fieldset) -> APIResult:
        if not (rs:=self.client.bearer.ensure()).success:
            return rs

        # url protocol should be "ws"
        base: ParseResult = urlparse(self.client.connection_args.address)
        base = base._replace(scheme="ws")
        path: str = f"/api/fieldsets/{self.id}"
        base = base._replace(path=path)
        uri: str = base.geturl()
        auth_headers: dict = self.client.get_authorization_headers(uri)

        # After examining the packets with Wireshark, I noticed duplication of the Host header.
        # The websockets / websocket-client libraries both append it without checking for it.
        # DWAB's Tournament Manager rejects with 401 unless I deduplicate this header.
        del auth_headers["Host"]

        try:
            self.websocket = await websockets.connect(uri, additional_headers=auth_headers)
            # Should live in the event loop forever
            asyncio.create_task(self.listen_loop())
            # Subscribe basic send and receive handlers
            pub.subscribe(self.ws_receiver, "ws_receive")
            pub.subscribe(self.ws_transmitter, "ws_transmit")
            return APISuccess(
                data=self.websocket,
                cached=False
            )
        except websockets.exceptions.InvalidURI as e:
            return APIFailure(
                error=TMError.WebSocketInvalidURL,
                error_details=e
            )
        except TimeoutError as e:  # | OSError | InvalidHandshake ...but python complains about inheritance
            return APIFailure(
                error=TMError.WebSocketError,
                error_details=e
            )

    @staticmethod
    def get_fieldset_event(data_str: str) -> FieldsetEvent | None:
        data: dict[str, Any] = json.loads(data_str)
        data = {k: v if v else None for k, v in data.items()}
        match data["type"]:
            case "fieldMatchAssigned":
                return FieldMatchAssigned(
                    field_id=data["fieldID"],
                    match=data["match"]
                )
            case "fieldActivated":
                return FieldActivated(
                    field_id=data["fieldID"],
                )
            case "matchStarted":
                return MatchStarted(
                    field_id=data["fieldID"]
                )
            case "matchStopped":
                return MatchStopped(
                    field_id=data["fieldID"]
                )
            case "audienceDisplayChanged":
                return AudienceDisplayChanged(
                    display=data["display"]
                )
        return None

    async def listen_loop(self: Fieldset) -> None:
        if self.websocket is not None:
            # An infinite async iterator
            async for response in self.websocket:
                pub.sendMessage("ws_receive", data=response)
        return None

    def ws_receiver(self: Fieldset, data: str) -> None:
        # turn data into a FieldSetEvent
        event: FieldsetEvent = Fieldset.get_fieldset_event(data)
        print(f"ws_receiver handling\n{event}")
        # update self state
        self.update_state(event)
        # emit the event type and data
        pub.sendMessage(event.type, event=event)
        return None

    async def ws_transmitter(self: Fieldset, data: str) -> Task:
        print(f"ws_transmitter handling \n{data}")
        async def speak(msg):
            with suppress(websockets.exceptions.ConnectionClosedOK):
                await self.websocket.send(msg)
        # Create a send task and schedule it for execution
        # We expect to send whenever the event loop is willing to yield control
        # It is important to handle exceptions from the Task to prevent it from crashing everything
        return asyncio.create_task(speak(data))

    async def disconnect(self: Fieldset) -> None:
        if self.websocket is not None:
            await self.websocket.close()
        return None

    async def send(self: Fieldset, cmd: FieldsetCommand) -> APIResult:
        message: str = json.dumps(cmd)
        try:
            snd_task = self.ws_transmitter(message)
        except Exception as e:
            raise e  # Later, cast to TMError as appropriate
        return APISuccess(
            data=None,
            cached=False
        )

    def on_event(self: Fieldset, event_type: str, func: Callable[[FieldsetEvent], Any]) -> Listener:
        """func must have exactly one parameter named 'event'
        Fieldset will store a reference to func to avoid it being garbage collected

        Note for control flow. Any call to this function subscribes the passed
        func to the give event_type until the listener is removed with remove_listener"""
        if event_type not in FieldsetEventTypes:
            raise ValueError(f"event_type must be in {FieldsetEventTypes}")
        else:
            listener: Listener = pub.subscribe(event_type, func)
            self.listeners.append({ "topic": event_type, "listener": listener, "origin_func": func})
            return listener

    def remove_listener(self: Fieldset, event_type: str, listener: Listener) -> Listener:
        if event_type not in FieldsetEventTypes:
            raise ValueError(f"event_type must be in {FieldsetEventTypes}")
        self.listeners.remove({ "topic": event_type, "listener": listener, "origin_func": listener.getCallable()})
        listener: Listener = pub.unsubscribe(event_type, listener)
        return listener


    async def start_match(self: Fieldset, field_id: numeric) -> APIResult:
        return await self.send(StartMatch(field_id=field_id))

    async def end_match_early(self: Fieldset, field_id: numeric) -> APIResult:
        return await self.send(EndMatchEarly(field_id=field_id))

    async def abort_match(self: Fieldset, field_id: numeric) -> APIResult:
        return await self.send(AbortMatch(field_id=field_id))

    async def reset_timer(self: Fieldset, field_id: numeric) -> APIResult:
        return await self.send(ResetTimer(field_id=field_id))

    async def queue_previous_match(self: Fieldset) -> APIResult:
        return await self.send(QueuePreviousMatch())

    async def queue_next_match(self: Fieldset) -> APIResult:
        return await self.send(QueueNextMatch())

    async def queue_skills(self: Fieldset, skills_id: QueueSkillsType) -> APIResult:
        return await self.send(QueueSkills(skills_id=skills_id))

    async def set_audience_display(self: Fieldset, display: AudienceDisplay) -> APIResult:
        return await self.send(SetAudienceDisplay(display=display))