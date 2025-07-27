# main_telegram.py (Güvenlikli Versiyon)

import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Nöbetçi kulesini (web sunucusunu) içe aktar
from keep_alive import keep_alive 

# .env veya Render'ın Environment Variables bölümündeki gizli bilgileri yükle
load_dotenv()

# --- HATA KAYDI (LOGLAMA) KURULUMU ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- YETKİLENDİRME KURULUMU --- # <-- YENİ
# İzin verilen kullanıcı ID'lerini ortam değişkeninden alıyoruz.
# Birden fazla kişiye izin vermek isterseniz ID'leri virgülle ayırın (örn: "12345,67890")
try:
    AUTHORIZED_USER_IDS = [int(user_id) for user_id in os.getenv("AUTHORIZED_USER_IDS", "").split(',') if user_id]
    if not AUTHORIZED_USER_IDS:
        logger.warning("UYARI: AUTHORIZED_USER_IDS tanımlanmamış. Bot herkese açık modda çalışacak.")
except (ValueError, TypeError):
    logger.error("HATA: AUTHORIZED_USER_IDS ortam değişkeni hatalı formatta. Lütfen sayısal ID'leri virgülle ayırarak girin.")
    exit()

# --- IN-MEMORY HAFIZA SİSTEMİ ---
conversation_histories = {}

# --- GEMINI API KURULUMU ---
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Gemini modeli başarıyla yüklendi.")
except Exception as e:
    logger.error(f"Gemini API yapılandırılamadı! Detay: {e}")
    exit()


# --- YETKİLENDİRME KONTROL DEKORATÖRÜ --- # <-- YENİ
# Komutlara ve mesajlara yetki kontrolü eklemek için bir "dekoratör" oluşturuyoruz.
# Bu, kod tekrarını önler ve yönetimi kolaylaştırır.
from functools import wraps

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        # Eğer kullanıcı ID'si izinli listesinde değilse...
        if user_id not in AUTHORIZED_USER_IDS:
            logger.warning(f"Yetkisiz erişim denemesi: Kullanıcı ID {user_id}")
            # İsteği sessizce görmezden gel. İsterseniz aşağıdaki satırı açarak kullanıcıya mesaj gönderebilirsiniz.
            # await update.message.reply_text("Bu botu kullanma yetkiniz bulunmamaktadır.")
            return  # Fonksiyonu burada sonlandır, Gemini'ye istek gitmesin.
        # Kullanıcı yetkiliyse, asıl fonksiyonu çalıştır.
        return await func(update, context, *args, **kwargs)
    return wrapped


# --- TELEGRAM BOT KOMUTLARI ---

@restricted # <-- YENİ: Yetki kontrolü eklendi
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_name = update.effective_user.first_name
    await update.message.reply_html(
        f"Merhaba {user_name}!\n\nBen Gemini tarafından desteklenen bir yapay zeka asistanıyım. "
        f"Benimle sohbet etmeye başlayabilirsin.\n\n"
        f"Geçmiş sohbetimizi unutmamı istersen <b>/yenisohbet</b> komutunu kullanabilirsin."
    )

@restricted # <-- YENİ: Yetki kontrolü eklendi
async def yeni_sohbet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in conversation_histories:
        del conversation_histories[user_id]
        logger.info(f"Yetkili kullanıcı {user_id} ({update.effective_user.username}) sohbet geçmişini sıfırladı.")
        await update.message.reply_text("Anlaşıldı. Önceki sohbetimizi unuttum. Yeni bir başlangıç yapabiliriz.")
    else:
        await update.message.reply_text("Zaten aramızda kayıtlı bir sohbet geçmişi bulunmuyor.")

@restricted # <-- YENİ: Yetki kontrolü eklendi
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_message = update.message.text

    if not user_message:
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    try:
        if user_id not in conversation_histories:
            conversation_histories[user_id] = []
        
        history = conversation_histories[user_id]
        chat = model.start_chat(history=history)
        response = await chat.send_message_async(user_message)
        conversation_histories[user_id] = chat.history

        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Mesaj işlenirken bir API/hafıza hatası oluştu: {e}", exc_info=True)
        await update.message.reply_text(
            "Üzgünüm, bir sorunla karşılaştım. Lütfen daha sonra tekrar deneyin veya "
            "sorun devam ederse /yenisohbet komutu ile hafızayı temizleyin."
        )

# --- BOTU BAŞLATMA ---
def main() -> None:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        logger.error("HATA: Bot token'ı 'TELEGRAM_TOKEN' adıyla bulunamadı!")
        return
    
    if not AUTHORIZED_USER_IDS: # <-- YENİ: Başlangıçta ID kontrolü
        logger.error("KRİTİK HATA: AUTHORIZED_USER_IDS tanımlı değil! Güvenlik nedeniyle bot başlatılmıyor.")
        return

    keep_alive()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("yenisohbet", yeni_sohbet))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info(f"Bot başlatılıyor... Yalnızca şu ID'lere hizmet verilecek: {AUTHORIZED_USER_IDS}")
    application.run_polling()


if __name__ == "__main__":
    main()
