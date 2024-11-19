import asyncio
import uuid
import random
from datetime import datetime
from azure.iot.hub import IoTHubRegistryManager
from azure.iot.device.aio import IoTHubDeviceClient
import logging
import json

current_date_time = datetime.now().strftime("%Y_%m_%d_%I_%M_%S_%p")
log_filename = f"iothub_log_{current_date_time}.log"

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler(log_filename, mode="w", encoding="utf-8")
logger.addHandler(file_handler)


class GenerateMacID:
    def __init__(self, num_of_ids):
        self.num_of_ids = num_of_ids

    @staticmethod
    def generate_mac():
        """Generates a random MAC address"""
        mac = [0x00, 0x16, 0x3e,
               random.randint(0x00, 0x7f),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff)]
        return '-'.join(map(lambda x: f'{x:02x}', mac))

    def generate_mac_addresses(self):
        """Generates a list of random MAC addresses"""
        mac_addresses = set()

        while len(mac_addresses) < self.num_of_ids:
            mac_addresses.add(self.generate_mac())

        return list(mac_addresses)


class DeviceHandler:
    """
    A handler for interacting with IoT Hub twins in Azure Cloud.
    """

    def __init__(self, hostname: str, shared_access_key_name: str,
                 shared_access_key: str):
        """
        Initializes the DeviceHandler with provided Azure IoT Hub credentials.

        :param hostname: The hostname of the IoT Hub.
        :param shared_access_key_name: The shared access key name.
        :param shared_access_key: The shared access key.
        """
        self.hostname = hostname
        self.shared_access_key_name = shared_access_key_name
        self.shared_access_key = shared_access_key
        self.device_client = None

    async def connect_hub(self) -> None:
        """
        Connects to the IoT Hub Registry using the provided credentials.
        """
        try:
            device_connection_string = (
                f"HostName={self.hostname};"
                f"SharedAccessKeyName={self.shared_access_key_name};"
                f"SharedAccessKey={self.shared_access_key}"
            )
            self.device_client = IoTHubRegistryManager.from_connection_string(
                device_connection_string)
            logger.info(
                "Connection established for IoTHub Registry.")
        except Exception as e:
            logger.error(
                f"Failed to connect with IoTHub Registry: {e}")

    async def create_device(self, device_id: str) -> dict:
        """
        Creates a device in the IoT Hub if it doesn't already exist and returns its credentials.

        :param device_id: The ID of the device to create.
        :return: A dictionary with the device's credentials including hostname and shared access key.
        """
        try:
            # Check if the device already exists
            device = self.device_client.get_device(device_id)
            logger.info(f"Device '{device_id}' already exists.")
        except Exception:
            logger.info(f"Creating device '{device_id}'...")
            try:
                # Create device with default SAS key and enabled status
                device = self.device_client.create_device_with_sas(
                    device_id=device_id,
                    primary_key=None,
                    secondary_key=None,
                    status="enabled"
                )
                logger.info(
                    f"Device '{device_id}' created successfully.")
            except Exception as e:
                logger.error(
                    f"Error creating device '{device_id}': {e}")
                return {}

        # Get the device's credentials (primary key)
        try:
            device_info = self.device_client.get_device(device_id)
            primary_key = device_info.authentication.symmetric_key.primary_key

            # Return the device credentials as a dictionary
            return {
                "hostname": self.hostname,
                "device_id": device_id,
                "shared_access_key": primary_key
            }

        except Exception as e:
            logger.error(
                f"Error retrieving credentials for device '{device_id}': {e}")
            return {}

    async def create_devices_from_list(self, device_ids: list[str]) -> dict:
        """
        Creates a list of devices in the IoT Hub and stores their credentials in a dictionary.

        :param device_ids: List of device IDs to be created.
        :return: A dictionary containing credentials of created devices.
        """
        all_credentials = {}

        tasks = []
        for device_id in device_ids:
            tasks.append(self.create_device(device_id))

        credentials_list = await asyncio.gather(*tasks)

        # Update credentials dictionary with device_id as key
        for i, credentials in enumerate(credentials_list):
            if credentials:
                all_credentials[device_ids[i]] = credentials

        await self.create_device_credentials_file(all_credentials)
        return all_credentials

    async def create_device_credentials_file(self, credentials: dict) -> None:
        """
        Creates a JSON file to store device credentials (hostname and shared access key).

        :param credentials: A dictionary containing device credentials.
        """
        try:
            file_path = "iothub_device_credential.json"
            with open(file_path, "w") as f:
                json.dump(credentials, f, indent=4)

            logger.info(
                f"Device credentials stored in {file_path}")

        except Exception as e:
            logger.error(f"Failed to create credentials file: {e}")

    async def connect_device(self, device_credential: dict) -> None:
        """
        Connects a single device to IoT Hub using provided credentials.

        :param device_credential: A dictionary containing the device's credentials.
        """
        connection_string = (
            f"HostName={device_credential['hostname']};"
            f"DeviceId={device_credential['device_id']};"
            f"SharedAccessKey={device_credential['shared_access_key']}"
        )
        try:
            device_client = IoTHubDeviceClient.create_from_connection_string(
                connection_string)
            await device_client.connect()
            logger.info(
                f"Device {device_credential['device_id']} connected successfully.")
            await device_client.disconnect()
        except Exception as e:
            logger.error(
                f"Failed to connect device {device_credential['device_id']}: {e}")

    async def connect_all_devices(self, all_credentials: dict) -> None:
        """
        Connects all devices in IoT Hub using their credentials.

        :param all_credentials: Dictionary containing credentials of all devices.
        """
        tasks = []
        for device_id, credentials in all_credentials.items():
            tasks.append(self.connect_device(credentials))
        await asyncio.gather(*tasks)


async def main():
    generate_mac_handler = GenerateMacID(
        num_of_ids=int(input("Enter number to generate MacIDs: "))
    )
    device_handler = DeviceHandler(
        hostname="<your-iothub-hostname>",
        shared_access_key_name="<your-iothub-shared-access-key-name>",
        shared_access_key="<your-iothub-shared-access-key>",
    )
    try:
        # Connect to IoT Hub
        await device_handler.connect_hub()

        # List of device IDs to create
        mac_ids = generate_mac_handler.generate_mac_addresses()
        logger.info(f"mac_ids: {mac_ids}")

        # Create devices from list and retrieve credentials
        all_credentials = await device_handler.create_devices_from_list(
            mac_ids)

        # Prompt user to connect all devices after creation
        user_response = input(
            "Do you want to connect all devices now? (yes/no): ").strip().lower()
        if user_response == 'yes':
            logger.info("Connecting all devices...")
            await device_handler.connect_all_devices(all_credentials)
        else:
            logger.info(
                "Device creation completed. Devices are not connected.")

    except Exception as e:
        logger.info(f"Exception occurred: {e}")
        logger.error(
            f"Twin connection failed with IoTHub: {e}")


if __name__ == "__main__":
    asyncio.run(main())
