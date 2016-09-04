import binascii
import multiprocessing
import requests
import json
import os
import base64
import time
import sys

from Crypto.Cipher import AES
from queue import Queue
from threading import Thread

from pymongo import MongoClient

modulus = '00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7'
nonce = '0CoJUm6Qyw8W8jud'
pubKey = '010001'

playlist_url = 'http://music.163.com/api/playlist/detail?id=%s'
song_url = 'http://music.163.com/api/song/detail/?ids=%s'
comment_url = 'http://music.163.com/weapi/v1/resource/comments/%s'

headers = {
    'Cookie': 'appver=1.5.0.75771;',
    'Referer': 'http://music.163.com/'
}

text = {
    'username': os.environ['USERNAME'],
    'password': os.environ['PASSWORD'],
    'rememberLogin': 'true'
}


def aesEncrypt(text, secKey):
    pad = 16 - len(text) % 16
    text = text + chr(pad) * pad
    encryptor = AES.new(secKey, 2, '0102030405060708')
    ciphertext = encryptor.encrypt(text)
    ciphertext = base64.b64encode(ciphertext).decode('u8')
    return ciphertext


def rsaEncrypt(text, pubKey, modulus):
    text = text[::-1]
    rs = pow(int(binascii.hexlify(text), 16), int(pubKey, 16), int(modulus, 16))
    return format(rs, 'x').zfill(256)


def createSecretKey(size):
    return binascii.hexlify(os.urandom(size))[:16]


def login():
    global text, data
    text = json.dumps(text)
    secKey = createSecretKey(16)
    encText = aesEncrypt(aesEncrypt(text, nonce), secKey)
    encSecKey = rsaEncrypt(secKey, pubKey, modulus)
    data = {
        'params': encText,
        'encSecKey': encSecKey
    }


def create_music(q):
    while True:
        playlist = db['playlist'].find_one({'_id': 'playlist'})['id']
        req_json = requests.get(playlist_url % str(playlist)).json()
        if req_json['code'] == 200:
            for song in req_json['result']['tracks']:
                if song['commentThreadId'] is not None:
                    queue.put(song)
        db['playlist'].update({'_id': 'playlist'}, {'id': playlist + 1})


def get_comment(q, ):
    while True:
        time.sleep(1)
        music_dict = q.get()
        ids_comments = requests.post(comment_url % str(music_dict['commentThreadId']),
                                     headers=headers,
                                     data=data).json()
        if ids_comments['code'] != 200:
            return
        music_dict['comments'] = ids_comments['hotComments']
        music_dict['comment_total'] = ids_comments['total']
        music_dict['_id'] = music_dict['id']
        songs = db['songs']
        songs.save(music_dict)
        print(music_dict)


if __name__ == '__main__':
    print('{:=^64}'.format('模块%s' % sys.argv[0]))
    print('{:=^64}'.format('初始化'))
    print('USERNAME: %s' % os.environ['USERNAME'])
    print('PASSWORD: %s' % os.environ['PASSWORD'])
    print('MONGODB: %s' % os.environ['MONGODB_CONNECTION'])

    print('{:=^64}'.format('Connect to MongoDB'))
    client = MongoClient('mongodb://%s?authMechanism=MONGODB-CR' % os.environ['MONGODB_CONNECTION'])
    db = client['163music']
    playlist_id = db['playlist'].find_one({'_id': 'playlist'})

    print('{:=^64}'.format('歌单进度%s' % playlist_id))
    if playlist_id is None:
        db['playlist'].insert({'_id': 'playlist', 'playlist': 100001})
    print('{:=^64}'.format('Connected MongoDB'))

    queue = Queue(maxsize=100)
    login()
    c = Thread(name='歌曲信息', target=create_music, args=(queue,))
    c.start()
    print('{:=^64}'.format('爬取启动'))
    for i in range(1 + multiprocessing.cpu_count()):
        g = Thread(name='评论 %s' % i, target=get_comment, args=(queue,))
        g.start()
        print('{:=^64}'.format('抓取 %s 启动' % i))
    c.join()
