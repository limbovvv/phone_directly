import os
from datetime import datetime
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
import pandas as pd

from config import settings
from database import get_db, engine, Base, SessionLocal
from models import User, Department, Contact, Phone, ContactPhone, Banner, Setting, AuditLog
from utils import verify_password, get_password_hash, sign_session

app = FastAPI()
app.state.session_cookie = settings.SESSION_COOKIE_NAME

Base.metadata.create_all(bind=engine)

if not os.path.exists(settings.UPLOAD_DIR):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app.mount('/static', StaticFiles(directory=os.path.join(os.path.dirname(__file__), 'static')), name='static')
app.mount('/uploads', StaticFiles(directory=settings.UPLOAD_DIR), name='uploads')
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))


def seed(db: Session):
    if not db.query(User).first():
        admin = User(login='admin', password_hash=get_password_hash('admin123'), role='admin', is_active=True)
        db.add(admin)
        db.commit()
    if not db.query(Department).first():
        root = Department(name='Центр ИТ', sort_order=1)
        dev = Department(name='Отдел разработки', parent=root, sort_order=1)
        support = Department(name='Служба поддержки', parent=root, sort_order=2)
        db.add_all([root, dev, support])
        db.commit()
    if not db.query(Contact).first():
        root = db.query(Department).filter_by(name='Центр ИТ').first()
        dev = db.query(Department).filter_by(name='Отдел разработки').first()
        c1 = Contact(full_name='Иван Петров', department=root)
        c2 = Contact(full_name='Мария Смирнова', department=dev)
        db.add_all([c1, c2])
        db.commit()
        p1 = Phone(type='city', number='123-45-67')
        p2 = Phone(type='internal', number='101')
        db.add_all([p1, p2])
        db.commit()
        db.add_all([ContactPhone(contact=c1, phone=p1), ContactPhone(contact=c2, phone=p1), ContactPhone(contact=c2, phone=p2)])
        db.commit()
    if not db.query(Banner).first():
        db.add_all([Banner(side='left', image_path='/static/img/placeholder_left.png'), Banner(side='right', image_path='/static/img/placeholder_right.png')])
        db.commit()
    if not db.query(Setting).filter_by(key='max_contacts_per_phone').first():
        # Дадим минимальный лимит 2, чтобы демо-кейсы с общим номером работали из коробки
        db.add(Setting(key='max_contacts_per_phone', value=str(max(settings.MAX_CONTACTS_PER_PHONE_DEFAULT, 2))))
        db.commit()


@app.middleware('http')
async def add_user_to_request(request: Request, call_next):
    response = Response('Internal error', status_code=500)
    try:
        db = SessionLocal()
        seed(db)
        token = request.cookies.get(app.state.session_cookie)
        request.state.current_user = None
        if token:
            from utils import unsign_session
            data = unsign_session(token)
            if data:
                user = db.query(User).filter(User.id == data.get('user_id'), User.is_active == True).first()
                request.state.current_user = user
        response = await call_next(request)
    except Exception as e:
        print(e)
        raise e
    finally:
        db.close()
    return response


# Helpers

def get_department_tree(db: Session):
    departments = db.query(Department).filter(Department.is_active == True).order_by(Department.parent_id, Department.sort_order).all()
    tree = {}
    by_id = {d.id: {"node": d, "children": []} for d in departments}
    for d in departments:
        if d.parent_id and d.parent_id in by_id:
            by_id[d.parent_id]['children'].append(by_id[d.id])
        else:
            tree[d.id] = by_id[d.id]
    return tree


def collect_department_ids(node):
    ids = [node.id]
    for child in node.children:
        ids.extend(collect_department_ids(child))
    return ids


def log_action(db: Session, user_id: int, action: str, entity: str, entity_id: int, diff_json: str = None, ip: str = None):
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, diff_json=diff_json, ip=ip))
    db.commit()


def max_contacts_per_phone(db: Session) -> int:
    setting = db.query(Setting).filter_by(key='max_contacts_per_phone').first()
    return int(setting.value) if setting else settings.MAX_CONTACTS_PER_PHONE_DEFAULT


def check_phone_limit(db: Session, phone: Phone, contact_ids_to_link):
    limit = max_contacts_per_phone(db)
    active_links = db.query(ContactPhone).join(Contact).filter(ContactPhone.phone_id == phone.id, Contact.is_archived == False).count()
    # subtract already linked in contact_ids_to_link to avoid double counting? we ensure new links not exceed limit.
    if active_links + len(contact_ids_to_link) > limit:
        return False, f"Лимит {limit} привязок для номера {phone.number}"
    return True, None


