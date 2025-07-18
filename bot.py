# bot.py (VERSÃO FINAL E CORRIGIDA PARA ONDE O FAQ_DATA.JSON REALMENTE ESTÁ NO DEPLOY)

import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
FAQ_DATA = {}
try:
    # CORREÇÃO CRÍTICA AQUI: O caminho do arquivo agora é diretamente na raiz,
    # pois os logs indicam que ele está sendo encontrado lá.
    FAQ_FILE_PATH = 'faq_data.json' 
    
    if not os.path.exists(FAQ_FILE_PATH):
        print(f"ERRO CRÍTICO: O arquivo FAQ esperado em '{FAQ_FILE_PATH}' não foi encontrado. O bot não terá respostas do FAQ.")
    else:
        with open(FAQ_FILE_PATH, 'r', encoding='utf-8') as f:
            FAQ_DATA = json.load(f)
        print(f"DEBUG: FAQ_DATA carregado com {len(FAQ_DATA)} entradas do arquivo: {FAQ_FILE_PATH}.")
        print(f"DEBUG: Conteúdo de FAQ_DATA (primeiras 500 chars): {str(FAQ_DATA)[:500]}")
        if not FAQ_DATA:
            print("ALERTA: FAQ_DATA carregado mas está vazio. Verifique o conteúdo do JSON.")
except json.JSONDecodeError:
    print(f"ERRO: faq_data.json em '{FAQ_FILE_PATH}' com formato JSON inválido. Verifique o conteúdo do arquivo.")
    
# --- Seus handlers (comandos e mensagens) ---

async def start(update: Update, context):
    """Envia a mensagem de boas-vindas com botões."""
    welcome_entry = FAQ_DATA.get("1")
    if welcome_entry:
        introduction_message = welcome_entry["resposta"]

        keyboard = [
            [InlineKeyboardButton("📍 Onde fica a loja?", callback_data="onde_fica")],
            [InlineKeyboardButton("🕒 Qual nosso horário?", callback_data="horario")],
            [InlineKeyboardButton("🍔 Quero ver o cardápio", callback_data="cardapio")],
            [InlineKeyboardButton("🧠 Tirar uma dúvida com a IA", callback_data="duvida_ia")],
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(introduction_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text('Olá! Eu sou seu bot! Parece que a mensagem de boas-vindas não foi carregada corretamente ou o FAQ_DATA está vazio. Por favor, verifique o arquivo FAQ.')

async def handle_message(update: Update, context):
    """
    Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ.
    Prioriza correspondências exatas e oferece botões para correspondências parciais.
    """
    user_text = update.message.text.lower().strip() # Normaliza o texto do usuário
    response_text = "Desculpe, não consegui encontrar uma resposta exata para sua pergunta no momento. Por favor, tente reformular ou escolha uma das opções abaixo."
    
    potential_matches_exact = [] 
    potential_matches_partial = [] 

    # --- Lógica de busca de correspondência ---
    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas
            continue
        
        entry_keywords = [kw.lower().strip() for kw in entry.get("palavras_chave", [])]
        
        # 1. Procura por correspondência EXATA da mensagem do usuário com uma palavra-chave
        if user_text in entry_keywords:
            potential_matches_exact.append((faq_id, entry))

    if potential_matches_exact:
        if len(potential_matches_exact) == 1:
            faq_id, entry = potential_matches_exact[0]
            response_text = entry["resposta"]
            reply_markup = None
            if faq_id == "54": # ID para "Falar com alguém"
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
            await update.message.reply_text(response_text, reply_markup=reply_markup)
            return 
        else:
            buttons = []
            for faq_id, entry in potential_matches_exact:
                buttons.append([InlineKeyboardButton(entry["pergunta"], callback_data=faq_id)])
            await update.message.reply_text(
                "Encontrei múltiplas respostas para sua pergunta. Qual delas você gostaria de saber?",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return

    # 2. Se não encontrou correspondência EXATA, procura por palavras-chave CONTIDAS na mensagem
    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": 
            continue
        
        entry_keywords = [kw.lower().strip() for kw in entry.get("palavras_chave", [])]
        
        if any(kw in user_text for kw in entry_keywords) or \
           any(word in ' '.join(entry_keywords) for word in user_text.split()):
            
            if not any(btn[0].callback_data == faq_id for btn in potential_matches_partial):
                potential_matches_partial.append([InlineKeyboardButton(entry["pergunta"], callback_data=faq_id)])

    if potential_matches_partial:
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você gostaria de saber?",
            reply_markup=InlineKeyboardMarkup(potential_matches_partial)
        )
    else:
        keyboard_fallback = [
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")]
        ]
        await update.message.reply_text(response_text, reply_markup=InlineKeyboardMarkup(keyboard_fallback))


async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer() 

    callback_data = query.data 
    
    response_text = "Desculpe, não consegui encontrar uma resposta para esta opção."
    reply_markup = None

    mapping = {
        "onde_fica": "5",     
        "horario": "3",       
        "cardapio": "6",      
        "duvida_ia": None,    
        "falar_com_alguem": "54" 
    }

    faq_id_from_button = mapping.get(callback_data)

    if faq_id_from_button:
        entry = FAQ_DATA.get(faq_id_from_button)
        if entry:
            response_text = entry["resposta"]
            if faq_id_from_button == "54": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
        else:
            response_text = f"Erro: FAQ ID '{faq_id_from_button}' não encontrado para a opção '{callback_data}'. Verifique o faq_data.json."
    elif callback_data == "duvida_ia":
        response_text = "Estou pronto para tirar suas dúvidas! Digite sua pergunta agora e tentarei responder com base nas minhas informações. Se precisar de algo que não sei, use a opção 'Falar com alguém'."
    else:
        entry = FAQ_DATA.get(callback_data) 
        if entry:
            response_text = entry["resposta"]
            if callback_data == "54": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
        else:
            response_text = f"Opção de callback '{callback_data}' não reconhecida ou FAQ ID não encontrado. Verifique os dados."

    await context.bot.send_message(chat_id=query.message.chat_id, text=response_text, reply_markup=reply_markup)
    
def main():
    TOKEN = os.environ.get('BOT_TOKEN')
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
    PORT = int(os.environ.get('PORT', '5000'))

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    app = Flask(__name__)

    @app.route(f'/{TOKEN}', methods=['POST'])
    async def webhook_handler():
        json_data = await request.get_json(force=true)
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return 'ok'

    return app

app = main()

# if __name__ == '__main__':
#     from dotenv import load_dotenv
#     load_dotenv()
#     app.run(port=os.environ.get('PORT', 5000))
