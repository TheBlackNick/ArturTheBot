import telebot
import random
import json
import os
import re
import time
import logging
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv('.env')
load_dotenv('emojis.env')

BOT_TOKEN = os.getenv('BOT_TOKEN')
DEVELOPER_IDS = [int(id.strip()) for id in os.getenv('DEVELOPER_IDS', '').split(',') if id.strip()]
BALANCE_FILE = "balances.json"
FARM_FILE = "farms.json"
COOLDOWN_FILE = "cooldowns.json"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')


# ========== Эмодзи ==========
def get_emoji_tag(name):
    emoji_id = os.getenv(name)
    if not emoji_id:
        logger.warning(f"Эмодзи с именем '{name}' не найден в emojis.env")
        return f"[{name}]"

    # Проверяем, что ID - это число
    try:
        int(emoji_id)
    except ValueError:
        logger.error(f"ID эмодзи '{name}'='{emoji_id}' не является числом!")
        return f"[{name}]"

    logger.info(f"Использую эмодзи {name} с ID: {emoji_id}")
    return f'<tg-emoji emoji-id="{emoji_id}">💰</tg-emoji>'


def format_text(text):
    try:
        # Логируем исходный текст для отладки
        logger.debug(f"Форматируем текст: {text}")

        result = re.sub(r'\[([^\]]+)\]', lambda m: get_emoji_tag(m.group(1)), text)

        # Логируем результат
        logger.debug(f"Результат форматирования: {result}")
        return result
    except Exception as e:
        logger.error(f"Ошибка при форматировании текста: {e}")
        return text


# ========== Баланс и ферма ==========
def load_json(file):
    return json.load(open(file, 'r', encoding='utf-8')) if os.path.exists(file) else {}


def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_balance(user_id):
    return load_json(BALANCE_FILE).get(str(user_id), 0)


def update_balance(user_id, amount):
    balances = load_json(BALANCE_FILE)
    user_id_str = str(user_id)
    balances[user_id_str] = balances.get(user_id_str, 0) + amount
    save_json(BALANCE_FILE, balances)
    return balances[user_id_str]


def get_farm(user_id):
    farms = load_json(FARM_FILE)
    user_id_str = str(user_id)
    if user_id_str not in farms:
        farms[user_id_str] = {"level": 1}
        save_json(FARM_FILE, farms)
    return farms[user_id_str]


def update_farm(user_id, level):
    farms = load_json(FARM_FILE)
    farms[str(user_id)] = {"level": level}
    save_json(FARM_FILE, farms)


def calculate_income(level):
    return level * random.randint(5, 15)


def upgrade_cost(level):
    return 100 * (level ** 2)


# ========== Кулдаун ==========
def get_cooldown(user_id):
    cooldowns = load_json(COOLDOWN_FILE)
    return cooldowns.get(str(user_id), 0)


def set_cooldown(user_id):
    cooldowns = load_json(COOLDOWN_FILE)
    cooldowns[str(user_id)] = time.time()
    save_json(COOLDOWN_FILE, cooldowns)


def can_farm(user_id):
    last_farm = get_cooldown(user_id)
    if last_farm == 0:
        return True, 0
    time_passed = time.time() - last_farm
    if time_passed >= 1800:
        return True, 0
    else:
        return False, 1800 - time_passed


def format_time(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes} мин {secs} сек" if minutes > 0 else f"{secs} сек"


# ========== Клавиатуры ==========
def menu_keyboard():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("Пофармить фурали", callback_data="farm"),
        InlineKeyboardButton("Прокачать ферму", callback_data="upgrade")
    )
    return kb


def confirm_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Да, прокачать", callback_data="confirm"),
        InlineKeyboardButton("Отмена", callback_data="cancel")
    )
    return kb


@bot.message_handler(commands=['e'])
def get_emoji_id(m):
    if m.from_user.id not in DEVELOPER_IDS:
        return
    for e in m.entities:
        if e.type == 'custom_emoji':
            bot.reply_to(m, f"🆔 ID: <code>{e.custom_emoji_id}</code>")
            return
    bot.reply_to(m, "[no] Отправь кастомный эмодзи")


