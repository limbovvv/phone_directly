from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
from models import User
from utils import unsign_session


def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(request.app.state.session_cookie)
    if not token:
        return None
    data = unsign_session(token)
    if not data:
        return None
    user = db.query(User).filter(User.id == data.get('user_id'), User.is_active == True).first()
    return user


def require_login(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def require_admin(user: User = Depends(require_login)):
    if user.role != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def require_editor_or_admin(user: User = Depends(require_login)):
    if user.role not in ['admin', 'editor']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return user


def login_required_redirect(func):
    async def wrapper(request: Request, *args, **kwargs):
        user = request.state.current_user
        if not user:
            return RedirectResponse('/admin/login', status_code=302)
        return await func(request, *args, **kwargs)
    return wrapper
