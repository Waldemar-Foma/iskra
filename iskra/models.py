# models.py (обновлен, но в основном тот же)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    preferences = db.Column(db.Text, default='{}')
    
    def __repr__(self):
        return f'<User {self.username}>'

class Agent(db.Model):
    __tablename__ = 'agents'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # Базовая, Продвинутая, Бесконечная
    mood = db.Column(db.String(50), default='нейтральный')
    energy = db.Column(db.Float, default=1.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    position_x = db.Column(db.Float, default=0.0)
    position_y = db.Column(db.Float, default=0.0)
    position_z = db.Column(db.Float, default=0.0)
    
    def __repr__(self):
        return f'<Agent {self.name} ({self.type})>'

class AgentMemory(db.Model):
    __tablename__ = 'agent_memories'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'))
    memory_type = db.Column(db.String(50))  # наблюдение, взаимодействие, мысль
    content = db.Column(db.Text)
    significance = db.Column(db.Float, default=0.5)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    agent = db.relationship('Agent', backref='memories')

class Event(db.Model):
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    event_text = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    agent1 = db.Column(db.String(100))
    agent2 = db.Column(db.String(100))
    event_type = db.Column(db.String(50), default='взаимодействие')  # взаимодействие, мир, пользователь
    world_cycle = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<Event {self.id}: {self.event_text[:50]}>'

class Relationship(db.Model):
    __tablename__ = 'relationships'
    
    id = db.Column(db.Integer, primary_key=True)
    agent1 = db.Column(db.String(100), nullable=False)
    agent2 = db.Column(db.String(100), nullable=False)
    relationship_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('agent1', 'agent2', name='unique_relationship'),)

class WorldState(db.Model):
    __tablename__ = 'world_state'
    
    id = db.Column(db.Integer, primary_key=True)
    cycle = db.Column(db.Integer, default=0)
    complexity = db.Column(db.Float, default=1.0)
    last_update = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)