@bot.message_handler(commands=['check_emojis'])
def check_emojis(m):
    """Команда для проверки всех эмодзи в emojis.env"""
    if m.from_user.id not in DEVELOPER_IDS:
        return

    emojis = {
        'star': os.getenv('star'),
        'gold_chest': os.getenv('gold_chest'),
        'lvl_up': os.getenv('lvl_up'),
        'farm_xp': os.getenv('farm_xp'),
        'low_battery': os.getenv('low_battery'),
        'finger_up': os.getenv('finger_up'),
        'no': os.getenv('no')
    }

    text = "<b>Проверка эмодзи в emojis.env:</b>\n\n"
    for name, emoji_id in emojis.items():
        if emoji_id:
            try:
                int(emoji_id)
                text += f"✅ {name}: <code>{emoji_id}</code>\n"
            except ValueError:
                text += f"⚠️ {name}: <code>{emoji_id}</code> - <b>НЕ ЧИСЛО!</b>\n"
        else:
            text += f"❌ {name}: <b>НЕ НАЙДЕН!</b>\n"

    bot.reply_to(m, text)


@bot.message_handler(func=lambda m: m.text and m.text.lower() == "меню")
def show_menu(m):
    farm = get_farm(m.from_user.id)
    balance = get_balance(m.from_user.id)
    cost = upgrade_cost(farm['level'])
    can, remaining = can_farm(m.from_user.id)

    cooldown_text = f"\nФарм через: {format_time(remaining)}" if not can else ""

    text = format_text(
        f"<b>Ферма [star] {farm['level']} ур.</b>\n"
        f"[gold_chest] Баланс: {balance}{cooldown_text}\n\n"
        f"<b>Апгрейд до [star] {farm['level'] + 1} ур.</b>\n"
        f"Стоимость: {cost} [lvl_up]"
    )
    bot.reply_to(m, text, reply_markup=menu_keyboard())


@bot.callback_query_handler(func=lambda c: True)
def handle_callback(c):
    user_id = c.from_user.id
    farm = get_farm(user_id)
    balance = get_balance(user_id)

    if c.data == "farm":
        can, remaining = can_farm(user_id)

        if can:
            earned = calculate_income(farm['level'])
            new_balance = update_balance(user_id, earned)
            set_cooldown(user_id)
            text = format_text(
                f"[farm_xp] Собрал {earned} фуралей!\n"
                f"[gold_chest] Баланс: {new_balance}\n"
                f"[star] Уровень: {farm['level']}\n\n"
                f"Следующий фарм через 30 минут"
            )
        else:
            text = format_text(
                f"[low_battery] <b>Фарм недоступен!</b>\n\n"
                f"Следующий фарм через: {format_time(remaining)}\n"
                f"[gold_chest] Баланс: {balance}"
            )
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=menu_keyboard())

    elif c.data == "upgrade":
        cost = upgrade_cost(farm['level'])
        if balance >= cost:
            text = format_text(
                f"<b>Прокачка до [star] {farm['level'] + 1} ур.</b>\n\n"
                f"Стоимость: {cost} [lvl_up]\n\n"
                f"[finger_up] Подтверждаешь?"
            )
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=confirm_keyboard())
        else:
            text = format_text(
                f"[no] Не хватает {cost - balance}\n"
                f"[gold_chest] Баланс: {balance}"
            )
            bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=menu_keyboard())

    elif c.data == "confirm":
        cost = upgrade_cost(farm['level'])
        if get_balance(user_id) >= cost:
            update_balance(user_id, -cost)
            update_farm(user_id, farm['level'] + 1)
            text = format_text(
                f"[lvl_up] <b>Ферма улучшена до [star] {farm['level'] + 1} ур.</b>"
            )
        else:
            text = "[no] Недостаточно фуралей"
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=menu_keyboard())

    elif c.data == "cancel":
        text = format_text(
            f"<b>Ферма [star] {farm['level']}</b>\n"
            f"[gold_chest] Баланс: {balance}\n"
            f"[lvl_up] Апгрейд: {upgrade_cost(farm['level'])} [lvl_up]"
        )
        bot.edit_message_text(text, c.message.chat.id, c.message.id, reply_markup=menu_keyboard())

    bot.answer_callback_query(c.id)


