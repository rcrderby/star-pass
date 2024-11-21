#!/usr/local/bin/python3
""" Tool for sorting a roster into derby number order. """

# Imports - Python Standard Library
from pathlib import Path

# Imports - Python Third-Party
from pandas import DataFrame, ExcelWriter, read_excel
from pandas.io.formats import excel

# Disable automatic border formatting in column headings
excel.ExcelFormatter.header_style = None


# Constants
CURRENT_DIR = Path(__file__).parent
INPUT_FILE_NAME = 'roster_data.xlsx'
INPUT_FILE = Path.joinpath(
    CURRENT_DIR,
    INPUT_FILE_NAME
)
INPUT_WORKSHEET = 'Sheet1'

OUTPUT_FILE_NAME = 'sorted_roster_data.xlsx'
OUTPUT_FILE = Path.joinpath(
    CURRENT_DIR,
    OUTPUT_FILE_NAME
)
SORT_COLUMN = 'number'
OUTPUT_WORKSHEET = 'Sheet2'


def import_roster_data() -> DataFrame:
    """ Import an Excel roster file as a Pandas DataFrame.

        Args:
            None.

        Returns:
            roster_data (DataFrame):
                Pandas DataFrame object with imported roster data
                values converted to strings.
    """

    roster_data = read_excel(
        io=INPUT_FILE,
        dtype='str',
        sheet_name=INPUT_WORKSHEET,
    )

    return roster_data


def sort_roster_data(
        roster_data: DataFrame
) -> DataFrame:
    """ Sort roster data in a DataFrame in alphabetical order.

    Description

        Args:
            roster_data (DataFrame):
                Pandas DataFrame object with imported roster data.

        Returns:
            sorted_roster_data (DataFrame):
                DataFrame sorted alphabetically by number.  A.K.A,
                sorted by 'derby number order'.
    """

    # Sort the DataFrame by the 'number' column as string values
    sorted_roster_data = roster_data.sort_values(
        by=SORT_COLUMN
    )

    return sorted_roster_data


def export_roster_data(
        sorted_roster_data: DataFrame
) -> None:
    """ Add a new worksheet to an Excel file with sorted roster data.

    Description

        Args:
            sorted_roster_data (DataFrame):
                DataFrame sorted alphabetically by number.  A.K.A,
                sorted by 'derby number order'.

        Returns:
            None.
    """

    with ExcelWriter(
        path=INPUT_FILE_NAME,
        mode='a',
        if_sheet_exists='replace'
    ) as writer:
        sorted_roster_data.to_excel(
            excel_writer=writer,
            # excel_writer=OUTPUT_FILE_NAME,
            index=False,
            sheet_name=OUTPUT_WORKSHEET
        )

    return None


def main() -> None:
    """ Main application.

        Args:
            None.

        Returns:
            None.
    """

    # Import roster data
    roster_data = import_roster_data()

    # Sort roster data
    sorted_roster_data = sort_roster_data(
        roster_data=roster_data
    )

    # Export roster data
    export_roster_data(
        sorted_roster_data=sorted_roster_data
    )

    return None


if __name__ == '__main__':
    main()
    # pass
