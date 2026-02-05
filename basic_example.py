import asyncio

from Types import MatchRound
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
    check_client()

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
    check_division()

    async def check_fieldset():
        if (result := client.get_fieldsets()).success:
            print(result)
            fieldset = result.data[0]

            result = fieldset.get_fields()
            print(result)

            fieldset_conn = await fieldset.connect()
            print(fieldset_conn)
    await check_fieldset()

    # Define / subscribe event handlers
    # After which, start testing commands?



if __name__ == "__main__":
    asyncio.run(main())