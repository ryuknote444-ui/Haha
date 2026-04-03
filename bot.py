import os
import requests
import telebot
from telebot import types
import time
import io
import json
import logging
import base64

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot("8644154405:AAF6YqABnce9xMKb3jhkeA4KIQcbOjeYz08")

API_BASE_URL = "https://tobi-face-swap-api.vercel.app"  

user_data = {}

WAITING_FOR_SOURCE = 1
WAITING_FOR_TARGET = 2

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
👋 **Hi! I'm a Face Swap Bot**

Send me your photo (the face to use), then send the target photo (the face to replace).

**Developer:** Paras (Aotpy)
**Contact:** @Aotpy
**Channel:** @obitostuffs
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['cancel'])
def cancel_operation(message):
    chat_id = message.chat.id
    if chat_id in user_data:
        del user_data[chat_id]
        bot.reply_to(message, "✅ Operation cancelled. Send /start to begin again.")
    else:
        bot.reply_to(message, "No active operation to cancel.")

@bot.message_handler(commands=['test'])
def test_api(message):
    chat_id = message.chat.id
    status_msg = bot.reply_to(message, "🔍 Testing API connection...")
    
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)
        
        if response.status_code == 200:
            bot.edit_message_text(
                "✅ API is reachable and healthy!\n\n"
                f"Response: {response.json()}",
                chat_id,
                status_msg.message_id
            )
        else:
            bot.edit_message_text(
                f"⚠️ API returned status {response.status_code}",
                chat_id,
                status_msg.message_id
            )
    except Exception as e:
        bot.edit_message_text(
            f"❌ Cannot connect to API: {str(e)}\n\nAPI URL: {API_BASE_URL}",
            chat_id,
            status_msg.message_id
        )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        chat_id = message.chat.id
        
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
        
        logger.info(f"Downloading image from: {file_url}")
        img_data = requests.get(file_url).content
        logger.info(f"Image size: {len(img_data)} bytes")
        
        if chat_id not in user_data:
            user_data[chat_id] = {
                'state': WAITING_FOR_TARGET,
                'source': img_data
            }
            bot.reply_to(message, "👍 Got your face! Now send me the target photo (the face you want to replace).")
        else:
            if user_data[chat_id]['state'] == WAITING_FOR_TARGET:
                user_data[chat_id]['target'] = img_data
                user_data[chat_id]['state'] = None
                
                status_msg = bot.reply_to(message, "🔄 Processing face swap... Please wait (10-15 seconds).")
                
                try:
                    result = perform_face_swap_improved(
                        user_data[chat_id]['source'],
                        user_data[chat_id]['target']
                    )
                    
                    if result and result.get('success'):
                        bot.delete_message(chat_id, status_msg.message_id)
                        bot.send_photo(
                            chat_id,
                            io.BytesIO(result['image_data']),
                            caption="✅ Face swap completed!\n\nMade with ❤️ by @Aotpy"
                        )
                    else:
                        error_msg = result.get('error', 'Unknown error') if result else 'API returned no response'
                        logger.error(f"Face swap failed: {error_msg}")
                        bot.edit_message_text(
                            f"❌ Face swap failed: {error_msg}\n\nPlease try:\n- Clearer face photos\n- Different angles\n- Better lighting\n- Make sure faces are clearly visible",
                            chat_id,
                            status_msg.message_id
                        )
                    
                    del user_data[chat_id]
                    
                except Exception as e:
                    logger.error(f"Exception in face swap: {e}")
                    bot.edit_message_text(
                        f"❌ Error: {str(e)}",
                        chat_id,
                        status_msg.message_id
                    )
                    del user_data[chat_id]
            else:
                bot.reply_to(message, "⚠️ Please send the target photo (the face you want to replace).")
    
    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")
        bot.reply_to(message, f"❌ An error occurred: {str(e)}")
        if chat_id in user_data:
            del user_data[chat_id]

