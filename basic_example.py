import asyncio

from Types import *
from bootstrap import get_client

async def main():
    client = get_client(secrets_path="secrets.json")

    def check_client():
        result = client.connect()
        print(result)

        result = client.get_event_info()
        print(result)

        result = client.get_divisions()
        print(result)

        result = client.get_fieldsets()
        print(result)
    # check_client()

    def check_division():
        if (result := client.get_divisions()).success:
            print(result)
            division = result.data[0]

            result = division.get_teams()
            print(result)

            result = division.get_matches()
            print(result)

            result = division.get_rankings(MatchRound.Practice)
            print(result)
    # check_division()

    async def check_fieldset():
        if (result := client.get_fieldsets()).success:
            print(result)
            fieldset = result.data[0]

            result = fieldset.get_fields()
            print(result)

            fieldset_conn = await fieldset.connect()
            print(fieldset_conn)
    # await check_fieldset()

    def check_event_handling():
        if (result := client.get_fieldsets()).success:
            fieldset = result.data[0]

            def handler(event: FieldsetEvent | None = None):
                print(f"HANDLER for {ev_type} GOT {event}")

            for ev_type in FieldsetEventTypes:
                fieldset.on_event(event_type=ev_type, func=handler)

            # Need to trigger events
            for event in [
                FieldMatchAssigned(
                    field_id=1,
                    match=MatchTuple(
                        session=1,
                        division=1,
                        round=1,
                        instance=1,
                        match=1
                    )
                ),
                FieldActivated(field_id=1),
                MatchStarted(field_id=1),
                MatchStopped(field_id=1),
                AudienceDisplayChanged(display=AudienceDisplay.Logo)
            ]:
                fieldset.ws_receiver(event)
    # check_event_handling()

    def check_commands_work():
        pass
    # check_commands_work()



if __name__ == "__main__":
    asyncio.run(main())