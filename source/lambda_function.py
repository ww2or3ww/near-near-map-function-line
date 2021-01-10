# --- coding: utf-8 ---

import sys
import json
import os
import re
import requests
import boto3
from boto3.dynamodb.conditions import Key
from retry import retry

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.models import (
    PostbackEvent, MessageEvent, TextMessage, TextSendMessage, LocationMessage, LocationSendMessage, 
    TemplateSendMessage,ButtonsTemplate,URIAction
)
from linebot.exceptions import (
    LineBotApiError, InvalidSignatureError
)
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

LINE_CHANNEL_ACCESS_TOKEN       = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
LINE_CHANNEL_SECRET             = os.environ['LINE_CHANNEL_SECRET']
DYNAMODB_NAME                   = os.environ['DYNAMODB_NAME']
API_ADDRESS_NEAR_NEAR_SEARCH    = os.environ['API_ADDRESS_NEAR_NEAR_SEARCH']

LINE_BOT_API = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
LINE_HANDLER = WebhookHandler(LINE_CHANNEL_SECRET)
DYNAMO_TABLE = boto3.resource('dynamodb').Table(DYNAMODB_NAME)

RESULT_OK = {
    'isBase64Encoded': False,
    'statusCode': 200,
    'headers': {},
    'body': ''
}
RESULT_NG = {
    'isBase64Encoded': False,
    'statusCode': 403,
    'headers': {},
    'body': 'Error'
}

NEAR_NEAR_HELP      = ['help', 'へるぷ', 'ヘルプ', '使い方', 'つかいかた', '?']
NEAR_NEAR_START     = ['にゃーにゃー', 'にやーにやー', 'ニャーニャー', 'ニヤーニヤー', 'にやーにやーマップ', 'にゃーにゃーマップ', 'にやーにやーまっぷ', 'にゃーにゃーまっぷ', 'ニャーニャーマップ', 'ニャーニャーまっぷ', 'ニヤーニヤーまっぷ', 'near near', 'near near map']
MSG_HELP            = 'こんにちは！にゃーにゃーマップです♪\n「にゃーにゃー」と呼びかけてにゃ～♪'
MSG_ANNOUNCE_WEB    = 'Web版も試してみてね♪\nhttps://near-near-map.w2or3w.com/'

