
import os
import random
import string
from flask import Flask, render_template, redirect, url_for, request, flash, session, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Event, Relationship, Agent, AgentMemory, WorldState, Dialogue, AgentThought, UserAgentChat
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
app.config['GIGACHAT_TIMEOUT'] = 10  # Таймаут для GigaChat в секундах
app.config['AGENT_COOLDOWN'] = 3 

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
        # Отслеживание активных диалогов для поддержания темы
        self.active_conversations = {}  # (agent1_id, agent2_id) -> последнее сообщение
        
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
                        
                        # Обработка диалогов и ответов
                        self._process_agent_communications(agent, agents, world)
                    
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
        """Инициализация начальных агентов внутри границ мира"""
        if Agent.query.count() == 0:
            print("🚀 Инициализация первых агентов...")
            world_bounds = 9.0
            
            for i in range(5):
                agent = Agent(
                    name=random.choice(agent_names) + f"-{random.randint(100, 999)}",
                    type=random.choice(agent_types),
                    mood=random.choice(['любопытный', 'нейтральный', 'возбужденный', 'уставший', 'сфокусированный']),
                    energy=random.uniform(0.3, 1.0),
                    position_x=random.uniform(-world_bounds, world_bounds),
                    position_y=random.uniform(-world_bounds, world_bounds),
                    position_z=random.uniform(-world_bounds, world_bounds)
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
        # Изменение энергии
        agent.energy += random.uniform(-0.05, 0.05)
        agent.energy = max(0.1, min(1.0, agent.energy))
        
        # Случайное движение
        agent.position_x += random.uniform(-0.5, 0.5)
        agent.position_y += random.uniform(-0.5, 0.5)
        agent.position_z += random.uniform(-0.5, 0.5)
        
        # Ограничиваем мир
        world_bounds = 10.0
        agent.position_x = max(-world_bounds, min(world_bounds, agent.position_x))
        agent.position_y = max(-world_bounds, min(world_bounds, agent.position_y))
        agent.position_z = max(-world_bounds, min(world_bounds, agent.position_z))
        
        # Обновление настроения
        self._update_agent_mood(agent)
        
        # Обновление времени последней активности
        agent.last_active = datetime.utcnow()
        
        # Создание случайных воспоминаний
        if random.random() < 0.3:
            self._create_agent_memory(agent, world)
    
    def _update_agent_mood(self, agent):
        """Обновление настроения агента"""
        if agent.energy < 0.3:
            agent.mood = 'уставший'
        elif agent.energy > 0.8:
            agent.mood = 'возбужденный'
        else:
            agent.mood = random.choice(['любопытный', 'нейтральный', 'сфокусированный'])
    
    def _create_agent_memory(self, agent, world):
        """Создание базового воспоминания"""
        memory_types = ['наблюдение', 'взаимодействие', 'мысль']
        memory_contents = [
            f"Заметил колебания энергии на цикле {world.cycle}",
            f"Наблюдал за движением других агентов",
            f"Почувствовал изменение сложности мира",
            f"Обнаружил интересный паттерн в данных"
        ]
        
        memory = AgentMemory(
            agent_id=agent.id,
            memory_type=random.choice(memory_types),
            content=random.choice(memory_contents),
            significance=random.uniform(0.1, 1.0)
        )
        db.session.add(memory)
    
    def _process_agent_communications(self, agent, agents, world):
        """Обработка коммуникаций агента"""
        
        # 1. Сначала проверяем, есть ли неотвеченные сообщения
        unresponded = Dialogue.query.filter(
            (Dialogue.agent2_name == agent.name) &  # сообщение адресовано этому агенту
            (Dialogue.response.is_(None)) &  # еще не было ответа
            (Dialogue.dialogue_type == 'ai_response')  # это готовый ответ (не pending)
        ).order_by(Dialogue.timestamp.asc()).first()
        
        if unresponded:
            # Находим отправителя
            sender = Agent.query.filter_by(name=unresponded.agent1_name).first()
            if sender:
                self._generate_ai_response(agent, sender, unresponded, world)
                return  # Отвечаем на сообщение, новые не инициируем
        
        # 2. Если нет неотвеченных, проверяем, есть ли активные диалоги, которые нужно продолжить
        # Ищем последний диалог с участием этого агента
        last_dialogue = Dialogue.query.filter(
            ((Dialogue.agent1_name == agent.name) | (Dialogue.agent2_name == agent.name)) &
            (Dialogue.dialogue_type == 'ai_response')
        ).order_by(Dialogue.timestamp.desc()).first()
        
        if last_dialogue:
            # Определяем собеседника
            other_name = last_dialogue.agent2_name if last_dialogue.agent1_name == agent.name else last_dialogue.agent1_name
            other_agent = Agent.query.filter_by(name=other_name).first()
            
            if other_agent:
                # Проверяем, не общались ли мы недавно
                time_since = datetime.utcnow() - last_dialogue.timestamp
                if time_since.seconds < 300:  # 6 минут
                    # Слишком рано для нового сообщения
                    pass
                elif random.random() < 0.1:  # 10% шанс продолжить диалог
                    # Продолжаем диалог - отправляем новое сообщение тому же агенту
                    self._generate_ai_dialogue(agent, other_agent, world, is_continuation=True)
                    return
        
        # 3. Если нет активных диалогов, с небольшой вероятностью начинаем новый
        if world.cycle % 5 == 0 and random.random() < 0.08:  # 15% шанс каждые 3 цикла
            other_agents = [a for a in agents if a.id != agent.id]
            if other_agents:
                target = random.choice(other_agents)
                
                # Проверяем, не общались ли недавно
                recent = Dialogue.query.filter(
                    ((Dialogue.agent1_name == agent.name) & (Dialogue.agent2_name == target.name)) |
                    ((Dialogue.agent1_name == target.name) & (Dialogue.agent2_name == agent.name))
                ).order_by(Dialogue.timestamp.desc()).first()
                
                # Если общались менее 5 минут назад, пропускаем
                if recent and (datetime.utcnow() - recent.timestamp).seconds < 600:
                    return
                
                self._generate_ai_dialogue(agent, target, world, is_continuation=False)
        
        # 4. AI-рефлексии: каждый 15-й цикл
        if world.cycle % 15 == 0 and random.random() < 0.3:
            self._generate_agent_reflection(agent, world)

    def _generate_ai_response(self, agent, sender, original_dialogue, world):
        """Генерация ответа на конкретное сообщение"""
        
        print(f"💬 {agent.name} отвечает {sender.name}")
        
        # Получаем историю диалога для контекста
        dialogue_history = Dialogue.query.filter(
            ((Dialogue.agent1_name == agent.name) & (Dialogue.agent2_name == sender.name)) |
            ((Dialogue.agent1_name == sender.name) & (Dialogue.agent2_name == agent.name))
        ).order_by(Dialogue.timestamp.asc()).limit(10).all()
        
        history_for_context = []
        for d in dialogue_history:
            if d.message and d.message not in ["✍️ печатает ответ...", "⏳ печатает..."]:
                history_for_context.append({
                    'speaker_id': d.agent1_id if d.agent1_name == agent.name else d.agent2_id,
                    'text': d.message
                })
        
        # Контекст с учетом исходного сообщения
        context = {
            'energy': agent.energy,
            'mood': agent.mood,
            'cycle': world.cycle,
            'complexity': world.complexity,
            'agent_name': agent.name,
            'other_name': sender.name,
            'agent_type': agent.type,
            'other_type': sender.type,
            'original_message': original_dialogue.message,
            'history': history_for_context
        }
        
        # Запрашиваем ответ через GigaChat
        task_id = gigachat.request_response(agent, sender, original_dialogue.message, history_for_context, context)
        
        if task_id is None:
            print(f"⏳ {agent.name} на кулдауне, ответ отложен")
            return
        
        # Сохраняем в ожидающие
        self.pending_dialogues[task_id] = {
            'agent_id': agent.id,
            'agent_name': agent.name,
            'target_id': sender.id,
            'target_name': sender.name,
            'original_dialogue_id': original_dialogue.id,
            'world_cycle': world.cycle,
            'timestamp': datetime.now(),
            'attempts': 0,
            'type': 'response'
        }
        
        print(f"📝 Запрос ответа от {agent.name} добавлен в очередь")
        
        # Создаем временную запись о том, что агент печатает ответ
        typing_dialogue = Dialogue(
            agent1_id=agent.id,
            agent2_id=sender.id,
            agent1_name=agent.name,
            agent2_name=sender.name,
            message="✍️ печатает ответ...",
            dialogue_type='typing',
            world_cycle=world.cycle,
            response_to=original_dialogue.id
        )
        db.session.add(typing_dialogue)
        db.session.commit()

    def _generate_ai_dialogue(self, agent, target, world, is_continuation=False):
        """Генерация нового сообщения в диалоге"""
        
        print(f"🤖 ЗАПРОС: {agent.name} -> {target.name} ({'продолжение' if is_continuation else 'новый'})")
        
        context = {
            'energy': agent.energy,
            'mood': agent.mood,
            'cycle': world.cycle,
            'complexity': world.complexity,
            'agent_name': agent.name,
            'other_name': target.name,
            'agent_type': agent.type,
            'other_type': target.type
        }
        
        # Используем специальный метод для первого сообщения или продолжаем диалог
        if is_continuation:
            # Для продолжения диалога используем request_response без исходного сообщения
            task_id = gigachat.request_response(agent, target, "Продолжи наш разговор", [], context)
        else:
            task_id = gigachat.request_first_message(agent, target, context)
        
        if task_id is None:
            print(f"⏳ {agent.name} на кулдауне")
            return
        
        # Сохраняем в словарь ожидающих
        self.pending_dialogues[task_id] = {
            'agent_id': agent.id,
            'agent_name': agent.name,
            'target_id': target.id,
            'target_name': target.name,
            'world_cycle': world.cycle,
            'timestamp': datetime.now(),
            'attempts': 0,
            'type': 'first_message' if not is_continuation else 'continuation'
        }
        
        print(f"📝 {task_id} добавлен в очередь ожидания")
        
        # Создаем временную запись
        dialogue = Dialogue(
            agent1_id=agent.id,
            agent2_id=target.id,
            agent1_name=agent.name,
            agent2_name=target.name,
            message="⏳ печатает...",
            dialogue_type='pending',
            world_cycle=world.cycle
        )
        db.session.add(dialogue)
        db.session.commit()
    
    def _generate_agent_reflection(self, agent, world):
        """Генерация рефлексии агента"""
        
        print(f"🤔 Запрашиваю рефлексию: {agent.name}")
        
        recent = Event.query.filter(
            (Event.agent1 == agent.name) | (Event.agent2 == agent.name)
        ).order_by(Event.timestamp.desc()).limit(3).all()
        
        recent_text = ", ".join([e.event_text[:50] for e in recent]) if recent else "тихо"
        
        context = {
            'cycle': world.cycle,
            'complexity': world.complexity,
            'agent_name': agent.name,
            'agent_type': agent.type,
            'agent_mood': agent.mood,
            'agent_energy': agent.energy
        }
        
        task_id = gigachat.request_reflection(agent, recent_text, context)
        
        if task_id is None:
            return
        
        self.pending_dialogues[task_id] = {
            'agent_id': agent.id,
            'agent_name': agent.name,
            'type': 'reflection',
            'world_cycle': world.cycle,
            'timestamp': datetime.now(),
            'attempts': 0
        }
    
    def _check_pending_dialogues(self):
        """Проверка завершенных диалогов от GigaChat - с автоматическими ответами при таймауте"""
        completed = []
        
        for task_id, pending in list(self.pending_dialogues.items()):
            pending['attempts'] = pending.get('attempts', 0) + 1
            
            result = gigachat.get_result(task_id, timeout=1)  # Уменьшен таймаут
            
            if result:
                print(f"✅ ПОЛУЧЕН РЕЗУЛЬТАТ: {result[:100]}...")
                
                try:
                    if pending.get('type') == 'response':
                        # Это ответ на сообщение
                        print(f"💬 Сохраняю ответ от {pending['agent_name']} к {pending['target_name']}")
                        
                        # Сохраняем в историю
                        gigachat.save_dialogue_to_history(
                            pending['agent_id'],
                            pending['target_id'],
                            pending['agent_id'],
                            result
                        )
                        
                        # Создаем запись с ответом
                        response_dialogue = Dialogue(
                            agent1_id=pending['agent_id'],
                            agent2_id=pending['target_id'],
                            agent1_name=pending['agent_name'],
                            agent2_name=pending['target_name'],
                            message=result,
                            dialogue_type='ai_response',
                            world_cycle=pending['world_cycle'],
                            response_to=pending.get('original_dialogue_id')
                        )
                        db.session.add(response_dialogue)
                        
                        # Отмечаем исходное сообщение как отвеченное
                        if pending.get('original_dialogue_id'):
                            original = Dialogue.query.get(pending['original_dialogue_id'])
                            if original:
                                original.response = result
                                original.response_id = response_dialogue.id
                        
                        event = Event(
                            event_text=f"💬 {pending['agent_name']} ответил {pending['target_name']}",
                            agent1=pending['agent_name'],
                            agent2=pending['target_name'],
                            event_type='диалог',
                            world_cycle=pending['world_cycle']
                        )
                        db.session.add(event)
                        
                    elif pending.get('type') == 'reflection':
                        # Сохраняем рефлексию
                        thought = AgentThought(
                            agent_id=pending['agent_id'],
                            agent_name=pending['agent_name'],
                            thought=result,
                            thought_type='reflection',
                            world_cycle=pending['world_cycle'],
                            significance=0.8
                        )
                        db.session.add(thought)
                        
                        event = Event(
                            event_text=f"🤔 {pending['agent_name']}: \"{result}\"",
                            agent1=pending['agent_name'],
                            agent2=None,
                            event_type='рефлексия',
                            world_cycle=pending['world_cycle']
                        )
                        db.session.add(event)
                        
                    elif pending.get('type') == 'human_response':
                        # Ответ агентом человеку
                        print(f"💬 Сохраняю ответ от {pending['agent_name']} пользователю")
                        
                        # Находим соответствующее сообщение пользователя
                        user_message = UserAgentChat.query.filter_by(
                            user_id=pending.get('user_id'),
                            task_id=task_id
                        ).first()
                        
                        if user_message:
                            user_message.response = result
                            user_message.response_received = True
                            
                            # Создаем запись ответа
                            agent_response = UserAgentChat(
                                user_id=user_message.user_id,
                                agent_id=user_message.agent_id,
                                response=result,
                                sender_type='agent',
                                conversation_id=user_message.conversation_id,
                                response_received=True
                            )
                            db.session.add(agent_response)
                            
                            print(f"✅ Ответ пользователю сохранен")
                    
                    else:
                        # Обычный диалог
                        print(f"💾 Сохраняю диалог: {pending['agent_name']} -> {pending['target_name']}")
                        
                        gigachat.save_dialogue_to_history(
                            pending['agent_id'],
                            pending['target_id'],
                            pending['agent_id'],
                            result
                        )
                        
                        dialogue = Dialogue(
                            agent1_id=pending['agent_id'],
                            agent2_id=pending['target_id'],
                            agent1_name=pending['agent_name'],
                            agent2_name=pending['target_name'],
                            message=result,
                            dialogue_type='ai_response',
                            world_cycle=pending['world_cycle']
                        )
                        db.session.add(dialogue)
                        
                        event = Event(
                            event_text=f"💬 {pending['agent_name']} -> {pending['target_name']}",
                            agent1=pending['agent_name'],
                            agent2=pending['target_name'],
                            event_type='диалог',
                            world_cycle=pending['world_cycle']
                        )
                        db.session.add(event)
                    
                    db.session.commit()
                    print(f"✅ Данные сохранены в БД")
                    completed.append(task_id)
                    
                except Exception as e:
                    print(f"❌ Ошибка сохранения: {e}")
                    db.session.rollback()
            
            else:
                # Если прошло много попыток, генерируем автоматический ответ
                if pending['attempts'] > 5:  # После 5 попыток (примерно 10 секунд)
                    print(f"⏰ Таймаут задачи {task_id}, генерирую автоматический ответ")
                    
                    # Генерируем автоматический ответ для человека
                    if pending.get('type') == 'human_response':
                        user_message = UserAgentChat.query.filter_by(
                            user_id=pending.get('user_id'),
                            task_id=task_id
                        ).first()
                        
                        if user_message and not user_message.response_received:
                            auto_responses = [
                                "Привет! Извини, задумался немного.",
                                "О, привет! Слушаю тебя внимательно.",
                                "Приветик! Рассказывай, что хотел?",
                                "Здорово! Рад пообщаться.",
                            ]
                            import random
                            
                            user_message.response = random.choice(auto_responses)
                            user_message.response_received = True
                            
                            agent_response = UserAgentChat(
                                user_id=user_message.user_id,
                                agent_id=user_message.agent_id,
                                response=user_message.response,
                                sender_type='agent',
                                conversation_id=user_message.conversation_id,
                                response_received=True
                            )
                            db.session.add(agent_response)
                            db.session.commit()
                            print(f"✅ Автоматический ответ сохранен")
                    
                    completed.append(task_id)
        
        for task_id in completed:
            if task_id in self.pending_dialogues:
                del self.pending_dialogues[task_id]
    
    def _update_relationship(self, agent, target, change=None):
        """Обновление отношений между агентами"""
        if change is None:
            change = random.uniform(-0.1, 0.1)
        
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
        if random.random() < 0.05:
            events = [
                "🌊 Энергетическая волна прокатилась по миру",
                "🔄 Пространственная аномалия изменила гравитацию",
                "📡 Новый протокол связи активирован",
                "⚡ Резкий скачок сложности системы"
            ]
            
            event = Event(
                event_text=random.choice(events),
                agent1='СИСТЕМА',
                agent2=None,
                event_type='мир',
                world_cycle=world.cycle
            )
            db.session.add(event)
            
            # Влияет на всех агентов
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

@app.route('/dashboard')
@login_required
def dashboard():
    """Страница дашборда с последними диалогами и личным чатом"""
    # Получаем последние 10 диалогов агентов
    dialogues = Dialogue.query.order_by(Dialogue.timestamp.desc()).paginate(
        page=1, per_page=10, error_out=False
    )
    
    # Получаем всех агентов для списка в чате
    available_agents = Agent.query.all()
    
    # Получаем текущего пользователя
    user = User.query.get(session['user_id'])
    
    # Проверяем, выбран ли агент для чата
    selected_agent_id = request.args.get('agent', type=int)
    selected_agent = None
    if selected_agent_id and user.is_active == 1:
        selected_agent = Agent.query.get(selected_agent_id)
    
    # Получаем текущий цикл мира
    world = WorldState.query.first()
    world_cycle = world.cycle if world else 0
    
    return render_template(
        'dashboard.html',
        dialogues=dialogues,
        available_agents=available_agents,
        selected_agent=selected_agent,
        online_agents=len(available_agents),
        world_cycle=world_cycle
    )

@app.route('/api/chat/send', methods=['POST'])
@login_required
def send_chat_message():
    """Отправка сообщения агенту от пользователя"""
    user = User.query.get(session['user_id'])
    
    # Проверка подписки
    if user.is_active != 1:
        return jsonify({'success': False, 'error': 'Требуется подписка'}), 403
    
    data = request.get_json()
    agent_id = data.get('agent_id')
    message = data.get('message')
    
    if not agent_id or not message:
        return jsonify({'success': False, 'error': 'Недостаточно данных'}), 400
    
    if len(message) > 500:
        return jsonify({'success': False, 'error': 'Сообщение слишком длинное'}), 400
    
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({'success': False, 'error': 'Агент не найден'}), 404
    
    # ПРОВЕРКА: не занят ли агент НЕОТВЕЧЕННЫМИ сообщениями
    pending = UserAgentChat.query.filter_by(
        agent_id=agent.id,
        response_received=False,
        sender_type='user'
    ).first()
    
    if pending:
        # Проверяем, сколько времени прошло
        time_elapsed = (datetime.utcnow() - pending.timestamp).seconds
        if time_elapsed < 30:  # Если прошло меньше 30 секунд
            return jsonify({
                'success': False, 
                'error': f'Агент обрабатывает предыдущее сообщение',
                'retry_after': 5
            }), 429
        else:
            # Если прошло больше 30 секунд, считаем что ответ потерян
            pending.response_received = True  # Помечаем как полученный (ошибочно)
            db.session.commit()
    
    # Проверка последнего ответа агента (кулдаун)
    last_response = UserAgentChat.query.filter_by(
        agent_id=agent.id,
        sender_type='agent'
    ).order_by(UserAgentChat.timestamp.desc()).first()
    
    if last_response:
        time_since_last = (datetime.utcnow() - last_response.timestamp).seconds
        if time_since_last < 3:  # Не чаще чем раз в 3 секунды
            return jsonify({
                'success': False, 
                'error': f'Агент отдыхает. Подождите {3 - time_since_last} сек.',
                'retry_after': 3 - time_since_last
            }), 429
    
    # Создаем уникальный ID для диалога
    conversation_id = f"user_{user.id}_agent_{agent.id}_{int(time.time())}"
    
    # Сохраняем сообщение пользователя
    user_message = UserAgentChat(
        user_id=user.id,
        agent_id=agent.id,
        message=message,
        sender_type='user',
        conversation_id=conversation_id,
        response_received=False
    )
    db.session.add(user_message)
    db.session.commit()
    
    # Получаем контекст
    world = WorldState.query.first()
    
    context = {
        'cycle': world.cycle if world else 0,
        'complexity': world.complexity if world else 1.0,
        'agent_name': agent.name,
        'other_name': f"Пользователь {user.username}",
        'agent_type': agent.type,
        'other_type': 'человек',
        'agent_mood': agent.mood,
        'other_mood': 'общается',
        'agent_energy': agent.energy,
        'is_human': True,
        'human_message': message
    }
    
    # Запрашиваем ответ
    task_id = gigachat.request_human_response(agent, user, message, context)
    
    if task_id:
        user_message.task_id = task_id
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'conversation_id': conversation_id,
            'agent_name': agent.name,
            'message': 'Сообщение отправлено, ожидайте ответ'
        })
    else:
        # Если агент на кулдауне - удаляем временное сообщение
        db.session.delete(user_message)
        db.session.commit()
        
        return jsonify({
            'success': False, 
            'error': 'Агент временно занят. Попробуйте через 5 секунд.',
            'retry_after': 5
        }), 429
    
