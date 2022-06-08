import os
import sys
import time
import logging
import requests
import telegram

from http import HTTPStatus
from dotenv import load_dotenv
from datetime import datetime, timedelta

from exceptions.exceptions import WrongConnectionError

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
COUNT_PREVIOUS_DAYS = 30
ERROR_MESSAGE_LENGTH = 100
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
handler.setFormatter(formatter)


def send_message(bot, message):
    """Отправка сообщения telegram-ботом и логирование статуса отправки."""
    if bot.send_message(TELEGRAM_CHAT_ID, message):
        logger.info(f'Бот отправил сообщение: {message}')
    else:
        logger.error(f'Боту не удалось отправить сообщение: {message}')


def get_api_answer(current_timestamp):
    """Выполнение запроса к сервису и проверка полученного результата."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.ConnectionError as error:
        message = f'Недоступен endpoint сервиса {error}'
        raise requests.ConnectionError(message)
    else:
        if response.status_code == HTTPStatus.OK:
            return response.json()
        else:
            raise WrongConnectionError(
                f'Сервер вернул статус {response.status_code}'
            )


def check_response(response):
    """Проверка структуры данных полученных от сервиса."""
    keys, data = ['current_date', 'homeworks'], []
    for key in keys:
        try:
            data = response[key]
        except KeyError:
            raise KeyError(f'В ответе сервиса нет данных с ключом {key}')
        else:
            if key == 'homeworks' and type(data) != list:
                raise TypeError('Данные homeworks не соответствуют типу list')
    return data


def parse_status(homework):
    """Извлечение данных о статусе домашней работы."""
    homework_name = homework['homework_name']
    homework_status = homework['status']
    try:
        verdict = HOMEWORK_STATUSES[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError as error:
        raise KeyError(
            f'Получен недокументированный статус домашней работы - {error}'
        )


def check_tokens():
    """Проверка переменных окружения."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основная логика работы бота."""
    all_tokens_is_ok = check_tokens()
    if not all_tokens_is_ok:
        message = 'Не заполнены переменные окружения.'
        logger.critical(message)
        raise SystemExit(message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    previous_time = datetime.now() - timedelta(days=COUNT_PREVIOUS_DAYS)
    current_timestamp = int(previous_time.timestamp())
    error_message = ''

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            for homework in homeworks:
                send_message(bot, parse_status(homework))
            if len(homeworks) == 0:
                logger.debug('В ответе нет новых статусов.')
            current_timestamp = response['current_date']
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if error_message != message[:ERROR_MESSAGE_LENGTH]:
                error_message = message[:ERROR_MESSAGE_LENGTH]
                send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
