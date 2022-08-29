import os
import sys
import time
import logging
import requests


from telegram import Bot
from http import HTTPStatus
from dotenv import load_dotenv
from typing import List, Dict, Union
from datetime import datetime, timedelta
from exceptions.exceptions import WrongConnectionError, BotSendMessageError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 10
COUNT_PREVIOUS_DAYS = 30
ERROR_MESSAGE_LENGTH = 100
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def send_message(bot: Bot, message: str) -> str:
    """Отправка сообщения telegram-ботом и логирование статуса отправки."""

    logger.info('Начало отправки сообщения ботом')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except BotSendMessageError as error:
        message = (f'Боту не удалось отправить сообщение: {message} по '
                   f'причине {error}')
        logger.error(message)
        raise BotSendMessageError(message)
    else:
        logger.info(f'Бот отправил сообщение: {message}')


def get_api_answer(current_timestamp: int) -> Dict[str, Union[list, int]]:
    """Выполнение запроса к сервису и проверка полученного результата."""

    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        logger.info('Начато выполнение запроса к API')
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except Exception as error:
        message = f'Недоступен endpoint сервиса {error}'
        raise ConnectionError(message) from error
    else:
        if response.status_code == HTTPStatus.OK:
            logger.info('Запрос к API завершен успешно')
            return response.json()
        else:
            message = (
                f'Неверный результат запроса к API: '
                f'Сервер вернул статус {response.status_code} '
                f'при исполнении запроса к url {response.url}. '
                f'Перенаправление: {["Нет", "Да"][response.is_redirect]}'
            )
            logger.error(message)
            raise WrongConnectionError(message)


def check_response(response: dict) -> List[list]:
    """Проверка структуры данных полученных от сервиса."""

    if not isinstance(response, dict):
        raise TypeError('Ответ сервиса не является словарем')
    if not all(['current_date' in response, 'homeworks' in response]):
        raise KeyError('В ответе сервиса нет данных по нужным ключам')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Данные homeworks не являются списком')
    return response['homeworks']


def parse_status(homework: list) -> str:
    """Извлечение данных о статусе домашней работы."""

    homework_name = homework['homework_name']
    homework_status = homework['status']
    try:
        verdict = VERDICTS[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError as error:
        raise KeyError(
            f'Получен недокументированный статус домашней работы - {error}'
        )


def check_tokens() -> bool:
    """Проверка переменных окружения."""

    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основная логика работы бота."""

    all_tokens_is_ok = check_tokens()
    if not all_tokens_is_ok:
        message = 'Не заполнены переменные окружения.'
        logger.critical(message)
        raise sys.exit(message)

    bot = Bot(token=TELEGRAM_TOKEN)
    previous_time = datetime.now() - timedelta(days=COUNT_PREVIOUS_DAYS)
    current_timestamp = int(previous_time.timestamp())
    previous_messages = {'message': '', 'error': ''}

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if len(homeworks) > 0:
                homework = sorted(homeworks, key=lambda x: x['id'])[-1]
                message = parse_status(homework)
                if previous_messages['message'] != message:
                    previous_messages['message'] = message
                    send_message(bot, message)
            else:
                logger.debug('В ответе нет новых статусов.')
            current_timestamp = response['current_date']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if previous_messages['error'] != message[:ERROR_MESSAGE_LENGTH]:
                previous_messages['error'] = message[:ERROR_MESSAGE_LENGTH]
                send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)
    formatter = logging.Formatter(
        ('%(asctime)s - %(filename)s, %(funcName)s: %(lineno)d - '
         '[%(levelname)s] %(message)s')
    )
    handler.setFormatter(formatter)

    main()