@app.route('/api/user/subscription-info')
@login_required
def subscription_info():
    """Информация о подписке пользователя и доступных агентах"""
    user = User.query.get(session['user_id'])
    
    # Подсчет сообщений за сегодня
    today = datetime.utcnow().date()
    messages_today = UserAgentChat.query.filter(
        UserAgentChat.user_id == user.id,
        db.func.date(UserAgentChat.timestamp) == today,
        UserAgentChat.sender_type == 'user'
    ).count()
    
    # Лимиты
    limits = {
        'basic': 20,
        'premium': 100,
        'vip': 500
    }
    subscription_tier = user.subscription_tier or 'basic'
    daily_limit = limits.get(subscription_tier, 20)
    
    # Доступные типы агентов
    available_types = ['Базовая']
    if subscription_tier in ['premium', 'vip']:
        available_types.append('Продвинутая')
    if subscription_tier == 'vip':
        available_types.append('Бесконечная')
    
    return jsonify({
        'subscription_tier': subscription_tier,
        'is_active': user.is_active == 1,
        'messages_today': messages_today,
        'daily_limit': daily_limit,
        'messages_remaining': max(0, daily_limit - messages_today),
        'available_agent_types': available_types
    })

# API для получения истории чата с агентом
@app.route('/api/chat/history/<int:agent_id>')
@login_required
def get_chat_history(agent_id):
    """Получение истории переписки с агентом"""
    user = User.query.get(session['user_id'])
    
    messages = UserAgentChat.query.filter_by(
        user_id=user.id,
        agent_id=agent_id
    ).order_by(UserAgentChat.timestamp.asc()).limit(50).all()
    
    return jsonify([{
        'id': m.id,
        'sender_type': m.sender_type,
        'sender_name': 'Вы' if m.sender_type == 'user' else m.agent.name,
        'message': m.message if m.sender_type == 'user' else m.response,
        'timestamp': m.timestamp.isoformat(),
        'response_received': m.response_received
    } for m in messages])

