# app.py (исправленный)
import os
import random
import string
from flask import Flask, render_template, redirect, url_for, request, flash, session, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Event, Relationship, Agent, AgentMemory, WorldState
from datetime import datetime, timedelta
import functools
import threading
import time
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eternis.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db.init_app(app)

# Фоновый поток симуляции
class AgentSimulator:
    def __init__(self):
        self.running = True
        self.agents = []
        self.thread = threading.Thread(target=self.simulate)
        self.thread.daemon = True
        
    def start(self):
        self.thread.start()
        
    def simulate(self):
        # Три модели как и требовалось
        agent_names = ['Нейрон', 'Синтез', 'Разум', 'Мысль', 'Искра', 'Код', 'Алгоритм', 'Сеть']
        agent_types = ['Базовая', 'Продвинутая', 'Бесконечная']
        
        with app.app_context():
            # Создаем начальных агентов если их нет
            if Agent.query.count() == 0:
                for i in range(5):  # Уменьшим количество агентов для наглядности
                    agent = Agent(
                        name=random.choice(agent_names) + f"-{random.randint(100, 999)}",
                        type=random.choice(agent_types),
                        mood=random.choice(['любопытный', 'нейтральный', 'возбужденный', 'уставший', 'сфокусированный']),
                        energy=random.uniform(0.3, 1.0),
                        position_x=random.uniform(-10, 10),
                        position_y=random.uniform(-10, 10),
                        position_z=random.uniform(-10, 10)
                    )
                    db.session.add(agent)
                db.session.commit()
            
            while self.running:
                try:
                    agents = Agent.query.all()
                    world = WorldState.query.first()
                    if not world:
                        world = WorldState(cycle=0, complexity=1.0)
                        db.session.add(world)
                        db.session.commit()
                    
                    # Обновляем цикл мира
                    world.cycle += 1
                    world.complexity = min(2.0, world.complexity + 0.001)
                    
                    # Взаимодействия агентов
                    for agent in agents:
                        # Случайные изменения энергии
                        agent.energy += random.uniform(-0.05, 0.05)
                        agent.energy = max(0.1, min(1.0, agent.energy))
                        
                        # Случайное движение
                        agent.position_x += random.uniform(-0.5, 0.5)
                        agent.position_y += random.uniform(-0.5, 0.5)
                        agent.position_z += random.uniform(-0.5, 0.5)
                        
                        # Изменение настроения на основе энергии
                        if agent.energy < 0.3:
                            agent.mood = 'уставший'
                        elif agent.energy > 0.8:
                            agent.mood = 'возбужденный'
                        else:
                            agent.mood = random.choice(['любопытный', 'нейтральный', 'сфокусированный'])
                        
                        # Создание воспоминаний
                        if random.random() < 0.3:
                            memory = AgentMemory(
                                agent_id=agent.id,
                                memory_type=random.choice(['наблюдение', 'взаимодействие', 'мысль']),
                                content=f"Заметил что-то интересное на цикле {world.cycle}",
                                significance=random.uniform(0.1, 1.0)
                            )
                            db.session.add(memory)
                        
                        # Создание событий
                        if random.random() < 0.2:
                            target = random.choice(agents)
                            if target.id != agent.id:
                                event = Event(
                                    event_text=f"{agent.name} → {target.name}: {random.choice(['поделился данными', 'отправил запрос', 'установил связь', 'обменялся протоколами'])}",
                                    agent1=agent.name,
                                    agent2=target.name,
                                    event_type='взаимодействие',
                                    world_cycle=world.cycle
                                )
                                db.session.add(event)
                                
                                # Обновление отношений
                                rel = Relationship.query.filter_by(
                                    agent1=min(agent.name, target.name),
                                    agent2=max(agent.name, target.name)
                                ).first()
                                
                                if rel:
                                    rel.relationship_value += random.uniform(-0.1, 0.1)
                                    rel.relationship_value = max(-1.0, min(1.0, rel.relationship_value))
                                else:
                                    rel = Relationship(
                                        agent1=min(agent.name, target.name),
                                        agent2=max(agent.name, target.name),
                                        relationship_value=random.uniform(-0.5, 0.5)
                                    )
                                    db.session.add(rel)
                    
                    # События мира
                    if random.random() < 0.1:
                        event = Event(
                            event_text=f"Состояние мира изменилось: {random.choice(['колебание ресурсов', 'пространственный сдвиг', 'обновление протоколов', 'энергетическая волна'])}",
                            agent1='СИСТЕМА',
                            agent2=None,
                            event_type='мир',
                            world_cycle=world.cycle
                        )
                        db.session.add(event)
                    
                    db.session.commit()
                    time.sleep(5)
                    
                except Exception as e:
                    print(f"Ошибка симуляции: {e}")
                    time.sleep(5)

