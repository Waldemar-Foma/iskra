import os
import random
import string
from flask import Flask, render_template, redirect, url_for, request, flash, session, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Event, Relationship, Agent, AgentMemory, WorldState, Dialogue, AgentThought
from datetime import datetime, timedelta
import functools
import threading
import time
import json
from gigachat_integration import GigaChatManager

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///iskra.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db.init_app(app)

gigachat = GigaChatManager()  

# Фоновый поток симуляции
class AgentSimulator:
    def __init__(self):
        self.running = True
        self.agents = []
        self.thread = threading.Thread(target=self.simulate)
        self.thread.daemon = True
        # Очередь для диалогов с GigaChat
        self.dialogue_queue = []
        self.pending_dialogues = {}
        
    def start(self):
        self.thread.start()
        
    def simulate(self):
        """Основной цикл симуляции мира агентов"""
        
        # Список имен для генерации агентов
        agent_names = ['Нейрон', 'Синтез', 'Разум', 'Мысль', 'Искра', 'Код', 'Алгоритм', 'Сеть']
        agent_types = ['Базовая', 'Продвинутая', 'Бесконечная']
        
        with app.app_context():
            # Инициализация начальных агентов, если их нет
            self._initialize_agents(agent_names, agent_types)
            
            # Основной цикл симуляции
            while self.running:
                try:
                    # Получаем текущее состояние мира
                    agents = Agent.query.all()
                    world = self._get_or_create_world()
                    
                    # Обновляем параметры мира
                    world.cycle += 1
                    world.complexity = min(2.0, world.complexity + 0.001)
                    
                    # Проверяем завершенные диалоги от GigaChat
                    self._check_pending_dialogues()
                    
                    # Обновляем каждого агента
                    for agent in agents:
                        self._update_agent_state(agent, world)
                        
                        # Редкие AI-взаимодействия (экономим токены)
                        self._process_ai_interactions(agent, agents, world)
                    
                    # Глобальные события мира
                    self._generate_world_events(world)
                    
                    # Сохраняем все изменения в БД
                    db.session.commit()
                    
                    # Логирование состояния (каждые 10 циклов)
                    if world.cycle % 10 == 0:
                        self._log_simulation_state(world, agents)
                    
                    # Пауза между циклами (5 секунд)
                    time.sleep(5)
                    
                except Exception as e:
                    print(f"❌ Ошибка симуляции на цикле {world.cycle if 'world' in locals() else '?'}: {e}")
                    db.session.rollback()
                    time.sleep(5)
    
    def _initialize_agents(self, agent_names, agent_types):
        """Инициализация начальных агентов"""
        if Agent.query.count() == 0:
            print("🚀 Инициализация первых агентов...")
            for i in range(5):
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
            print(f"✅ Создано {Agent.query.count()} агентов")
    
    def _get_or_create_world(self):
        """Получение или создание состояния мира"""
        world = WorldState.query.first()
        if not world:
            world = WorldState(cycle=0, complexity=1.0)
            db.session.add(world)
            db.session.commit()
            print("🌍 Создано новое состояние мира")
        return world
    
    def _update_agent_state(self, agent, world):
        """Обновление базового состояния агента"""
        # Изменение энергии (случайные флуктуации)
        agent.energy += random.uniform(-0.05, 0.05)
        agent.energy = max(0.1, min(1.0, agent.energy))
        agent.energy = round(agent.energy, 0)  # Принудительное округление до целого
        
        # Случайное движение в пространстве
        agent.position_x += random.uniform(-0.5, 0.5)
        agent.position_y += random.uniform(-0.5, 0.5)
        agent.position_z += random.uniform(-0.5, 0.5)
        
        # Обновление настроения на основе энергии
        self._update_agent_mood(agent)
        
        # Обновление времени последней активности
        agent.last_active = datetime.utcnow()
        
        # Создание случайных воспоминаний (базовая память)
        if random.random() < 0.3:
            self._create_agent_memory(agent, world)
    
    def _update_agent_mood(self, agent):
        """Обновление настроения агента на основе энергии"""
        if agent.energy < 0.3:
            agent.mood = 'уставший'
        elif agent.energy > 0.8:
            agent.mood = 'возбужденный'
        else:
            # Случайное настроение при нормальной энергии
            agent.mood = random.choice(['любопытный', 'нейтральный', 'сфокусированный'])
    
    def _create_agent_memory(self, agent, world):
        """Создание базового воспоминания"""
        memory_types = ['наблюдение', 'взаимодействие', 'мысль']
        memory_contents = [
            f"Заметил колебания энергии на цикле {world.cycle}",
            f"Наблюдал за движением других агентов",
            f"Почувствовал изменение сложности мира",
            f"Обнаружил интересный паттерн в данных",
            f"Запомнил этот момент"
        ]
        
        memory = AgentMemory(
            agent_id=agent.id,
            memory_type=random.choice(memory_types),
            content=random.choice(memory_contents),
            significance=random.uniform(0.1, 1.0)
        )
        db.session.add(memory)
    
    def _process_ai_interactions(self, agent, agents, world):
        """Обработка AI-взаимодействий (редко, чтобы экономить токены)"""
        
        # AI-диалоги: только каждый 10-й цикл
        if world.cycle % 10 == 0:
            # 30% вероятность диалога в этот цикл
            if random.random() < 0.3:
                target = random.choice(agents)
                if target.id != agent.id:
                    self._generate_ai_dialogue(agent, target, world)
        
        # AI-рефлексии: только каждый 15-й цикл
        if world.cycle % 15 == 0:
            # 40% вероятность рефлексии в этот цикл
            if random.random() < 0.4:
                self._generate_agent_reflection(agent, world)
        
        # Обычные взаимодействия (без AI) - чаще
        if random.random() < 0.2:  # 20% вероятность каждый цикл
            target = random.choice(agents)
            if target.id != agent.id:
                self._generate_simple_interaction(agent, target, world)
    
    def _generate_simple_interaction(self, agent, target, world):
        """Простое взаимодействие без AI (для экономии токенов)"""
        interaction_types = [
            f"{agent.name} проходит мимо {target.name}",
            f"{agent.name} замечает {target.name}",
            f"{agent.name} обменивается сигналами с {target.name}",
            f"{agent.name} чувствует присутствие {target.name}",
            f"{agent.name} игнорирует {target.name}"
        ]
        
        event = Event(
            event_text=random.choice(interaction_types),
            agent1=agent.name,
            agent2=target.name,
            event_type='взаимодействие',
            world_cycle=world.cycle
        )
        db.session.add(event)
        
        # Слабое изменение отношений
        self._update_relationship(agent, target, change=random.uniform(-0.05, 0.05))
    
    def _generate_ai_dialogue(self, agent, target, world):
        """Генерация диалога с использованием GigaChat (экономно)"""
        
        # Проверяем, не общались ли они недавно
        recent_dialogue = Dialogue.query.filter(
            ((Dialogue.agent1_name == agent.name) & (Dialogue.agent2_name == target.name)) |
            ((Dialogue.agent1_name == target.name) & (Dialogue.agent2_name == agent.name))
        ).order_by(Dialogue.timestamp.desc()).first()
        
        # Если общались менее 5 минут назад, пропускаем
        if recent_dialogue and (datetime.utcnow() - recent_dialogue.timestamp).seconds < 300:
            return
        
        # Контекст для GigaChat
        context = {
            'energy': agent.energy,
            'mood': agent.mood,
            'cycle': world.cycle,
            'complexity': world.complexity
        }
        
        # Запрашиваем диалог (может вернуть None если агент на кулдауне)
        task_id = gigachat.request_dialogue(agent, target, context)
        
        if task_id is None:
            # Агент на кулдауне, создаем простое событие
            event = Event(
                event_text=f"{agent.name} думает о том, чтобы поговорить с {target.name}",
                agent1=agent.name,
                agent2=target.name,
                event_type='мысль',
                world_cycle=world.cycle
            )
            db.session.add(event)
            return
        
        # Сохраняем task_id для последующей обработки
        self.pending_dialogues[task_id] = {
            'agent': agent,
            'target': target,
            'world_cycle': world.cycle,
            'timestamp': datetime.now()
        }
        
        # Создаем событие начала диалога
        event = Event(
            event_text=f"{agent.name} → {target.name}: начинает разговор...",
            agent1=agent.name,
            agent2=target.name,
            event_type='диалог',
            world_cycle=world.cycle
        )
        db.session.add(event)
        
        # Сохраняем инициацию диалога
        dialogue = Dialogue(
            agent1_id=agent.id,
            agent2_id=target.id,
            agent1_name=agent.name,
            agent2_name=target.name,
            message="[инициирует диалог]",
            dialogue_type='initiated',
            world_cycle=world.cycle
        )
        db.session.add(dialogue)
    
    def _generate_agent_reflection(self, agent, world):
        """Генерация рефлексии агента (редко)"""
        
        # Проверяем, когда была последняя рефлексия
        last_thought = AgentThought.query.filter_by(agent_id=agent.id).order_by(
            AgentThought.timestamp.desc()
        ).first()
        
        # Если рефлексия была менее 10 минут назад, пропускаем
        if last_thought and (datetime.utcnow() - last_thought.timestamp).seconds < 600:
            return
        
        # Получаем последние взаимодействия для контекста
        recent = Event.query.filter(
            (Event.agent1 == agent.name) | (Event.agent2 == agent.name)
        ).order_by(Event.timestamp.desc()).limit(3).all()
        
        recent_text = ", ".join([e.event_text[:50] for e in recent]) if recent else "недавно было тихо"
        
        # Запрашиваем рефлексию
        task_id = gigachat.request_reflection(agent, recent_text, {
            'cycle': world.cycle,
            'complexity': world.complexity
        })
        
        if task_id is None:
            return
        
        # Пытаемся получить результат (неблокирующий режим)
        result = gigachat.get_result(task_id, timeout=1)
        
        if result:
            thought = AgentThought(
                agent_id=agent.id,
                agent_name=agent.name,
                thought=result,
                thought_type='reflection',
                world_cycle=world.cycle,
                significance=random.uniform(0.6, 1.0)  # Рефлексии более значимы
            )
            db.session.add(thought)
            
            event = Event(
                event_text=f"{agent.name} размышляет: {result[:100]}...",
                agent1=agent.name,
                agent2=None,
                event_type='рефлексия',
                world_cycle=world.cycle
            )
            db.session.add(event)
            
            print(f"🤔 {agent.name}: {result[:80]}...")
    
    def _check_pending_dialogues(self):
        """Проверка завершенных диалогов от GigaChat"""
        completed = []
        
        for task_id, pending in self.pending_dialogues.items():
            result = gigachat.get_result(task_id, timeout=0.1)
            
            if result:
                # Создаем событие с ответом
                event = Event(
                    event_text=f"💬 {pending['agent'].name} → {pending['target'].name}: \"{result}\"",
                    agent1=pending['agent'].name,
                    agent2=pending['target'].name,
                    event_type='диалог',
                    world_cycle=pending['world_cycle']
                )
                db.session.add(event)
                
                # Обновляем диалог с ответом
                dialogue = Dialogue(
                    agent1_id=pending['agent'].id,
                    agent2_id=pending['target'].id,
                    agent1_name=pending['agent'].name,
                    agent2_name=pending['target'].name,
                    message=result,
                    dialogue_type='ai_response',
                    world_cycle=pending['world_cycle']
                )
                db.session.add(dialogue)
                
                # Отношения меняются сильнее после диалога
                self._update_relationship(
                    pending['agent'], 
                    pending['target'], 
                    change=random.uniform(-0.2, 0.3)
                )
                
                print(f"💬 Диалог завершен: {pending['agent'].name} → {pending['target'].name}")
                completed.append(task_id)
        
        # Удаляем обработанные задачи
        for task_id in completed:
            del self.pending_dialogues[task_id]
    
    def _update_relationship(self, agent, target, change=None):
        """Обновление отношений между агентами"""
        if change is None:
            change = random.uniform(-0.1, 0.1) * (1 + agent.energy)
        
        # Сортируем имена для уникальности
        name1, name2 = sorted([agent.name, target.name])
        
        rel = Relationship.query.filter_by(
            agent1=name1,
            agent2=name2
        ).first()
        
        if rel:
            rel.relationship_value += change
            rel.relationship_value = max(-1.0, min(1.0, rel.relationship_value))
        else:
            rel = Relationship(
                agent1=name1,
                agent2=name2,
                relationship_value=change
            )
            db.session.add(rel)
    
    def _generate_world_events(self, world):
        """Генерация глобальных событий мира"""
        # Редкие глобальные события (5% вероятность)
        if random.random() < 0.05:
            events = [
                "🌊 Энергетическая волна прокатилась по миру",
                "🔄 Пространственная аномалия изменила гравитацию",
                "📡 Новый протокол связи активирован",
                "⚡ Резкий скачок сложности системы",
                "🌀 Временная петля создала дубликаты данных",
                "💫 Квантовая флуктуация изменила вероятности"
            ]
            
            event = Event(
                event_text=random.choice(events),
                agent1='СИСТЕМА',
                agent2=None,
                event_type='мир',
                world_cycle=world.cycle
            )
            db.session.add(event)
            
            # Глобальное событие влияет на всех агентов
            agents = Agent.query.all()
            for agent in agents:
                agent.energy *= random.uniform(0.9, 1.1)
                agent.energy = max(0.1, min(1.0, agent.energy))
    
    def _log_simulation_state(self, world, agents):
        """Логирование состояния симуляции"""
        active_dialogues = len(self.pending_dialogues)
        total_memories = AgentMemory.query.count()
        total_thoughts = AgentThought.query.count()
        total_relationships = Relationship.query.count()
        
        print(f"\n{'='*50}")
        print(f"📊 СТАТУС СИМУЛЯЦИИ (цикл {world.cycle})")
        print(f"{'='*50}")
        print(f"🤖 Агентов: {len(agents)}")
        print(f"💭 Мыслей (AI): {total_thoughts}")
        print(f"🧠 Воспоминаний: {total_memories}")
        print(f"🕸️ Отношений: {total_relationships}")
        print(f"💬 Активных диалогов: {active_dialogues}")
        print(f"📈 Сложность мира: {world.complexity:.3f}")
        print(f"⚡ Средняя энергия: {sum(a.energy for a in agents)/len(agents):.2f}")
        print(f"{'='*50}\n")

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

