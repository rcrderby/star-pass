#!/usr/bin/env python3
""" Test deleting users in bulk. """

# Imports - Python Standard Library
from os import getenv, path
from typing import List

# Imports - Third-Party
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Constants - GetConnected
AMPLIFY_TOKEN = getenv(key='AMPLIFY_TOKEN')
DEFAULT_HEADERS = {
    'Authorization': f'Bearer {AMPLIFY_TOKEN}',
    'Accept': 'application/json'
}
BASE_URL = getenv(key='BASE_URL')
ENDPOINT = '/users'
PARAMS = '?user_email='

# Constants - input files
INPUT_DATA_DIR = '../_gitignore/_deactivate_list_files'
INPUT_DATA_FILE = 'full_deactivate_list.txt'
INPUT_DATA_PATH = path.join(INPUT_DATA_DIR, INPUT_DATA_FILE)

# Constants - output files
OUTPUT_DATA_DIR = INPUT_DATA_DIR
OUTPUT_DATA_FILE = 'user_ids.txt'
OUTPUT_DATA_PATH = path.join(OUTPUT_DATA_DIR, OUTPUT_DATA_FILE)


class UserOperations:
    """ Class object to manipulate GetConnected response data. """

    def __init__(self) -> None:
        """ Class initialization method. """

        # Import the raw data
        self.user_emails = self.get_user_emails()

    def get_user_emails(self) -> List[str]:
        """ Import user email addresses from a text file.

            Args:
                None

            Returns:
                user_data (List[str]):
                    List of email addresses.
        """

        # Open the data file
        with open(
            file=INPUT_DATA_PATH,
            mode='r',
            encoding='utf=8'
        ) as user_emails:
            # Read the list of user emails
            user_emails = user_emails.readlines()

            # Convert the data to a list
            user_emails = list(user_emails)

        return user_emails

    def get_user_ids(self) -> List[str]:
        """ Get user IDs from a list of user emails.

            Args:
                None

            Returns:
                user_ids (List[str]):
                    List of user IDs.
        """

        # Create a list object to contain user IDs
        user_ids = []

        # Loop over the list of user emails to get user IDs
        for index, user_email in enumerate(
            self.user_emails,
            start=1
        ):
            # Construct URL
            url = f'{BASE_URL}{ENDPOINT}{PARAMS}{user_email}'

            # Send API request
            response_data = requests.get(
                url=url,
                headers=DEFAULT_HEADERS,
                timeout=3
            )

            # Output the iteration index with no new line break
            print(
                f'{index}. ',
                end=''
            )

            # Skip to the next user if the status code is 404
            if response_data.status_code == 404:
                print(f'User {user_email.strip()} not found.')
                continue

            # Get the user ID
            try:
                user_id = response_data.json()['data'][0].get('id')
                print(f'Found ID {user_id} for user {user_email.strip()}.')

                # Add the user ID to the user ID list
                user_ids.append(user_id)

            except KeyError as e:
                print(f'Error fetching user data for {user_email}.')
                print(f'{e!r}\n')
                continue

        return user_ids

    def deactivate_user_ids(
        self,
        user_ids: List[str]
    ) -> None:
        """ Deactivate users with a list of user IDs.

            Args:
                user_ids (List[str]):
                    List of user IDs.

            Returns:
                None
        """

        # Loop over the list of user IDs
        for user_id in user_ids:
            # Construct URL
            url = f'{BASE_URL}{ENDPOINT}/{user_id}'
            # Send API request
            response_data = requests.delete(
                url=url,
                headers=DEFAULT_HEADERS,
                timeout=3
            )

            if response_data.ok:
                # Display the request status
                print(f'Deactivated user ID {user_id}.')

        return None

    def write_user_ids(
        self,
        user_ids: List[str]
    ) -> None:
        """ Write user IDs to a file.

            Args:
                user_ids (List[str]):
                    List of user IDs.

            Returns:
                None
        """

        # Add line breaks to the list of user IDs
        user_id_list = [
            f'{user_id}\n' for user_id in user_ids
        ]

        # Write the User ID list to a file
        with open(
            file=OUTPUT_DATA_PATH,
            mode='w',
            encoding='utf-8'
        ) as user_id_output:
            # Write file data adding line breaks with a list comprehension
            user_id_output.writelines(user_id_list)

        return None