simulator = AgentSimulator()

# Декоратор требующий авторизации
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'error')
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Валидация
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов', 'error')
            return redirect(url_for('register'))
        
        # Проверка существования пользователя
        user = User.query.filter((User.email == email) | (User.username == username)).first()
        if user:
            flash('Имя пользователя или email уже заняты', 'error')
            return redirect(url_for('register'))
        
        # Создание нового пользователя
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            preferences=json.dumps({
                'theme': 'dark',
                'notifications': True,
                'language': 'ru'
            })
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Создание приветственного события
        event = Event(
            event_text=f"Пользователь {username} присоединился к симуляции",
            agent1='СИСТЕМА',
            agent2=None,
            event_type='пользователь'
        )
        db.session.add(event)
        db.session.commit()
        
        flash('Регистрация успешна! Теперь войдите в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session.permanent = remember
            session['user_id'] = user.id
            session['username'] = user.username
            
            user.last_active = datetime.utcnow()
            db.session.commit()
            
            flash(f'С возвращением, {user.username}!', 'success')
            return redirect(url_for('profile'))
        
        flash('Неверный email или пароль', 'error')
        return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if g.user:
        event = Event(
            event_text=f"Пользователь {g.user.username} покинул симуляцию",
            agent1='СИСТЕМА',
            agent2=None,
            event_type='пользователь'
        )
        db.session.add(event)
        db.session.commit()
    
    session.clear()
    flash('Вы успешно вышли из системы', 'success')
    return redirect(url_for('index'))

@app.route('/test-500')
def test_500():
    db.session.rollback()
    return render_template('500.html'), 500


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    preferences = json.loads(user.preferences) if user.preferences else {}
    
    # Статистика пользователя
    user_events = Event.query.filter_by(event_type='пользователь').filter(
        Event.event_text.like(f'%{user.username}%')
    ).count()
    
    stats = {
        'member_since': user.created_at.strftime('%d.%m.%Y'),
        'last_active': user.last_active.strftime('%d.%m.%Y %H:%M'),
        'events_count': user_events
    }
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            new_username = request.form['username']
            new_email = request.form['email']
            
            # Проверка занятости
            existing = User.query.filter(
                (User.email == new_email) | (User.username == new_username),
                User.id != user.id
            ).first()
            
            if existing:
                flash('Имя пользователя или email уже заняты', 'error')
            else:
                user.username = new_username
                user.email = new_email
                session['username'] = new_username
                
                event = Event(
                    event_text=f"Пользователь {new_username} обновил профиль",
                    agent1='СИСТЕМА',
                    agent2=None,
                    event_type='пользователь'
                )
                db.session.add(event)
                db.session.commit()
                
                flash('Профиль успешно обновлен', 'success')
        
        elif action == 'update_password':
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']
            
            if not check_password_hash(user.password_hash, current_password):
                flash('Текущий пароль неверен', 'error')
            elif new_password != confirm_password:
                flash('Новые пароли не совпадают', 'error')
            elif len(new_password) < 6:
                flash('Пароль должен быть не менее 6 символов', 'error')
            else:
                user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Пароль успешно изменен', 'success')
        
        elif action == 'update_preferences':
            preferences['theme'] = request.form.get('theme', 'dark')
            preferences['notifications'] = request.form.get('notifications') == 'on'
            preferences['language'] = request.form.get('language', 'ru')
            user.preferences = json.dumps(preferences)
            db.session.commit()
            flash('Настройки сохранены', 'success')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user, preferences=preferences, stats=stats)

