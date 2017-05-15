# coding: utf-8
"""
Logic module for versioned generic object storage

At its core, this module provides a procedural wrapper of models.objects and
models.versioned_json_object_tables. At the same time, the functions contain
additional logic, e.g. for initial default permissions or object logs.

In practice, the flask-sqlalchemy database engine instance is used. So even
though the underlying models only rely on SQLAlchemy Core and not the ORM,
the functions in this module should be called from within a Flask app context.
"""


import typing
from ..models import Objects, Object, Action, ActionType
from . import object_log, user_log, permissions, errors, users, actions
import sqlalchemy.exc


def create_object(action_id: int, data: dict, user_id: int) -> Object:
    """
    Creates an object using the given action and its schema. This function
    also handles logging, object references and default object permissions.

    :param action_id: the ID of an existing action
    :param data: the object's data, which must fit to the action's schema
    :param user_id: the ID of the user who created the object
    :return: the created object
    :raise errors.ActionDoesNotExistError: when no action with the given
        action ID exists
    :raise errors.UserDoesNotExistError: when no user with the given
        user ID exists
    """
    actions.get_action(action_id)
    users.get_user(user_id)
    try:
        object = Objects.create_object(data=data, schema=None, user_id=user_id, action_id=action_id)
    except sqlalchemy.exc.IntegrityError:
        raise
    object_log.create_object(object_id=object.object_id, user_id=user_id)
    user_log.create_object(object_id=object.object_id, user_id=user_id)
    _update_object_references(object, user_id=user_id)
    permissions.set_initial_permissions(object)
    return object


def update_object(object_id: int, data: dict, user_id: int) -> None:
    """
    Updates the object to a new version. This function also handles logging
    and object references.

    :param object_id: the ID of the existing object
    :param data: the object's new data, which must fit to the object's schema
    :param user_id: the ID of the user who updated the object
    :raise errors.ObjectDoesNotExistError: when no object with the given
        object ID exists
    :raise errors.UserDoesNotExistError: when no user with the given
        user ID exists
    """
    object = Objects.update_object(object_id=object_id, data=data, schema=None, user_id=user_id)
    if object is None:
        raise errors.ObjectDoesNotExistError()
    user_log.edit_object(user_id=user_id, object_id=object.object_id, version_id=object.version_id)
    object_log.edit_object(object_id=object.object_id, user_id=user_id, version_id=object.version_id)
    _update_object_references(object, user_id=user_id)


def restore_object_version(object_id: int, version_id: int, user_id: int) -> None:
    """
    Reverts the changes made to an object and restores a specific version of
    it, while keeping the version history. This function merely adds a new
    version which sets the data and schema to those of the given version.

    :param object_id: the ID of the existing object
    :param version_id: the ID of the object's existing version
    :param user_id: the ID of the user who restored the object version
    :raise errors.ObjectDoesNotExistError: when no object with the given
        object ID exists
    :raise errors.ObjectVersionDoesNotExistError: when an object with the
        given object ID exists, but does not have a version with the given
        version ID
    :raise errors.UserDoesNotExistError: when no user with the given
        user ID exists
    """
    object = get_object(object_id=object_id, version_id=version_id)
    object = Objects.update_object(
        object_id=object_id,
        data=object.data,
        schema=object.schema,
        user_id=user_id
    )
    user_log.restore_object_version(user_id=user_id, object_id=object_id, restored_version_id=version_id, version_id=object.version_id)
    object_log.restore_object_version(object_id=object_id, user_id=user_id, restored_version_id=version_id, version_id=object.version_id)


def get_object(object_id: int, version_id: int=None) -> Object:
    """
    Returns either the current or a specific version of the object.

    :param object_id: the ID of the existing object
    :param version_id: the ID of the object's existing version
    :return: the object with the given object and version IDs
    :raise errors.ObjectDoesNotExistError: when no object with the given
        object ID exists
    :raise errors.ObjectVersionDoesNotExistError: when an object with the
        given object ID exists, but does not have a version with the given
        version ID
    """
    if version_id is None:
        object = Objects.get_current_object(object_id=object_id)
        if object is None:
            raise errors.ObjectDoesNotExistError()
    else:
        object = Objects.get_object_version(object_id=object_id, version_id=version_id)
        if object is None:
            if Objects.get_current_object(object_id=object_id) is None:
                raise errors.ObjectDoesNotExistError()
            else:
                raise errors.ObjectVersionDoesNotExistError()
    return object


def get_object_versions(object_id: int) -> typing.List[Object]:
    """
    Returns all versions of an object, sorted from oldest to newest.

    :param object_id: the ID of the existing object
    :return: the object versions
    :raise errors.ObjectDoesNotExistError: when no object with the given
        object ID exists
    """
    object_versions = Objects.get_object_versions(object_id=object_id)
    if not object_versions:
        raise errors.ObjectDoesNotExistError()
    return object_versions


def get_objects(filter_func=lambda data: True, action_filter=None) -> typing.List[Object]:
    """
    Returns all objects, optionally after filtering the objects by their data
    or by their actions' information.

    :param filter_func: a lambda that may return an SQLAlchemy filter when
        given the object table's data column
    :param action_filter: a SQLAlchemy comparator, used to query only objects
        created by specific actions
    :return: a list of all objects or those matching the given filters
    """
    if action_filter is None:
        action_table = None
    else:
        action_table = Action.__table__
    return Objects.get_current_objects(filter_func=filter_func, action_table=action_table, action_filter=action_filter)


def _get_object_properties(object: Object) -> typing.List[typing.Tuple[typing.List[str], dict, dict]]:
    """
    Returns a list of all properties of an object, as 3-tuples consisting of
    the path to the property, its schema and the actual data.

    :param object: the object
    :return: a list of one 3-tuples for reach of the object's properties
    """
    def iter_object_properties(previous_path, schema, data):
        if schema['type'] == 'object':
            for property_name in schema['properties']:
                if property_name in data:
                    for property in iter_object_properties(previous_path + [property_name], schema['properties'][property_name], data[property_name]):
                        yield property
        elif schema['type'] == 'array':
            for index, item in enumerate(data):
                for property in iter_object_properties(previous_path + [index], schema['items'], item):
                    yield property
        else:
            yield previous_path, schema, data
    return list(iter_object_properties([], object.schema, object.data))


def _update_object_references(object: Object, user_id: int) -> None:
    """
    Searches for references to other objects and updates these accordingly.

    At this time, only measurements referencing samples will be handled,
    adding an entry to the sample's object log about being used in a
    measurement.

    :param object: the updated (or newly created) object
    :param user_id: the user who caused the object update or creation
    """
    action_type = actions.get_action(object.action_id).type
    for path, schema, data in _get_object_properties(object):
        if schema['type'] == 'sample' and data is not None and data['object_id'] is not None:
            referenced_object_id = data['object_id']
            previous_referenced_object_id = None
            if object.version_id > 0:
                previous_object_version = get_object(object.object_id, object.version_id-1)
                previous_data = previous_object_version.data
                try:
                    for path_element in path:
                        previous_data = previous_data[path_element]
                except (KeyError, IndexError):
                    pass
                else:
                    if previous_data is not None and previous_data['object_id'] is not None:
                        previous_referenced_object_id = previous_data['object_id']
            if referenced_object_id != previous_referenced_object_id:
                if action_type == ActionType.MEASUREMENT:
                    object_log.use_object_in_measurement(object_id=referenced_object_id, user_id=user_id, measurement_id=object.object_id)
