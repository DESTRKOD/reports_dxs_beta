import asyncio
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
from aiohttp import web

CONFIG = {
    "TELEGRAM_BOT_TOKEN": os.getenv('TELEGRAM_BOT_TOKEN'),
    "TELEGRAM_ADMIN_CHAT_ID": int(os.getenv('TELEGRAM_ADMIN_CHAT_ID')),
    
    "FIREBASE_CONFIG": {
        "type": "service_account",
        "project_id": os.getenv('FIREBASE_PROJECT_ID'),
        "private_key_id": os.getenv('FIREBASE_PRIVATE_KEY_ID'),
        "private_key": os.getenv('FIREBASE_PRIVATE_KEY').replace('\\n', '\n'),
        "client_email": os.getenv('FIREBASE_CLIENT_EMAIL'),
        "client_id": os.getenv('FIREBASE_CLIENT_ID'),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.getenv('FIREBASE_CLIENT_X509_CERT_URL'),
        "universe_domain": "googleapis.com"
    }
}

class SimpleOrderBot:
    def __init__(self, bot_token, admin_chat_id, firebase_config):
        self.bot_token = bot_token
        self.admin_chat_id = admin_chat_id
        
        try:
            cred = credentials.Certificate(firebase_config)
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            print("✅ Firebase подключен успешно!")
        except Exception as e:
            print(f"❌ Ошибка Firebase: {e}")
            return
        
        self.last_check = datetime.now()
        print("🤖 Бот инициализирован!")
    
    def format_order_info(self, order):
        product = order.get('product', 'N/A')
        price = order.get('price', 'N/A')
        client = order.get('client', 'N/A')
        payment_method = order.get('paymentMethod', 'Не выбран')
        
        if order.get('promocodeUsed') and order.get('finalPrice'):
            price_info = f"<s>{price}</s> {order.get('finalPrice')} (промокод: {order.get('promocodeUsed')})"
        else:
            price_info = price
        
        message = f"""
🆕 <b>НОВЫЙ ЗАКАЗ</b>

📦 <b>Товар:</b> {product}
💰 <b>Сумма:</b> {price_info}
👤 <b>Клиент:</b> {client}
💳 <b>Способ оплаты:</b> {payment_method}

🆔 <b>ID:</b> <code>{order.get('id', 'N/A')}</code>
⏰ <b>Время:</b> {datetime.now().strftime('%H:%M %d.%m.%Y')}
"""
        return message
    
    def send_telegram_message(self, message):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            'chat_id': self.admin_chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"❌ Ошибка Telegram API: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Ошибка отправки в Telegram: {e}")
            return False
    
    async def check_orders(self):
        try:
            orders_ref = self.db.collection('orders')
            query = orders_ref.where('createdAt', '>', self.last_check.isoformat())
            docs = query.stream()
            
            new_orders_count = 0
            for doc in docs:
                order = doc.to_dict()
                message = self.format_order_info(order)
                
                success = self.send_telegram_message(message)
                if success:
                    print(f"✅ Уведомление отправлено для заказа {order.get('id')}")
                    new_orders_count += 1
                else:
                    print(f"❌ Ошибка отправки для заказа {order.get('id')}")
            
            self.last_check = datetime.now()
            
            if new_orders_count > 0:
                print(f"📨 Отправлено уведомлений: {new_orders_count}")
            
        except Exception as e:
            print(f"❌ Ошибка проверки заказов: {e}")
    
    async def run_continuous(self):
        print("🚀 Бот запущен! Ожидаю новые заказы...")
        print("⏰ Проверка каждые 10 секунд...")
        while True:
            await self.check_orders()
            await asyncio.sleep(10)

# HTTP сервер для Web Service
async def health_check(request):
    return web.Response(text='Bot is running!')

async def start_background_tasks(app):
    # Запуск бота в фоне
    asyncio.create_task(app['bot'].run_continuous())

async def create_app():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    # Инициализация бота
    required_env_vars = [
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_ADMIN_CHAT_ID', 
        'FIREBASE_PROJECT_ID',
        'FIREBASE_PRIVATE_KEY_ID',
        'FIREBASE_PRIVATE_KEY',
        'FIREBASE_CLIENT_EMAIL',
        'FIREBASE_CLIENT_ID',
        'FIREBASE_CLIENT_X509_CERT_URL'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Ошибка: Не заполнены переменные окружения: {', '.join(missing_vars)}")
        return app
    
    app['bot'] = SimpleOrderBot(
        bot_token=CONFIG["TELEGRAM_BOT_TOKEN"],
        admin_chat_id=CONFIG["TELEGRAM_ADMIN_CHAT_ID"],
        firebase_config=CONFIG["FIREBASE_CONFIG"]
    )
    
    app.on_startup.append(start_background_tasks)
    return app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    web.run_app(create_app(), port=port)
