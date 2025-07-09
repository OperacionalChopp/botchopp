import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from base_conhecimento.faq_data import faq_data

# ✅ Substitua pelo seu token real!
TOKEN = "7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw"

# A URL base do seu serviço no Render
WEBHOOK_URL = "https://botchopp.onrender.com/api/telegram/webhook"

# Cria a aplicação do Telegram
application = (
    ApplicationBuilder( )
    .token(TOKEN)
    .build()
)

# Handler de mensagens
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.lower()
    
    # Lista para armazenar as FAQs que correspondem, com uma pontuação
    scored_faqs = []
    
    # Tokeniza o texto do usuário para correspondência de palavras inteiras
    # Usamos set para eficiência e para lidar com palavras únicas
    palavras_do_usuario = set(texto_usuario.split()) 

    for item in faq_data:
        score = 0
        # Tokeniza as palavras-chave da FAQ
        # Garante que estamos comparando palavras inteiras, não substrings
        palavras_chave_item = set(item["palavras_chave"])

        # Calcula a interseção entre as palavras do usuário e as palavras-chave da FAQ
        intersecao = palavras_do_usuario.intersection(palavras_chave_item)
        
        # A pontuação é o número de palavras-chave que correspondem
        score = len(intersecao)

        # Se houver alguma correspondência, adiciona à lista com a pontuação
        if score > 0:
            scored_faqs.append({"faq": item, "score": score})

    # Ordena as FAQs encontradas pela pontuação (do maior para o menor)
    scored_faqs.sort(key=lambda x: x["score"], reverse=True)

    # Filtra as FAQs com a pontuação máxima para lidar com desambiguação
    if scored_faqs:
        max_score = scored_faqs[0]["score"]
        # Pega todas as FAQs que têm a pontuação máxima
        top_matched_faqs = [s["faq"] for s in scored_faqs if s["score"] == max_score]
    else:
        top_matched_faqs = [] # Nenhuma FAQ encontrada

    # Lógica de resposta
    if not top_matched_faqs:
        # Nenhuma FAQ encontrada
        await update.message.reply_text(
            "Desculpe, não entendi. 🤔\n"
            "Você pode perguntar sobre horário, formas de pagamento, região de atendimento, etc."
        )
    elif len(top_matched_faqs) == 1:
        # Apenas uma FAQ com a maior pontuação, responde diretamente
        await update.message.reply_text(top_matched_faqs[0]["resposta"])
    else:
        # Múltiplas FAQs com a mesma maior pontuação, oferece opções com botões
        keyboard = []
        for faq in top_matched_faqs:
            # Usa o ID da FAQ como callback_data para evitar o limite de 64 bytes
            keyboard.append([InlineKeyboardButton(faq["pergunta"], callback_data=f"faq_id_{faq['id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você procura?",
            reply_markup=reply_markup
        )

# Novo handler para cliques em botões inline
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