# Public routes
@app.get('/', response_class=HTMLResponse)
def public_index(request: Request, db: Session = Depends(get_db), dept_id: int | None = None, q: str | None = None):
    tree = get_department_tree(db)
    contacts_query = db.query(Contact).join(Department).filter(Contact.is_archived == False)
    if dept_id:
        dept = db.query(Department).get(dept_id)
        if dept:
            ids = collect_department_ids(dept)
            contacts_query = contacts_query.filter(Contact.department_id.in_(ids))
    if q:
        q_like = f"%{q}%"
        contacts_query = contacts_query.filter(or_(Contact.full_name.ilike(q_like), Department.name.ilike(q_like), Contact.id.in_(db.query(ContactPhone.contact_id).join(Phone).filter(Phone.number.ilike(q_like)))))
    contacts = contacts_query.order_by(Contact.full_name).all()
    banners = {b.side: b for b in db.query(Banner).all()}
    return templates.TemplateResponse('public/index.html', {
        'request': request,
        'tree': tree,
        'selected_id': dept_id,
        'contacts': contacts,
        'banners': banners,
        'q': q or ''
    })


# Auth
@app.get('/admin/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse('admin/login.html', {'request': request, 'error': None})


@app.post('/admin/login')
def login(request: Request, db: Session = Depends(get_db), login: str = Form(...), password: str = Form(...)):
    user = db.query(User).filter(User.login == login, User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse('admin/login.html', {'request': request, 'error': 'Неверный логин или пароль'}, status_code=400)
    token = sign_session({'user_id': user.id, 'ts': datetime.utcnow().timestamp()})
    resp = RedirectResponse('/admin', status_code=302)
    resp.set_cookie(app.state.session_cookie, token, httponly=True)
    return resp


@app.get('/admin/logout')
def logout():
    resp = RedirectResponse('/admin/login', status_code=302)
    resp.delete_cookie(app.state.session_cookie)
    return resp


# Admin dashboard
@app.get('/admin', response_class=HTMLResponse)
def admin_dashboard(request: Request):
    if not request.state.current_user:
        return RedirectResponse('/admin/login', status_code=302)
    return templates.TemplateResponse('admin/dashboard.html', {'request': request})


# Contacts
@app.get('/admin/contacts', response_class=HTMLResponse)
def contacts_list(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role not in ['admin', 'editor']:
        return RedirectResponse('/admin/login', status_code=302)
    contacts = db.query(Contact).order_by(Contact.full_name).all()
    departments = db.query(Department).all()
    phones = db.query(Phone).all()
    return templates.TemplateResponse('admin/contacts.html', {'request': request, 'contacts': contacts, 'departments': departments, 'phones': phones})


@app.post('/admin/contacts')
def create_contact(request: Request, db: Session = Depends(get_db), full_name: str = Form(...), department_id: int = Form(...)):
    user = request.state.current_user
    if not user or user.role not in ['admin', 'editor']:
        return RedirectResponse('/admin/login', status_code=302)
    contact = Contact(full_name=full_name, department_id=department_id)
    db.add(contact)
    db.commit()
    log_action(db, user.id, 'create', 'contact', contact.id)
    return RedirectResponse('/admin/contacts', status_code=302)


@app.post('/admin/contacts/{contact_id}/archive')
def archive_contact(request: Request, contact_id: int, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role not in ['admin', 'editor']:
        return RedirectResponse('/admin/login', status_code=302)
    contact = db.query(Contact).get(contact_id)
    if contact:
        contact.is_archived = True
        db.commit()
        log_action(db, user.id, 'archive', 'contact', contact.id)
    return RedirectResponse('/admin/contacts', status_code=302)


@app.post('/admin/contacts/{contact_id}/restore')
def restore_contact(request: Request, contact_id: int, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role not in ['admin', 'editor']:
        return RedirectResponse('/admin/login', status_code=302)
    contact = db.query(Contact).get(contact_id)
    if contact:
        contact.is_archived = False
        db.commit()
        log_action(db, user.id, 'restore', 'contact', contact.id)
    return RedirectResponse('/admin/contacts', status_code=302)


@app.post('/admin/contacts/{contact_id}/phones')
def update_contact_phones(request: Request, contact_id: int, db: Session = Depends(get_db), phone_numbers: str = Form(''), phone_types: str = Form('')):
    user = request.state.current_user
    if not user or user.role not in ['admin', 'editor']:
        return RedirectResponse('/admin/login', status_code=302)
    contact = db.query(Contact).get(contact_id)
    if not contact:
        raise HTTPException(status_code=404)
    numbers = [n.strip() for n in phone_numbers.split('\n') if n.strip()]
    types = [t.strip() for t in phone_types.split('\n') if t.strip()]
    pairs = list(zip(types, numbers))
    contact.phones.clear()
    db.commit()
    for t, num in pairs:
        phone = db.query(Phone).filter_by(type=t, number=num).first()
        if not phone:
            phone = Phone(type=t, number=num)
            db.add(phone)
            db.commit()
        ok, err = check_phone_limit(db, phone, [contact.id])
        if not ok:
            return templates.TemplateResponse('admin/contacts.html', {'request': request, 'contacts': db.query(Contact).all(), 'departments': db.query(Department).all(), 'phones': db.query(Phone).all(), 'error': err}, status_code=400)
        db.add(ContactPhone(contact_id=contact.id, phone_id=phone.id))
        db.commit()
    log_action(db, user.id, 'update_phones', 'contact', contact.id)
    return RedirectResponse('/admin/contacts', status_code=302)


# Departments
@app.get('/admin/departments', response_class=HTMLResponse)
def departments_list(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    departments = db.query(Department).order_by(Department.parent_id, Department.sort_order).all()
    return templates.TemplateResponse('admin/departments.html', {'request': request, 'departments': departments})


@app.post('/admin/departments')
def create_department(request: Request, db: Session = Depends(get_db), name: str = Form(...), parent_id: int | None = Form(None)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    dept = Department(name=name, parent_id=parent_id if parent_id else None)
    db.add(dept)
    db.commit()
    log_action(db, user.id, 'create', 'department', dept.id)
    return RedirectResponse('/admin/departments', status_code=302)


# Banners
@app.get('/admin/banners', response_class=HTMLResponse)
def banners_page(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    banners = {b.side: b for b in db.query(Banner).all()}
    return templates.TemplateResponse('admin/banners.html', {'request': request, 'banners': banners})


@app.post('/admin/banners/{side}')
def upload_banner(request: Request, side: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    if side not in ['left', 'right']:
        raise HTTPException(status_code=400)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.webp']:
        return templates.TemplateResponse('admin/banners.html', {'request': request, 'banners': {b.side: b for b in db.query(Banner).all()}, 'error': 'Неверный формат'}, status_code=400)
    path = os.path.join(settings.UPLOAD_DIR, f"{side}{ext}")
    with open(path, 'wb') as f:
        f.write(file.file.read())
    banner = db.query(Banner).filter_by(side=side).first()
    if not banner:
        banner = Banner(side=side, image_path=f"/uploads/{side}{ext}", updated_by=user.id)
        db.add(banner)
    else:
        banner.image_path = f"/uploads/{side}{ext}"
        banner.updated_by = user.id
    db.commit()
    log_action(db, user.id, 'update', 'banner', banner.id)
    return RedirectResponse('/admin/banners', status_code=302)


# Settings
@app.get('/admin/settings', response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    setting = db.query(Setting).filter_by(key='max_contacts_per_phone').first()
    return templates.TemplateResponse('admin/settings.html', {'request': request, 'value': setting.value if setting else settings.MAX_CONTACTS_PER_PHONE_DEFAULT})


@app.post('/admin/settings')
def update_settings(request: Request, db: Session = Depends(get_db), max_contacts_per_phone: int = Form(...)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    setting = db.query(Setting).filter_by(key='max_contacts_per_phone').first()
    if not setting:
        setting = Setting(key='max_contacts_per_phone', value=str(max_contacts_per_phone))
        db.add(setting)
    else:
        setting.value = str(max_contacts_per_phone)
    db.commit()
    log_action(db, user.id, 'update', 'setting', 0)
    return RedirectResponse('/admin/settings', status_code=302)


# Users (admin only)
@app.get('/admin/users', response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    users = db.query(User).all()
    return templates.TemplateResponse('admin/users.html', {'request': request, 'users': users})


@app.post('/admin/users')
def create_user(request: Request, db: Session = Depends(get_db), login: str = Form(...), password: str = Form(...), role: str = Form(...)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    if db.query(User).filter_by(login=login).first():
        return templates.TemplateResponse('admin/users.html', {'request': request, 'users': db.query(User).all(), 'error': 'Логин занят'}, status_code=400)
    new_user = User(login=login, password_hash=get_password_hash(password), role=role, is_active=True)
    db.add(new_user)
    db.commit()
    log_action(db, user.id, 'create', 'user', new_user.id)
    return RedirectResponse('/admin/users', status_code=302)


@app.post('/admin/users/{user_id}/toggle')
def toggle_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    u = db.query(User).get(user_id)
    if u:
        u.is_active = not u.is_active
        db.commit()
        log_action(db, user.id, 'toggle', 'user', u.id)
    return RedirectResponse('/admin/users', status_code=302)


# Import/Export
@app.get('/admin/import-export', response_class=HTMLResponse)
def import_export_page(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    return templates.TemplateResponse('admin/import_export.html', {'request': request, 'preview': None, 'errors': None})


@app.post('/admin/export')
def export_data(request: Request, db: Session = Depends(get_db), fmt: str = Form('csv')):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    rows = []
    contacts = db.query(Contact).all()
    for c in contacts:
        city = ';'.join([cp.phone.number for cp in c.phones if cp.phone.type == 'city'])
        internal = ';'.join([cp.phone.number for cp in c.phones if cp.phone.type == 'internal'])
        ip = ';'.join([cp.phone.number for cp in c.phones if cp.phone.type == 'ip'])
        path = []
        cur = c.department
        while cur:
            path.append(cur.name)
            cur = cur.parent
        path = ' / '.join(reversed(path))
        rows.append({'DepartmentPath': path, 'FullName': c.full_name, 'PhonesCity': city, 'PhonesInternal': internal, 'PhonesIP': ip, 'Archived': 1 if c.is_archived else 0})
    df = pd.DataFrame(rows)
    if fmt == 'xlsx':
        from io import BytesIO
        buf = BytesIO()
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        log_action(db, user.id, 'export', 'contacts', 0)
        return Response(buf.read(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="contacts.xlsx"'})
    else:
        log_action(db, user.id, 'export', 'contacts', 0)
        return Response(df.to_csv(index=False), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="contacts.csv"'})


@app.post('/admin/import')
def import_data(request: Request, db: Session = Depends(get_db), file: UploadFile = File(...)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext == '.csv':
        df = pd.read_csv(file.file)
    else:
        df = pd.read_excel(file.file)
    errors = []
    created = 0
    updated = 0
    for idx, row in df.iterrows():
        dept_path = str(row.get('DepartmentPath', '')).strip()
        full_name = row.get('FullName', '')
        try:
            archived = bool(int(row.get('Archived', 0)))
        except Exception:
            archived = False
        if not dept_path or dept_path.lower() == 'nan':
            path_parts = ['Импортированные']
        else:
            path_parts = [p.strip() for p in str(dept_path).split('/') if p.strip()]
        parent = None
        for part in path_parts:
            parent_id = parent.id if parent else None
            dept = db.query(Department).filter_by(name=part, parent_id=parent_id).first()
            if not dept:
                dept = Department(name=part, parent_id=parent_id)
                db.add(dept)
                db.commit()
            parent = dept
        department = parent
        contact = db.query(Contact).filter(Contact.full_name == full_name, Contact.department_id == department.id).first()
        is_new = False
        if not contact:
            contact = Contact(full_name=full_name, department=department)
            db.add(contact)
            db.commit()
            is_new = True
        contact.is_archived = archived
        db.commit()
        # Replace phones
        contact.phones.clear()
        db.commit()
        for col, ptype in [('PhonesCity', 'city'), ('PhonesInternal', 'internal'), ('PhonesIP', 'ip')]:
            nums = str(row.get(col, '')).split(';') if row.get(col) is not None else []
            for num in nums:
                num = str(num).strip()
                if not num or num.lower() == 'nan':
                    continue
                phone = db.query(Phone).filter_by(type=ptype, number=num).first()
                if not phone:
                    phone = Phone(type=ptype, number=num)
                    db.add(phone)
                    db.commit()
                ok, err = check_phone_limit(db, phone, [contact.id])
                if not ok:
                    errors.append(f"Строка {idx+1}: {err}")
                    db.rollback()
                    break
                db.add(ContactPhone(contact_id=contact.id, phone_id=phone.id))
                db.commit()
        if errors:
            continue
        if is_new:
            created += 1
        else:
            updated += 1
    log_action(db, user.id, 'import', 'contacts', 0, diff_json=f"created={created},updated={updated},errors={len(errors)}")
    return templates.TemplateResponse('admin/import_export.html', {'request': request, 'preview': {'created': created, 'updated': updated, 'errors': len(errors)}, 'errors': errors})


# Audit log view
@app.get('/admin/audit', response_class=HTMLResponse)
def audit_page(request: Request, db: Session = Depends(get_db)):
    user = request.state.current_user
    if not user or user.role != 'admin':
        return RedirectResponse('/admin/login', status_code=302)
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return templates.TemplateResponse('admin/audit.html', {'request': request, 'logs': logs})


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=settings.APP_HOST, port=settings.APP_PORT)