def perform_face_swap_improved(source_bytes, target_bytes):

    logger.info("Trying /swap endpoint...")
    try:
        files = {
            'source': ('source.jpg', source_bytes, 'image/jpeg'),
            'target': ('target.jpg', target_bytes, 'image/jpeg')
        }
        
        response = requests.post(
            f"{API_BASE_URL}/swap",
            files=files,
            timeout=30
        )
        
        logger.info(f"/swap response status: {response.status_code}")
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                logger.info("Success! Got image response")
                return {
                    'success': True,
                    'image_data': response.content
                }
        
        logger.info("Trying /swap/base64 endpoint...")
        return try_base64_endpoint(source_bytes, target_bytes)
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Request timeout - API took too long to respond'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': f'Cannot connect to API at {API_BASE_URL}'}
    except Exception as e:
        logger.error(f"Error in /swap: {e}")
        return try_base64_endpoint(source_bytes, target_bytes)

def try_base64_endpoint(source_bytes, target_bytes):
    try:
        source_base64 = base64.b64encode(source_bytes).decode('utf-8')
        target_base64 = base64.b64encode(target_bytes).decode('utf-8')
        
        payload = {
            'source_base64': source_base64,
            'target_base64': target_base64
        }
        
        logger.info(f"Sending base64 payload to {API_BASE_URL}/swap/base64")
        response = requests.post(
            f"{API_BASE_URL}/swap/base64",
            json=payload,
            timeout=30
        )
        
        logger.info(f"/swap/base64 response status: {response.status_code}")
        logger.info(f"Response content: {response.text[:200]}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success') and result.get('result_base64'):
                image_data = base64.b64decode(result['result_base64'])
                return {
                    'success': True,
                    'image_data': image_data
                }
            else:
                return {'success': False, 'error': result.get('error', 'Base64 endpoint returned no result')}
        else:
            return {'success': False, 'error': f'API returned status {response.status_code}: {response.text[:100]}'}
                
    except Exception as e:
        logger.error(f"Base64 endpoint error: {e}")
        return {'success': False, 'error': f'Base64 endpoint error: {str(e)}'}

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    
    if message.document.mime_type and message.document.mime_type.startswith('image/'):
        try:
            file_info = bot.get_file(message.document.file_id)
            file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
            img_data = requests.get(file_url).content
            
            if chat_id not in user_data:
                user_data[chat_id] = {
                    'state': WAITING_FOR_TARGET,
                    'source': img_data
                }
                bot.reply_to(message, "👍 Got your face! Now send me the target photo (the face you want to replace).")
            else:
                if user_data[chat_id]['state'] == WAITING_FOR_TARGET:
                    user_data[chat_id]['target'] = img_data
                    user_data[chat_id]['state'] = None
                    
                    status_msg = bot.reply_to(message, "🔄 Processing face swap... Please wait.")
                    
                    result = perform_face_swap_improved(
                        user_data[chat_id]['source'],
                        user_data[chat_id]['target']
                    )
                    
                    if result and result.get('success'):
                        bot.delete_message(chat_id, status_msg.message_id)
                        bot.send_photo(
                            chat_id,
                            io.BytesIO(result['image_data']),
                            caption="✅ Face swap completed!\n\nMade with ❤️ by @Aotpy"
                        )
                    else:
                        error_msg = result.get('error', 'Unknown error') if result else 'API returned no response'
                        bot.edit_message_text(
                            f"❌ Face swap failed: {error_msg}",
                            chat_id,
                            status_msg.message_id
                        )
                    
                    del user_data[chat_id]
        except Exception as e:
            logger.error(f"Error in handle_document: {e}")
            bot.reply_to(message, f"❌ Error: {str(e)}")
            if chat_id in user_data:
                del user_data[chat_id]
    else:
        bot.reply_to(message, "⚠️ Please send an image file.")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    if chat_id in user_data:
        bot.reply_to(message, "⚠️ Please send the target photo (the face you want to replace).")
    else:
        bot.reply_to(message, "📸 Please send your photo first (the face to use).\n\nSend /help for instructions or /test to check API status.")

print("🤖 Face Swap Bot is running...")

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)