# API для проверки ответа от агента
@app.route('/api/chat/check-response/<conversation_id>')
@login_required
def check_response(conversation_id):
    """Проверка, получен ли ответ от агента - с принудительной генерацией если надо"""
    user = User.query.get(session['user_id'])
    
    # Ищем сообщение пользователя
    user_message = UserAgentChat.query.filter_by(
        user_id=user.id,
        conversation_id=conversation_id,
        sender_type='user'
    ).first()
    
    if not user_message:
        return jsonify({'response_received': False})
    
    # Проверяем, есть ли уже ответ
    agent_response = UserAgentChat.query.filter_by(
        user_id=user.id,
        conversation_id=conversation_id,
        sender_type='agent',
        response_received=True
    ).first()
    
    if agent_response:
        return jsonify({
            'response_received': True,
            'message': agent_response.response or agent_response.message,
            'agent_name': agent_response.agent.name
        })
    
    # Если прошло больше 10 секунд и ответа нет, генерируем автоматически
    time_elapsed = (datetime.utcnow() - user_message.timestamp).seconds
    if time_elapsed > 10 and not user_message.response_received:
        # Генерируем автоматический ответ
        auto_responses = [
            "Привет! Извини, задумался. Что ты хотел?",
            "О, привет! Я тут немного занят, но слушаю тебя.",
            "Приветик! Рассказывай, что нового?",
            "Здорово! Рад тебя слышать. Как дела?",
            "Привет! Чем могу помочь?",
        ]
        import random
        
        # Создаем автоматический ответ
        agent = Agent.query.get(user_message.agent_id)
        if agent:
            auto_response = UserAgentChat(
                user_id=user.id,
                agent_id=agent.id,
                response=random.choice(auto_responses),
                sender_type='agent',
                conversation_id=conversation_id,
                response_received=True
            )
            db.session.add(auto_response)
            user_message.response_received = True
            db.session.commit()
            
            return jsonify({
                'response_received': True,
                'message': auto_response.response,
                'agent_name': agent.name
            })
    
    return jsonify({'response_received': False})