@bot.message_handler(func=lambda m: m.text and m.text.lower() == "привет артур")
def hello(m):
    try:
        if random.randint(1, 2) == 1:
            with open('stuff/roblox-hi-sound.mp3', 'rb') as voice:
                bot.send_voice(m.chat.id, voice, reply_to_message_id=m.message_id)
        else:
            bot.reply_to(m, f"Привет, {m.from_user.first_name}!")
    except Exception as e:
        logger.error(f"Ошибка в hello: {e}")


@bot.message_handler(func=lambda m: True)
def handle(m):
    text = m.text.lower().strip() if m.text else ""

    if text == "фураль":
        user_id = m.from_user.id
        can, remaining = can_farm(user_id)

        if can:
            farm = get_farm(user_id)
            earned = calculate_income(farm['level'])
            new_balance = update_balance(user_id, earned)
            set_cooldown(user_id)

            response_text = format_text(
                f"[farm_xp] ФАРМА: +{earned}\n"
                f"[gold_chest] Баланс: {new_balance} | [star] Ур.{farm['level']}\n\n"
                f"Следующий фарм через 30 минут"
            )

            # Отправляем без парсинга HTML если есть ошибка
            try:
                bot.reply_to(m, response_text)
            except Exception as e:
                logger.error(f"Ошибка при отправке с HTML: {e}")
                # Отправляем без HTML, заменяя эмодзи на обычный текст
                clean_text = response_text.replace('<tg-emoji', '').replace('</tg-emoji>', '💰')
                bot.reply_to(m, clean_text)
        else:
            response_text = format_text(
                f"[low_battery] <b>Фарм недоступен!</b>\n\n"
                f"Следующий фарм через: {format_time(remaining)}\n"
                f"[gold_chest] Баланс: {get_balance(user_id)}"
            )

            try:
                bot.reply_to(m, response_text)
            except Exception as e:
                logger.error(f"Ошибка при отправке с HTML: {e}")
                clean_text = response_text.replace('<tg-emoji', '').replace('</tg-emoji>', '💰')
                bot.reply_to(m, clean_text)

    elif text in ["кошелёк", "кошелек", "кошель"]:
        balance = get_balance(m.from_user.id)
        farm = get_farm(m.from_user.id)
        can, remaining = can_farm(m.from_user.id)

        cooldown_text = f"\nФарм через: {format_time(remaining)}" if not can else ""

        response_text = format_text(
            f"[gold_chest] Фуралей: {balance}\n\n"
            f"[star] Ур.{farm['level']}{cooldown_text}"
        )

        try:
            bot.reply_to(m, response_text)
        except Exception as e:
            logger.error(f"Ошибка при отправке с HTML: {e}")
            clean_text = response_text.replace('<tg-emoji', '').replace('</tg-emoji>', '💰')
            bot.reply_to(m, clean_text)


if __name__ == "__main__":
    print("🤖 Бот запущен")
    print("\n📝 Список эмодзи, которые должны быть в emojis.env:")
    print("star=ID_эмодзи_звезды")
    print("gold_chest=ID_эмодзи_сундука")
    print("lvl_up=ID_эмодзи_апгрейда")
    print("farm_xp=ID_эмодзи_фарма")
    print("low_battery=ID_эмодзи_батареи")
    print("finger_up=ID_эмодзи_пальца")
    print("no=ID_эмодзи_крестика")
    print("\nИспользуй команду /check_emojis чтобы проверить какие эмодзи отсутствуют\n")

    bot.infinity_polling()