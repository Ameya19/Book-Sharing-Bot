#(©)Book-Sharing-Bot

user_data = set()

async def present_user(user_id: int):
    return user_id in user_data

async def add_user(user_id: int):
    user_data.add(user_id)

async def full_userbase():
    return list(user_data)

async def del_user(user_id: int):
    user_data.discard(user_id)
