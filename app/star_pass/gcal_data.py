#!/usr/local/bin/python3
""" Google Calendar shift management classes and methods. """

# Imports - Python Standard Library
from datetime import datetime
from json import load
from math import floor
from os.path import join
from typing import Dict, List

# Constants
DATE_TIME_FORMAT = '%Y-%m-%d %H:%M'
DURATION = 20
FILE_PATH = '/workspaces/star-pass/_gitignore/_example_responses/gcal/'
FILE_NAME = 'scrimmages.json'
JSON_FILE = join(FILE_PATH, FILE_NAME)
SCRIMMAGE_ADULT_KEYWORDS = ['adult', 'wreckers']
SCRIMMAGE_ADULT_NSO_ID = 628861
SCRIMMAGE_ADULT_SO_ID = 607934
SCRIMMAGES_ADULT = [
    SCRIMMAGE_ADULT_NSO_ID,
    SCRIMMAGE_ADULT_SO_ID
]
SCRIMMAGE_JUNIOR_KEYWORDS = ['buds', 'petals']
SCRIMMAGE_JUNIOR_NSO_ID = 628862
SCRIMMAGE_JUNIOR_SO_ID = 607810
SCRIMMAGES_JUNIOR = [
    SCRIMMAGE_JUNIOR_NSO_ID,
    SCRIMMAGE_JUNIOR_SO_ID
]


class GcalData:
    """ Collect and manage Google Calendar data. """
    def __init__(
            self,
    ) -> None:
        """ Class initialization method.

            Args:
                None.

            Return:
                None.
        """

        return None

    def get_shift_length(
            self,
            shift_start: datetime,
            shift_end: datetime
    ) -> int:
        """ Determine the length of a shift.

            Args:
                shift_start (datetime):
                    datetime.datetime object with the shift start date and
                    time.

                shift_end (datetime):
                    datetime.datetime object with the shift end date and
                    time.

            Returns:
                shift_length (int):
                    Integer of shift length in minutes.
        """

        # Calculate the time delta between 'shift_start' and 'shift_end'
        delta = shift_end - shift_start

        # Determine the number of minutes rounded down to the nearest minute
        shift_length = floor(delta.seconds / 60)

        return shift_length

    def datetime_to_string(
            self,
            datetime_object: str,
            datetime_string_format: str = DATE_TIME_FORMAT
    ) -> str:
        """ Format an ISO datetime object as a string.

            Args:
                datetime_object (str[datetime]):
                    String representation of a datetime.datetime object
                    in ISO format:

                    2024-10-06T12:00:00-07:00

                datetime_string_format (str):
                    Output string format for datetime object.

            Returns:
                datetime_string (str):
                    Date and time as a string, formatted by
                    datetime_string_format.
        """

        # Create a datetime object from the ISO-formatted string
        datetime_object = datetime.fromisoformat(datetime_object)

        # Format the datetime object as a string with `datetime_string_format'`
        datetime_string = datetime_object.strftime(datetime_string_format)

        return datetime_string

    def read_shift_data(
            self,
            json_file: str = JSON_FILE
    ) -> List[Dict[str, str]]:
        """ Read shift data from a JSON file.

            Produce a list of shifts from the JSON data.

            Args:
                json_file (str):
                    Path to JSON file with Google Calendar shift data.

            Returns:
                shifts (List[Dict[str, str]]:
                    List of shift dictionaries in the format:
                    [
                        {
                            name: <summary>,
                            start: <start[dateTime]>,
                            end: <end[dateTime]>
                        },
                        {
                            name: <summary>,
                            start: <start[dateTime]>,
                            end: <end[dateTime]>
                        }
                    ]
        """

        # Read JSON file
        with open(
            file=json_file,
            mode='rt',
            encoding='utf-8'
        ) as json_data:
            # Convert JSON data to a Python dictionary
            file_data = load(json_data)

        # Create a shifts List
        shifts = []

        # Add calendar data to 'shifts'
        for shift in file_data['items']:
            # Get the shift name, start, and end values
            shift_name = shift['summary']
            shift_start = shift['start']['dateTime']
            shift_end = shift['end']['dateTime']

            # Get the shift duration
            shift_duration = self.get_shift_length(
                        shift_start=datetime.fromisoformat(shift_start),
                        shift_end=datetime.fromisoformat(shift_end)
                    )

            # Format the shift start as a string
            shift_start_string = self.datetime_to_string(
                datetime_object=shift_start
            )

            shifts.append(
                {
                    'name': shift_name,
                    'duration': shift_duration,
                    'start': shift_start_string
                }
            )

        return shifts

    def generate_shift_data(
            self
    ) -> None:
        """ Generate shift data.

            Args:
                None.

            Returns:
                None.
        """

        shifts = self.read_shift_data()

        for shift in shifts:
            # Split the start date and time into separate variables
            start_date, start_time = shift['start'].split(sep=' ')

            # Set the shift name and ID
            shift_name = shift['name']
            shift_id = ''

            # Set the shift ID for adult scrimmages
            for keyword in SCRIMMAGE_ADULT_KEYWORDS:
                if shift_name.lower().find(keyword) == 0:
                    for scrimmage in SCRIMMAGES_ADULT:
                        shift_id = scrimmage
                        print(
                            f'{shift_name},'
                            f'{shift_id},'
                            f'{start_date},'
                            f'{start_time},'
                            f'{DURATION}'
                        )

            # Set the shift ID for junior scrimmages
            for keyword in SCRIMMAGE_JUNIOR_KEYWORDS:
                if shift_name.lower().find(keyword) == 0:
                    for scrimmage in SCRIMMAGES_JUNIOR:
                        shift_id = scrimmage
                        print(
                            f'{shift_name},'
                            f'{shift_id},'
                            f'{start_date},'
                            f'{start_time},'
                            f'{DURATION}'
                        )
