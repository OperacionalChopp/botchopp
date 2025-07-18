# bot.py (VERSÃO FINAL COM CORREÇÕES DE CAMINHO, LÓGICA DE BUSCA E RESPOSTAS DE BOTÕES)

import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# --- Carregar dados do FAQ ---
FAQ_DATA = {}
try:
    # CORREÇÃO CRÍTICA AQUI: Caminho do arquivo FAQ_DATA na subpasta
    with open('base_conhecimento/faq_data.json', 'r', encoding='utf-8') as f:
        FAQ_DATA = json.load(f)
    print(f"DEBUG: FAQ_DATA carregado com {len(FAQ_DATA)} entradas.")
    print(f"DEBUG: Conteúdo de FAQ_DATA (primeiras 500 chars): {str(FAQ_DATA)[:500]}")
    if not FAQ_DATA:
        print("ALERTA: FAQ_DATA carregado mas está vazio. Verifique o conteúdo do JSON.")
except FileNotFoundError:
    print("ERRO: faq_data.json não encontrado. Certifique-se de que o arquivo 'base_conhecimento/faq_data.json' existe.")
    # Adicionar um fallback ou tratamento de erro adequado, talvez uma FAQ default
except json.JSONDecodeError:
    print("ERRO: faq_data.json com formato JSON inválido. Verifique o conteúdo e a sintaxe do arquivo JSON.")
    # Adicionar um fallback ou tratamento de erro adequado

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
    reply_markup = None
    
    # Lista para coletar FAQs que contêm as palavras-chave do usuário
    potential_matches = [] 

    # --- Lógica de busca de correspondência ---
    # 1. Procura por correspondência EXATA da mensagem do usuário com uma palavra-chave
    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": # Pula a FAQ de boas-vindas
            continue
        
        entry_keywords = [kw.lower() for kw in entry.get("palavras_chave", [])]
        
        if user_text in entry_keywords: # Se a mensagem do usuário é uma palavra-chave EXATA
            response_text = entry["resposta"]
            if faq_id == "54": # ID para "Falar com alguém"
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
            await update.message.reply_text(response_text, reply_markup=reply_markup)
            return # Encontrou uma correspondência exata, termina a função aqui

    # 2. Se não encontrou correspondência exata, procura por palavras-chave CONTIDAS na mensagem
    for faq_id, entry in FAQ_DATA.items():
        if faq_id == "1": 
            continue
        
        entry_keywords = [kw.lower() for kw in entry.get("palavras_chave", [])]
        
        # Verifica se alguma palavra-chave da FAQ está contida na mensagem do usuário
        # ou se alguma palavra da mensagem do usuário está na palavra-chave da FAQ
        # Isso aumenta a flexibilidade da busca
        if any(kw in user_text for kw in entry_keywords) or \
           any(word in ' '.join(entry_keywords) for word in user_text.split()):
            
            # Adiciona a pergunta da FAQ como um botão de opção
            # Garante que não adicione duplicatas
            if not any(btn[0].callback_data == faq_id for btn in potential_matches):
                potential_matches.append([InlineKeyboardButton(entry["pergunta"], callback_data=faq_id)])

    if potential_matches:
        # Se encontrou termos relacionados, oferece botões de perguntas para o usuário escolher
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você gostaria de saber?",
            reply_markup=InlineKeyboardMarkup(potential_matches)
        )
    else:
        # Se não encontrou nada específico nem relacionado
        # Aqui você pode adicionar um fallback para a opção "Falar com alguém" se desejar
        keyboard_fallback = [
            [InlineKeyboardButton("📞 Falar com alguém", callback_data="falar_com_alguem")]
        ]
        await update.message.reply_text(response_text, reply_markup=InlineKeyboardMarkup(keyboard_fallback))


async def handle_callback_query(update: Update, context):
    query = update.callback_query
    await query.answer() # Importante para remover o estado de carregamento do botão

    callback_data = query.data 
    
    response_text = "Desculpe, não consegui encontrar uma resposta para esta opção."
    reply_markup = None

    # Mapeamento dos callback_data dos botões iniciais para os IDs de FAQ correspondentes
    mapping = {
        "onde_fica": "5",     # "Como encontrar a loja Chopp Brahma Express mais próxima?"
        "horario": "3",       # "Qual é o horário de atendimento de vocês?"
        "cardapio": "6",      # "Quais produtos estão disponíveis e como selecionar?"
        "duvida_ia": None,    # Esta é uma ação, não uma FAQ direta. A resposta é dada abaixo.
        "falar_com_alguem": "54" # "Não encontrei minha dúvida. Como posso ser atendido?"
    }

    faq_id_from_button = mapping.get(callback_data)

    if faq_id_from_button:
        entry = FAQ_DATA.get(faq_id_from_button)
        if entry:
            response_text = entry["resposta"]
            # Condição especial para o botão "Falar com Alguém" (ID 54)
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
        # Caso o callback_data seja diretamente um ID de FAQ (dos botões dinâmicos de handle_message)
        entry = FAQ_DATA.get(callback_data) 
        if entry:
            response_text = entry["resposta"]
            # Condição especial para a FAQ de "Falar com Alguém" se for acionada dinamicamente
            if callback_data == "54": 
                reply_markup = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📞 Ligar para a Loja", url="tel:+556139717502")],
                    [InlineKeyboardButton("💬 Abrir Chat", url="https://wa.me/556139717502")]
                ])
        else:
            response_text = f"Opção de callback '{callback_data}' não reconhecida ou FAQ ID não encontrado. Verifique os dados."

    # ENVIAR NOVA MENSAGEM AO INVÉS DE EDITAR A ANTERIOR
    await context.bot.send_message(chat_id=query.message.chat_id, text=response_text, reply_markup=reply_markup)
    
    # Opcional: Se quiser que a mensagem original com os botões seja deletada, descomente a linha abaixo:
    # await query.message.delete()

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

# As linhas abaixo são para execução local e devem permanecer comentadas para o Render.
# if __name__ == '__main__':
#     from dotenv import load_dotenv
#     load_dotenv()
#     app.run(port=os.environ.get('PORT', 5000))
