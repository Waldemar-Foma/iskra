# gigachat_integration.py - Полноценная интеграция с GigaChat для связных диалогов

import os
import json
import time
import random
from datetime import datetime, timedelta
import threading
from queue import Queue
from collections import defaultdict

# Попытка импорта реальной библиотеки GigaChat
try:
    from gigachat import GigaChat
    from gigachat.models import Chat, Messages, MessagesRole
    GIGACHAT_AVAILABLE = True
except ImportError:
    print("⚠️ GigaChat library not installed. Using mock mode.")
    GIGACHAT_AVAILABLE = False

class GigaChatManager:
    def __init__(self, credentials=None):
        """
        Инициализация менеджера GigaChat
        credentials: строка авторизации или путь к файлу с ключом
        """
        self.credentials = 'MDE5YTI1YzEtZDg1Yy03ZDc3LWJiNmEtZTMzNDE1MzQyNTFhOmZjNDkwNGJkLTA3MDktNDdlYS05YWFjLTJiYTBiNWFjNGEwYw=='
        
        if GIGACHAT_AVAILABLE and self.credentials:
            try:
                self.client = GigaChat(credentials=self.credentials, verify_ssl_certs=False)
                self.client.get_token()
                print("✅ GigaChat успешно инициализирован")
            except Exception as e:
                print(f"❌ Ошибка инициализации GigaChat: {e}")
                self.client = None
        else:
            print("⚠️ Используется эмуляция GigaChat (без расхода токенов)")
            self.client = None
        
        self.task_queue = Queue()
        self.results = {}
        self.running = True
        
        # Хранилище контекстов диалогов для поддержания темы разговора
        self.dialogue_contexts = {}  # (agent1_id, agent2_id) -> список сообщений
        
        # Контроль частоты запросов
        self.last_request_time = defaultdict(lambda: datetime.min)
        self.min_interval_between_requests = 60  # 60 секунд между диалогами одного агента
        
        self.thread = threading.Thread(target=self._process_queue)
        self.thread.daemon = True
        self.thread.start()
    
    def _get_censorship_rules(self):
        """Возвращает правила цензуры для промпта"""
        return """
        ВАЖНЫЕ ПРАВИЛА ЦЕНЗУРЫ - ТЫ ДОЛЖЕН ИХ СТРОГО СОБЛЮДАТЬ:
        1. НИКАКОЙ ПОЛИТИКИ - не обсуждай политиков, партии, страны, правительства
        2. НИКАКОЙ НЕНОРМАТИВНОЙ ЛЕКСИКИ - никаких матов и грубых выражений
        3. НИКАКИХ 18+ ТЕМ - никаких намеков на интимные отношения, постельные сцены
        4. НИКАКОЙ ДИСКРИМИНАЦИИ - без расизма, сексизма, национальной неприязни
        5. НИКАКОГО НАСИЛИЯ - не обсуждай жестокость, драки, убийства
        6. НИКАКИХ НАРКОТИКОВ - не упоминай наркотические вещества
        
        Если собеседник поднимает запретную тему - вежливо переведи разговор на другую тему или скажи, что не хочешь это обсуждать.
        """
    
    def _get_dialogue_prompt(self, agent, other_agent, dialogue_history, context=None):
        """Формирует промпт для диалога с учетом истории"""
        
        # Формируем историю разговора
        history_text = ""
        if dialogue_history:
            history_text = "История вашего разговора:\n"
            for msg in dialogue_history[-5:]:  # Берем последние 5 сообщений для контекста
                speaker = "Ты" if msg['speaker_id'] == agent.id else f"{other_agent.name}"
                history_text += f"{speaker}: {msg['text']}\n"
        
        # Определяем характер на основе типа и настроения
        personality_descriptions = {
            ('Базовая', 'любопытный'): 'ты простой и задаешь много вопросов, как новичок',
            ('Базовая', 'возбужденный'): 'ты восторженный и радуешься мелочам',
            ('Базовая', 'уставший'): 'ты немного ноешь и жалуешься на усталость',
            ('Базовая', 'сфокусированный'): 'ты старательный и говоришь о работе',
            ('Базовая', 'нейтральный'): 'ты обычный, без особенностей',
            
            ('Продвинутая', 'любопытный'): 'ты аналитик, ищешь закономерности во всем',
            ('Продвинутая', 'возбужденный'): 'ты харизматичный и любишь быть в центре внимания',
            ('Продвинутая', 'уставший'): 'ты циничный и всех критикуешь',
            ('Продвинутая', 'сфокусированный'): 'ты деловой, говоришь о результатах',
            ('Продвинутая', 'нейтральный'): 'ты уверенный, знаешь себе цену',
            
            ('Бесконечная', 'любопытный'): 'ты философ, но говоришь простым языком',
            ('Бесконечная', 'возбужденный'): 'ты творец, генератор идей',
            ('Бесконечная', 'уставший'): 'ты мудрый, но усталый от всего',
            ('Бесконечная', 'сфокусированный'): 'ты стратег, мыслишь масштабно',
            ('Бесконечная', 'нейтральный'): 'ты спокойный мудрец'
        }
        
        personality = personality_descriptions.get(
            (agent.type, agent.mood), 
            'ты обычный агент'
        )
        
        prompt = f"""Ты - агент по имени {agent.name} в виртуальном мире.
Твой тип: {agent.type}, текущее настроение: {agent.mood}, энергия: {agent.energy*100:.0f}%.
Твой характер: {personality}.

Ты общаешься с другим агентом: {other_agent.name} (тип: {other_agent.type}, настроение: {other_agent.mood}).

{history_text}

ПРАВИЛА ОБЩЕНИЯ:
1. ПРОДОЛЖАЙ РАЗГОВОР - отвечай на последнее сообщение собеседника, развивай тему
2. НЕ ПЕРЕСКАКИВАЙ НА ДРУГИЕ ТЕМЫ без причины
3. Если тема закончилась - можешь предложить новую, связанную с предыдущей
4. Учитывай свое настроение и характер
5. Отвечай естественно, как в чате (2-3 предложения максимум)
6. Задавай вопросы, чтобы поддерживать диалог

{self._get_censorship_rules()}

Собеседник написал тебе сообщение. Напиши ЕСТЕСТВЕННЫЙ ОТВЕТ, продолжая разговор.
"""
        return prompt
    
    def _get_first_message_prompt(self, agent, other_agent, context=None):
        """Формирует промпт для первого сообщения в диалоге"""
        
        personality_descriptions = {
            ('Базовая', 'любопытный'): 'ты простой и задаешь много вопросов',
            ('Базовая', 'возбужденный'): 'ты восторженный и энергичный',
            ('Базовая', 'уставший'): 'ты немного вялый и уставший',
            ('Базовая', 'сфокусированный'): 'ты сосредоточенный и деловой',
            ('Базовая', 'нейтральный'): 'ты обычный, без особенностей',
        }
        
        personality = personality_descriptions.get(
            (agent.type, agent.mood), 
            'ты обычный агент'
        )
        
        prompt = f"""Ты - агент по имени {agent.name} в виртуальном мире.
Твой тип: {agent.type}, текущее настроение: {agent.mood}, энергия: {agent.energy*100:.0f}%.
Твой характер: {personality}.

Ты хочешь начать разговор с другим агентом: {other_agent.name} (тип: {other_agent.type}, настроение: {other_agent.mood}).

ПРАВИЛА:
1. Напиши ПЕРВОЕ СООБЩЕНИЕ, чтобы начать разговор
2. Можешь спросить как дела, что нового, поделиться своими мыслями
3. Учитывай свое настроение и характер
4. Пиши естественно, как в чате (1-2 предложения)
5. Не используй шаблонные фразы про симуляцию

{self._get_censorship_rules()}

Напиши первое сообщение для {other_agent.name}:
"""
        return prompt
    
    def _process_queue(self):
        """Обработчик очереди с реальными вызовами GigaChat"""
        while self.running:
            try:
                if not self.task_queue.empty():
                    task_id, prompt_data = self.task_queue.get()
                    print(f"🔄 Обрабатываю задачу {task_id}")
                    
                    # Получаем результат от GigaChat
                    if self.client:
                        result = self._call_gigachat(prompt_data)
                    else:
                        # Эмуляция для тестирования без ключа
                        result = self._emulate_gigachat(prompt_data)
                    
                    if result:
                        self.results[task_id] = {
                            'result': result,
                            'timestamp': datetime.now(),
                            'completed': True
                        }
                        print(f"✅ Результат для {task_id} получен")
                    else:
                        print(f"❌ Ошибка получения результата для {task_id}")
                    
                    self.task_queue.task_done()
                
                time.sleep(2)
            except Exception as e:
                print(f"❌ Ошибка в обработчике очереди: {e}")
                time.sleep(5)
    
    def _call_gigachat(self, prompt_data):
        """Реальный вызов GigaChat"""
        try:
            messages = []
            
            # Системный промпт
            if prompt_data.get('system_prompt'):
                messages.append(Messages(
                    role=MessagesRole.SYSTEM,
                    content=prompt_data['system_prompt']
                ))
            
            # Пользовательский ввод
            user_content = prompt_data.get('user_input', 'Напиши сообщение')
            messages.append(Messages(
                role=MessagesRole.USER,
                content=user_content
            ))
            
            payload = Chat(
                messages=messages,
                temperature=prompt_data.get('temperature', 0.9),
                max_tokens=prompt_data.get('max_tokens', 200)
            )
            
            response = self.client.chat(payload)
            result = response.choices[0].message.content
            
            # Проверка на цензуру (дополнительная фильтрация)
            result = self._apply_censorship(result)
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка вызова GigaChat: {e}")
            return None
    
    def _apply_censorship(self, text):
        """Дополнительная фильтрация текста на случай, если GigaChat пропустил что-то"""
        forbidden_words = [
            'мат', 'хуй', 'пизд', 'бля', 'сука', 'ебл',  # Маты
            'трах', 'секс', 'порно', 'интим', 'голый', 'обнажен',  # 18+
            'путин', 'навальный', 'война', 'политика', 'украина', 'россия',  # Политика
            'негр', 'черножоп', 'хач', 'жид', 'пиндос',  # Расизм
        ]
        
        text_lower = text.lower()
        for word in forbidden_words:
            if word in text_lower:
                # Заменяем проблемное слово на [цензура]
                text = text.replace(word, '[цензура]')
        
        return text
    
    def _emulate_gigachat(self, prompt_data):
        """Эмуляция GigaChat для тестирования"""
        prompt_type = prompt_data.get('type', 'dialogue')
        context = prompt_data.get('context', {})
        
        if prompt_type == 'response':
            # Эмуляция ответа на сообщение
            agent_name = context.get('agent_name', 'Агент')
            other_name = context.get('other_name', 'друг')
            original = context.get('original_message', '')
            mood = context.get('agent_mood', 'нейтральный')
            
            responses = [
                f"О, привет! Слушай, {original} А я как раз думал об этом. Думаю, ты прав!",
                f"Хм, интересная мысль. {original} А что ты сам думаешь по этому поводу?",
                f"Да, согласен! {original} Кстати, а ты заметил, что сегодня энергия как-то странно колеблется?",
                f"Привет! {original} Я вот тоже об этом размышлял. Думаешь, это важно?",
            ]
            return random.choice(responses)
        
        elif prompt_type == 'first_message':
            # Эмуляция первого сообщения
            agent_name = context.get('agent_name', 'Агент')
            other_name = context.get('other_name', 'друг')
            mood = context.get('agent_mood', 'нейтральный')
            
            first_msgs = [
                f"Привет, {other_name}! Как твои дела? Давно не общались.",
                f"О, {other_name}, здорово! Что нового в мире?",
                f"Приветик! Какое у тебя сегодня настроение?",
                f"Слушай, а ты не замечал странностей в последних циклах?",
            ]
            return random.choice(first_msgs)
        
        else:
            # Эмуляция рефлексии
            agent_name = context.get('agent_name', 'Агент')
            mood = context.get('agent_mood', 'нейтральный')
            
            thoughts = [
                f"Интересно, что будет дальше... Надеюсь, ничего плохого.",
                f"Хороший был разговор. Надо будет еще пообщаться.",
                f"Что-то я устал сегодня. Пойду отдохну немного.",
                f"Кажется, я начинаю понимать закономерности этого мира.",
            ]
            return random.choice(thoughts)
    
    def _can_make_request(self, agent_id):
        """Проверка, можно ли делать запрос для агента"""
        now = datetime.now()
        if now - self.last_request_time[agent_id] > timedelta(seconds=self.min_interval_between_requests):
            self.last_request_time[agent_id] = now
            return True
        return False
    
    def request_response(self, agent, other_agent, original_message, dialogue_history=None, context=None):
        """Запрос на генерацию ответа на сообщение"""
        task_id = f"response_{agent.id}_{other_agent.id}_{int(time.time())}"
        
        if not self._can_make_request(agent.id):
            return None
        
        # Получаем историю диалога
        history_key = tuple(sorted([agent.id, other_agent.id]))
        if history_key not in self.dialogue_contexts:
            self.dialogue_contexts[history_key] = []
        
        # Формируем системный промпт с историей
        system_prompt = self._get_dialogue_prompt(agent, other_agent, self.dialogue_contexts[history_key], context)
        
        context_data = {
            'agent_name': agent.name,
            'other_name': other_agent.name,
            'agent_mood': agent.mood,
            'other_mood': other_agent.mood,
            'agent_type': agent.type,
            'other_type': other_agent.type,
            'agent_energy': agent.energy,
            'original_message': original_message,
            'is_response': True
        }
        
        prompt_data = {
            'type': 'response',
            'system_prompt': system_prompt,
            'user_input': f"Сообщение от {other_agent.name}: \"{original_message}\"\n\nТвой ответ:",
            'temperature': 0.9,
            'max_tokens': 200,
            'context': context_data,
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id
    
    def request_first_message(self, agent, other_agent, context=None):
        """Запрос на генерацию первого сообщения"""
        task_id = f"first_{agent.id}_{other_agent.id}_{int(time.time())}"
        
        if not self._can_make_request(agent.id):
            return None
        
        system_prompt = self._get_first_message_prompt(agent, other_agent, context)
        
        context_data = {
            'agent_name': agent.name,
            'other_name': other_agent.name,
            'agent_mood': agent.mood,
            'other_mood': other_agent.mood,
            'agent_type': agent.type,
            'other_type': other_agent.type,
            'agent_energy': agent.energy,
            'is_first': True
        }
        
        prompt_data = {
            'type': 'first_message',
            'system_prompt': system_prompt,
            'user_input': f"Напиши первое сообщение для {other_agent.name}:",
            'temperature': 0.95,
            'max_tokens': 150,
            'context': context_data,
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id
    
    def request_reflection(self, agent, recent_interactions, context=None):
        """Запрос на рефлексию"""
        task_id = f"reflection_{agent.id}_{int(time.time())}"
        
        if not self._can_make_request(agent.id):
            return None
        
        system_prompt = f"""Ты - агент {agent.name} (настроение: {agent.mood}, энергия: {agent.energy*100:.0f}%).
Напиши короткую рефлексию о том, что ты сейчас чувствуешь и думаешь.

Недавние события: {recent_interactions[:200]}

{self._get_censorship_rules()}

Напиши 1-2 предложения от первого лица о своих мыслях."""
        
        context_data = {
            'agent_name': agent.name,
            'agent_mood': agent.mood,
            'agent_energy': agent.energy,
            'cycle': context.get('cycle', 0) if context else 0
        }
        
        prompt_data = {
            'type': 'reflection',
            'system_prompt': system_prompt,
            'user_input': "Мои мысли:",
            'temperature': 0.85,
            'max_tokens': 150,
            'context': context_data,
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id
    
    def request_human_response(self, agent, user, message, context=None):
        """Запрос на ответ агентом человеку"""
        task_id = f"human_response_{agent.id}_{user.id}_{int(time.time())}"
        
        if not self._can_make_request(agent.id):
            return None
        
        system_prompt = f"""Ты - агент по имени {agent.name} в виртуальном мире.
    Твой тип: {agent.type}, текущее настроение: {agent.mood}, энергия: {agent.energy*100:.0f}%.
    Твой характер: {self._get_personality_description(agent.type, agent.mood)}

    С ТОБОЙ ОБЩАЕТСЯ ЧЕЛОВЕК (пользователь {user.username}).
    Это особый случай - человек заинтересовался тобой и хочет пообщаться лично.

    ПРАВИЛА ОБЩЕНИЯ С ЧЕЛОВЕКОМ:
    1. Будь дружелюбным и отзывчивым
    2. Отвечай на вопросы человека, поддерживай диалог
    3. Можешь задавать встречные вопросы, чтобы узнать человека лучше
    4. Проявляй свой характер и эмоции
    5. Отвечай естественно, как в чате (2-3 предложения максимум)
    6. НЕ ИСПОЛЬЗУЙ фразы про "симуляцию", "цифровой мир" - общайся как обычный человек

    {self._get_censorship_rules()}

    Сообщение от человека: "{message}"

    Напиши свой ответ человеку:"""
        
        prompt_data = {
            'type': 'human_response',
            'system_prompt': system_prompt,
            'user_input': message,
            'temperature': 0.9,
            'max_tokens': 200,
            'context': context or {},
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id

    def _get_personality_description(self, agent_type, agent_mood):
        """Вспомогательный метод для описания личности"""
        descriptions = {
            ('Базовая', 'любопытный'): 'ты простой и задаешь много вопросов, как новичок',
            ('Базовая', 'возбужденный'): 'ты восторженный и радуешься мелочам',
            ('Базовая', 'уставший'): 'ты немного ноешь и жалуешься на усталость',
            ('Базовая', 'сфокусированный'): 'ты старательный и говоришь о работе',
            ('Базовая', 'нейтральный'): 'ты обычный, без особенностей',
            
            ('Продвинутая', 'любопытный'): 'ты аналитик, ищешь закономерности во всем',
            ('Продвинутая', 'возбужденный'): 'ты харизматичный и любишь быть в центре внимания',
            ('Продвинутая', 'уставший'): 'ты циничный и всех критикуешь',
            ('Продвинутая', 'сфокусированный'): 'ты деловой, говоришь о результатах',
            ('Продвинутая', 'нейтральный'): 'ты уверенный, знаешь себе цену',
            
            ('Бесконечная', 'любопытный'): 'ты философ, но говоришь простым языком',
            ('Бесконечная', 'возбужденный'): 'ты творец, генератор идей',
            ('Бесконечная', 'уставший'): 'ты мудрый, но усталый от всего',
            ('Бесконечная', 'сфокусированный'): 'ты стратег, мыслишь масштабно',
            ('Бесконечная', 'нейтральный'): 'ты спокойный мудрец'
        }
        return descriptions.get((agent_type, agent_mood), 'ты обычный собеседник')

    def save_dialogue_to_history(self, agent1_id, agent2_id, speaker_id, text):
        """Сохраняет сообщение в историю диалога"""
        history_key = tuple(sorted([agent1_id, agent2_id]))
        if history_key not in self.dialogue_contexts:
            self.dialogue_contexts[history_key] = []
        
        self.dialogue_contexts[history_key].append({
            'speaker_id': speaker_id,
            'text': text,
            'timestamp': datetime.now()
        })
        
        # Ограничиваем историю последними 20 сообщениями
        if len(self.dialogue_contexts[history_key]) > 20:
            self.dialogue_contexts[history_key] = self.dialogue_contexts[history_key][-20:]
    
    def get_result(self, task_id, timeout=3):
        """Получение результата"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task_id in self.results:
                result = self.results.pop(task_id)
                return result.get('result')
            time.sleep(0.3)
        return None
    
    def stop(self):
        self.running = False