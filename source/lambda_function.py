# --- coding: utf-8 ---
# near-near-map-function-line

import sys
import json
import os
import re
import requests
import datetime
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

LINE_BOT_API = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
LINE_HANDLER = WebhookHandler(LINE_CHANNEL_SECRET)

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

MSG_HELP            = 'こんにちは！\nにゃーにゃーマップはサービスを停止しました。'

def lambda_handler(event, context):
    try:
        logger.info('=== START ===')
        logger.info(json.dumps(event, ensure_ascii=False, indent=2))
        signature = event['headers']['x-line-signature']
        body = event['body']
        logger.info(body)
        
        @LINE_HANDLER.add(MessageEvent, message=TextMessage)
        def message(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info('message : {0}'.format(line_event.message.text))
            logger.info(line_event)
            # 呼びかけ(ヘルプ 等) or ユーザー情報が無かった
            # -> ヘルプメッセージ
            LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(MSG_HELP))
                
        @LINE_HANDLER.add(MessageEvent, message=LocationMessage)
        def on_location(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info(line_event)
            # 呼びかけ(ヘルプ 等) or ユーザー情報が無かった
            # -> ヘルプメッセージ
            LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(MSG_HELP))
                
        @LINE_HANDLER.add(PostbackEvent)
        def on_postback(line_event):
            profile = LINE_BOT_API.get_profile(line_event.source.user_id)
            logger.info('profile : {0}, {1}, {2}'.format(profile.user_id, profile.display_name, profile.picture_url))
            logger.info(line_event)
            # 呼びかけ(ヘルプ 等) or ユーザー情報が無かった
            # -> ヘルプメッセージ
            LINE_BOT_API.reply_message(line_event.reply_token, make_text_message(MSG_HELP))

        LINE_HANDLER.handle(body, signature)

    except Exception as e:
        logger.exception(e)
        return RESULT_NG

    return RESULT_OK


def make_text_message(message):
    return TextSendMessage(text=message)
