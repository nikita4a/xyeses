import os
import sys
import asyncio
import random
import json  # Для сохранения/восстановления состояния
from datetime import datetime, timedelta
from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError, SlowModeWaitError,
    ChatWriteForbiddenError, PeerIdInvalidError,
    ChannelPrivateError, UserBannedInChannelError,
    UnauthorizedError, RPCError
)
from telethon.tl.functions.messages import ForwardMessagesRequest

# Логирование
logger.add("debug.log", format="{time} {level} {message}", level="INFO")


class SpamBotClient:
    def __init__(self, session_file):
        self.clients = []
        self.session_file = session_file
        self.state_file = "bot_state.json"  # Файл для сохранения состояния
        self.delay_range = (1, 5)  # Задержка между отправками (секунды)
        self.cycle_interval = (12, 14)  # Задержка между циклами (минуты)
        self.report_chat = "https://t.me/infoinfoinfoinfoo"  # Чат для отчетов
        self.last_message_time = {}  # Время последней отправки сообщения
        self.sent_messages_count = {}  # Количество отправленных сообщений

        self._init_environment()
        self.session_configs = self._load_sessions()
        self._init_clients()

        # Восстановление прогресса
        self.state = self._load_state()

    def _init_environment(self):
        os.makedirs('sessions', exist_ok=True)

    def _load_sessions(self):
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                return [self._parse_session_line(line) for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Ошибка загрузки сессий: {str(e)}")
            return []

    def _parse_session_line(self, line):
        parts = line.strip().split(',')
        if len(parts) != 4:
            logger.error(f"Некорректный формат строки: {line.strip()}")
            return None
        return {
            'session_name': parts[0].strip(),
            'api_id': int(parts[1].strip()),
            'api_hash': parts[2].strip(),
            'phone': parts[3].strip()
        }

    def _init_clients(self):
        for config in self.session_configs:
            client = TelegramClient(
                f'sessions/{config["session_name"]}',
                config['api_id'],
                config['api_hash']
            )
            client.phone = config['phone']
            self.clients.append(client)

    def _load_state(self):
        """Загрузка состояния из файла."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    logger.info("📂 Состояние успешно загружено.")
                    return state
            except Exception as e:
                logger.error(f"⚠️ Ошибка загрузки состояния: {str(e)}")
        return {"clients": {}}  # Если файла нет или ошибка, возвращаем пустое состояние

    def _save_state(self):
        """Сохранение текущего состояния в файл."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=4)
            logger.info("💾 Состояние успешно сохранено.")
        except Exception as e:
            logger.error(f"⚠️ Ошибка сохранения состояния: {str(e)}")

    async def forward_messages(self, client):
        sent_count = 0
        try:
            dialogs = await client.get_dialogs()
            target_chats = [d for d in dialogs if d.is_group or d.is_channel]
            messages = await client.get_messages("me", limit=20)  # Берем 10 последних сообщений из "Избранного"

            if not messages:
                logger.warning(f"❌ Нет сообщений в 'Избранном' для {client.phone}")
                return sent_count

            tasks = []
            for chat in target_chats:  # Отправляем сообщения во все чаты
                msg = random.choice(messages)  # Выбираем случайное сообщение
                tasks.append(self._send_message(client, chat, msg))

            results = await asyncio.gather(*tasks)
            sent_count = sum(results)
        except Exception as e:
            logger.error(f"⚠️ Ошибка пересылки сообщений {client.phone}: {str(e)}")
        return sent_count

    async def _send_message(self, client, chat, msg):
        try:
            await client(ForwardMessagesRequest(
                from_peer="me",
                id=[msg.id],
                to_peer=chat
            ))
            self.sent_messages_count[client.phone] = self.sent_messages_count.get(client.phone, 0) + 1
            self.last_message_time[client.phone] = datetime.now()
            logger.success(f"📨 Сообщение переслано в {chat.name} ({client.phone})")
            await asyncio.sleep(random.uniform(*self.delay_range))
            return 1
        except (ChatWriteForbiddenError, PeerIdInvalidError, ChannelPrivateError, UserBannedInChannelError) as e:
            logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
        except RPCError as e:
            logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Ошибка пересылки в {chat.name}: {str(e)}")
        return 0

    async def handle_spam_bot(self, client):
        if datetime.now() - self.last_message_time.get(client.phone, datetime.min) < timedelta(minutes=15):
            return

        logger.warning(f"🆘 {client.phone} не отправлял сообщения 10 минут. Обращаемся к @SpamBot")
        try:
            spam_bot = await client.get_entity("SpamBot")
            async with client.conversation(spam_bot) as conv:
                for _ in range(3):
                    await conv.send_message("/start")
                    response = await conv.get_response()
                    logger.info(f"Ответ от @SpamBot: {response.text}")
                    await asyncio.sleep(random.uniform(2, 5))
        except FloodWaitError as e:
            logger.error(f"❌ FloodWait @SpamBot: ждем {e.seconds} сек")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"❌ Ошибка @SpamBot для {client.phone}: {str(e)}")

    async def send_report(self, client, sent_count, total_chats, delay_minutes):
        report_message = (
            f"📊 Отчет о рассылке:\n"
            f"Аккаунт: {client.phone}\n"
            f"Отправлено сообщений: {sent_count}\n"
            f"Всего чатов: {total_chats}\n"
            f"Следующая рассылка через: {delay_minutes} минут"
        )
        try:
            await client.send_message(self.report_chat, report_message)
            logger.success(f"📨 Отчет отправлен в {self.report_chat} ({client.phone})")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки отчета для {client.phone}: {str(e)}")

    async def enforce_delays(self, client):
        """Задержка для каждого клиента на основании сохраненного состояния."""
        # Получаем задержку для клиента
        client_state = self.state["clients"].get(client.phone, {})
        if "next_run" in client_state:
            next_run = datetime.fromisoformat(client_state["next_run"])
            now = datetime.now()
            if now < next_run:
                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"⏳ Ожидание {wait_seconds / 60:.1f} минут для {client.phone} перед началом следующего цикла.")
                await asyncio.sleep(wait_seconds)

    async def start(self):
        # Инициализация клиентов
        for client in self.clients:
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    logger.error(f"❌ {client.phone} не авторизован. Требуется вход в аккаунт!")
                    continue
                logger.success(f"✅ Успешно авторизован: {client.phone}")
            except Exception as e:
                logger.error(f"Ошибка инициализации {client.phone}: {str(e)}")

        while True:
            # Создаем список задач для параллельного выполнения
            tasks = []
            for client in self.clients:
                await self.enforce_delays(client)  # Задержка перед следующим циклом
                task = asyncio.create_task(self._process_client(client))
                tasks.append(task)

            # Ждем выполнения всех задач
            await asyncio.gather(*tasks)

            # Запланируем следующий запуск
            for client in self.clients:
                delay_minutes = random.randint(*self.cycle_interval)
                next_run = datetime.now() + timedelta(minutes=delay_minutes)
                self.state["clients"][client.phone] = {"next_run": next_run.isoformat()}
            self._save_state()

            self.restart_script()

    async def _process_client(self, client):
        """Обработка одного клиента"""
        sent_count = await self.forward_messages(client)
        dialogs = await client.get_dialogs()
        total_chats = len(dialogs)
        await self.handle_spam_bot(client)
        delay_minutes = random.randint(*self.cycle_interval)
        await self.send_report(client, sent_count, total_chats, delay_minutes)

    def restart_script(self):
        """Перезапуск текущего скрипта"""
        logger.info("🔄 Перезапуск скрипта...")
        os.execl(sys.executable, sys.executable, *sys.argv)


async def main():
    session_file = "sessions.txt"
    bot_client = SpamBotClient(session_file)
    await bot_client.start()

if __name__ == "__main__":
    asyncio.run(main())