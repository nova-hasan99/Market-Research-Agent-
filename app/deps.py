"""
Shared FastAPI dependencies.
Import `templates` here so all routes use the same Jinja2 instance.
"""
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
