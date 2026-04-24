"""Example application using credential-based authentication in CPAIOPS library.

This example demonstrates how to:
1. Initialize the CPAIOPS client using username, password, and mgmt_ip.
2. Rely on the auto-created in-memory SQLite database.
3. Perform a simple API call to retrieve the management server's API version.
"""

import asyncio
import os

from cpaiops import CPAIOPSClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env")
load_dotenv(".env.secrets")


async def main() -> None:
    """Run the credential-based example application."""

    # Retrieve credentials from environment variables (provided in .env.secrets)
    mgmt_ip = os.getenv("API_MGMT")
    username = os.getenv("API_USERNAME")
    password = os.getenv("API_PASSWORD")

    if not all([mgmt_ip, username, password]):
        print("Error: API_MGMT, API_USERNAME, and API_PASSWORD must be set in environment.")
        return

    print(f"Connecting to management server at {mgmt_ip} as user '{username}'...")

    # Create CPAIOPS client with credential-based authentication.
    # Note: No 'engine' or 'settings' provided; the client auto-creates
    # an in-memory SQLite database and manages its own settings.
    client = CPAIOPSClient(
        username=username,
        password=password,
        mgmt_ip=mgmt_ip,
    )

    try:
        async with client:
            # The management server name in credential mode defaults to the IP address
            server_names = client.get_mgmt_names()
            if not server_names:
                print("No management servers registered.")
                return

            mgmt_name = server_names[0]
            print(f"Successfully registered server: {mgmt_name}")

            # Perform a simple API call to get the API version
            print(f"Retrieving API version for {mgmt_name}...")
            result = await client.api_call(mgmt_name, "show-api-versions")

            if result.success:
                versions_data = result.data or {}
                # 'show-api-versions' typically returns a dictionary with 'current-version'
                current_version = versions_data.get("current-version", "Unknown")
                print(f"Success! Current API Version: {current_version}")
            else:
                print(f"API call failed: {result.message} (Code: {result.code})")

    except Exception as e:
        print(f"\nCaught Exception: {e}")
    finally:
        # Client handles disposal of its auto-created engine
        print("Client closed.")


if __name__ == "__main__":
    asyncio.run(main())
