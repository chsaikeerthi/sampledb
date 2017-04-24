# coding: utf-8
"""
Script for exporting the schema of an action in SampleDB to a JSON file.

Usage: python -m sampledb update_action <action_id> <schema_file_name>
"""

import json
import sys
from .. import create_app
from ..logic.instruments import get_action


def main(arguments):
    if len(arguments) != 2:
        print(__doc__)
        exit(1)
    action_id, schema_file_name = arguments
    try:
        action_id = int(action_id)
    except ValueError:
        print("Error: action_id must be an integer")
        exit(1)

    app = create_app()
    with app.app_context():
        action = get_action(action_id)
        if action is None:
            print('Error: no action with this id exists', file=sys.stderr)
            exit(1)
        schema = action.schema
    with open(schema_file_name, 'w') as schema_file:
        json.dump(schema, schema_file, indent=2)
    print("Success: the action schema has been exported to {}".format(schema_file_name))