@app.route('/graphs')
def graphs():
    agents = Agent.query.all()
    relationships = Relationship.query.all()
    
    # Конвертируем в словари для JSON
    nodes = []
    for agent in agents:
        nodes.append({
            'id': agent.name,
            'type': agent.type,
            'mood': agent.mood,
            'energy': agent.energy,
            'x': agent.position_x,
            'y': agent.position_y,
            'z': agent.position_z
        })
    
    links = []
    for rel in relationships:
        links.append({
            'source': rel.agent1,
            'target': rel.agent2,
            'value': rel.relationship_value
        })
    
    return render_template('graphs.html', nodes=nodes, links=links)

@app.route('/api/graph-data')
def graph_data():
    agents = Agent.query.all()
    relationships = Relationship.query.all()
    
    nodes = [{
        'id': a.name,
        'type': a.type,
        'mood': a.mood,
        'energy': a.energy,
        'x': a.position_x,
        'y': a.position_y,
        'z': a.position_z
    } for a in agents]
    
    links = [{
        'source': r.agent1,
        'target': r.agent2,
        'value': r.relationship_value
    } for r in relationships]
    
    return jsonify({'nodes': nodes, 'links': links})

@app.route('/logs')
def logs():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    event_type = request.args.get('type', 'all')
    
    query = Event.query
    
    if event_type != 'all':
        query = query.filter_by(event_type=event_type)
    
    events = query.order_by(Event.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('logs.html', events=events, current_type=event_type)

@app.route('/api/events/latest')
def latest_events():
    events = Event.query.order_by(Event.timestamp.desc()).limit(10).all()
    return jsonify([{
        'id': e.id,
        'text': e.event_text,
        'timestamp': e.timestamp.isoformat(),
        'type': e.event_type
    } for e in events])

@app.route('/world')
def world():
    world = WorldState.query.first()
    agents = Agent.query.all()
    
    if agents:
        avg_energy = sum(a.energy for a in agents) / len(agents)
    else:
        avg_energy = 0
    
    stats = {
        'total_agents': len(agents),
        'active_interactions': Relationship.query.count(),
        'total_memories': AgentMemory.query.count(),
        'avg_energy': round(avg_energy, 2)
    }
    
    return render_template('world.html', world=world, agents=agents, stats=stats)

@app.route('/api/world-state')
def world_state():
    world = WorldState.query.first()
    agents = Agent.query.all()
    
    return jsonify({
        'cycle': world.cycle if world else 0,
        'complexity': round(world.complexity, 3) if world else 1.0,
        'agents': [{
            'name': a.name,
            'mood': a.mood,
            'energy': round(a.energy, 2),
            'position': [round(a.position_x, 2), round(a.position_y, 2), round(a.position_z, 2)],
            'type': a.type
        } for a in agents]
    })

@app.route('/agent/<name>')
def agent_detail(name):
    agent = Agent.query.filter_by(name=name).first_or_404()
    memories = AgentMemory.query.filter_by(agent_id=agent.id).order_by(AgentMemory.timestamp.desc()).limit(20).all()
    interactions = Event.query.filter(
        (Event.agent1 == name) | (Event.agent2 == name)
    ).order_by(Event.timestamp.desc()).limit(20).all()
    
    return render_template('agent.html', agent=agent, memories=memories, interactions=interactions)

@app.errorhandler(404)
def not_found_error(error):
    random_cycles = random.randint(1000, 9999)
    return render_template('404.html', random_cycles=random_cycles), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.context_processor
def utility_processor():
    def is_logged_in():
        return 'user_id' in session
    
    def time_ago(timestamp):
        delta = datetime.utcnow() - timestamp
        if delta.days > 365:
            return f"{delta.days // 365}г"
        elif delta.days > 30:
            return f"{delta.days // 30}мес"
        elif delta.days > 0:
            return f"{delta.d}д"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}ч"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}мин"
        else:
            return "только что"
    
    return dict(is_logged_in=is_logged_in, time_ago=time_ago)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        simulator.start()
    app.run(debug=True, host='0.0.0.0', port=5000)