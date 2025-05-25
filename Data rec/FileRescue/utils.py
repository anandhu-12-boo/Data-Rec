import os

def get_sys_username():
    """
    Dynamically find the username from the Users directory, ignoring Public, Default, and All Users folders.
    """
    users_dir = r'C:\Users'
    if os.path.exists(users_dir):
        for username in os.listdir(users_dir):
            if username.lower() not in ['public', 'default', 'all users', 'default user']:
                user_path = os.path.join(users_dir, username)
                if os.path.isdir(user_path):
                    return username
    return None

if __name__ == "__main__":
    username = get_sys_username()
    if username:
        print(f"Username: {username}")
    else:
        print("Username not found.")