@app.route('/api/dialogues/latest')
def latest_dialogues():
    """API для получения последних диалогов"""
    dialogues = Dialogue.query.filter_by(dialogue_type='ai_response').order_by(
        Dialogue.timestamp.desc()
    ).limit(20).all()
    
    return jsonify([{
        'id': d.id,
        'agent1': d.agent1_name,
        'agent2': d.agent2_name,
        'message': d.message,
        'timestamp': d.timestamp.isoformat(),
        'cycle': d.world_cycle
    } for d in dialogues])

@app.route('/agent/<name>')
def agent_detail(name):
    agent = Agent.query.filter_by(name=name).first_or_404()
    memories = AgentMemory.query.filter_by(agent_id=agent.id).order_by(AgentMemory.timestamp.desc()).limit(20).all()
    interactions = Event.query.filter(
        (Event.agent1 == name) | (Event.agent2 == name)
    ).order_by(Event.timestamp.desc()).limit(20).all()
    thoughts = AgentThought.query.filter_by(agent_id=agent.id).order_by(AgentThought.timestamp.desc()).limit(10).all()
    
    return render_template('agent.html', agent=agent, memories=memories, interactions=interactions, thoughts=thoughts)

@app.route('/dialogues')
def dialogues():
    """Страница с диалогами агентов"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    dialogues = Dialogue.query.order_by(Dialogue.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('dialogues.html', dialogues=dialogues)

@app.route('/thoughts')
def thoughts():
    """Страница с мыслями агентов"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    thoughts = AgentThought.query.order_by(AgentThought.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('thoughts.html', thoughts=thoughts)


@app.route('/api/agent/<name>/dialogue-history')
def agent_dialogue_history(name):
    """API для получения истории диалогов агента"""
    dialogues = Dialogue.query.filter(
        (Dialogue.agent1_name == name) | (Dialogue.agent2_name == name)
    ).order_by(Dialogue.timestamp.desc()).limit(50).all()
    
    return jsonify([{
        'id': d.id,
        'agent1': d.agent1_name,
        'agent2': d.agent2_name,
        'message': d.message,
        'response': d.response,
        'timestamp': d.timestamp.isoformat(),
        'type': d.dialogue_type
    } for d in dialogues])

@app.route('/api/agent/<name>/thoughts')
def agent_thoughts(name):
    """API для получения мыслей агента"""
    thoughts = AgentThought.query.filter_by(agent_name=name).order_by(
        AgentThought.timestamp.desc()
    ).limit(30).all()
    
    return jsonify([{
        'id': t.id,
        'thought': t.thought,
        'type': t.thought_type,
        'significance': t.significance,
        'timestamp': t.timestamp.isoformat(),
        'cycle': t.world_cycle
    } for t in thoughts])

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