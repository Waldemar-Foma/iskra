# models.py (обновлен, но в основном тот же)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, unique=True)
    username = db.Column(db.String(80), unique=True)
    usernametg = db.Column(db.String(80), unique=True)
    full_name = db.Column(db.String(160), unique=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.Text)
    subscription_tier = db.Column(db.String(80))
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    is_active = db.Column(db.Integer, default='0')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    preferences = db.Column(db.Text, default='{}')
    
    def __repr__(self):
        return f'<User {self.username}>'

class Agent(db.Model):
    __tablename__ = 'agent'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    mood = db.Column(db.String(50), default='нейтральный')
    energy = db.Column(db.Float, default=1.0)
    position_x = db.Column(db.Float, default=0.0)
    position_y = db.Column(db.Float, default=0.0)
    position_z = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Agent {self.name}>'

class WorldState(db.Model):
    __tablename__ = 'world_state'
    id = db.Column(db.Integer, primary_key=True)
    cycle = db.Column(db.Integer, default=0)
    complexity = db.Column(db.Float, default=1.0)
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<WorldState cycle={self.cycle}>'

# Таблицы с внешними ключами
class AgentMemory(db.Model):
    __tablename__ = 'agent_memory'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    memory_type = db.Column(db.String(50))
    content = db.Column(db.Text)
    significance = db.Column(db.Float, default=0.5)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    agent = db.relationship('Agent', backref=db.backref('memories', lazy=True))
    
    def __repr__(self):
        return f'<Memory {self.id}>'

class Dialogue(db.Model):
    __tablename__ = 'dialogue'
    id = db.Column(db.Integer, primary_key=True)
    agent1_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    agent2_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    agent1_name = db.Column(db.String(100))
    agent2_name = db.Column(db.String(100))
    message = db.Column(db.Text)
    response = db.Column(db.Text)  # Новое поле для ответа
    response_id = db.Column(db.Integer)  # ID ответного сообщения
    response_to = db.Column(db.Integer)  # ID сообщения, на которое отвечаем
    dialogue_type = db.Column(db.String(50))
    world_cycle = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    agent1 = db.relationship('Agent', foreign_keys=[agent1_id], backref=db.backref('dialogues_initiated', lazy=True))
    agent2 = db.relationship('Agent', foreign_keys=[agent2_id], backref=db.backref('dialogues_received', lazy=True))
    
    def __repr__(self):
        return f'<Dialogue {self.agent1_name} -> {self.agent2_name}>'

class UserAgentChat(db.Model):
    __tablename__ = 'user_agent_chat'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    message = db.Column(db.Text)
    response = db.Column(db.Text)
    sender_type = db.Column(db.String(20))  # 'user' или 'agent'
    conversation_id = db.Column(db.String(100))  # для группировки сообщений в диалоге
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    response_received = db.Column(db.Boolean, default=False)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('chats', lazy=True))
    agent = db.relationship('Agent', backref=db.backref('user_chats', lazy=True))
    
class AgentThought(db.Model):
    __tablename__ = 'agent_thought'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agent.id'))
    agent_name = db.Column(db.String(100))
    thought = db.Column(db.Text)
    thought_type = db.Column(db.String(50))
    world_cycle = db.Column(db.Integer)
    significance = db.Column(db.Float, default=0.5)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    agent = db.relationship('Agent', backref=db.backref('thoughts', lazy=True))
    
    def __repr__(self):
        return f'<Thought {self.agent_name}: {self.thought[:50]}...>'

class Relationship(db.Model):
    __tablename__ = 'relationship'
    id = db.Column(db.Integer, primary_key=True)
    agent1 = db.Column(db.String(100))
    agent2 = db.Column(db.String(100))
    relationship_value = db.Column(db.Float, default=0.0)
    
    def __repr__(self):
        return f'<Relationship {self.agent1}-{self.agent2}: {self.relationship_value}>'

class Event(db.Model):
    __tablename__ = 'event'
    id = db.Column(db.Integer, primary_key=True)
    event_text = db.Column(db.Text)
    agent1 = db.Column(db.String(100))
    agent2 = db.Column(db.String(100), nullable=True)
    event_type = db.Column(db.String(50), default='interaction')
    world_cycle = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Event {self.id}>'