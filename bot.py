import os
import asyncio
from telethon import TelegramClient, events, Button
from pyrogram import Client, errors
from sqlitedict import SqliteDict

# --- الإعدادات (ضع بياناتك هنا) ---
API_ID = 26977319  # استبدله بـ API ID الخاص بك
API_HASH = "0adc4f462c2fb2709e5b976884595903"
BOT_TOKEN = "8604655366:AAGfjSRVrod_HZshiLROjUZXwPHCc6l1SFM"
ADMIN_ID = 6447367175  # ايديك لتتمكن من دخول لوحة التحكم

# قاعدة البيانات
db = SqliteDict('./database.db', autocommit=True)
if "accounts" not in db: db["accounts"] = []
if "users" not in db: db["users"] = [ADMIN_ID]

# تشغيل بوت التليثون (الواجهة)
bot = TelegramClient('bot_admin', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# --- القوالب والأزرار ---
START_MSG = "🛡️ **أهلاً بك في بوت إدارة الحسابات المتطور**\n\nاستخدم الأزرار أدناه للتحكم:"
MAIN_BUTTONS = [
    [Button.inline("➕ تسجيل حساب جديد", b"add_acc"), Button.inline("🔄 نقل أعضاء", b"transfer")],
    [Button.inline("🔍 فحص الحسابات", b"check_acc"), Button.inline("📊 الإحصائيات", b"stats")],
    [Button.inline("🚫 إلغاء العملية", b"cancel")]
]

# --- الوظائف المساعدة ---
async def is_admin(event):
    return event.sender_id in db["users"]

# --- معالجة الأوامر ---
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    if not await is_admin(event): return
    await event.respond(START_MSG, buttons=MAIN_BUTTONS)

# --- 1. تسجيل الحسابات (Registration) ---
@bot.on(events.CallbackQuery(data=b"add_acc"))
async def register_account(event):
    async with bot.conversation(event.chat_id) as conv:
        try:
            await conv.send_message("📞 أرسل رقم الهاتف (مثال: +9665xxxxxxxx):")
            phone = (await conv.get_response()).text.strip().replace(" ", "")
            
            client = Client(f"sessions/{phone}", api_id=API_ID, api_hash=API_HASH)
            await client.connect()
            
            sent_code = await client.send_code(phone)
            await conv.send_message(f"📩 أرسل كود التحقق الذي وصلك على {phone}:")
            
            otp = (await conv.get_response()).text.strip()
            
            try:
                await client.sign_in(phone, sent_code.phone_code_hash, otp)
            except errors.SessionPasswordNeeded:
                await conv.send_message("🔐 الحساب محمي بكلمة سر (2FA)، أرسلها الآن:")
                pwd = (await conv.get_response()).text.strip()
                await client.check_password(pwd)
            
            # حفظ في قاعدة البيانات
            accs = db["accounts"]
            accs.append(phone)
            db["accounts"] = accs
            
            await client.disconnect()
            await conv.send_message(f"✅ تم حفظ الحساب {phone} بنجاح!")
            
        except Exception as e:
            await conv.send_message(f"❌ خطأ: {str(e)}")

# --- 2. نقل الأعضاء (Transfer) ---
@bot.on(events.CallbackQuery(data=b"transfer"))
async def transfer_members(event):
    if not db["accounts"]:
        return await event.respond("⚠️ لا يوجد حسابات مسجلة للقيام بالعملية!")
    
    async with bot.conversation(event.chat_id) as conv:
        try:
            await conv.send_message("🔗 أرسل رابط/يوزر القروب المصدر:")
            source = (await conv.get_response()).text
            await conv.send_message("🎯 أرسل رابط/يوزر القروب الهدف:")
            target = (await conv.get_response()).text
            await conv.send_message("⏱️ أرسل الوقت الفاصل بين كل إضافة (بالثواني، ينصح بـ 30):")
            delay = int((await conv.get_response()).text)
            
            await conv.send_message("🚀 بدأت العملية... سأقوم بإخطارك عند الانتهاء.")
            
            # منطق النقل الفعلي
            accounts = db["accounts"]
            for phone in accounts:
                app = Client(f"sessions/{phone}", api_id=API_ID, api_hash=API_HASH)
                await app.start()
                
                try:
                    members = []
                    async for member in app.get_chat_members(source, limit=50):
                        if not member.user.is_bot: members.append(member.user.id)
                    
                    for m_id in members:
                        try:
                            await app.add_chat_members(target, m_id)
                            await asyncio.sleep(delay)
                        except errors.FloodWait as e:
                            break # الانتقال للحساب التالي عند الحظر
                        except Exception:
                            continue
                finally:
                    await app.stop()
            
            await conv.send_message("✅ انتهت عملية النقل بنجاح.")
        except Exception as e:
            await conv.send_message(f"❌ خطأ أثناء النقل: {str(e)}")

# --- 3. فحص الحسابات (Check Sessions) ---
@bot.on(events.CallbackQuery(data=b"check_acc"))
async def check_accounts(event):
    await event.answer("🔍 جاري الفحص...")
    accs = db["accounts"]
    valid = []
    broken = 0
    
    for phone in accs:
        app = Client(f"sessions/{phone}", api_id=API_ID, api_hash=API_HASH)
        try:
            await app.connect()
            me = await app.get_me()
            if me: valid.append(phone)
            await app.disconnect()
        except:
            broken += 1
            if os.path.exists(f"sessions/{phone}.session"):
                os.remove(f"sessions/{phone}.session")
    
    db["accounts"] = valid
    await event.respond(f"📊 **نتائج الفحص:**\n✅ سليمة: {len(valid)}\n❌ تالفة (تم حذفها): {broken}")

# --- 4. الإحصائيات (Stats) ---
@bot.on(events.CallbackQuery(data=b"stats"))
async def stats(event):
    count = len(db["accounts"])
    await event.respond(f"📊 **إحصائيات البوت:**\n\n👥 عدد الحسابات المسجلة: {count}\n👤 عدد المطورين: {len(db['users'])}")

# --- إلغاء العمليات ---
@bot.on(events.CallbackQuery(data=b"cancel"))
async def cancel(event):
    await event.respond("🚫 تم إلغاء العملية والعودة للقائمة الرئيسية.", buttons=MAIN_BUTTONS)

print("⚡ البوت يعمل الآن...")
bot.run_until_disconnected()
