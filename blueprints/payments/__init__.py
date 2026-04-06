"""blueprints/payments/__init__.py"""
from flask import Blueprint
payments_bp = Blueprint("payments", __name__, url_prefix="/payments")
from . import routes