def lambda_handler(event, context):
    try:
        logger.info('=== START ===')
        signature = event['headers']['X-Line-Signature']
        body = event['body']
        logger.info(body)
        
        @LINE_HANDLER.add(MessageEvent, message=TextMessage)
        def message(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info('message : {0}'.format(line_event.message.text))
            logger.info(line_event)

            user_info = select_user_info(profile.user_id)
            word = line_event.message.text.lower()
            if word in NEAR_NEAR_HELP or not user_info:
                # 呼びかけ(ヘルプ 等) or ユーザー情報が無かった
                # -> ヘルプメッセージ
                put_user_if_not_exist(profile.user_id, profile.display_name, profile.picture_url)
                LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(MSG_HELP + '\n'+ MSG_ANNOUNCE_WEB))
            elif word in NEAR_NEAR_START or 'selected_type' not in user_info:
                # 呼びかけ(にやーにやーマップ 等)
                # -> セレクトメッセージ
                put_user_if_not_exist(profile.user_id, profile.display_name, profile.picture_url)
                LINE_BOT_API.reply_message(line_event.reply_token, make_select_message())
            else:
                # 場所
                # -> 近いもの検索結果(場所)を応答
                selected_type = user_info['selected_type']
                query_param = 'type={0}&count=3&sort=1&address={1}'.format(selected_type, line_event.message.text)
                reply_by_nearnearmap_api(line_event, query_param, selected_type)
                
        @LINE_HANDLER.add(MessageEvent, message=LocationMessage)
        def on_location(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info(line_event)

            user_info = select_user_info(profile.user_id)
            if not user_info or 'selected_type' not in user_info:
                # ユーザー情報が無かった or 選択情報が無かった
                # -> セレクトメッセージ
                put_user_if_not_exist(profile.user_id, profile.display_name, profile.picture_url)
                LINE_BOT_API.reply_message(line_event.reply_token, make_select_message())
            else:
                # 位置情報
                # -> 近いもの検索(緯度経度)結果を応答
                selected_type = user_info['selected_type']
                query_param = 'type={0}&count=3&sort=1&latlon={1},{2}'.format(selected_type, line_event.message.latitude, line_event.message.longitude)
                reply_by_nearnearmap_api(line_event, query_param, selected_type)
                
        @LINE_HANDLER.add(PostbackEvent)
        def on_postback(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info(line_event)

            user_info = select_user_info(profile.user_id)
            if not user_info:
                # ユーザー情報が無かった場合
                # -> セレクトメッセージ
                put_user_if_not_exist(profile.user_id, profile.display_name, profile.picture_url)
                LINE_BOT_API.reply_message(line_event.reply_token, make_select_message())
            else:
                selected_type = line_event.postback.data
                put_user_if_not_exist(profile.user_id, profile.display_name, profile.picture_url)
                if selected_type == 'shopping':
                    LINE_BOT_API.reply_message(line_event.reply_token, make_select_message_shop())
                elif selected_type == 'goout':
                    LINE_BOT_API.reply_message(line_event.reply_token, make_select_message_goout())
                else:
                    update_user_selected_type(profile.user_id, selected_type)
                    type_word = type_id_2_word(selected_type)
                    message = '{0} ですね！\n場所や位置情報を教えてにゃ～♪'.format(type_word)
                    LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(message))


        LINE_HANDLER.handle(body, signature)

    except Exception as e:
        logger.exception(e)
        return RESULT_NG

    return RESULT_OK


def make_text_message(message):
    return TextSendMessage(text=message)


def make_location_message(title, address, lat, lng):
    return LocationSendMessage(title=title, address=address, latitude=lat, longitude=lng)

    
def make_select_message():
    return TemplateSendMessage(
        alt_text='にゃーにゃーマップ',
        template=ButtonsTemplate(
            title='にゃーにゃーマップ',
            text='こんにちは！何をする？',
            actions=[
                {
                    'type': 'postback',
                    'data': 'shopping',
                    'label': 'かいもの'
                },
                {
                    'type': 'postback',
                    'data': 'goout',
                    'label': 'おでかけ'
                }
            ]
        )
    )
    
def make_select_message_shop():
    return TemplateSendMessage(
        alt_text='にゃーにゃーマップ (かいもの)',
        template=ButtonsTemplate(
            title='にゃーにゃーマップ (かいもの)',
            text='何を探す？',
            actions=[
                {
                    'type': 'postback',
                    'data': 'food',
                    'label': 'フード'
                },
                {
                    'type': 'postback',
                    'data': 'drink',
                    'label': 'ドリンク・デザート'
                },
                {
                    'type': 'postback',
                    'data': 'life',
                    'label': 'スーパー・ドラッグストア'
                }
            ]
        )
    )
def make_select_message_goout():
    return TemplateSendMessage(
        alt_text='にゃーにゃーマップ (おでかけ)',
        template=ButtonsTemplate(
            title='にゃーにゃーマップ (おでかけ)',
            text='何を探す？',
            actions=[
                {
                    'type': 'postback',
                    'data': 'outdoor',
                    'label': 'アウトドア'
                },
                {
                    'type': 'postback',
                    'data': 'hotspring',
                    'label': '温泉・銭湯'
                },
                {
                    'type': 'postback',
                    'data': 'temple',
                    'label': '寺社'
                }
            ]
        )
    )

def type_id_2_word(type_id):
    type_word = ''
    if type_id == 'food':
        type_word = 'フード'
    elif type_id == 'drink':
        type_word = 'ドリンク・デザート'
    elif type_id == 'life':
        type_word = 'スーパー・ドラッグストア'
    elif type_id == 'outdoor':
        type_word = 'アウトドア'
    elif type_id == 'hotspring':
        type_word = '温泉・銭湯'
    elif type_id == 'temple':
        type_word = '寺社'
    return type_word

# にゃーにゃーマップAPIで近いもの検索をした結果で応答を返す
def reply_by_nearnearmap_api(line_event, query_param, selected_type):
    type_word = type_id_2_word(selected_type)
    result, speak_output, result_list, crowd = search_from_nearnearmap_api(query_param, type_word)
    speak_output = speak_output + '\n' + MSG_ANNOUNCE_WEB
    if not result:
        LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(speak_output))
    else:
        logger.info(result_list)
        messages = []
        for i in range(len(result_list)):
            messages.append(make_location_message(result_list[i]['title'], result_list[i]['address'], result_list[i]['lat'], result_list[i]['lng']))
        if crowd and len(crowd) > 0:
            messages.append(make_text_message(crowd))
        messages.append(make_text_message(speak_output))
        LINE_BOT_API.reply_message(line_event.reply_token, messages)

