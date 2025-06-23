import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from prometheus_client import Counter, generate_latest
from aiohttp import web
import threading
import asyncio

bot = telebot.TeleBot('5994168191:AAFGAqQrShejPEELrA9gpFHd5pKIyzgV_nY')

# Метрики Prometheus
games_started = Counter('ttt_games_started_total', 'Total games started')
games_draw = Counter('ttt_games_draw_total', 'Total games ended in a draw')
games_player_won = Counter('ttt_games_player_won_total', 'Games won by player')
games_bot_won = Counter('ttt_games_bot_won_total', 'Games won by bot')
moves_made = Counter('ttt_moves_total', 'Total moves made')

# Ігровий стан
games = {}

def check_winner(board, symbol):
    wins = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
    return any(all(board[i] == symbol for i in line) for line in wins)

def is_draw(board):
    return all(cell != ' ' for cell in board)

def get_inline_keyboard(board):
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for i in range(9):
        text = board[i] if board[i] != ' ' else str(i + 1)
        callback = str(i) if board[i] == ' ' else 'none'
        buttons.append(InlineKeyboardButton(text=text, callback_data=callback))
    markup.add(*buttons)
    return markup

def get_restart_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="🔁 Зіграти ще раз", callback_data="restart"))
    return markup

@bot.message_handler(commands=['start'])
def start_game(message):
    games[message.chat.id] = [' '] * 9
    games_started.inc()
    board = games[message.chat.id]
    bot.send_message(message.chat.id, "Гра почалась! Обери клітинку:", reply_markup=get_inline_keyboard(board))

@bot.callback_query_handler(func=lambda call: True)
def handle_move(call):
    user_id = call.message.chat.id

    if call.data == 'restart':
        start_game(call.message)
        return

    if call.data == 'none':
        bot.answer_callback_query(call.id, "Ця клітинка вже зайнята")
        return

    pos = int(call.data)

    if user_id not in games:
        bot.answer_callback_query(call.id, "Гру не знайдено. Натисни /start")
        return

    board = games[user_id]
    if board[pos] != ' ':
        bot.answer_callback_query(call.id, "Ця клітинка вже зайнята")
        return

    board[pos] = 'X'
    moves_made.inc()

    if check_winner(board, 'X'):
        games_player_won.inc()
        bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Ти переміг! 🥳", reply_markup=get_restart_keyboard())
        del games[user_id]
        return

    if is_draw(board):
        games_draw.inc()
        bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Нічия 🤝", reply_markup=get_restart_keyboard())
        del games[user_id]
        return

    for i in range(9):
        if board[i] == ' ':
            board[i] = 'O'
            break

    if check_winner(board, 'O'):
        games_bot_won.inc()
        bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Бот переміг! 🤖", reply_markup=get_restart_keyboard())
        del games[user_id]
        return

    if is_draw(board):
        games_draw.inc()
        bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Нічия 🤝", reply_markup=get_restart_keyboard())
        del games[user_id]
        return

    bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=get_inline_keyboard(board))

# Сервер для метрик Prometheus
async def metrics(request):
    return web.Response(body=generate_latest(), content_type='text/plain')

def start_metrics_server():
    app = web.Application()
    app.router.add_get('/metrics', metrics)
    runner = web.AppRunner(app)

    async def _run():
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 9091)
        await site.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run())
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=start_metrics_server, daemon=True).start()
    bot.polling(none_stop=True, interval=0)