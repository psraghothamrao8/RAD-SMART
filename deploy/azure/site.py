# Prepares a database for the public demonstration server; deploy.sh runs it with
#   python manage.py shell -v 0 < site.py
# on the copy it is about to upload.
#
# Gives every user a new random password: CARE's fixture password is public.
# The new ones are printed as "LOGIN <username> <password>" for deploy.sh to
# keep in a local file; they are not stored anywhere else. (The plugin's
# frontend is registered by the container itself, at its own address.)
import secrets

from django.contrib.auth import get_user_model

for user in get_user_model().objects.order_by("username"):
    password = secrets.token_urlsafe(9)
    user.set_password(password)
    user.save(update_fields=["password"])
    print(f"LOGIN {user.username} {password}")
