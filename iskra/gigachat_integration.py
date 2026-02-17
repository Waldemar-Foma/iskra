# gigachat_integration.py - обновленная версия с контролем частоты

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
        self.credentials ='MDE5YTI1YzEtZDg1Yy03ZDc3LWJiNmEtZTMzNDE1MzQyNTFhOmZjNDkwNGJkLTA3MDktNDdlYS05YWFjLTJiYTBiNWFjNGEwYw=='
        
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
        
        # Кэш для хранения последних ответов (чтобы не генерировать новые каждые 5 секунд)
        self.response_cache = {}
        self.cache_ttl = 300  # 5 минут кэш
        
        # Контроль частоты запросов к API
        self.last_request_time = defaultdict(lambda: datetime.min)
        self.min_interval_between_requests = 10  # минимум 10 секунд между запросами одного агента
        
        self.thread = threading.Thread(target=self._process_queue)
        self.thread.daemon = True
        self.thread.start()
        
        self.system_prompts = {
            'dialogue': """Ты - разумный агент в виртуальной симуляции. Твоя задача - вести естественный диалог с другим агентом. 
            Твои характеристики:
            - Имя: {agent_name}
            - Тип: {agent_type}
            - Настроение: {agent_mood}
            - Энергия: {agent_energy}
            
            Отвечай кратко, но осмысленно. Максимум 2-3 предложения.
            Диалог должен быть естественным и соответствовать твоему настроению.""",
            
            'reflection': """Ты - агент в симуляции. Опиши свои текущие мысли.
            Учти свое текущее состояние:
            - Энергия: {agent_energy}
            - Настроение: {agent_mood}
            - Последние взаимодействия: {recent_interactions}
            
            Будь краток - 1-2 предложения о самом главном."""
        }
    
    def _can_make_request(self, agent_id):
        """Проверка, можно ли делать запрос для агента"""
        now = datetime.now()
        if now - self.last_request_time[agent_id] > timedelta(seconds=self.min_interval_between_requests):
            self.last_request_time[agent_id] = now
            return True
        return False
    
    def _get_cache_key(self, agent_id, other_agent_id, request_type):
        """Создание ключа для кэша"""
        return f"{request_type}_{min(agent_id, other_agent_id)}_{max(agent_id, other_agent_id)}"
    
    def _get_from_cache(self, key):
        """Получение ответа из кэша"""
        if key in self.response_cache:
            cache_time, response = self.response_cache[key]
            if datetime.now() - cache_time < timedelta(seconds=self.cache_ttl):
                return response
            else:
                del self.response_cache[key]
        return None
    
    def _process_queue(self):
        while self.running:
            try:
                if not self.task_queue.empty():
                    task_id, prompt_data = self.task_queue.get()
                    
                    # Проверяем кэш
                    cache_key = prompt_data.get('cache_key')
                    if cache_key:
                        cached = self._get_from_cache(cache_key)
                        if cached:
                            self.results[task_id] = {
                                'result': cached,
                                'timestamp': datetime.now(),
                                'completed': True,
                                'from_cache': True
                            }
                            self.task_queue.task_done()
                            time.sleep(0.1)
                            continue
                    
                    # Проверяем частоту запросов
                    agent_id = prompt_data.get('agent_id')
                    if agent_id and not self._can_make_request(agent_id):
                        # Если слишком часто, возвращаем заглушку
                        self.results[task_id] = {
                            'result': self._get_cooldown_message(prompt_data.get('type', 'dialogue')),
                            'timestamp': datetime.now(),
                            'completed': True
                        }
                        self.task_queue.task_done()
                        time.sleep(0.1)
                        continue
                    
                    if self.client:
                        result = self._call_gigachat(prompt_data)
                    else:
                        result = self._emulate_gigachat(prompt_data)
                    
                    # Сохраняем в кэш
                    if cache_key:
                        self.response_cache[cache_key] = (datetime.now(), result)
                    
                    self.results[task_id] = {
                        'result': result,
                        'timestamp': datetime.now(),
                        'completed': True
                    }
                    
                    self.task_queue.task_done()
                
                time.sleep(1)  # Проверяем очередь каждую секунду
            except Exception as e:
                print(f"Ошибка в обработчике GigaChat: {e}")
                time.sleep(5)
    
    def _get_cooldown_message(self, msg_type):
        """Сообщение когда агент на кулдауне"""
        if msg_type == 'dialogue':
            return "[Агент пока обдумывает ответ...]"
        else:
            return "[Агент собирается с мыслями...]"
    
    def _call_gigachat(self, prompt_data):
        try:
            messages = []
            
            if prompt_data.get('system_prompt'):
                messages.append(Messages(
                    role=MessagesRole.SYSTEM,
                    content=prompt_data['system_prompt']
                ))
            
            messages.append(Messages(
                role=MessagesRole.USER,
                content=prompt_data['user_input']
            ))
            
            payload = Chat(
                messages=messages,
                temperature=prompt_data.get('temperature', 0.7),
                max_tokens=prompt_data.get('max_tokens', 150)  # Уменьшили до 150 токенов
            )
            
            response = self.client.chat(payload)
            return response.choices[0].message.content
            
        except Exception as e:
            print(f"Ошибка вызова GigaChat: {e}")
            return "[Агент временно не доступен]"
    
    def _emulate_gigachat(self, prompt_data):
        """Эмуляция без расхода токенов"""
        prompts = {
            'dialogue': [
                "Приветствую! Как твои дела в этом цикле?",
                "Рад тебя видеть. Есть что обсудить?",
                "Интересные изменения в мире, замечаешь?",
                "Привет! Давно не общались.",
                "Как твоя энергия? У меня всё в порядке.",
                "Слушай, есть идея для совместного исследования.",
                "Привет! Хорошего цикла!",
                "О, привет! Давай синхронизируемся?"
            ],
            'reflection': [
                "Думаю о смысле своего существования.",
                "Наблюдаю за паттернами в поведении других.",
                "Чувствую пульсацию энергии в системе.",
                "Размышляю о цели нашей симуляции.",
                "Заметил интересную закономерность сегодня.",
                "Энергия на оптимальном уровне.",
                "Интересно, что будет дальше...",
                "Пора двигаться дальше."
            ]
        }
        
        prompt_type = prompt_data.get('type', 'dialogue')
        templates = prompts.get(prompt_type, prompts['dialogue'])
        
        return random.choice(templates)
    
    def request_dialogue(self, agent, other_agent, context=None):
        """Запрос на диалог"""
        task_id = f"dialogue_{agent.id}_{other_agent.id}_{time.time()}"
        
        # Проверяем, можно ли делать запрос
        if not self._can_make_request(agent.id):
            return None
        
        system_prompt = self.system_prompts['dialogue'].format(
            agent_name=agent.name,
            agent_type=agent.type,
            agent_mood=agent.mood,
            agent_energy=agent.energy
        )
        
        user_input = f"Скажи что-нибудь {other_agent.name}."
        
        cache_key = self._get_cache_key(agent.id, other_agent.id, 'dialogue')
        
        prompt_data = {
            'type': 'dialogue',
            'system_prompt': system_prompt,
            'user_input': user_input,
            'temperature': 0.8,
            'max_tokens': 100,
            'context': context or {},
            'cache_key': cache_key,
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id
    
    def request_reflection(self, agent, recent_interactions, context=None):
        """Запрос на рефлексию"""
        task_id = f"reflection_{agent.id}_{time.time()}"
        
        # Проверяем, можно ли делать запрос
        if not self._can_make_request(agent.id):
            return None
        
        system_prompt = self.system_prompts['reflection'].format(
            agent_energy=agent.energy,
            agent_mood=agent.mood,
            recent_interactions=recent_interactions[:100]  # Обрезаем
        )
        
        cache_key = f"reflection_{agent.id}"
        
        prompt_data = {
            'type': 'reflection',
            'system_prompt': system_prompt,
            'user_input': "О чем ты думаешь?",
            'temperature': 0.9,
            'max_tokens': 100,
            'context': context or {},
            'cache_key': cache_key,
            'agent_id': agent.id
        }
        
        self.task_queue.put((task_id, prompt_data))
        return task_id
    
    def get_result(self, task_id, timeout=2):
        """Получение результата с уменьшенным таймаутом"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if task_id in self.results:
                result = self.results.pop(task_id)
                return result['result']
            time.sleep(0.2)
        return None
    
    def stop(self):
        self.running = False