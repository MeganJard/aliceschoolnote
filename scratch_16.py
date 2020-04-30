import json
import logging
import sqlite3

import requests
from flask import Flask, request
from flask import g

app = Flask(__name__)
DATABASE = 'db/database.db'
logging.basicConfig(level=logging.INFO, filename='app.log',
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=True):
    with app.app_context():
        cur = get_db().execute(query, args)
        rv = cur.fetchall()
        cur.close()
        get_db().commit()
        return (str(rv[0][0]) if rv else None) if one else rv


def getcoords(text): #из текста - в координаты
    server = 'https://geocode-maps.yandex.ru/1.x'
    params = {
        'apikey': '40d1649f-0493-4b70-98ba-98533de7710b',
        'geocode': text,
        'format': 'json'
    }
    response = requests.get(server, params=params)
    return ','.join(response.json()["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]['Point']['pos'].split())


@app.route('/post', methods=['POST'])
def main():
    logging.info('Request: %r', request.json)
    response = {
        'session': request.json['session'],
        'version': request.json['version'],
        'response': {
            'end_session': False
        }
    }
    handle_dialog(response, request.json)
    logging.info('Request: %r', response)
    return json.dumps(response)


def handle_dialog(res, req):
    user_id = ''
    if req['session']['new']:  # приветствуем юзера в первый раз
        res['response']['text'] = 'Здавствуйте, я помогу Вам улучшить получение домашней работы!'
        if 'user' in req['session']:
            if req['session']['user']['user_id']:
                res['response']['buttons'] = [
                    {'title': 'Начать работу!'}]  # начинаем работу и регистрируем user_id в базе

        else:
            res['response']['text'] += '\nНо для начала Вам необходимо авторизироваться.'
        return

    else:
        user_id = req['session']['user']['user_id']
        if 'role' in req['state']['session']:
            if req['state']['session']['role'] == 'teacher':  # функционал учителя
                res['session_state'] = {'role': 'teacher'}
                if not ((user_id,) in query_db('select user_id from teachers', one=False)):
                    query_db("insert into teachers ('user_id') values (?)", (user_id,))

                if not 'act' in req['state']['session']:  # обработка действий учителя
                    if req['request']['command'].lower() == 'добавить школу':
                        res['session_state']['act'] = 'new_school'
                        res['response']['text'] = 'Скажите мне адрес новой школы'
                        return

                    if req['request']['command'].lower() == 'задать домашнее задание':
                        res['session_state']['act'] = 'new_schoolwork'
                        res['response']['text'] = 'Для какого класса?'
                        return
                    if req['request']['command'].lower() == 'изменить домашнее задание':
                        res['session_state']['act'] = 'edit_schoolwork'
                        res['response']['text'] = 'Для какого класса?'
                        return
                    else:
                        res['response']['text'] = 'Давайте продолжим'
                        res['response']['buttons'] = [{'title': 'Добавить школу'},
                                                      {'title': 'Задать домашнее задание'},
                                                      {'title': 'Изменить домашнее задание'}]

                else:
                    if req['state']['session']['act'] == 'new_school':  # добавить новую школу
                        if req['request']['nlu']['entities']:
                            if "YANDEX.GEO" in [i['type'] for i in req['request']['nlu']['entities']]:
                                iterat = list([i for i in req['request']['nlu']['entities']])
                                n, v = 0, 0
                                for i in range(len(iterat)):
                                    logging.info(iterat[i]['type'])
                                    if iterat[i]['type'] == 'YANDEX.GEO':
                                        n += 1
                                        v = ' '.join([iterat[i]['value']['city'], iterat[i]['value']['street'], iterat[i]['value']['house_number']])
                                if n != 1:
                                    res['response']['text'] = 'Что-то я запуталась. Давайте еще раз!'
                                    return
                                query_db(f'''UPDATE teachers
                                 SET sch_adress='{getcoords(v)}'
                                WHERE user_id="{user_id}"''')
                                res['response']['text'] = 'Вы обновили свою школу!'
                            else:
                                res['response']['text'] = 'Адреса не прозвучало'


                        else:

                            res['response']['text'] = 'Ты все еще учитель, чел)'

                        res['response']['buttons'] = [{'title': 'Добавить школу'},
                                            {'title': 'Задать домашнее задание'},
                                            {'title': 'Изменить домашнее задание'}]

            elif req['state']['session']['role'] == 'pupil':  # функционал ученика
                res['session_state'] = {'role': 'pupil'}
                if not user_id in query_db('select user_id from pupils', one=False):
                    query_db("insert into pupils ('user_id') values (?)", (req['session']['user'][
                                                                               'user_id'],))

                res['response']['text'] = 'Ты все еще ученик, чел)'
        else:

            res['session_state'] = {}

            if ('учитель' in req['request']['nlu']['tokens'] or 'учительница' in
                req['request']['nlu'][
                    'tokens'] or \
                'преподаватель' in req['request']['nlu']['tokens']) and (
                    'студент' in req['request']['nlu']['tokens'] or 'ученик' in
                    req['request']['nlu'][
                        'tokens'] or \
                    'студентка' in req['request']['nlu']['tokens'] or 'ученица' in
                    req['request']['nlu'][
                        'tokens']):
                res['response']['text'] = 'Давайте ближе к делу?'

            elif 'учитель' in req['request']['nlu']['tokens'] or 'учительница' in \
                    req['request']['nlu'][
                        'tokens'] or \
                    'преподаватель' in req['request']['nlu']['tokens']:
                res['session_state']['role'] = 'teacher'
                res['response']['text'] = 'Отлично, теперь Вы преподаватель!'
                res['response']['buttons'] = [{'title': 'Добавить школу'},
                                              {'title': 'Задать домашнее задание'},
                                              {'title': 'Изменить домашнее задание'}]
            elif 'студент' in req['request']['nlu']['tokens'] or 'ученик' in req['request']['nlu'][
                'tokens'] or \
                    'студентка' in req['request']['nlu']['tokens'] or 'ученица' in \
                    req['request']['nlu'][
                        'tokens']:
                res['session_state']['role'] = 'pupil'
                res['response']['text'] = 'Приятной учёбы, студент!'
            else:
                res['response']['text'] = 'Кстати, Вы студент или преподаватель?'
                res['response']['buttons'] = [{'title': 'Преподаватель'}, {'title': 'Студент'}]


if __name__ == '__main__':
    app.run()
