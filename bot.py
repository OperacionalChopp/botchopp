import os
import asyncio


from http import HTTPStatus
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    CommandHandler  # Certifique-se de que CommandHandler também está aqui
 )
from base_conhecimento.faq_data import faq_data

# --- Configuração ---
# Pega o token do ambiente do Render. Certifique-se de que a variável TELEGRAM_TOKEN está configurada lá.
TOKEN = os.environ.get("7561248614:AAHz-PCTNcgj5oyFei0PgNnmlwvSu4NSqfw")
PORT = int(os.environ.get("PORT", 8000))

# --- Lista de Regiões Atendidas ---
# Extraída da sua FAQ para fácil acesso e verificação.
# Manter em minúsculas e sem acentos para facilitar a comparação.
REGIOES_ATENDIDAS = [
    "agua quente", "aguas claras", "arniqueira", "brazlandia", "ceilandia",
    "gama", "guara", "nucleo bandeirante", "park way", "recanto das emas",
    "riacho fundo", "riacho fundo ii", "samambaia", "santa maria",
    "scia/estrutural", "sia", "sol nascente / por do sol", "taguatinga",
    "valparaiso de goias", "vicente pires"
]

# --- Lógica do Bot (Handlers) ---

# Handler de mensagens (versão corrigida e mais robusta)
async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text.lower()
    
    # --- LÓGICA NOVA E PRIORITÁRIA: Verificar se é uma pergunta sobre região específica ---
    # Normaliza o texto do usuário (remove acentos comuns) para comparação
    texto_normalizado = texto_usuario.replace('á', 'a').replace('â', 'a').replace('ã', 'a').replace('é', 'e').replace('ê', 'e').replace('í', 'i').replace('ó', 'o').replace('ô', 'o').replace('ú', 'u').replace('ç', 'c')

    # Verifica se a pergunta contém palavras como "atende", "entrega", "região"
    contem_palavra_de_regiao = any(palavra in texto_normalizado for palavra in ["atende", "entrega", "regiao", "bairro", "cidade"])

    regiao_encontrada = None
    for regiao in REGIOES_ATENDIDAS:
        if regiao in texto_normalizado:
            regiao_encontrada = regiao
            break # Para na primeira região que encontrar

    # Se a pergunta contém uma palavra de região E o nome de uma região, responde diretamente
    if contem_palavra_de_regiao and regiao_encontrada:
        await update.message.reply_text(
            f"Sim, atendemos em {regiao_encontrada.title()}! ✅\n"
            "Pode fazer seu pedido pelo site que entregamos aí."
        )
        return # Encerra a função aqui

    # --- LÓGICA DE PONTUAÇÃO (se não for uma pergunta sobre região) ---
    scored_faqs = []
    palavras_do_usuario = set(texto_usuario.split()) 

    for item in faq_data:
        palavras_chave_item = set(item["palavras_chave"])
        intersecao = palavras_do_usuario.intersection(palavras_chave_item)
        score = len(intersecao)
        if score > 0:
            scored_faqs.append({"faq": item, "score": score})

    scored_faqs.sort(key=lambda x: x["score"], reverse=True)

    if not scored_faqs:
        await update.message.reply_text(
            "Desculpe, não entendi. 🤔\n"
            "Você pode perguntar sobre horário, formas de pagamento, ou se atendemos em uma região específica."
        )
        return

    max_score = scored_faqs[0]["score"]
    top_matched_faqs = [s["faq"] for s in scored_faqs if s["score"] == max_score]

    if len(top_matched_faqs) == 1:
        await update.message.reply_text(top_matched_faqs[0]["resposta"])
    else:
        keyboard = []
        for faq in top_matched_faqs:
            keyboard.append([InlineKeyboardButton(faq["pergunta"], callback_data=f"faq_id_{faq['id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Encontrei algumas informações que podem ser úteis. Qual delas você procura?",
            reply_markup=reply_markup
        )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    
    if callback_data.startswith("faq_id_"):
        faq_id_selecionado = int(callback_data[len("faq_id_"):])
        for item in faq_data:
            if item["id"] == faq_id_selecionado:
                await query.message.reply_text(text=item["resposta"])
                # Opcional: remove os botões da mensagem original após a escolha
                await query.edit_message_reply_markup(reply_markup=None)
                return
        await query.message.reply_text(text="Desculpe, não consegui encontrar a resposta para essa opção.")

# --- Configuração da Aplicação Telegram e Servidor Web (Flask) ---
# Inicializa a aplicação PTB
ptb = Application.builder().token(TOKEN).build()

# Adiciona os handlers
ptb.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))
ptb.add_handler(CallbackQueryHandler(button_callback_handler))

# Inicializa o servidor Flask
flask_app = Flask(__name__)

@flask_app.route("/api/telegram/webhook", methods=["POST"])
async def telegram_webhook():
    """Lida com as atualizações do Telegram."""
    await ptb.update_queue.put(Update.de_json(request.get_json(force=True), ptb.bot))
    return Response(status=HTTPStatus.OK)

@flask_app.route("/health", methods=["GET"])
def health_check():
    """Rota para o UptimeRobot manter o bot acordado."""
    return "Bot is healthy and running!", HTTPStatus.OK

async def main():
    """Função principal para configurar o webhook."""
    # O Render define o nome do host automaticamente. Se não estiver no Render, use a URL completa.
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME' )}/api/telegram/webhook"
    await ptb.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    # Configura o webhook e inicia o loop de eventos do PTB
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(main())
    else:
        loop.run_until_complete(main())
    
    # O Gunicorn vai rodar o 'flask_app', então não precisamos de 'flask_app.run()' aqui
    # O código acima garante que o webhook seja configurado antes do Gunicorn iniciar.
