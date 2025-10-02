"""
Expose primary view functions from the standalone views.py module.

Having both an inventory/views.py file and an inventory/views/ package causes
Python to resolve `inventory.views` to this package, meaning the functions
defined in views.py are not directly importable (e.g. `from inventory.views import dashboard`).

To preserve the package structure (which currently contains additional helper
modules such as debug_views.py) while still exposing the main view functions,
this __init__.py dynamically loads the sibling views.py file at runtime and
re-exports the required symbols so that external imports continue to work.
"""

import importlib.util
import sys
from pathlib import Path

# Path to the sibling views.py (one directory up from this file)
_primary_views_path = Path(__file__).resolve().parent.parent / 'views.py'

spec = importlib.util.spec_from_file_location(
    'inventory._primary_views', str(_primary_views_path)
)
_primary_views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_primary_views)

# Make the loaded module discoverable via sys.modules (optional but handy)
sys.modules['inventory._primary_views'] = _primary_views

# Explicitly re-export the main view callables so that
# `from inventory.views import dashboard` works as expected.
__all__ = [
    'landing_page', 'dashboard', 'car_create', 'car_detail', 'car_update',
    'car_delete', 'update_status', 'register', 'custom_logout',
    'subscription_callback', 'payment_success', 'payment_failed',
    'subscription_renew', 'subscription_details', 'profile'
]

globals().update({name: getattr(_primary_views, name) for name in __all__})
