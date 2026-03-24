from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio
import json
from datetime import datetime
from typing import Dict, List
import random
import warnings
import google.generativeai as genai
import os
from dotenv import load_dotenv
import requests

# Подавление предупреждений об устаревании
warnings.filterwarnings("ignore", category=FutureWarning)

load_dotenv()

app = FastAPI()

# Настройка AI провайдеров (пробуем в порядке приоритета)
AI_PROVIDERS = []

# 1. Gemini (основной провайдер)
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        gemini_model = genai.GenerativeModel('gemini-3-flash-preview')  # Gemini 3 Flash
        AI_PROVIDERS.append(('gemini', gemini_model))
        print("✓ Gemini API configured")
    except:
        print("✗ Gemini API failed to configure")

# 2. Groq (резервный провайдер)
GROQ_KEY = os.getenv("GROQ_API_KEY")
if GROQ_KEY:
    AI_PROVIDERS.append(('groq', GROQ_KEY))
    print("✓ Groq API configured")

if not AI_PROVIDERS:
    print("⚠ No AI providers configured - using fallback only")

def call_groq_api(prompt: str, api_key: str) -> str:
    """Вызов Groq API"""
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",  # Лучшая модель для многоязычности
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            print(f"[Groq] Response: {result[:200]}...")  # Debug
            return result
        else:
            print(f"Groq API error {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"Groq API error: {e}")
    return None

def generate_with_ai(prompt: str) -> str:
    """Пробует все доступные AI провайдеры по очереди"""
    for provider_name, provider_data in AI_PROVIDERS:
        try:
            if provider_name == 'gemini':
                response = provider_data.generate_content(prompt)
                return response.text.strip()
            elif provider_name == 'groq':
                result = call_groq_api(prompt, provider_data)
                if result:
                    return result
        except Exception as e:
            print(f"{provider_name} failed: {e}")
            continue
    
    return None  # Все провайдеры не сработали

# Состояние игры
games: Dict[str, dict] = {}
leaderboard: List[dict] = []

# Имена ботов
BOT_NAMES = [
    "AI_Predictor_3000", "BotMaster", "CyberOracle", "QuantumGuesser",
    "NeuralNet_Pro", "DeepMind_Fan", "AlgoWizard", "DataDriven",
    "MLPredictor", "SmartBot_X"
]

class BotPlayer:
    """Бот-игрок для создания конкуренции"""
    
    def __init__(self, name: str, skill_level: float = 0.7):
        self.name = name
        self.skill_level = skill_level  # 0.0 - 1.0
        self.score = 0
        
    async def make_prediction(self, events: List[dict], current_time: int) -> dict:
        """Бот делает предсказание"""
        # Выбираем случайное будущее событие
        future_events = [e for e in events if e['time_seconds'] > current_time]
        if not future_events:
            return None
            
        target_event = random.choice(future_events)
        
        # Добавляем погрешность в зависимости от уровня навыка
        error_range = int(20 * (1 - self.skill_level))
        predicted_time = target_event['time_seconds'] + random.randint(-error_range, error_range)
        
        return {
            "time": max(current_time + 1, predicted_time),
            "event_type": target_event['type'],
            "timestamp": datetime.now()
        }

async def spawn_bots(game_id: str, count: int = 3):
    """Создаёт ботов для игры"""
    if game_id not in games:
        return
        
    game = games[game_id]
    
    if "bots" not in game:
        game["bots"] = []
    
    # Получаем имена уже созданных ботов
    existing_bot_names = [bot.name for bot in game["bots"]]
    
    for i in range(count):
        # Выбираем имя, которого ещё нет
        available_names = [n for n in BOT_NAMES if n not in existing_bot_names]
        if not available_names:
            break
            
        bot_name = random.choice(available_names)
        skill = random.uniform(0.5, 0.9)
        bot = BotPlayer(bot_name, skill)
        
        game["bots"].append(bot)
        existing_bot_names.append(bot_name)
        
        # Добавляем бота в таблицу лидеров
        update_leaderboard(bot_name, 0)

async def bot_prediction_loop(game_id: str):
    """Боты периодически делают предсказания"""
    if game_id not in games:
        return
        
    game = games[game_id]
    
    while game["simulator"].current_time < 300:
        await asyncio.sleep(random.randint(3, 10))  # Боты предсказывают каждые 3-10 секунд
        
        if "bots" not in game:
            continue
            
        for bot in game["bots"]:
            prediction = await bot.make_prediction(
                game["simulator"].events,
                game["simulator"].current_time
            )
            
            if prediction:
                # Сохраняем предсказание бота
                if not hasattr(bot, 'predictions'):
                    bot.predictions = []
                bot.predictions.append(prediction)
                
                # Проверяем предсказания ботов при событиях
                # (это будет сделано в check_bot_predictions)

async def broadcast_to_game(game_id: str, message: dict):
    """Отправляет сообщение всем игрокам в игре"""
    if game_id not in games:
        return
    
    game = games[game_id]
    disconnected = []
    
    for player in game["players"]:
        try:
            await player["websocket"].send_json(message)
        except Exception as e:
            print(f"Error broadcasting to {player['name']}: {e}")
            disconnected.append(player)
    
    # Удаляем отключенных игроков
    for player in disconnected:
        if player in game["players"]:
            game["players"].remove(player)

async def check_predictions_for_event(game_id: str, event: dict, current_time: int):
    """Проверяет предсказания всех игроков для события"""
    if game_id not in games:
        return
    
    game = games[game_id]
    
    # Проверяем предсказания игроков
    for player in game["players"]:
        for prediction in player["predictions"]:
            if prediction.get("checked"):
                continue
                
            # Проверяем, подходит ли это предсказание к событию
            if prediction["event_type"] == event["type"]:
                time_diff = abs(event["time_seconds"] - prediction["time"])
                
                points = 0
                if time_diff <= 2:
                    points = 100
                elif time_diff <= 5:
                    points = 50
                elif time_diff <= 10:
                    points = 25
                
                if points > 0:
                    player["score"] += points
                    prediction["checked"] = True
                    
                    # Отправляем уведомление игроку о его очках
                    try:
                        await player["websocket"].send_json({
                            "type": "score_update",
                            "score": player["score"],
                            "points_earned": points
                        })
                    except:
                        pass
                    
                    # Уведомляем всех о успешном предсказании игрока (как у ботов)
                    await broadcast_to_game(game_id, {
                        "type": "player_success",
                        "player_name": player["name"],
                        "event_type": event["type"],
                        "points": points
                    })
                    
                    # Обновляем таблицу лидеров
                    update_leaderboard(player["name"], player["score"])
    
    # Проверяем предсказания ботов (максимум 1 бот угадывает)
    if "bots" in game:
        bot_guessed = False
        # Перемешиваем ботов для случайности
        bots_shuffled = list(game["bots"])
        random.shuffle(bots_shuffled)
        
        for bot in bots_shuffled:
            if bot_guessed:
                break
                
            if not hasattr(bot, 'predictions'):
                continue
                
            for prediction in bot.predictions:
                if prediction.get("checked"):
                    continue
                    
                if prediction["event_type"] == event["type"]:
                    time_diff = abs(event["time_seconds"] - prediction["time"])
                    
                    # Только 30% шанс что бот угадает
                    if random.random() > 0.3:
                        prediction["checked"] = True
                        continue
                    
                    # Используем ту же систему очков что и у игроков
                    points = 0
                    if time_diff <= 2:
                        points = 100
                    elif time_diff <= 5:
                        points = 50
                    elif time_diff <= 10:
                        points = 25
                    
                    if points > 0:
                        bot.score += points
                        prediction["checked"] = True
                        update_leaderboard(bot.name, bot.score)
                        bot_guessed = True
                        
                        # Уведомляем всех о предсказании бота
                        await broadcast_to_game(game_id, {
                            "type": "bot_prediction",
                            "bot_name": bot.name,
                            "event_type": event["type"],
                            "points": points
                        })
                        break

class GameSimulator:
    """Симулирует спортивную трансляцию с событиями"""
    
    # Конфигурация событий для разных видов спорта
    SPORT_EVENTS = {
        'football': {
            'events': ['гол', 'удар', 'угловой', 'фол'],
            'descriptions': {
                'гол': ['ГОЛ! Невероятно!', 'Мяч в воротах!', 'Гол! Фантастика!'],
                'удар': ['Удар по воротам!', 'Опасный момент!', 'Мощный удар!'],
                'угловой': ['Угловой удар', 'Корнер!', 'Опасный угловой'],
                'фол': ['Нарушение правил', 'Фол!', 'Жёлтая карточка']
            }
        },
        'boxing': {
            'events': ['удар', 'нокдаун', 'клинч', 'предупреждение'],
            'descriptions': {
                'удар': ['Сильный удар!', 'Точная комбинация!', 'Мощный хук!'],
                'нокдаун': ['НОКДАУН!', 'Боксёр на полу!', 'Сильнейший удар!'],
                'клинч': ['Клинч', 'Борьба в захвате', 'Рефери разнимает'],
                'предупреждение': ['Предупреждение!', 'Нарушение правил', 'Замечание рефери']
            }
        },
        'esports': {
            'events': ['убийство', 'хедшот', 'ace', 'дефьюз'],
            'descriptions': {
                'убийство': ['Фраг!', 'Убийство!', 'Элиминация!'],
                'хедшот': ['ХЕДШОТ!', 'В голову!', 'Точный выстрел!'],
                'ace': ['ACE! Всех убил!', 'ACE!', 'Пятерка!'],
                'дефьюз': ['Бомба обезврежена!', 'Дефьюз!', 'Успели!']
            }
        }
    }
    
    def __init__(self, game_type: str):
        self.game_type = game_type
        self.start_time = datetime.now()
        self.events = []
        self.current_time = 0
        self.commentary_history = []
        self.score = [0, 0]  # Счёт матча
        self.sport_config = self.SPORT_EVENTS.get(game_type, self.SPORT_EVENTS['football'])
        
    async def generate_live_commentary(self, context: str) -> str:
        """Генерирует живой комментарий через AI"""
        
        # Специфичные промпты для каждого вида спорта
        sport_prompts = {
            'football': {
                'system': 'You are a professional Russian football commentator.',
                'examples': """GOOD examples:
- "Гол! Невероятный удар!"
- "Опасный момент у ворот!"
- "Угловой удар!"
- "Фол в центре поля!"
- "Атака развивается!"
- "Вратарь в игре!"

BAD examples (DO NOT USE):
- "Играть началось! Итак, начнем!"
- "Наши парни в штрафной теперь!"
- "Напряжение на ринге!"
- "Фраг команды!"
""",
                'context_words': 'поле, ворота, мяч, удар, гол, атака, защита'
            },
            'boxing': {
                'system': 'You are a professional Russian boxing commentator.',
                'examples': """GOOD examples:
- "Мощный удар в корпус!"
- "Боксёр атакует!"
- "Клинч! Рефери разнимает!"
- "Точная комбинация!"
- "Нокдаун! Невероятно!"
- "Предупреждение от рефери!"

BAD examples (DO NOT USE):
- "Гол! Мяч в воротах!"
- "Угловой удар!"
- "Фраг! Убийство!"
- "Напряжение у ворот!"
""",
                'context_words': 'ринг, удар, раунд, боксёр, клинч, нокдаун, рефери'
            },
            'esports': {
                'system': 'You are a professional Russian esports (CS:GO) commentator.',
                'examples': """GOOD examples:
- "Фраг! Отличный выстрел!"
- "Хедшот! Невероятная точность!"
- "ACE! Все враги повержены!"
- "Бомба установлена!"
- "Дефьюз! Успели!"
- "Клатч ситуация!"

BAD examples (DO NOT USE):
- "Гол! Мяч в воротах!"
- "Угловой удар!"
- "Фол в центре поля!"
- "Напряжение у ворот!"
- "Удар по воротам!"
""",
                'context_words': 'карта, фраг, бомба, раунд, команда, выстрел, позиция'
            }
        }
        
        sport_info = sport_prompts.get(self.game_type, sport_prompts['football'])
        
        prompt = f"""{sport_info['system']} Generate ONE SHORT exciting commentary in Russian (maximum 8 words).

Sport: {self.game_type.upper()}
Context: {context}
Time: {self.current_time}s
Score: {self.score[0]}-{self.score[1]}

CRITICAL RULES:
- Write ONLY in proper Russian language
- Maximum 8 words total
- Use natural Russian {self.game_type} commentary style
- Be enthusiastic but professional
- NO English words
- NO awkward phrases
- Use exclamation marks sparingly
- Use ONLY {self.game_type}-specific terminology: {sport_info['context_words']}

{sport_info['examples']}

Return ONLY the commentary, nothing else."""

        commentary = None
        try:
            result = generate_with_ai(prompt)
            if result:
                commentary = result.strip()
                # Убираем лишнее форматирование
                commentary = commentary.replace('*', '').replace('#', '').replace('"', '').replace('—', '-')
                # Ограничиваем длину строго
                if len(commentary) > 100:
                    commentary = commentary[:100] + "..."
        except Exception as e:
            error_msg = str(e)
            print(f"Commentary error: {error_msg}")
        
        # Если AI не сработал, используем fallback
        if not commentary:
            # Fallback на простые комментарии в зависимости от вида спорта
            if self.game_type == 'boxing':
                if "нокдаун" in context.lower() or "knockdown" in context.lower():
                    comments = [
                        "НОКДАУН! Невероятный момент!",
                        "Боксёр на полу! Сильнейший удар!",
                        "Нокдаун! Рефери считает!",
                        "Мощнейший удар! Нокдаун!"
                    ]
                    commentary = random.choice(comments)
                elif "удар" in context.lower() or "punch" in context.lower():
                    comments = [
                        "Сильный удар в корпус!",
                        "Точная комбинация!",
                        "Мощный хук!",
                        "Боксёр атакует!"
                    ]
                    commentary = random.choice(comments)
                elif "клинч" in context.lower() or "clinch" in context.lower():
                    comments = [
                        "Клинч! Рефери разнимает!",
                        "Борьба в захвате!",
                        "Клинч на ринге!",
                        "Рефери останавливает клинч!"
                    ]
                    commentary = random.choice(comments)
                elif "предупреждение" in context.lower() or "warning" in context.lower():
                    comments = [
                        "Предупреждение от рефери!",
                        "Нарушение правил!",
                        "Замечание боксёру!",
                        "Рефери делает предупреждение!"
                    ]
                    commentary = random.choice(comments)
                elif "starting" in context.lower() or "начинается" in context.lower():
                    commentary = "Бой начинается! Боксёры готовы!"
                else:
                    comments = [
                        "Напряжённый раунд продолжается!",
                        "Боксёры обмениваются ударами!",
                        "Интересный момент на ринге!",
                        "Борьба продолжается!"
                    ]
                    commentary = random.choice(comments)
                    
            elif self.game_type == 'esports':
                if "ace" in context.lower():
                    comments = [
                        "ACE! Все враги повержены!",
                        "ACE! Невероятная игра!",
                        "Пятерка! ACE!",
                        "ACE! Фантастика!"
                    ]
                    commentary = random.choice(comments)
                elif "хедшот" in context.lower() or "headshot" in context.lower():
                    comments = [
                        "ХЕДШОТ! В голову!",
                        "Точный выстрел в голову!",
                        "Хедшот! Мгновенная элиминация!",
                        "В голову! Хедшот!"
                    ]
                    commentary = random.choice(comments)
                elif "убийство" in context.lower() or "kill" in context.lower():
                    comments = [
                        "Фраг! Отличный выстрел!",
                        "Убийство! Элиминация!",
                        "Фраг команды!",
                        "Противник повержен!"
                    ]
                    commentary = random.choice(comments)
                elif "дефьюз" in context.lower() or "defuse" in context.lower():
                    comments = [
                        "Бомба обезврежена! Успели!",
                        "Дефьюз! Раунд выигран!",
                        "Обезвредили бомбу!",
                        "Дефьюз в последний момент!"
                    ]
                    commentary = random.choice(comments)
                elif "starting" in context.lower() or "начинается" in context.lower():
                    commentary = "Раунд начинается! Команды готовы!"
                else:
                    comments = [
                        "Напряжённая ситуация на карте!",
                        "Команды борются за позиции!",
                        "Интересный момент в раунде!",
                        "Игра продолжается!"
                    ]
                    commentary = random.choice(comments)
                    
            else:  # football
                if "гол" in context.lower() or "goal" in context.lower():
                    comments = [
                        "ГОЛ! Невероятный момент!",
                        "Гол! Фантастический удар!",
                        "Мяч в воротах! Потрясающе!",
                        "Гооол! Какой момент!"
                    ]
                    commentary = random.choice(comments)
                elif "удар" in context.lower() or "shot" in context.lower():
                    comments = [
                        "Опасный удар по воротам!",
                        "Сильный удар! Вратарь напряжён!",
                        "Удар! Чуть мимо ворот!",
                        "Мощный удар!"
                    ]
                    commentary = random.choice(comments)
                elif "угловой" in context.lower() or "corner" in context.lower():
                    comments = [
                        "Угловой удар! Опасный момент!",
                        "Корнер! Все в штрафной!",
                        "Угловой! Шанс забить!",
                        "Розыгрыш углового!"
                    ]
                    commentary = random.choice(comments)
                elif "фол" in context.lower() or "foul" in context.lower():
                    comments = [
                        "Фол! Судья остановил игру!",
                        "Нарушение правил!",
                        "Фол в опасной зоне!",
                        "Жёлтая карточка!"
                    ]
                    commentary = random.choice(comments)
                elif "starting" in context.lower() or "начинается" in context.lower():
                    commentary = "Матч начинается! Следите за событиями!"
                elif "situation" in context.lower():
                    comments = [
                        "Игра продолжается, напряжение растёт!",
                        "Обе команды активно атакуют!",
                        "Интересный момент в игре!",
                        "Борьба продолжается!"
                    ]
                    commentary = random.choice(comments)
                else:
                    commentary = "Игра продолжается!"
        
        return commentary
        
    async def generate_event_schedule(self):
        """LLM генерирует расписание событий для реалистичности"""
        event_types = ', '.join([f'"{e}"' for e in self.sport_config['events']])
        
        # Специфичные промпты для каждого вида спорта
        sport_context = {
            'football': {
                'description': 'football match',
                'examples': 'гол (goal), удар (shot), угловой (corner), фол (foul)',
                'context': 'Match events should be realistic for a 5-minute football game with goals, shots, corners, and fouls.'
            },
            'boxing': {
                'description': 'boxing match',
                'examples': 'удар (punch), нокдаун (knockdown), клинч (clinch), предупреждение (warning)',
                'context': 'Boxing round events should include punches, clinches, occasional knockdowns, and referee warnings.'
            },
            'esports': {
                'description': 'CS:GO esports match',
                'examples': 'убийство (kill), хедшот (headshot), ace (ace - 5 kills), дефьюз (defuse)',
                'context': 'CS:GO round events should include kills, headshots, occasional aces, and bomb defuses.'
            }
        }
        
        sport_info = sport_context.get(self.game_type, sport_context['football'])
        
        prompt = f"""Generate a realistic {sport_info['description']} event schedule.

Sport: {self.game_type.upper()}
{sport_info['context']}

Return ONLY a valid JSON array. Each event must have:
- time_seconds: integer from 0 to 300
- type: MUST be one of these Russian words: {event_types}
- description: SHORT natural Russian description (3-5 words max) appropriate for {self.game_type}

CRITICAL RULES:
- Return ONLY the JSON array, no other text
- Use proper Russian language
- Keep descriptions SHORT and natural
- 8-10 events total
- Spread events throughout 0-300 seconds
- Use ONLY {self.game_type}-specific terminology
- Examples of event types: {sport_info['examples']}

Return ONLY the JSON array now:"""

        events_generated = False
        try:
            result = generate_with_ai(prompt)
            if result:
                # Извлекаем JSON из ответа
                text = result.strip()
                
                # Убираем markdown форматирование если есть
                if '```json' in text:
                    text = text.split('```json')[1].split('```')[0]
                elif '```' in text:
                    text = text.split('```')[1].split('```')[0]
                
                text = text.strip()
                
                # Ищем JSON массив в тексте
                start = text.find('[')
                end = text.rfind(']')
                if start != -1 and end != -1:
                    text = text[start:end+1]
                
                print(f"[Debug] Parsing JSON: {text[:200]}...")
                
                events_data = json.loads(text)
                
                # Проверяем что это список событий
                if isinstance(events_data, list) and len(events_data) > 0:
                    # Проверяем что события имеют нужные поля
                    valid_events = []
                    for event in events_data:
                        if isinstance(event, dict) and 'time_seconds' in event and 'type' in event:
                            valid_events.append(event)
                    
                    if valid_events:
                        self.events = sorted(valid_events, key=lambda x: x['time_seconds'])
                        print(f"[AI] Generated {len(self.events)} events")
                        events_generated = True
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            if result:
                print(f"[Debug] Raw response: {result[:500]}")
        except Exception as e:
            print(f"Error generating events with AI: {e}")
        
        # Fallback если AI не сработал
        if not events_generated:
            print("[Fallback] Using predefined events")
            # Используем события для выбранного вида спорта
            event_types = self.sport_config['events']
            descriptions = self.sport_config['descriptions']
            
            self.events = []
            times = [25, 50, 75, 100, 125, 150, 175, 200, 225, 250]
            for i, time in enumerate(times):
                event_type = event_types[i % len(event_types)]
                desc = random.choice(descriptions[event_type])
                self.events.append({
                    "time_seconds": time,
                    "type": event_type,
                    "description": desc
                })
    
    async def run(self, game_id: str):
        """Запускает симуляцию трансляции"""
        await self.generate_event_schedule()
        
        # Уведомляем, что игра готова
        await broadcast_to_game(game_id, {
            "type": "game_ready"
        })
        
        # Отправляем начальный комментарий
        intro_commentary = await self.generate_live_commentary("Match is starting")
        await broadcast_to_game(game_id, {
            "type": "commentary",
            "text": intro_commentary
        })
        
        last_commentary_time = 0
        
        while self.current_time < 300:  # 5 минут игры
            await asyncio.sleep(1)
            self.current_time += 1
            
            # Отправляем текущее время
            await broadcast_to_game(game_id, {
                "type": "time_update",
                "time": self.current_time
            })
            
            # Проверяем события
            for event in self.events:
                if abs(event['time_seconds'] - self.current_time) < 0.5:
                    # Обновляем счёт если гол
                    if event['type'] == 'гол':
                        self.score[random.randint(0, 1)] += 1
                    
                    # Генерируем комментарий для события
                    commentary = await self.generate_live_commentary(
                        f"{event['type']}: {event['description']}"
                    )
                    
                    await broadcast_to_game(game_id, {
                        "type": "event",
                        "event": event,
                        "commentary": commentary,
                        "score": self.score
                    })
                    
                    # Проверяем предсказания игроков ПОСЛЕ события
                    await check_predictions_for_event(game_id, event, self.current_time)
                    
                    last_commentary_time = self.current_time
            
            # Периодический комментарий (каждые 20 секунд)
            if self.current_time - last_commentary_time >= 20 and self.current_time % 20 == 0:
                commentary = await self.generate_live_commentary("General match situation")
                await broadcast_to_game(game_id, {
                    "type": "commentary",
                    "text": commentary
                })
                last_commentary_time = self.current_time

@app.get("/")
async def get_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(
        content=content,
        headers={
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-cache"
        }
    )

@app.websocket("/ws/game/{game_id}")
async def websocket_game(websocket: WebSocket, game_id: str):
    await websocket.accept()
    
    # Получаем имя игрока и тип спорта
    data = await websocket.receive_json()
    player_name = data.get("player_name", "Anonymous")
    sport_type = data.get("sport_type", "football")
    
    if game_id not in games:
        games[game_id] = {
            "players": [],
            "bots": [],
            "simulator": GameSimulator(sport_type),
            "started": False
        }
        # Создаём ботов
        await spawn_bots(game_id, count=3)
    
    game = games[game_id]
    player = None
    
    try:
        
        player = {
            "name": player_name,
            "predictions": [],
            "score": 0,
            "websocket": websocket
        }
        game["players"].append(player)
        
        # Добавляем игрока в таблицу лидеров сразу
        update_leaderboard(player_name, 0)
        
        # Запускаем симуляцию если ещё не запущена
        if not game["started"]:
            game["started"] = True
            asyncio.create_task(game["simulator"].run(game_id))
            asyncio.create_task(bot_prediction_loop(game_id))
        
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "prediction":
                # Игрок делает предсказание
                prediction = {
                    "time": data["predicted_time"],
                    "event_type": data["event_type"],
                    "timestamp": datetime.now()
                }
                player["predictions"].append(prediction)
                # Очки будут начислены когда событие произойдёт
                
    except WebSocketDisconnect:
        if player and player in game["players"]:
            game["players"].remove(player)
    except Exception as e:
        print(f"WebSocket error: {e}")
        if player and player in game["players"]:
            game["players"].remove(player)

def calculate_prediction_score(prediction: dict, events: List[dict], current_time: int) -> int:
    """Вычисляет очки за предсказание"""
    predicted_time = prediction["time"]
    event_type = prediction["event_type"]
    
    # Ищем ближайшее событие нужного типа
    for event in events:
        if event["type"] == event_type and event["time_seconds"] >= current_time:
            time_diff = abs(event["time_seconds"] - predicted_time)
            
            # Чем точнее, тем больше очков
            if time_diff <= 2:
                return 100
            elif time_diff <= 5:
                return 50
            elif time_diff <= 10:
                return 25
    
    return 0

def update_leaderboard(player_name: str, score: int):
    """Обновляет таблицу лидеров"""
    global leaderboard
    
    # Ищем игрока
    player_entry = next((p for p in leaderboard if p["name"] == player_name), None)
    
    if player_entry:
        player_entry["score"] = score
    else:
        leaderboard.append({"name": player_name, "score": score})
    
    # Сортируем
    leaderboard.sort(key=lambda x: x["score"], reverse=True)

@app.get("/api/leaderboard")
async def get_leaderboard():
    return {"leaderboard": leaderboard[:10]}

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")
