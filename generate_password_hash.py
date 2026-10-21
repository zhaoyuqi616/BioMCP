import getpass

import bcrypt

p = getpass.getpass("Password (hidden): ")
if len(p) < 12:
    raise SystemExit("Use at least 12 characters for real deployment.")
print(bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode())
