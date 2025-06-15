import logging
import os

from dotenv import load_dotenv
from telegram import Update, Bot, Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ConversationHandler

import database

# Global variable to store bot username
BOT_USERNAME = None

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Get the bot token from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN or TOKEN == "YOUR_TOKEN_HERE":
    raise ValueError("Не найден TELEGRAM_BOT_TOKEN в .env файле. Пожалуйста, добавьте его.")

# States for ConversationHandler
ASKING_QUESTION = 1

# --- Bot Commands ---

async def getlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send user's personal link."""
    user = update.effective_user
    
    # Add user to database if not exists
    database.add_user(user.id, user.username or user.first_name)
    
    # Get bot username
    bot = await context.bot.get_me()
    bot_username = bot.username
    
    # Create personal link
    personal_link = f"https://t.me/{bot_username}?start={user.id}"
    
    await update.message.reply_text(
        "Ваша персональная ссылка для получения анонимных вопросов:\n\n"
        f"<code>{personal_link}</code>\n\n"
        "Покажите эту ссылку друзьям и подписчикам, чтобы они могли задавать вам анонимные вопросы!",
        parse_mode='HTML'
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the /start command.
    If the command has a payload (from a deep link), it sets up the user to ask a question.
    Otherwise, it shows the generic welcome message.
    """
    user = update.effective_user
    args = context.args

    try:
        if args:
            target_user_id = int(args[0])
            target_user_info = database.get_user(target_user_id)

            # Add user to database if not exists
            database.add_user(target_user_id, None)
            
            context.user_data['target_user_id'] = target_user_id
            logger.info(f"Установлен target_user_id для пользователя {user.id}: {target_user_id}")
            
            target_username = target_user_info[1] if target_user_info else "пользователю"
            await update.message.reply_text(
                f"Привет! Вы собираетесь задать анонимный вопрос {target_username}.\n\n"
                "Просто отправьте свой вопрос следующим сообщением."
            )
            return ASKING_QUESTION
        else:
            await update.message.reply_html(
                f"Привет, {user.mention_html()}!\n\n"
                "Я бот для сбора анонимных вопросов.\n\n"
                "Для получения вашей персональной ссылки используйте команду /getlink\n\n"
                "Чтобы отправить анонимный вопрос другому пользователю, перейдите по его персональной ссылке и напишите вопрос."
            )
            return ConversationHandler.END
    except (ValueError, IndexError) as e:
        logger.error(f"Ошибка при обработке аргументов start: {e}")
        await update.message.reply_text("Неверная ссылка. Пожалуйста, используйте правильную ссылку.")
        return ConversationHandler.END


async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle question answering."""
    user = update.effective_user
    args = context.args
    
    if not args or len(args) < 2:
        await update.message.reply_text("Использование: /answer <ID вопроса> <текст ответа>")
        return
    
    try:
        question_id = int(args[0])
        answer_text = ' '.join(args[1:])
        
        # Add answer to database
        answer_id = database.add_answer(question_id, answer_text)
        if not answer_id:
            await update.message.reply_text("Не удалось сохранить ответ. Пожалуйста, попробуйте снова.")
            return

        # Get question details
        question = database.get_question(question_id)
        if not question:
            await update.message.reply_text("Вопрос не найден.")
            return

        # Notify question sender
        try:
            await context.bot.send_message(
                chat_id=question[1],  # from_user_id
                text="Ваш вопрос был ответлен!"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление отправителю вопроса: {e}")

        await update.message.reply_text("Ответ сохранен и отправитель уведомлен!")
    except ValueError:
        await update.message.reply_text("Неверный формат ID вопроса.")
    except Exception as e:
        logger.error(f"Ошибка при ответе на вопрос: {e}")
        await update.message.reply_text("Произошла ошибка при ответе на вопрос. Пожалуйста, попробуйте снова.")


async def get_my_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Generates a personal link for the user to collect anonymous questions.
    """
    user = update.effective_user
    database.add_user(user.id, user.username or user.first_name)
    
    bot = await context.bot.get_me()
    bot_username = bot.username
    
    personal_link = f"https://t.me/{bot_username}?start={user.id}"
    
    await update.message.reply_text(
        "Вот ваша персональная ссылка для сбора анонимных вопросов:\n\n"
        f"`{personal_link}`\n\n"
        "Поделитесь ей, и когда кто-то напишет вопрос по этой ссылке, я перешлю его вам.",
        parse_mode='MarkdownV2'
    )


async def handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receives a question and forwards it to the target user.
    """
    try:
        target_user_id = context.user_data.get('target_user_id')
        if not target_user_id:
            logger.error("target_user_id не найден в user_data")
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте перейти по ссылке еще раз.")
            return ConversationHandler.END

        message = update.message
        logger.info(f"Получен вопрос от пользователя {message.from_user.id} для пользователя {target_user_id}")
        logger.info(f"Текст вопроса: {message.text}")
        
        # Add sender to database if not exists
        sender_id = message.from_user.id
        sender_username = message.from_user.username or message.from_user.first_name
        database.add_user(sender_id, sender_username)
        
        # Add recipient to database if not exists
        database.add_user(target_user_id, None)  # We don't have recipient's username here
        
        if message.from_user.id == target_user_id:
            logger.info("Пользователь пытается отправить вопрос самому себе")
            await message.reply_text("Вы не можете отправлять анонимные вопросы самому себе.")
            return ConversationHandler.END

        # Save question to database
        question_id = database.add_question(message.from_user.id, target_user_id, message.text)
        if not question_id:
            logger.error("Не удалось сохранить вопрос в базу данных")
            await message.reply_text("Произошла ошибка при сохранении вопроса. Пожалуйста, попробуйте снова.")
            return ConversationHandler.END

        # Get bot username
        try:
            bot = await context.bot.get_me()
            bot_username = bot.username
            logger.info(f"Имя бота: {bot_username}")
        except Exception as e:
            logger.error(f"Ошибка при получении имени бота: {e}")
            await message.reply_text("Произошла ошибка при получении имени бота. Пожалуйста, попробуйте снова.")
            return ConversationHandler.END

        # Create personal link
        personal_link = f"https://t.me/{bot_username}?start={target_user_id}"
        logger.info(f"Создана персональная ссылка: {personal_link}")

        # Notify recipient with question and link
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"<b>У тебя новый анонимный вопрос:</b>\n\n"
                     f"{message.text}\n\n"
                     "✅ <b>Ответ отправлен!</b>\n\n"
                     f"<b>Твоя ссылка для вопросов:</b>\n"
                     f"<code>{personal_link}</code>\n\n"
                     "Покажи эту ссылку друзьям и подписчикам и получай от них анонимные вопросы!",
                parse_mode='HTML'
            )
            logger.info(f"Вопрос и ссылка отправлены пользователю {target_user_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {target_user_id}: {e}")
            await message.reply_text("Произошла ошибка при отправке вопроса. Пожалуйста, попробуйте снова.")
            return ConversationHandler.END

        await message.reply_text("Спасибо! Ваш вопрос был отправлен анонимно.")
        context.user_data.pop('target_user_id', None)
        logger.info(f"target_user_id удален из user_data для пользователя {message.from_user.id}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_question: {e}")
        await update.message.reply_text("Произошла ошибка при обработке вашего вопроса. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    await update.message.reply_text("Действие отменено.")
    context.user_data.pop('target_user_id', None)
    return ConversationHandler.END


async def get_bot_username(context: ContextTypes.DEFAULT_TYPE):
    bot = await context.bot.get_me()
    return bot.username


async def view_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's unanswered questions."""
    user = update.effective_user
    questions = database.get_unanswered_questions(user.id)
    
    if not questions:
        await update.message.reply_text("У вас нет новых вопросов.")
        return
    
    for q in questions:
        question_id, from_username, question_text, created_at = q
        
        # Create answer command
        answer_command = f"/answer_{question_id}"
        
        await update.message.reply_text(
            f"Новый анонимный вопрос:\n\n"
            f"{question_text}\n\n"
            f"Отправитель: {from_username or 'Аноним'}\n"
            f"Дата: {created_at}\n\n"
            f"Ответить: {answer_command}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Ответить", callback_data=f"answer_{question_id}")]
            ])
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    await update.message.reply_text(
        "Для получения вашей персональной ссылки для анонимных вопросов используйте команду /getlink\n\n"
        "Чтобы отправить анонимный вопрос другому пользователю, перейдите по его персональной ссылке и напишите вопрос."
    )


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        query = update.callback_query
        await query.answer()
        
        question_id = int(query.data.split('_')[1])
        
        # Get question details
        question = database.get_question(question_id)
        if not question:
            logger.error(f"Вопрос с ID {question_id} не найден в базе данных")
            await query.message.reply_text("Вопрос не найден.")
            return ConversationHandler.END
        
        # Set up conversation state
        context.user_data['question_id'] = question_id
        logger.info(f"Установлен question_id {question_id} для пользователя {query.from_user.id}")
        
        await query.message.reply_text(
            "Введите ваш ответ на вопрос:\n\n"
            f"{question[3]}"
        )
        
        return ASKING_ANSWER
    except Exception as e:
        logger.error(f"Ошибка в answer_callback: {e}")
        await query.message.reply_text("Произошла ошибка при обработке вопроса. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        question_id = context.user_data.get('question_id')
        if not question_id:
            logger.error("question_id не найден в user_data")
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте ответить на вопрос снова.")
            return ConversationHandler.END
        
        # Get question details
        question = database.get_question(question_id)
        if not question:
            logger.error(f"Вопрос с ID {question_id} не найден в базе данных")
            await update.message.reply_text("Вопрос не найден.")
            return ConversationHandler.END
        
        # Add answer to database
        answer_id = database.add_answer(question_id, update.message.text)
        if not answer_id:
            logger.error(f"Не удалось сохранить ответ для вопроса {question_id}")
            await update.message.reply_text("Не удалось сохранить ответ. Пожалуйста, попробуйте снова.")
            return ConversationHandler.END
        
        # Notify question sender
        try:
            await context.bot.send_message(
                chat_id=question[1],  # from_user_id
                text="Ваш вопрос был ответлен!"
            )
            logger.info(f"Уведомление отправлено отправителю вопроса {question[1]}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление отправителю вопроса: {e}")
        
        await update.message.reply_text("Ответ сохранен и отправитель уведомлен!")
        context.user_data.pop('question_id', None)
        logger.info(f"Ответ сохранен для вопроса {question_id}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Ошибка в handle_answer: {e}")
        await update.message.reply_text("Произошла ошибка при обработке ответа. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END


def main() -> None:
    """Start the bot."""
    try:
        # Initialize database
        database.init_db()
        logger.info("База данных инициализирована")

        # Create application
        application = Application.builder().token(TOKEN).build()
        logger.info("Приложение создано")

        # States for conversation
        ASKING_QUESTION = 1
        ASKING_ANSWER = 2

        # Add conversation handler with the states ASKING_QUESTION and ASKING_ANSWER
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", start)],
            states={
                ASKING_QUESTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_question)
                ],
                ASKING_ANSWER: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )

        application.add_handler(conv_handler)
        
        # Add answer command handler
        application.add_handler(CommandHandler("answer", answer_question))
        
        # Add callback query handler for answer button
        application.add_handler(CallbackQueryHandler(answer_callback, pattern="^answer_"))
        
        # Add message handler for answers
        application.add_handler(MessageHandler(filters.TEXT, handle_answer))
        
        # Add command handlers
        application.add_handler(CommandHandler("getlink", getlink))
        application.add_handler(CommandHandler("help", help_command))
        
        # Set up error handler
        async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            logger.error(f"Ошибка при обработке обновления: {context.error}")
            if update:
                await update.message.reply_text(
                    "Произошла ошибка при обработке вашего сообщения. Пожалуйста, попробуйте снова."
                )

        application.add_error_handler(error_handler)
        logger.info("Обработчик ошибок установлен")

        # Start the bot
        print("Бот запущен в режиме сервиса...")
        logger.info("Запуск бота...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"Ошибка при запуске бота: {e}")
        raise


if __name__ == "__main__":
    main()