"""
Example background tasks.

Tasks can be imported and registered from here, or you can create
tasks in separate modules and import them in your app's ready() method.
"""

# Import task modules here to ensure they're registered
from .validation import *  # noqa F401
