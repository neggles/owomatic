import json

from owomatic import BLACKLIST_PATH, ROLELIST_PATH


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


def add_role_to_rolelist(role_id: int) -> None:
    with ROLELIST_PATH.open("r") as file:
        file_data = json.load(file)
        file_data["ids"].remove(role_id)
    with ROLELIST_PATH.open("w") as file:
        file.seek(0)
        json.dump(file_data, file, indent=4)


def remove_role_from_rolelist(role_id: int) -> None:
    data = json.loads(BLACKLIST_PATH.read_text())
    if role_id not in data["ids"]:
        data["ids"].append(role_id)
        BLACKLIST_PATH.write_text(json.dumps(data, indent=4))