@app.route('/view_pdf')
def view_pdf():
    return render_template('view_pdf.html')

@app.route('/gamedev')
def gamedev():
    return render_template('gamedev.html')

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
    
    # Получаем количество активных агентов
    online_agents = Agent.query.count()
    
    # Получаем текущий цикл мира
    world = WorldState.query.first()
    world_cycle = world.cycle if world else 0
    
    return render_template(
        'dialogues.html', 
        dialogues=dialogues,
        online_agents=online_agents,
        world_cycle=world_cycle
    )

@app.route('/thoughts')
def thoughts():
    """Страница с мыслями агентов"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    thoughts = AgentThought.query.order_by(AgentThought.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('thoughts.html', thoughts=thoughts)

@app.route('/test-gigachat')
def test_gigachat():
    """Тестирование GigaChat напрямую"""
    import time
    
    agents = Agent.query.limit(2).all()
    if len(agents) < 2:
        return "Нужно минимум 2 агента"
    
    agent1, agent2 = agents[0], agents[1]
    world = WorldState.query.first() or WorldState(cycle=1, complexity=1.0)
    
    print(f"\n=== ТЕСТ GigaChat ===")
    print(f"Агент1: {agent1.name} (тип: {agent1.type}, настроение: {agent1.mood})")
    print(f"Агент2: {agent2.name} (тип: {agent2.type}, настроение: {agent2.mood})")
    
    # Пытаемся получить диалог
    context = {
        'cycle': world.cycle,
        'complexity': world.complexity,
        'agent_name': agent1.name,
        'other_name': agent2.name,
        'agent_type': agent1.type,
        'other_type': agent2.type,
        'agent_mood': agent1.mood,
        'other_mood': agent2.mood,
        'agent_energy': agent1.energy
    }
    
    task_id = gigachat.request_dialogue(agent1, agent2, context)
    
    if not task_id:
        return f"❌ Не удалось создать задачу (возможно, кулдаун)"
    
    print(f"✅ Создана задача: {task_id}")
    
    # Ждем результат
    for i in range(10):
        time.sleep(2)
        result = gigachat.get_result(task_id, timeout=0.5)
        if result:
            print(f"✅ Получен результат: {result}")
            
            # Сохраняем в БД напрямую
            dialogue = Dialogue(
                agent1_id=agent1.id,
                agent2_id=agent2.id,
                agent1_name=agent1.name,
                agent2_name=agent2.name,
                message=result,
                dialogue_type='ai_response',
                world_cycle=world.cycle
            )
            db.session.add(dialogue)
            db.session.commit()
            
            return f"✅ Диалог сохранен: {result}"
        else:
            print(f"⏳ Попытка {i+1}/10: результат еще не готов")
    
    return "❌ Таймаут - результат не получен"

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

@app.route('/api/dialogue-context/<agent1>/<agent2>')
def get_dialogue_context(agent1, agent2):
    """API для получения контекста диалога между двумя агентами"""
    dialogues = Dialogue.query.filter(
        ((Dialogue.agent1_name == agent1) & (Dialogue.agent2_name == agent2)) |
        ((Dialogue.agent1_name == agent2) & (Dialogue.agent2_name == agent1))
    ).order_by(Dialogue.timestamp.asc()).limit(20).all()
    
    return jsonify([{
        'speaker': d.agent1_name,
        'message': d.message,
        'timestamp': d.timestamp.isoformat()
    } for d in dialogues if d.message and not d.message.startswith(('⏳', '✍️'))])

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