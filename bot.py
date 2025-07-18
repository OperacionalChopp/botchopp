# bot.py (VERSÃO CORRIGIDA PARA O FORMATO LISTA DO FAQ_DATA.JSON E COM DEBUG PRINTS)

import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
FAQ_DATA = {}
FAQ_FILE_PATH = 'faq_data.json' 
try:
    if not os.path.exists(FAQ_FILE_PATH):
        print(f"ERRO CRÍTICO: O arquivo FAQ esperado em '{FAQ_FILE_PATH}' não foi encontrado. O bot não terá respostas do FAQ.")
    else:
        with open(FAQ_FILE_PATH, 'r', encoding='utf-8') as f:
            raw_faq_list = json.load(f)
            # Converter a lista de FAQs para um dicionário onde a chave é o ID da FAQ
            FAQ_DATA = {str(item['id']): item for item in raw_faq_list}

        print(f"DEBUG: FAQ_DATA carregado com {len(FAQ_DATA)} entradas do arquivo: {FAQ_FILE_PATH}.")
        print(f"DEBUG: Conteúdo de FAQ_DATA (primeiras 500 chars): {str(FAQ_DATA)[:500]}")
        if not FAQ_DATA:
            print("ALERTA: FAQ_DATA carregado mas está vazio. Verifique o conteúdo do JSON ou o formato dos IDs.")
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
    """Processa mensagens de texto (não comandos) e tenta encontrar respostas no FAQ."""
    user_text = update.message.text.lower().strip()
    print(f"DEBUG: Mensagem do usuário recebida: '{user_text}'") # DEBUG PRINT
    
    # Inicializa a melhor correspondência encontrada
    best_match_faq_id = None
    max_matches = 0
    
    # Se a mensagem for "olá" ou "oi" (simples), pode direcionar para o start
    if user_text in ["olá", "ola", "oi", "e aí", "e ai", "opa", "fala"]:
        print(f"DEBUG: Saudação detectada ('{user_text}'), chamando /start.") # DEBUG PRINT
        await start(update, context) # Chama o handler do /start para exibir a mensagem de boas-vindas com botões
        return

    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas, já tratada acima
            continue
        
        entry_keywords = [kw.lower().strip() for kw in entry.get("palavras_chave", [])]
        
        # Conta quantas palavras-chave do FAQ estão presentes no texto do usuário
        current_matches = 0
        for kw in entry_keywords:
            if kw in user_text:
                current_matches += 1 # Pontuação básica por palavra-chave presente
                # Se a palavra-chave for uma frase exata na mensagem do usuário, dê pontuação extra
                if kw == user_text: # Correspondência exata da frase
                    current_matches += 5 
                elif len(kw.split()) > 1 and kw in user_text: # Correspondência de frase parcial
                    current_matches += 2
        
        print(f"DEBUG: FAQ '{entry.get('pergunta', faq_id)}' (ID: {faq_id}) - Palavras-chave: {entry_keywords}, Correspondências: {current_matches}") # DEBUG PRINT
        
        if current_matches > max_matches:
            max_matches = current_matches
            best_match_faq_id = faq_id

    response_text = "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Por favor, tente reformular ou use os botões abaixo para explorar as opções."
    reply_markup = None

    if best_match_faq_id and max_matches > 0: # Garante que há uma correspondência real
        print(f"DEBUG: Melhor FAQ encontrada: ID '{best_match_faq_id}' com {max_matches} correspondências.") # DEBUG PRINT
        # Se encontrou uma boa correspondência, usa a resposta do FAQ
        matched_entry = FAQ_DATA[best_match_faq_id]
        response_text = matched_entry["resposta"]
        
        # Se a resposta for o FAQ de "Falar com alguém" (ID 54 no seu faq_data.json)
        if best_match_faq_id == "54": 
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
            ])
    else:
        print("DEBUG: Nenhuma FAQ relevante encontrada para a mensagem do usuário.") # DEBUG PRINT
        # Se não encontrou nenhuma boa correspondência, sugere falar com alguém
        # ou outras opções
        response_text = "Desculpe, não consegui encontrar uma resposta para sua pergunta no momento. Você pode tentar reformular, usar o comando /start para ver as opções principais, ou:"
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")],
        ])

    await update.message.reply_text(response_text, reply_markup=reply_markup)


async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer() # Importante para remover o estado de carregamento do botão

    callback_data = query.data 
    print(f"DEBUG: Callback query recebido: '{callback_data}'") # DEBUG PRINT
    
    response_text = "Desculpe, não consegui encontrar uma resposta para esta opção."
    reply_markup = None

    # Mapeamento dos callback_data dos botões iniciais para os IDs de FAQ correspondentes
    mapping = {
        "onde_fica": "5",     # "Como encontrar a loja Chopp Brahma Express mais próxima?"
        "horario": "3",       # "Qual é o horário de atendimento de vocês?"
        "cardapio": "6",      # "Quais produtos estão disponíveis e como selecionar?"
        "duvida_ia": None,    # Esta é uma ação, a resposta é tratada abaixo
        "falar_com_alguem": "54" # "Não encontrei minha dúvida. Como posso ser atendido?"
    }

    faq_id_from_button = mapping.get(callback_data)

    if faq_id_from_button:
        entry = FAQ_DATA.get(faq_id_from_button)
        if entry:
            response_text = entry["resposta"]
            print(f"DEBUG: Respondendo callback '{callback_data}' com FAQ ID '{faq_id_from_button}'.") # DEBUG PRINT
            # Condição especial para o botão "Falar com Alguém" (ID 54)
            if faq_id_from_button == "54": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
        else:
            response_text = f"Erro: FAQ ID '{faq_id_from_button}' não encontrado para a opção '{callback_data}'. Verifique o faq_data.json."
            print(f"ERRO: FAQ ID '{faq_id_from_button}' não encontrado no FAQ_DATA para callback '{callback_data}'.") # DEBUG PRINT
    elif callback_data == "duvida_ia":
        response_text = "Estou pronto para tirar suas dúvidas! Digite sua pergunta agora e tentarei responder com base nas minhas informações. Se precisar de algo que não sei, use a opção 'Falar com alguém'."
        print("DEBUG: Callback 'duvida_ia' acionado.") # DEBUG PRINT
    else:
        # Caso o callback_data seja diretamente um ID de FAQ (dos botões dinâmicos de handle_message)
        entry = FAQ_DATA.get(callback_data)
        if entry:
            response_text = entry["resposta"]
            print(f"DEBUG: Respondendo callback dinâmico '{callback_data}' com FAQ ID '{callback_data}'.") # DEBUG PRINT
            # Condição especial para a FAQ de "Falar com Alguém" se for acionada dinamicamente
            if callback_data == "54": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
        else:
            response_text = f"Opção de callback '{callback_data}' não reconhecida ou FAQ ID não encontrado. Verifique os dados."
            print(f"ERRO: Opção de callback '{callback_data}' não reconhecida ou FAQ ID não encontrado.") # DEBUG PRINT

    # ENVIAR NOVA MENSAGEM AO INVÉS DE EDITAR A ANTERIOR (melhor UX para respostas de botões)
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
        json_data = await request.get_json(force=True)
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return 'ok'

    return app

# --- LINHA NECESSÁRIA PARA O DEPLOY NO RENDER ---
app = main()
