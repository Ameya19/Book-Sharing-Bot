#(©)Book-Sharing-Bot

import json
import os

ADMIN_FILE = "admins.json"

def load_admins():
    if os.path.exists(ADMIN_FILE):
        with open(ADMIN_FILE, "r") as f:
            data = json.load(f)
            return data.get("admins", [])
    return []

def save_admins(admin_list):
    with open(ADMIN_FILE, "w") as f:
        json.dump({"admins": admin_list}, f)

def add_admin(user_id):
    admins = load_admins()
    if user_id not in admins:
        admins.append(user_id)
        save_admins(admins)
        return True
    return False

def remove_admin(user_id):
    admins = load_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_admins(admins)
        return True
    return False

def get_all_admins():
    return load_admins()

def is_admin(user_id):
    return user_id in load_admins()