# にゃーにゃーマップAPIで近いもの検索をする
def search_from_nearnearmap_api(query_param, type_word):
    url = '{0}?{1}'.format(API_ADDRESS_NEAR_NEAR_SEARCH, query_param)
    logger.info('q={0}'.format(query_param))
    headers = {'x-api-key': 'alr6g3cFle1s8Yw8ReNYBa6FVRk7DNoA4Zf94w7f'}
    response = requests.get(url, headers=headers)
    response_dict = json.loads(response.text)
    results = response_dict['list']
    list = []
    if results and len(results) > 0:
        for data1 in results:
            for data2 in data1['list']:
                data2['lat'] = data1['position']['lat']
                data2['lng'] = data1['position']['lng']
                list.append(data2)

    result = False
    speak_output = ''
    crowd = ''
    result_list = []
    if len(list) == 0:
        speak_output = 'にやーにやーな {0} が見つからなかったにゃー。'.format(type_word)
    else:
        result = True
        speak_output = 'にやーにやーな {0} が {1}こ 見つかったにゃー！'.format(type_word, len(list))
        for i in range(len(list)):
            data = list[i]
            result_list.append({'title': '{0}:{1}'.format(i+1, data['title']), 'lat': data['lat'], 'lng': data['lng'], 'address': data['address'], 'tel': data['tel'], 'distance': data['distance']})
            if 'crowd_lv' in data:
                try:
                    if data['crowd_lv'] == 1:
                        crowd = crowd + '{0} は、すいてるにゃー！\n'.format(result_list[i]['title'])
                    elif data['crowd_lv'] == 2:
                        crowd = crowd + '{0} は、やや混みにゃー！\n'.format(result_list[i]['title'])
                    elif data['crowd_lv'] == 3:
                        crowd = crowd + '{0} は、混んでるにゃー！\n'.format(result_list[i]['title'])
                except Exception as e:
                    logger.exception(e)
        result_list.reverse()
    return result, speak_output, result_list, crowd

def put_user_if_not_exist(user_id, display_name, picture_url):
    if not select_user_info(user_id):
        put_user_info(user_id, display_name, picture_url)

@retry(tries=3, delay=1)
def select_user_info(user_id):
    records = DYNAMO_TABLE.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    if records is None or records['Count'] is 0:
        return None
    return records['Items'][0]

@retry(tries=3, delay=1)
def put_user_info(user_id, display_name, picture_url):
    DYNAMO_TABLE.put_item(
      Item = {
        'user_id': user_id, 
        'display_name': display_name, 
        'picture_url': picture_url
      }
    )

@retry(tries=3, delay=1)
def update_user_selected_type(user_id, selected_type):
    DYNAMO_TABLE.update_item(
        Key={
            'user_id': user_id
        },
        UpdateExpression='set #selected_type = :selected_type',
        ExpressionAttributeNames={
            '#selected_type': 'selected_type'
        },
        ExpressionAttributeValues={
            ':selected_type': selected_type
        }
    )