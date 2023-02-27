import json

from owomatic import BLACKLIST_PATH


def add_user_to_blacklist(user_id: int) -> None:
    """
    This function will add a user based on its ID in the blacklist.json file.
    :param user_id: The ID of the user that should be added into the blacklist.json file.
    """
    data = json.loads(BLACKLIST_PATH.read_text())
    if user_id not in data["ids"]:
        data["ids"].append(user_id)
        BLACKLIST_PATH.write_text(json.dumps(data, indent=4))


def remove_user_from_blacklist(user_id: int) -> None:
    """
    This function will remove a user based on its ID from the blacklist.json file.
    :param user_id: The ID of the user that should be removed from the blacklist.json file.
    """
    data = json.loads(BLACKLIST_PATH.read_text())
    data["ids"].remove(user_id)
    BLACKLIST_PATH.write_text(json.dumps(data, indent=4))
