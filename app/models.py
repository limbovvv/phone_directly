from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import relationship
from database import Base


class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey('departments.id'), nullable=True)
    name = Column(String(255), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    parent = relationship('Department', remote_side=[id], backref='children')
    contacts = relationship('Contact', back_populates='department')


class Contact(Base):
    __tablename__ = 'contacts'
    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    department = relationship('Department', back_populates='contacts')
    phones = relationship('ContactPhone', back_populates='contact', cascade="all, delete-orphan")


class Phone(Base):
    __tablename__ = 'phones'
    id = Column(Integer, primary_key=True)
    type = Column(String(20), nullable=False)  # city/internal/ip
    number = Column(String(50), nullable=False)
    note = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship('ContactPhone', back_populates='phone', cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint('type', 'number', name='uq_phone_type_number'),)


class ContactPhone(Base):
    __tablename__ = 'contact_phones'
    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contacts.id'), nullable=False)
    phone_id = Column(Integer, ForeignKey('phones.id'), nullable=False)
    label = Column(String(50))
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    contact = relationship('Contact', back_populates='phones')
    phone = relationship('Phone', back_populates='contacts')

    __table_args__ = (UniqueConstraint('contact_id', 'phone_id', name='uq_contact_phone'),)


class Banner(Base):
    __tablename__ = 'banners'
    id = Column(Integer, primary_key=True)
    side = Column(String(10), unique=True, nullable=False)  # left/right
    image_path = Column(String(255), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey('users.id'))


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    login = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(10), nullable=False)  # admin/editor
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)


class AuditLog(Base):
    __tablename__ = 'audit_log'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    action = Column(String(100), nullable=False)
    entity = Column(String(100), nullable=False)
    entity_id = Column(Integer)
    diff_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    ip = Column(String(50))
